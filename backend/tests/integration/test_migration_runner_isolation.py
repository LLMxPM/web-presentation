"""文件功能：验证进程内迁移不会向后续测试泄漏数据库配置或修改日志 handler。"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from alembic.util.exc import CommandError

from tests.fixtures.migrations import run_alembic


@pytest.mark.parametrize("revision", ["base", "missing-revision"])
def test_migration_runner_restores_environment_after_success_or_failure(tmp_path: Path, revision: str) -> None:
    """真实 env.py 成功与失败后均恢复父环境、Settings 和 pytest 日志 handler。"""
    from app.core.config import get_settings

    previous_env = dict(os.environ)
    get_settings.cache_clear()
    previous_url = get_settings().database_url
    handlers = list(logging.getLogger().handlers)
    database = tmp_path / "isolated.db"
    env = {**previous_env, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}", "REDIS_URL": "memory://migration-isolation"}
    if revision == "missing-revision":
        with pytest.raises(CommandError, match="missing-revision"):
            run_alembic(Path(__file__).resolve().parents[2], env, revision)
    else:
        run_alembic(Path(__file__).resolve().parents[2], env, revision)
    assert dict(os.environ) == previous_env
    assert get_settings().database_url == previous_url
    assert logging.getLogger().handlers == handlers
    get_settings.cache_clear()
