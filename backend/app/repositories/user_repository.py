"""文件功能：封装平台用户与会话的数据访问逻辑。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecordStatus, UserRole
from app.models.user import UserSession, User
from app.schemas.preview_size_preset import build_default_preview_size_presets


class UserRepository:
    """用户仓储，负责用户和会话的增删查改。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_users(self) -> int:
        """统计平台用户数量，用于初始化默认账号。"""

        result = await self.session.scalar(select(func.count(User.id)))
        return int(result or 0)

    async def get_by_username(self, username: str) -> User | None:
        """按用户名查询用户。"""

        return await self.session.scalar(select(User).where(User.username == username))

    async def get_by_id(self, user_id: int) -> User | None:
        """按主键查询用户。"""

        return await self.session.scalar(select(User).where(User.id == user_id))

    async def count_platform_admins(self, *, exclude_user_id: int | None = None) -> int:
        """统计启用中的平台管理员数量，用于保护最后一个管理员。"""

        statement = (
            select(func.count(User.id))
            .where(User.role == UserRole.PLATFORM_ADMIN.value)
            .where(User.status == RecordStatus.ACTIVE.value)
        )
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        result = await self.session.scalar(statement)
        return int(result or 0)

    async def list_users(self) -> list[User]:
        """按更新时间倒序列出全部用户。"""

        result = await self.session.scalars(select(User).order_by(User.updated_at.desc(), User.id.desc()))
        return list(result)

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str,
        role: str = UserRole.WORKSPACE_USER.value,
        status: str = RecordStatus.ACTIVE.value,
    ) -> User:
        """创建平台用户。"""

        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            status=status,
            preview_size_presets=build_default_preview_size_presets(),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_last_login(self, user: User, login_at: datetime) -> None:
        """更新最近登录时间。"""

        user.last_login_at = login_at
        await self.session.flush()

    async def create_session(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        last_active_at: datetime,
    ) -> UserSession:
        """写入登录会话。"""

        session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            last_active_at=last_active_at,
            is_active=True,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_active_session(self, token_hash: str) -> UserSession | None:
        """按 token 摘要查询仍然有效的会话。"""

        return await self.session.scalar(
            select(UserSession)
            .where(UserSession.token_hash == token_hash)
            .where(UserSession.is_active.is_(True))
        )

    async def touch_session(self, session_model: UserSession, touched_at: datetime, expires_at: datetime) -> None:
        """刷新会话活跃时间和过期时间。"""

        session_model.last_active_at = touched_at
        session_model.expires_at = expires_at
        await self.session.flush()

    async def deactivate_session(self, token_hash: str) -> None:
        """将指定会话置为失效状态。"""

        session_model = await self.get_active_session(token_hash)
        if session_model is not None:
            session_model.is_active = False
            await self.session.flush()

    async def deactivate_user_sessions(self, user_id: int) -> None:
        """将指定用户的全部会话置为失效。"""

        sessions = await self.session.scalars(
            select(UserSession).where(UserSession.user_id == user_id).where(UserSession.is_active.is_(True))
        )
        for session_model in sessions:
            session_model.is_active = False
        await self.session.flush()
