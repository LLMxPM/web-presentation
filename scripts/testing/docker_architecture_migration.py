"""文件功能：提取固定 N-1 源码，在专属 PostgreSQL 库执行前滚和旧业务兼容探针。"""

import io
import json
import subprocess
import tarfile

from docker_architecture_env import ROOT, DockerDrill, command


def legacy(drill: DockerDrill) -> None:
    """只从 Git 对象读取旧代码，不改变当前 checkout；数据库与数据目录均为测试专属。"""
    destination = drill.directory / "legacy"
    destination.mkdir(exist_ok=True)
    archive = subprocess.run(["git", "archive", "4c7eee8", "backend"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(destination, filter="data")
    pg = drill.container("postgres")
    # 只重置本专属 PG 的兼容夹具库，使重复执行仍真正从 N-1 schema 前滚。
    # architecture_e2e 和主机开发数据库不参与此操作。
    command("docker", "exec", pg, "psql", "-U", "drill", "-d", "postgres", "-c", "DROP DATABASE IF EXISTS compat_e2e WITH (FORCE)")
    command("docker", "exec", pg, "psql", "-U", "drill", "-d", "postgres", "-c", "CREATE DATABASE compat_e2e OWNER drill")
    database = "postgresql+asyncpg://drill:drill-only@postgres:5432/compat_e2e"
    for revision in ("20260926_0100", "head"):
        log = drill.compose("run", "--rm", "-e", "DATABASE_URL=" + database, "--entrypoint", "alembic", "backend_a", "upgrade", revision)
        (drill.output / f"migration-{revision}.log").write_text(log, encoding="utf-8")
        current_revision = command("docker", "exec", pg, "psql", "-U", "drill", "-d", "compat_e2e", "-tAc", "SELECT version_num FROM alembic_version")
        if revision != "head":
            assert current_revision == revision, "未真正迁移到选定 N-1 revision"
    script = ROOT / "scripts/testing/docker_architecture_legacy_fixture.py"
    mounts = ["-v", f"{(destination / 'backend/app').as_posix()}:/app/backend/app:ro", "-v", f"{script.as_posix()}:/app/backend/docker_architecture_legacy_fixture.py:ro"]
    value = drill.compose("run", "--rm", "-e", "DATABASE_URL=" + database, *mounts, "--entrypoint", "python", "backend_a", "-m", "docker_architecture_legacy_fixture")
    report = json.loads(value.splitlines()[-1])
    report["n1_revision"] = "20260926_0100"
    report["target_revision"] = current_revision
    drill.save("legacy-postgres.json", report)
    # 实际旧 Alembic 无法识别新 revision，这个非零退出是约定的明确拒绝。
    result = subprocess.run(["docker", "compose", "-p", drill.project, "-f", str(drill.directory / "compose.json"),
                             "run", "--rm", "-e", "DATABASE_URL=" + database, "-v", f"{(destination / 'backend/migrations').as_posix()}:/app/backend/migrations:ro",
                             "--entrypoint", "alembic", "backend_a", "current"], capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    diagnostic = result.stdout + result.stderr
    assert result.returncode != 0 and "Can't locate revision" in diagnostic, "旧迁移器没有明确拒绝未知 revision"
    drill.save("legacy-migrator.json", {"status": "passed", "exit_code": result.returncode, "rejected_revision": current_revision, "reason": "旧迁移器不能识别新 revision；应用回滚须关闭自动迁移"})
