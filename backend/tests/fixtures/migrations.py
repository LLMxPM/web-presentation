"""文件功能：复用进程内 Alembic 模块执行真实迁移，同时保留 CLI/进程崩溃验收入口。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config


def run_alembic(
    backend_root: Path,
    env: dict[str, str],
    revision: str = "head",
    *,
    command: str = "upgrade",
) -> None:
    """在临时环境中执行完整 env.py/DDL；每次新建引擎和事务，仅复用 Python 导入缓存。

    仅用于同步测试；不共享数据库连接、不 stamp、不跳过 revision。
    使用无日志配置的 Config，避免 env.py 重配 pytest 的全局 logging handlers。
    """
    from app.core.config import get_settings

    if command not in {"upgrade", "downgrade"}:
        raise ValueError(f"不支持的迁移命令：{command}")
    if not env.get("DATABASE_URL"):
        raise ValueError("迁移测试必须显式提供 DATABASE_URL")
    config = Config()
    config.set_main_option("script_location", str(backend_root / "migrations").replace("%", "%%"))
    try:
        with pytest.MonkeyPatch.context() as patch:
            for key, value in env.items():
                patch.setenv(key, value)
            get_settings.cache_clear()
            getattr(alembic_command, command)(config, revision)
    finally:
        # 失败同样清理，不能让后续 API 测试命中迁移库的 Settings。
        get_settings.cache_clear()


def run_alembic_cli(backend_root: Path, env: dict[str, str], revision: str = "head") -> None:
    """保留从空库到 head 的真实 CLI 验证；异常退出测试继续自行创建子进程。"""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
        cwd=backend_root, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
