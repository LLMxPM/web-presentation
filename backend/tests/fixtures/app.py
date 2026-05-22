"""文件功能：集中提供后台测试使用的数据库、客户端与 Runtime 服务令牌夹具。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path: Path) -> AsyncClient:
    """为每个测试创建独立 SQLite 数据库和带 Cookie 的测试客户端。"""

    database_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    os.environ["DEFAULT_ADMIN_USERNAME"] = "admin"
    os.environ["DEFAULT_ADMIN_PASSWORD"] = "Admin123456"
    os.environ["AI_TEST_MODE"] = "mock"
    os.environ["REDIS_URL"] = "memory://test"
    os.environ["REDIS_KEY_PREFIX"] = f"test_{database_path.stem}"

    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.session import get_engine, get_session_factory, reset_database_state
    from app.main import create_app
    from app.services.bootstrap_service import BootstrapService
    from app.services.redis_runtime_client import reset_redis_runtime_client
    import app.models  # noqa: F401

    get_settings.cache_clear()
    reset_redis_runtime_client()
    await reset_database_state()
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await BootstrapService(get_session_factory()).ensure_default_admin()

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
