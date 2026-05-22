"""文件功能：在应用启动时初始化默认平台管理员账号。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


class BootstrapService:
    """负责启动阶段的默认平台管理员初始化。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def ensure_default_admin(self) -> None:
        """如果系统中还没有用户，则按配置创建默认平台管理员账号。"""

        settings = get_settings()
        async with self.session_factory() as session:
            repository = UserRepository(session)
            if await repository.count_users() == 0:
                await repository.create_user(
                    username=settings.default_admin_username,
                    password_hash=hash_password(settings.default_admin_password),
                    display_name=settings.default_admin_display_name,
                    role=UserRole.PLATFORM_ADMIN.value,
                )
                await session.commit()
