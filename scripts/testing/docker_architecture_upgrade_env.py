"""文件功能：为 M05 配置独立 PG/SQLite 数据、真实 platform/Lite 入口及对应 Runtime。"""

from __future__ import annotations

import json
from copy import deepcopy

from docker_architecture_env import DockerDrill, command, free_port


def config_path(drill: DockerDrill):
    """返回本演练唯一 Compose 文件，所有阶段只修改该专属配置。"""
    return drill.directory / "compose.json"


def write_config(drill: DockerDrill, config: dict) -> None:
    """保存配置与带凭证上下文；这些文件仅留在 .tmp，禁止入库。"""
    config_path(drill).write_text(json.dumps(config, indent=2), encoding="utf-8")
    (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")


def prepare(drill: DockerDrill) -> None:
    """增加专属业务库和卷，不触碰 architecture_e2e 或其它 Docker 项目。"""
    config = json.loads(config_path(drill).read_text(encoding="utf-8"))
    if "m05_lite" in config["services"]:
        return
    command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "postgres",
            "-c", "CREATE DATABASE m05_pg OWNER drill")
    images = {role: command("docker", "image", "inspect", f"wp-{role}-m05-4c7eee8:local", "--format", "{{.Id}}")
              for role in ("lite", "platform", "runtime")}
    images["platform_n"] = command("docker", "image", "inspect", "wp-platform-m05-n:local", "--format", "{{.Id}}")
    drill.context["m05_images"] = images
    base = deepcopy(config["services"]["backend_a"]["environment"])
    base.update(BACKEND_MULTI_INSTANCE="false", RUNTIME_RSA_ALLOW_AUTO_GENERATE="true",
                RUNTIME_RSA_PRIVATE_KEY_FILE="/app/backend/data/drill-key.pem")
    for role in ("platform", "lite"):
        name = "m05_" + role
        port = free_port()
        drill.context["origins"][name] = f"http://127.0.0.1:{port}"
        env = {**base, "DATABASE_URL": "postgresql+asyncpg://drill:drill-only@postgres:5432/m05_pg" if role == "platform"
               else "sqlite+aiosqlite:////app/backend/data/m05.db", "REDIS_KEY_PREFIX": name,
               "BACKEND_PUBLIC_BASE_URL": f"http://{name}",
               "RUNTIME_PUBLIC_BASE_URL": f"http://{name}/runtime",
               "RUNTIME_BASE_URL": "http://m05_runtime:7373" if role == "platform" else "http://127.0.0.1:7373",
               "RUNTIME_PREVIEW_BASE_URL": "http://m05_runtime:7373" if role == "platform" else "http://127.0.0.1:7373",
               "RUNTIME_CHECK_BASE_URL": "http://m05_runtime:7373" if role == "platform" else "http://m05_check_lite:7373",
               "RENDER_RUNTIME_NAVIGATION_BASE_URL": f"http://{name}/runtime",
               "RENDER_RUNTIME_ASSET_BASE_URL": f"http://{name}/runtime",
               "RENDER_PLATFORM_ASSET_BASE_URL": f"http://{name}", "PAGE_SCREENSHOT_BACKEND_BASE_URL": f"http://{name}"}
        if role == "lite":
            env.update(RUNTIME_BACKEND_API_BASE_URL="http://127.0.0.1:8000",
                       RUNTIME_PREVIEW_JWKS_URL="http://127.0.0.1:8000/.well-known/jwks.json",
                       RUNTIME_SERVER_ALLOWED_HOSTS="m05_lite,runtime,localhost,127.0.0.1")
        config["volumes"][name + "_data"] = {}
        config["services"][name] = {"image": images[role], "environment": env,
                                    "volumes": [name + "_data:/app/backend/data"],
                                    "ports": [f"127.0.0.1:{port}:80"], "extra_hosts": ["backend:127.0.0.1"]}
        if role == "platform":
            config["services"][name]["links"] = ["m05_runtime:runtime"]
        config["services"][name + "_migrate"] = {"image": drill.context["images"]["backend"], "environment": env,
                                                   "working_dir": "/app/backend", "entrypoint": ["alembic"],
                                                   "volumes": [name + "_data:/app/backend/data"]}
    runtime = deepcopy(config["services"]["preview_a"])
    runtime["image"] = images["runtime"]
    runtime["environment"].update(RUNTIME_ROLE="all", RUNTIME_BACKEND_API_BASE_URL="http://m05_platform:8000",
                                  RUNTIME_PUBLIC_BASE_URL="http://m05_platform/runtime", BACKEND_PUBLIC_BASE_URL="http://m05_platform",
                                  RUNTIME_PREVIEW_JWKS_URL="http://m05_platform:8000/.well-known/jwks.json",
                                  RUNTIME_BUILD_WORKER_CREDENTIAL=base["RUNTIME_BUILD_WORKER_CREDENTIAL"],
                                  RUNTIME_BUILD_WORKER_ID="m05-platform-build", RUNTIME_INSTANCE_ID="m05-runtime",
                                  RUNTIME_SERVER_ALLOWED_HOSTS="m05_platform,m05_runtime,runtime,localhost,127.0.0.1")
    config["services"]["m05_runtime"] = runtime
    check = deepcopy(runtime)
    check["environment"].update(RUNTIME_ROLE="check", RUNTIME_BACKEND_API_BASE_URL="http://m05_lite:8000",
                                RUNTIME_PREVIEW_JWKS_URL="http://m05_lite:8000/.well-known/jwks.json",
                                RUNTIME_SERVER_ALLOWED_HOSTS="m05_check_lite,runtime,localhost,127.0.0.1")
    config["services"]["m05_check_lite"] = check
    write_config(drill, config)
    drill.save("m05-images.json", {"source_n1": "4c7eee8", "images": images,
                                   "backend_n": drill.context["images"]["backend"], "runtime_n": drill.context["images"]["runtime"]})


