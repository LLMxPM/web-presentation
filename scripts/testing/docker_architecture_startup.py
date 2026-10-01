"""文件功能：以真实 N 镜像 CMD 验证旧 schema 启动拒绝，负例只使用演练专属数据库/文件。"""

from __future__ import annotations

import json
import time
from copy import deepcopy

from docker_architecture_env import DockerDrill, command
from docker_architecture_upgrade import wait_exit
from docker_architecture_upgrade_env import config_path, write_config


def startup_negatives(drill: DockerDrill) -> None:
    """N 的迁移器只构造旧 schema；随后关闭自动迁移，以实际 platform/Lite CMD 证明组合 D 不支持。"""
    config = json.loads(config_path(drill).read_text(encoding="utf-8"))
    report = {"status": "running", "cases": []}
    suffix = str(time.time_ns())
    for role in ("platform", "lite"):
        name = "m05_negative_" + role
        database_name = "m05_negative_" + suffix
        database_url = "postgresql+asyncpg://drill:drill-only@postgres:5432/" + database_name if role == "platform" else "sqlite+aiosqlite:////app/backend/data/" + database_name + ".db"
        if role == "platform":
            command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "postgres",
                    "-c", f"CREATE DATABASE {database_name} OWNER drill")
        migration = deepcopy(config["services"]["m05_" + role + "_migrate"])
        migration["environment"]["DATABASE_URL"] = database_url
        config["services"][name + "_migrate"] = migration
        entry = deepcopy(config["services"]["m05_" + role])
        entry["image"] = drill.context["images"]["backend"] if role == "lite" else drill.context["m05_images"]["platform_n"]
        entry["environment"]["DATABASE_URL"] = database_url
        entry["environment"]["PLATFORM_LITE_RUN_MIGRATIONS" if role == "lite" else "PLATFORM_SIMPLE_RUN_MIGRATIONS"] = "false"
        entry.pop("ports", None)
        config["services"][name] = entry
        write_config(drill, config)
        drill.compose("run", "--rm", "--no-deps", name + "_migrate", "upgrade", "20260926_0100")
        try:
            drill.compose("up", "-d", "--no-deps", "--force-recreate", name)
            rejected = wait_exit(drill, name, "process_owner")
            report["cases"].append({"dialect": role, "revision": "20260926_0100", "auto_migrate": False, **rejected})
        finally:
            drill.compose("rm", "-s", "-f", name)
        drill.save("m05-startup-negatives.json", report)
    report["status"] = "passed"
    drill.save("m05-startup-negatives.json", report)
