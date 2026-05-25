"""文件功能：创建异步数据库引擎与会话工厂，并对外提供依赖注入接口。"""

from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """按需初始化数据库引擎，避免导入时就触发连接。"""

    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            future=True,
            connect_args=_build_connect_args(
                settings.database_url,
                settings.database_connect_timeout_seconds,
            ),
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取异步会话工厂，供依赖注入和服务层复用。"""

    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def reset_database_state() -> None:
    """重置数据库引擎与会话工厂，供测试在切换数据库 URL 时复用。"""

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """为 FastAPI 路由提供数据库会话，并在请求结束后自动关闭。"""

    async with get_session_factory()() as session:
        yield session


def _build_connect_args(database_url: str, timeout_seconds: float) -> dict[str, object]:
    """按数据库驱动生成连接参数；当前只对 PostgreSQL 驱动设置连接超时。"""

    try:
        driver_name = make_url(database_url).drivername
    except Exception:  # noqa: BLE001
        return {}

    if driver_name == "postgresql+asyncpg":
        return {"timeout": timeout_seconds}
    if driver_name.startswith("postgresql+psycopg"):
        return {"connect_timeout": max(1, int(timeout_seconds))}
    return {}
