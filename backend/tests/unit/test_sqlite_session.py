"""文件功能：验证 SQLite 数据库连接参数和轻量部署所需 PRAGMA 初始化。"""

from pathlib import Path

from sqlalchemy import text


async def test_sqlite_engine_should_enable_foreign_keys_busy_timeout_and_wal(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """SQLite 文件库连接应启用外键、锁等待和 WAL，降低轻量部署写入冲突风险。"""

    database_path = tmp_path / "lite.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "7")

    from app.core.config import get_settings
    from app.db.session import get_engine, reset_database_state

    get_settings.cache_clear()
    await reset_database_state()
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
            busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar_one()
            journal_mode = str((await connection.execute(text("PRAGMA journal_mode"))).scalar_one()).lower()

        assert foreign_keys == 1
        assert busy_timeout == 7000
        assert journal_mode == "wal"
    finally:
        await reset_database_state()
        get_settings.cache_clear()
