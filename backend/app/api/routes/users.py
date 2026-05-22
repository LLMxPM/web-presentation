"""文件功能：提供平台管理员使用的用户管理接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_platform_admin
from app.db.session import get_db_session
from app.schemas.user import UserCreateRequest, UserItem, UserResetPasswordRequest, UserUpdateRequest
from app.services.auth_service import AuthContext
from app.services.user_service import UserService

router = APIRouter(prefix="/users", dependencies=[Depends(require_platform_admin)])


@router.get("", response_model=list[UserItem])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UserItem]:
    """列出全部平台用户。"""

    return await UserService(session).list_users()


@router.post("", response_model=UserItem, status_code=201)
async def create_user(
    payload: UserCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserItem:
    """创建平台用户。"""

    return await UserService(session).create_user(payload)


@router.patch("/{user_id}", response_model=UserItem)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    current: Annotated[AuthContext, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserItem:
    """更新平台用户资料、角色或状态。"""

    return await UserService(session).update_user(user_id, payload, operator_id=current.user.id)


@router.post("/{user_id}/reset-password", response_model=UserItem)
async def reset_user_password(
    user_id: int,
    payload: UserResetPasswordRequest,
    current: Annotated[AuthContext, Depends(require_platform_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserItem:
    """重置平台用户密码。"""

    return await UserService(session).reset_password(user_id, payload, operator_id=current.user.id)
