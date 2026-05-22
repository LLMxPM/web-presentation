"""文件功能：创建异步数据库引擎与会话工厂，并对外提供依赖注入接口。"""

from collections.abc import AsyncGenerator

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
        _engine = create_async_engine(settings.database_url, future=True)
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