def switch_entry(drill: DockerDrill, role: str, *, current: bool, migrate: bool) -> None:
    """停止业务入口后切换固定镜像；应用回滚保留 schema 并明确关闭旧入口迁移器。"""
    name = "m05_" + role
    drill.compose("stop", name)
    config = json.loads(config_path(drill).read_text(encoding="utf-8"))
    image = drill.context["images"]["backend"] if role == "lite" else drill.context["m05_images"]["platform_n"]
    config["services"][name]["image"] = image if current else drill.context["m05_images"][role]
    key = "PLATFORM_LITE_RUN_MIGRATIONS" if role == "lite" else "PLATFORM_SIMPLE_RUN_MIGRATIONS"
    config["services"][name]["environment"][key] = str(migrate).lower()
    write_config(drill, config)
    drill.compose("up", "-d", "--no-deps", "--force-recreate", name)


def query(drill: DockerDrill, role: str, statement: str):
    """读取脱敏业务字段；SQLite 通过专属迁移服务打开，只允许 SELECT。"""
    if not statement.upper().lstrip().startswith("SELECT"):
        raise ValueError("业务观察仅允许 SELECT")
    if role == "platform":
        raw = command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "m05_pg", "-tAc", statement)
        return json.loads(raw) if raw else None
    code = "import sqlite3,json; c=sqlite3.connect('file:/app/backend/data/m05.db?mode=ro',uri=True); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute(" + repr(statement) + ")]))"
    return json.loads(drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", "m05_lite_migrate", "-c", code).splitlines()[-1])


def rows(drill: DockerDrill, role: str, fields: str, table: str, condition: str = "TRUE") -> list:
    """两种方言保持相同观察字段；方言差异限于演练采集适配器。"""
    statement = f"SELECT {fields} FROM {table} WHERE {condition}"
    if role == "platform":
        statement = f"SELECT coalesce(json_agg(t),'[]'::json) FROM ({statement}) t"
    return query(drill, role, statement)
