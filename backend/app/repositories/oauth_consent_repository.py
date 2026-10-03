"""文件功能：实时验证确认会话和空间成员关系，受限注册 ChatGPT 客户端。"""

from datetime import datetime

from authlib.oauth2.rfc6749.errors import InvalidClientError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.oauth_registration import OAuthClient
from app.models.user import User, UserSession
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.oauth_account import OAuthWorkspaceChoice
from app.services.oauth.chatgpt_client import CHATGPT_CLIENT_ID, CHATGPT_REDIRECT_URI
from app.services.oauth.snapshots import ClientSnapshot


async def register_chatgpt_client(session: AsyncSession, client: ClientSnapshot) -> None:
    """通过同一客户端 UPDATE 序列化已有注册；禁用状态和回调不得被元数据覆盖。"""
    if client.client_id != CHATGPT_CLIENT_ID or client.redirect_uris != (CHATGPT_REDIRECT_URI,):
        raise InvalidClientError()
    await session.execute(update(OAuthClient).where(
        OAuthClient.client_id == client.client_id
    ).values(is_active=OAuthClient.is_active).execution_options(synchronize_session=False))
    registered = await session.get(OAuthClient, client.client_id, populate_existing=True)
    if registered is None:
        session.add(OAuthClient(
            client_id=client.client_id, name="ChatGPT", redirect_uris=list(client.redirect_uris),
            scopes=sorted(client.scopes), resource=client.resource, auth_method="none",
        ))
        await session.flush()
    elif (
        not registered.is_active
        or registered.auth_method != "none"
        or registered.secret_hash is not None
        or registered.resource != client.resource
        or registered.redirect_uris != list(client.redirect_uris)
        or set(registered.scopes) != client.scopes
    ):
        raise InvalidClientError()


async def require_consent_session(session: AsyncSession, user_id: int, session_id: int, now: datetime) -> None:
    """确认每次入队和消费均复核真实 Cookie 会话与用户启用状态。"""
    valid = await session.scalar(select(UserSession.id).join(User, User.id == UserSession.user_id).where(
        UserSession.id == session_id, UserSession.user_id == user_id,
        UserSession.is_active.is_(True), UserSession.expires_at > now, User.status == "active",
    ))
    if valid is None:
        raise AppException(401, "AUTH_INVALID_SESSION", "授权确认的登录会话已失效，请重新登录。")


async def consent_workspaces(session: AsyncSession, user_id: int) -> list[OAuthWorkspaceChoice]:
    """只列出当前可访问空间；管理员也不能借授权获得未来或非成员空间。"""
    rows = (await session.execute(select(Workspace.id, Workspace.name).join(
        WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id
    ).where(
        WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active",
        Workspace.status == "active", Workspace.deleted_at.is_(None),
    ).order_by(Workspace.id))).all()
    return [OAuthWorkspaceChoice(id=row.id, name=row.name) for row in rows]
