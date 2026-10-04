"""文件功能：验证 OAuth 存储迁移与 ORM 对拍、降级边界及既有用户数据保留。"""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import app.models  # noqa: F401
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url


@pytest.mark.parametrize("database_kind", ["sqlite", "postgresql"])
def test_oauth_migration_roundtrip_preserves_business_data(tmp_path: Path, database_kind: str) -> None:
    """只创建/移除 OAuth 表；迁移后类型、索引和外键与模型一致，旧用户保留。"""
    backend_root = Path(__file__).resolve().parents[2]
    database = tmp_path / "oauth-migration.db"
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"
    sync_url = f"sqlite:///{database.as_posix()}"
    admin = None
    owned_database = 'wp_oauth_test_migration_' + uuid4().hex
    if database_kind == "postgresql":
        configured = os.getenv("OAUTH_TEST_POSTGRES_DATABASE_URL", "")
        if not configured:
            if os.getenv("OAUTH_TEST_POSTGRES_REQUIRED") == "1":
                pytest.fail("OAuth 迁移 PG 门禁必须配置专属测试数据库")
            pytest.skip("未配置专属 OAuth PostgreSQL 迁移库")
        url = make_url(configured)
        assert url.drivername == 'postgresql+asyncpg' and (url.database or '').startswith('wp_oauth_test_')
        admin = create_engine(url.set(drivername='postgresql+psycopg'), isolation_level='AUTOCOMMIT')
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{owned_database}"'))
        database_url = url.set(database=owned_database).render_as_string(hide_password=False)
        sync_url = url.set(database=owned_database, drivername='postgresql+psycopg')
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "REDIS_URL": "memory://oauth-migration",
    }

    def migrate(command: str, revision: str) -> None:
        """在一次性数据库执行真实 Alembic，不使用开发环境数据库。"""
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
            cwd=backend_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    engine = create_engine(sync_url)
    try:
        migrate("upgrade", "20261002_0100")
        with engine.begin() as connection:
            connection.execute(
                User.__table__.insert().values(
                    username="preserved-user",
                    display_name="保留用户",
                    password_hash="unused",
                    preview_size_presets=[],
                )
            )
        migrate("upgrade", "20261004_0101")
        oauth_names = {
            name for name in Base.metadata.tables if name.startswith("oauth_")
        }
        assert len(oauth_names) == 8
        assert oauth_names <= set(inspect(engine).get_table_names())
        with engine.begin() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_object": lambda obj, name, kind, reflected, compare_to: (
                        kind != "table" or name.startswith("oauth_")
                    ),
                },
            )
            assert compare_metadata(context, Base.metadata) == []
            connection.execute(
                OAuthClient.__table__.insert().values(
                    client_id="public-probe",
                    name="迁移探针",
                    redirect_uris=["https://client.test/cb"],
                    scopes=["page:read"],
                    resource="https://mcp.test/mcp",
                    auth_method="none",
                )
            )
            assert connection.scalar(select(OAuthClient.created_at)) is not None
        migrate("downgrade", "20261004_0100")
        assert "service_id" not in {
            column["name"]
            for column in inspect(engine).get_columns("oauth_audit_events")
        }
        with engine.connect() as connection:
            assert connection.scalar(select(OAuthClient.client_id)) == "public-probe"
        migrate("upgrade", "20261004_0101")
        migrate("downgrade", "20261002_0100")
        assert not oauth_names & set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(select(User.username)) == "preserved-user"
        migrate("upgrade", "20261004_0101")
        assert oauth_names <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        if admin is not None:
            # 只清理本例明确创建的 UUID 数据库，绝不删除配置中的测试库或用户数据。
            assert owned_database.startswith('wp_oauth_test_migration_')
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{owned_database}"'))
            admin.dispose()
