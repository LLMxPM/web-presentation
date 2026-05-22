"""文件功能：提供用户登录、登出、当前用户和修改密码接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_cookie import set_user_session_cookie
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.auth import AuthUser, ChangePasswordRequest, LoginRequest, LoginResponse, PreviewSizePresetUpdateRequest
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthContext, AuthService

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    """校验用户账号密码并写入会话 Cookie。"""

    user, token, _ = await AuthService(session).login(payload.username, payload.password)
    set_user_session_cookie(response, token)
    return LoginResponse(user=AuthUser.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> MessageResponse:
    """注销当前登录会话并移除浏览器 Cookie。"""

    settings = get_settings()
    await AuthService(session).logout(current.session_token)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return MessageResponse(message="已退出登录。")


@router.get("/me", response_model=AuthUser)
async def get_me(current: Annotated[AuthContext, Depends(get_current_user)]) -> AuthUser:
    """返回当前登录用户的基础信息。"""

    return AuthUser.model_validate(current.user)


@router.patch("/me/preview-size-presets", response_model=AuthUser)
async def update_preview_size_presets(
    payload: PreviewSizePresetUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthUser:
    """更新当前用户的预设尺寸 JSON。"""

    user = await AuthService(session).update_preview_size_presets(
        current.user,
        [item.model_dump(mode="python") for item in payload.presets],
    )
    return AuthUser.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> MessageResponse:
    """校验旧密码后更新当前管理员密码。"""

    await AuthService(session).change_password(current.user, payload.old_password, payload.new_password)
    return MessageResponse(message="密码修改成功。")
