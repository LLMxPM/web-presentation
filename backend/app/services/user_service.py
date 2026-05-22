"""文件功能：封装平台用户管理、角色状态维护与最后管理员保护逻辑。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import hash_password
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreateRequest, UserItem, UserResetPasswordRequest, UserUpdateRequest


class UserService:
    """平台用户管理服务，仅供平台管理员调用。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)

    async def list_users(self) -> list[UserItem]:
        """列出全部平台用户。"""

        return [self._to_item(user) for user in await self.repository.list_users()]

    async def create_user(self, payload: UserCreateRequest) -> UserItem:
        """创建平台用户，用户名全局唯一。"""

        username = payload.username.strip()
        if await self.repository.get_by_username(username) is not None:
            raise AppException(status_code=409, code="USER_USERNAME_CONFLICT", detail="用户名已存在。")

        user = await self.repository.create_user(
            username=username,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name.strip(),
            role=payload.role.value,
            status=payload.status.value,
        )
        await self.session.commit()
        await self.session.refresh(user)
        return self._to_item(user)

    async def update_user(self, user_id: int, payload: UserUpdateRequest, *, operator_id: int) -> UserItem:
        """更新用户资料、角色或状态，并保护最后一个启用管理员。"""

        user = await self._get_user_or_raise(user_id)
        await self._ensure_not_last_platform_admin_if_needed(user, next_role=payload.role, next_status=payload.status)

        if payload.display_name is not None:
            user.display_name = payload.display_name.strip()
        if payload.role is not None:
            user.role = payload.role.value
        if payload.status is not None:
            user.status = payload.status.value
            if payload.status != RecordStatus.ACTIVE:
                await self.repository.deactivate_user_sessions(user.id)

        await self.session.commit()
        await self.session.refresh(user)
        return self._to_item(user)

    async def reset_password(self, user_id: int, payload: UserResetPasswordRequest, *, operator_id: int) -> UserItem:
        """重置指定用户密码，并让其现有会话失效。"""

        user = await self._get_user_or_raise(user_id)
        user.password_hash = hash_password(payload.new_password)
        await self.repository.deactivate_user_sessions(user.id)
        await self.session.commit()
        await self.session.refresh(user)
        return self._to_item(user)

    async def _get_user_or_raise(self, user_id: int) -> User:
        """按主键读取用户，不存在时返回标准错误。"""

        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AppException(status_code=404, code="USER_NOT_FOUND", detail="用户不存在。")
        return user

    async def _ensure_not_last_platform_admin_if_needed(
        self,
        user: User,
        *,
        next_role: UserRole | None,
        next_status: RecordStatus | None,
    ) -> None:
        """禁止禁用或降级最后一个启用平台管理员。"""

        is_current_admin = user.role == UserRole.PLATFORM_ADMIN.value and user.status == RecordStatus.ACTIVE.value
        role_removes_admin = next_role is not None and next_role != UserRole.PLATFORM_ADMIN
        status_disables = next_status is not None and next_status != RecordStatus.ACTIVE
        if not is_current_admin or not (role_removes_admin or status_disables):
            return

        remaining_admins = await self.repository.count_platform_admins(exclude_user_id=user.id)
        if remaining_admins <= 0:
            raise AppException(
                status_code=409,
                code="USER_LAST_ADMIN_PROTECTED",
                detail="不能禁用或降级最后一个启用的平台管理员。",
            )

    @staticmethod
    def _to_item(user: User) -> UserItem:
        """转换 ORM 用户为接口响应。"""

        return UserItem.model_validate(user)
