"""文件功能：封装平台用户登录、登出、鉴权和改密的业务逻辑。"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.security import generate_session_token, hash_password, hash_session_token, verify_password
from app.core.time_utils import normalize_utc, utc_now
from app.models.user import User
from app.models.enums import RecordStatus
from app.repositories.user_repository import UserRepository
from app.schemas.preview_size_preset import validate_preview_size_presets

_SESSION_TOUCH_INTERVAL = timedelta(seconds=60)
_SESSION_EXPIRY_RENEW_WINDOW = timedelta(minutes=5)


@dataclass
class AuthContext:
    """当前登录上下文，供路由层复用用户信息和当前会话 token。"""

    user: User
    session_token: str
    backend_session_id: str


class AuthService:
    """用户认证服务，统一管理登录、鉴权、登出和密码更新。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)

    async def login(self, username: str, password: str) -> tuple[User, str, int]:
        """校验用户名密码，成功后写入新会话并返回 token。"""

        user = await self.repository.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AppException(status_code=401, code="AUTH_INVALID", detail="用户名或密码错误。")
        if user.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=403, code="AUTH_DISABLED", detail="当前账号不可登录。")

        settings = get_settings()
        now = utc_now()
        raw_token = generate_session_token()
        await self.repository.create_session(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            last_active_at=now,
        )
        await self.repository.update_last_login(user, now)
        await self.session.commit()
        return user, raw_token, settings.session_ttl_hours * 3600

    async def get_context_by_token(self, token: str | None) -> AuthContext:
        """根据 Cookie 中的 token 恢复当前登录上下文。"""

        if not token:
            raise AppException(status_code=401, code="AUTH_REQUIRED", detail="请先登录后再访问。")

        token_hash = hash_session_token(token)
        session_model = await self.repository.get_active_session(token_hash)
        if session_model is None:
            raise AppException(status_code=401, code="AUTH_INVALID_SESSION", detail="登录态已失效，请重新登录。")

        now = utc_now()
        if normalize_utc(session_model.expires_at) <= now:
            session_model.is_active = False
            await self.session.commit()
            raise AppException(status_code=401, code="AUTH_SESSION_EXPIRED", detail="登录已过期，请重新登录。")

        user = await self.repository.get_by_id(session_model.user_id)
        if user is None:
            raise AppException(status_code=401, code="AUTH_INVALID_SESSION", detail="登录态已失效，请重新登录。")
        if user.status != RecordStatus.ACTIVE.value:
            session_model.is_active = False
            await self.session.commit()
            raise AppException(status_code=403, code="AUTH_DISABLED", detail="当前账号不可登录。")

        settings = get_settings()
        if self._should_touch_session(session_model.last_active_at, session_model.expires_at, now):
            await self.repository.touch_session(
                session_model,
                now,
                now + timedelta(hours=settings.session_ttl_hours),
            )
            await self.session.commit()
        return AuthContext(
            user=user,
            session_token=token,
            backend_session_id=str(session_model.id),
        )

    async def logout(self, token: str | None) -> None:
        """注销当前会话，删除 token 对应的有效登录态。"""

        if token:
            await self.repository.deactivate_session(hash_session_token(token))
            await self.session.commit()

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        """校验旧密码后更新账号密码。"""

        if not verify_password(old_password, user.password_hash):
            raise AppException(status_code=400, code="AUTH_OLD_PASSWORD_INVALID", detail="旧密码不正确。")
        user.password_hash = hash_password(new_password)
        await self.session.commit()

    async def update_preview_size_presets(self, user: User, presets: object) -> User:
        """更新当前用户维护的预设尺寸 JSON。"""

        user.preview_size_presets = validate_preview_size_presets(presets)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    @staticmethod
    def _should_touch_session(last_active_at: datetime, expires_at: datetime, now: datetime) -> bool:
        """判断是否需要刷新会话，避免高并发读接口反复写同一会话行。"""

        return (
            normalize_utc(last_active_at) <= now - _SESSION_TOUCH_INTERVAL
            or normalize_utc(expires_at) <= now + _SESSION_EXPIRY_RENEW_WINDOW
        )
