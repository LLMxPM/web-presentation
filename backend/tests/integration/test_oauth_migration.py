"""文件功能：验证 OAuth 存储迁移与 ORM 对拍、降级边界及既有用户数据保留。"""

import os
import subprocess
import sys
from pathlib import Path

import app.models  # noqa: F401
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from sqlalchemy import create_engine, inspect, select


def test_oauth_migration_roundtrip_preserves_business_data(tmp_path: Path) -> None:
    """只创建/移除 OAuth 表；迁移后类型、索引和外键与模型一致，旧用户保留。"""
    backend_root = Path(__file__).resolve().parents[2]
    database = tmp_path / "oauth-migration.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}",
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

    migrate("upgrade", "20261002_0100")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                User.__table__.insert().values(
                    username="preserved-user",
                    display_name="保留用户",
                    password_hash="unused",
                    preview_size_presets=[],
                )
            )
        migrate("upgrade", "20261004_0100")
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
        migrate("downgrade", "20261002_0100")
        assert not oauth_names & set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(select(User.username)) == "preserved-user"
        migrate("upgrade", "20261004_0100")
        assert oauth_names <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
