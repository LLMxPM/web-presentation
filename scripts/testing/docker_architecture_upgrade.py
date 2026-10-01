"""文件功能：执行 M05 的完整旧镜像入口、迁移中断、前向补偿及保留 schema 的应用回滚。"""

from __future__ import annotations

import json
import subprocess
import time

from docker_architecture_env import ROOT, DockerDrill, command
from docker_architecture_upgrade_business import create_data, mutation, read_write
from docker_architecture_upgrade_env import (
    config_path,
    prepare,
    rows,
    switch_entry,
    write_config,
)


def wait_backend(drill: DockerDrill, role: str) -> None:
    """先从容器回环确认 Backend 就绪，避免启动期请求把真实 Nginx upstream 暂时摘流。"""
    container = drill.container("m05_" + role)
    code = "import json,urllib.request; x=json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=2)); assert '/api/pages' in x['paths']"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = subprocess.run(["docker", "exec", container, "python", "-c", code], capture_output=True, check=False)
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise TimeoutError("真实入口中的 Backend 未就绪")


def wait_exit(drill: DockerDrill, service: str, signature: str, seconds: int = 60) -> dict:
    """以真实入口退出和错误特征判拒绝；仅保存错误码/退出状态，不提交原始应用日志。"""
    deadline = time.monotonic() + seconds
    container = drill.container(service)
    while time.monotonic() < deadline:
        value = json.loads(command("docker", "inspect", container, "--format", "{{json .State}}"))
        if not value["Running"]:
            # Docker 的应用日志常在 stderr；合并只用于判据，不输出全文。
            log = subprocess.run(["docker", "logs", container], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            diagnostic = log.stdout + log.stderr
            assert value["ExitCode"] != 0 and signature in diagnostic, "实际入口未按约定拒绝"
            return {"exit_code": value["ExitCode"], "error_signature": signature, "status": "rejected"}
        time.sleep(0.3)
    raise TimeoutError("入口没有在观察预算内退出")


def baseline(drill: DockerDrill) -> None:
    """先以完整 N-1 镜像的原始 CMD 自动迁移和启动，分别验证 SQLite 与真实 PG。"""
    prepare(drill)
    code = "from pathlib import Path; from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption; p=Path('/app/backend/data/drill-key.pem'); p.parent.mkdir(exist_ok=True); p.exists() or p.write_bytes(rsa.generate_private_key(public_exponent=65537,key_size=2048).private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption())); p.chmod(0o600)"
    for role in ("platform", "lite"):
        drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", "m05_" + role + "_migrate", "-c", code)
    drill.compose("restart", "mock")
    drill.compose("up", "-d", "m05_runtime", "m05_check_lite")
    for role in ("platform", "lite"):
        name = "m05_" + role
        drill.compose("up", "-d", "--no-deps", name)
        wait_backend(drill, role)
        data_path = drill.output / ("m05-" + role + "-data.json")
        data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else create_data(drill, role)
        read_write(drill, role, data, "old-baseline")
        mutation(drill, role, data, "old-resume")
        mutation(drill, role, data, "old-cancel", cancel=True)
        revision = rows(drill, role, "version_num", "alembic_version")
        assert revision == [{"version_num": "20260926_0100"}], revision
        drill.save("m05-" + role + "-baseline.json", {"status": "passed", "revision": revision,
                   "image": drill.context["m05_images"][role], "entrypoint": "原始镜像 CMD，自动迁移开启"})


def migrate(drill: DockerDrill, role: str, revision: str) -> list:
    """始终由 N 独立迁移服务执行，历史 revision 保持原样；不 stamp、不 downgrade。"""
    drill.compose("run", "--rm", "--no-deps", "m05_" + role + "_migrate", "upgrade", revision)
    return rows(drill, role, "version_num", "alembic_version")


def orm_probe(drill: DockerDrill, role: str, *, missing: bool) -> dict:
    """完整旧映射 SELECT 在删列窗口必须失败，补偿后实际旧 Batch 查询恢复。"""
    code = """import asyncio,json
from sqlalchemy import select
from app.models.ai_page_mutation import AiPageMutationBatch
from app.db.session import get_session_factory
async def probe():
 async with get_session_factory()() as s:
  b=(await s.scalars(select(AiPageMutationBatch))).all()
  if b:
   item=b[-1]; before=item.lease_generation; batch_id=item.batch_id; item.lease_generation+=1
   await s.commit(); s.expire_all()
   item=await s.get(AiPageMutationBatch,batch_id)
   assert item.lease_generation==before+1
   print(json.dumps({'rows':len(b),'updated_batch':item.batch_id,'before':before,'after':item.lease_generation}))
  else:
   print(json.dumps({'rows':0}))
asyncio.run(probe())
"""
    args = ["docker", "compose", "-p", drill.project, "-f", str(drill.directory / "compose.json"), "run", "--rm", "--no-deps",
            "--entrypoint", "python", "m05_" + role, "-c", code]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    diagnostic = result.stdout + result.stderr
    if missing:
        assert result.returncode != 0 and "lease_generation" in diagnostic, "没有复现完整旧 ORM 缺列"
        return {"status": "rejected", "exit_code": result.returncode, "error_column": "lease_generation"}
    assert result.returncode == 0, "补偿后完整旧 ORM 仍失败"
    return {"status": "passed", **json.loads(result.stdout.splitlines()[-1])}


def interrupt_postgres(drill: DockerDrill) -> dict:
    """在真实删列 DDL 被锁阻塞时强杀迁移容器，证明 PG 整笔事务回退到旧 revision。"""
    pg = drill.container("postgres")
    lock = subprocess.Popen(["docker", "exec", "-e", "PGAPPNAME=m05-lock", pg, "psql", "-U", "drill", "-d", "m05_pg",
                             "-c", "BEGIN; LOCK TABLE ai_page_mutation_batches IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(120)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    migration = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            count = command("docker", "exec", pg, "psql", "-U", "drill", "-d", "m05_pg", "-tAc",
                            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid WHERE a.application_name='m05-lock' AND l.mode='AccessExclusiveLock' AND l.granted")
            if count == "1":
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("迁移 DDL 锁未建立")
        migration = drill.compose("run", "-d", "--no-deps", "m05_platform_migrate", "upgrade", "head").splitlines()[-1]
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            count = command("docker", "exec", pg, "psql", "-U", "drill", "-d", "m05_pg", "-tAc",
                            "SELECT count(*) FROM pg_stat_activity WHERE datname='m05_pg' AND wait_event_type='Lock' AND query LIKE 'ALTER TABLE ai_page_mutation_batches%'")
            if count == "1":
                break
            time.sleep(0.25)
        else:
            raise TimeoutError("真实迁移未进入预定 DDL 阻塞点")
        command("docker", "kill", migration)
        revision = rows(drill, "platform", "version_num", "alembic_version")
        assert revision == [{"version_num": "20260926_0100"}], revision
        return {"status": "passed", "fault": "SIGKILL 实际迁移容器，阻塞于真实 DROP COLUMN",
                "revision_after_kill": revision, "migration_exit_code": 137}
    finally:
        command("docker", "exec", pg, "psql", "-U", "drill", "-d", "m05_pg", "-tAc",
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='m05-lock'")
        lock.wait(timeout=10)
        if migration:
            command("docker", "rm", "-f", migration)


def interrupt_sqlite(drill: DockerDrill) -> dict:
    """强杀真实首个 DDL 后的 SQLite 迁移；失败保存 orphan 列证据并恢复本次专属快照。"""
    service = "m05_lite_migrate"
    backup = "import sqlite3; a=sqlite3.connect('/app/backend/data/m05.db'); b=sqlite3.connect('/app/backend/data/m05-before.db'); a.backup(b); b.close(); a.close()"
    drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", service, "-c", backup)
    marker_code = "from pathlib import Path; print(Path('/app/backend/data/m05-migration-gate').exists())"
    gate_path = ROOT / "scripts/testing/docker_architecture_migration_gate.py"
    container = drill.compose("run", "-d", "--no-deps", "-v", f"{gate_path.as_posix()}:/drill-gate.py:ro",
                              "--entrypoint", "python", service, "/drill-gate.py").splitlines()[-1]
    report = {"status": "failed", "fault": "SIGKILL 真实 ALTER ADD COLUMN 执行后、revision 写入前"}
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", service, "-c", marker_code).splitlines()[-1] == "True":
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("SQLite 迁移没有进入真实 DDL 挂起点")
        command("docker", "kill", container)
        revision = rows(drill, "lite", "version_num", "alembic_version")
        columns = rows(drill, "lite", "name", "pragma_table_info('ai_agent_runs')")
        report.update(revision_after_kill=revision, orphan_process_owner=any(item["name"] == "process_owner" for item in columns))
        assert revision == [{"version_num": "20260926_0100"}] and not report["orphan_process_owner"], "SQLite DDL 与 revision 没有一起回滚"
        report["status"] = "passed"
        return report
    finally:
        command("docker", "rm", "-f", container)
        restore = "import sqlite3; from pathlib import Path; a=sqlite3.connect('/app/backend/data/m05-before.db'); b=sqlite3.connect('/app/backend/data/m05.db'); a.backup(b); b.close(); a.close(); Path('/app/backend/data/m05-migration-gate').unlink(missing_ok=True)"
        drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", service, "-c", restore)
        drill.save("m05-sqlite-interrupt-" + str(time.time_ns()) + ".json", report)


def upgrade(drill: DockerDrill) -> None:
    """按停旧实例→中断观察→补偿→N 应用→禁旧迁移器回退应用顺序，保留历史数据。"""
    for role in ("platform", "lite"):
        assert rows(drill, role, "version_num", "alembic_version") == [{"version_num": "20260926_0100"}], "upgrade 需新演练旧 head 基线，禁止回退已升级数据"
    config = json.loads(config_path(drill).read_text(encoding="utf-8"))
    drill.context["m05_images"]["platform_n"] = command("docker", "image", "inspect", "wp-platform-m05-n:local", "--format", "{{.Id}}")
    for role in ("platform", "lite"):
        config["services"]["m05_" + role + "_migrate"]["image"] = drill.context["images"]["backend"]
    write_config(drill, config)
    for role in ("platform", "lite"):
        data = json.loads((drill.output / ("m05-" + role + "-data.json")).read_text(encoding="utf-8"))
        name = "m05_" + role
        drill.compose("stop", name)
        report = {"status": "running", "dialect": "postgresql" if role == "platform" else "sqlite", "steps": []}
        drill.save("m05-" + role + "-upgrade.json", report)
        if role == "platform":
            report["steps"].append(interrupt_postgres(drill))
        else:
            report["steps"].append(interrupt_sqlite(drill))
        report["steps"].append({"checkpoint": "20260930_0100", "revision": migrate(drill, role, "20260930_0100"),
                                "old_orm": orm_probe(drill, role, missing=True)})
        report["steps"].append({"checkpoint": "forward-compensation", "revision": migrate(drill, role, "head"),
                                "old_orm": orm_probe(drill, role, missing=False)})
        # 旧镜像真实 CMD 默认开启迁移时，必须对未知 revision 非零退出。
        switch_entry(drill, role, current=False, migrate=True)
        report["steps"].append({"checkpoint": "old-entry-migrator", **wait_exit(drill, name, "Can't locate revision")})
        switch_entry(drill, role, current=True, migrate=False)
        wait_backend(drill, role)
        read_write(drill, role, data, "new-upgrade")
        # 新 Backend 的 Runtime 版本要求单独在组合阶段验；页面队列此处用当前 Runtime。
        if role == "platform":
            path = drill.directory / "compose.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config["services"]["m05_runtime"]["image"] = drill.context["images"]["runtime"]
            path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            drill.compose("up", "-d", "--no-deps", "--force-recreate", "m05_runtime")
            drill.compose("restart", name)
            wait_backend(drill, role)
        mutation(drill, role, data, "new-resume")
        mutation(drill, role, data, "new-cancel", cancel=True)
        switch_entry(drill, role, current=False, migrate=False)
        wait_backend(drill, role)
        read_write(drill, role, data, "old-rollback")
        mutation(drill, role, data, "rollback-resume")
        mutation(drill, role, data, "rollback-cancel", cancel=True)
        report.update(status="passed", retained_revision=rows(drill, role, "version_num", "alembic_version"),
                      rollback="仅回退完整旧应用镜像；关闭旧入口自动迁移，保留前向补偿 schema 与历史业务数据")
        drill.save("m05-" + role + "-upgrade.json", report)
