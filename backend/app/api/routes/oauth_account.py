"""文件功能：以平台 Cookie 和精确 Origin 提供用户确认、授权列表和整链撤销。"""

from typing import Annotated

from authlib.oauth2.rfc6749.errors import OAuth2Error
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.api.oauth_http import PRIVATE_HEADERS, get_oauth_policy, require_oauth_origin
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.oauth_config import resolve_oauth_policy
from app.db.session import get_session_factory
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.repositories.oauth_repository import load_live_grant
from app.schemas.common import MessageResponse
from app.schemas.oauth_account import (
    OAuthConsentBegin,
    OAuthConsentDecision,
    OAuthConsentResult,
    OAuthConsentView,
    OAuthGrantItem,
    OAuthGrantList,
)
from app.services.auth_service import AuthContext
from app.services.oauth.consent_service import OAuthConsentService
from app.services.oauth.grant_service import OAuthGrantService
from app.services.oauth.policy import OAuthPolicy

router = APIRouter(prefix="/v1/account/oauth", tags=["account-oauth"])
Current = Annotated[AuthContext, Depends(get_current_user)]
Policy = Annotated[OAuthPolicy, Depends(get_oauth_policy)]


@router.post("/consents", response_model=OAuthConsentView, dependencies=[Depends(require_oauth_origin)])
async def begin_oauth_consent(payload: OAuthConsentBegin, current: Current, policy: Policy, response: Response) -> OAuthConsentView:
    """原始用户身份只来自 Cookie，会话与 nonce 不接受请求体覆盖。"""
    response.headers.update(PRIVATE_HEADERS)
    try:
        return await OAuthConsentService(get_session_factory(), policy).begin(
            query=payload.authorization_query, user_id=current.user.id, session_id=int(current.backend_session_id),
        )
    except OAuth2Error as error:
        raise AppException(400, "OAUTH_REQUEST_INVALID", "ChatGPT 授权请求无效，请重新发起连接。", headers=PRIVATE_HEADERS) from error


@router.post("/consents/{request_id}/decision", response_model=OAuthConsentResult, dependencies=[Depends(require_oauth_origin)])
async def decide_oauth_consent(request_id: str, payload: OAuthConsentDecision, current: Current, policy: Policy, response: Response) -> OAuthConsentResult:
    """只消费当前会话本次确认，提交之后才让浏览器导航到已验证回调。"""
    response.headers.update(PRIVATE_HEADERS)
    redirect = await OAuthConsentService(get_session_factory(), policy).decide(
        request_id=request_id, user_id=current.user.id, session_id=int(current.backend_session_id), decision=payload,
    )
    return OAuthConsentResult(redirect_uri=redirect)


@router.get("/grants", response_model=OAuthGrantList)
async def list_oauth_grants(current: Current, response: Response) -> OAuthGrantList:
    """最多展示本人最近 100 条授权，并实时复核成员和客户端状态。"""
    response.headers.update(PRIVATE_HEADERS)
    policy = resolve_oauth_policy(get_settings())
    if policy is None:
        return OAuthGrantList(enabled=False, items=[])
    async with get_session_factory()() as session:
        rows = (await session.execute(select(OAuthGrant, OAuthClient.name).join(
            OAuthClient, OAuthClient.client_id == OAuthGrant.client_id
        ).where(
            OAuthGrant.user_id == current.user.id, OAuthGrant.issuer == policy.issuer,
            OAuthGrant.resource == policy.mcp_resource,
        ).order_by(OAuthGrant.created_at.desc()).limit(100))).all()
        items = []
        for grant, name in rows:
            active = await load_live_grant(session, grant.grant_id, policy) is not None
            items.append(OAuthGrantItem(
                grant_id=grant.grant_id, client_name=name, resource=grant.resource,
                scopes=grant.scopes, workspace_ids=grant.workspace_ids, created_at=grant.created_at,
                revoked_at=grant.revoked_at, is_active=active,
            ))
    return OAuthGrantList(enabled=True, items=items)


@router.post("/grants/{grant_id}/revoke", response_model=MessageResponse, dependencies=[Depends(require_oauth_origin)])
async def revoke_oauth_grant(grant_id: str, current: Current, policy: Policy, response: Response) -> MessageResponse:
    """撤销本人整条授权；未知和他人 ID 同为 404，重复撤销幂等。"""
    response.headers.update(PRIVATE_HEADERS)
    if not await OAuthGrantService(get_session_factory(), policy).revoke(user_id=current.user.id, grant_id=grant_id):
        raise AppException(404, "OAUTH_GRANT_NOT_FOUND", "授权不存在。", headers=PRIVATE_HEADERS)
    return MessageResponse(message="外部授权已撤销。")
