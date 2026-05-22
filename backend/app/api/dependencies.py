"""文件功能：定义接口层的公共依赖，包括列表查询和登录态恢复。"""

from typing import Annotated

from fastapi import Cookie, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_cookie import set_user_session_cookie
from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.common import ListQuery
from app.schemas.page import PageListQuery
from app.models.enums import UserRole
from app.models.workspace import Workspace
from app.core.exceptions import AppException
from app.services.auth_service import AuthContext, AuthService
from app.services.workspace_service import WorkspaceService


async def get_current_user(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    session_token: Annotated[str | None, Cookie(alias=get_settings().session_cookie_name)] = None,
) -> AuthContext:
    """从 HttpOnly Cookie 中恢复当前用户上下文。"""

    context = await AuthService(session).get_context_by_token(session_token)
    set_user_session_cookie(response, context.session_token)
    return context


async def require_platform_admin(
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthContext:
    """要求当前用户具备平台管理员角色。"""

    if current.user.role != UserRole.PLATFORM_ADMIN.value:
        raise AppException(status_code=403, code="USER_ADMIN_REQUIRED", detail="需要平台管理员权限。")
    return current


async def require_workspace_access(
    workspace_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Workspace:
    """要求当前用户是指定工作空间的启用成员。"""

    return await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)


def get_list_query(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    keyword: str | None = None,
    status: str | None = None,
    sort_by: str = "updated_at",
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> ListQuery:
    """解析通用列表参数，并转为统一的查询模型。"""

    normalized_status = status or None
    return ListQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=normalized_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def get_page_list_query(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    keyword: str | None = None,
    status: str | None = None,
    sort_by: str = "updated_at",
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    workspace_id: int | None = None,
    project_id: int | None = None,
) -> PageListQuery:
    """解析页面资源专属列表参数。"""

    normalized_status = status or None
    return PageListQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=normalized_status,
        sort_by=sort_by,
        sort_order=sort_order,
        workspace_id=workspace_id,
        project_id=project_id,
    )
