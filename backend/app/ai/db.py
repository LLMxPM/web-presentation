"""文件功能：根据现有应用配置构建 Agno 所需的会话与审批数据库。"""

from __future__ import annotations

from pathlib import Path

from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def build_agno_db() -> PostgresDb | SqliteDb:
    """按主应用数据库配置派生 Agno 会话库，兼容 PostgreSQL 与 SQLite。"""

    settings = get_settings()
    raw_database_url = (settings.ai_db_url or settings.database_url).strip()

    if raw_database_url.startswith("sqlite"):
        return _build_sqlite_db(raw_database_url)
    return _build_postgres_db(raw_database_url)


def _build_sqlite_db(database_url: str) -> SqliteDb:
    """把主库 SQLite 配置转换为 Agno 独立文件库，避免与业务事务抢占连接。"""

    url = make_url(database_url)
    database_path = Path(url.database or "agno.db")
    agno_database_path = database_path.with_suffix(".agno.db")
    agno_database_path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    return SqliteDb(
        db_file=str(agno_database_path),
        session_table=settings.ai_session_table,
        approvals_table=settings.ai_approvals_table,
    )


def _build_postgres_db(database_url: str) -> PostgresDb:
    """把 asyncpg/标准 PostgreSQL URL 统一转换为 psycopg 驱动，供 Agno 同步使用。"""

    settings = get_settings()
    resolved_url = database_url
    if resolved_url.startswith("postgresql+asyncpg://"):
        resolved_url = resolved_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif resolved_url.startswith("postgresql://"):
        resolved_url = resolved_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif resolved_url.startswith("postgres://"):
        resolved_url = resolved_url.replace("postgres://", "postgresql+psycopg://", 1)

    return PostgresDb(
        db_url=resolved_url,
        db_schema=settings.ai_db_schema,
        session_table=settings.ai_session_table,
        approvals_table=settings.ai_approvals_table,
    )

