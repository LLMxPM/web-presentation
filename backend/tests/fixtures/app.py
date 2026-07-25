"""文件功能：集中提供后台测试使用的数据库、客户端与 Runtime 服务令牌夹具。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def database_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """创建一次空的 SQLite schema 模板，供各测试复制以避免重复建表。"""

    from sqlalchemy import create_engine

    from app.db.base import Base
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User
    from app.schemas.preview_size_preset import build_default_preview_size_presets

    import app.models  # noqa: F401

    template_path = tmp_path_factory.getbasetemp() / "backend-schema-template.db"
    engine = create_engine(f"sqlite:///{template_path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                User.__table__.insert().values(
                    username="admin",
                    password_hash=hash_password("Admin123456"),
                    display_name="平台系统管理员",
                    role=UserRole.PLATFORM_ADMIN.value,
                    preview_size_presets=build_default_preview_size_presets(),
                )
            )
    finally:
        engine.dispose()
    return template_path


@pytest.fixture
async def client(tmp_path: Path, database_template: Path) -> AsyncClient:
    """复制独立 SQLite 数据库并创建带 Cookie 的测试客户端。"""

    database_path = tmp_path / "test.db"
    shutil.copyfile(database_template, database_path)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "Admin123456"
    os.environ["AI_TEST_MODE"] = "mock"
    os.environ["REDIS_URL"] = "memory://test"
    os.environ["REDIS_KEY_PREFIX"] = f"test_{database_path.stem}"

    from app.core.config import get_settings
    from app.db.session import reset_database_state
    from app.main import create_app
    from app.services.redis_runtime_client import reset_redis_runtime_client
    import app.models  # noqa: F401

    get_settings.cache_clear()
    reset_redis_runtime_client()
    await reset_database_state()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
        yield async_client

    await reset_database_state()
    get_settings.cache_clear()
    reset_redis_runtime_client()


@pytest.fixture
async def authenticated_client(client: AsyncClient) -> AsyncClient:
    """先登录默认管理员，再返回已带登录态的客户端。"""

    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin123456"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def runtime_service_headers() -> dict[str, str]:
    """生成 Runtime 访问 Backend 内部 artifact 接口所需的服务级请求头。"""

    from app.services.token_service import TokenService

    service_token = TokenService.generate_runtime_service_access_token(
        expires_in_seconds=300,
    )
    return {
        "Authorization": f"Bearer {service_token}",
    }
