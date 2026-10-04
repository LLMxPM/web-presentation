"""文件功能：提供 ChatGPT 所需 OAuth 发现、授权跳转及有界 Token/自省/撤销协议端点。"""

from typing import Annotated
from urllib.parse import urlencode

from authlib.oauth2.rfc6749.errors import OAuth2Error
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.api.oauth_http import (
    PRIVATE_HEADERS,
    get_oauth_policy,
    protocol_error_response,
    protocol_http_response,
    read_oauth_form,
)
from app.core.config import get_settings
from app.core.external_operations import ALL_VALID_SCOPES
from app.db.session import get_session_factory
from app.services.oauth.audit_logging import log_protocol_result
from app.services.oauth.consent_service import OAuthConsentService
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.resource_protocol import EXCHANGE_GRANT_TYPE
from app.services.oauth.resource_service import OAuthResourceService
from app.services.oauth.token_service import OAuthTokenService

router = APIRouter(tags=["oauth"], include_in_schema=False)
Policy = Annotated[OAuthPolicy, Depends(get_oauth_policy)]


@router.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(policy: Policy) -> JSONResponse:
    """发现只使用显式 issuer；首批发布 CIMD、S256 和 RFC 9207，省略未实现的 DCR/OIDC。"""
    return JSONResponse({
        "issuer": policy.issuer,
        "authorization_endpoint": policy.issuer + "/oauth/authorize",
        "token_endpoint": policy.issuer + "/oauth/token",
        "introspection_endpoint": policy.issuer + "/oauth/introspect",
        "revocation_endpoint": policy.issuer + "/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token", EXCHANGE_GRANT_TYPE],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        "introspection_endpoint_auth_methods_supported": ["client_secret_basic"],
        "revocation_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
        "scopes_supported": sorted(ALL_VALID_SCOPES),
    }, headers={"Cache-Control": "public, max-age=300"})


@router.get("/oauth/authorize")
async def oauth_authorize(request: Request, policy: Policy) -> Response:
    """先验证受限客户端和协议，随后交给 Editor Cookie 登录守卫及显式确认。"""
    try:
        await OAuthConsentService(get_session_factory(), policy).validate(request.url.query)
    except OAuth2Error as error:
        return protocol_error_response(error, policy)
    target = get_settings().oauth_editor_origin + "/oauth/consent?" + urlencode({"authorization_query": request.url.query})
    return RedirectResponse(target, status_code=302, headers=PRIVATE_HEADERS)


async def handle_form(request: Request, policy: OAuthPolicy, endpoint: str) -> Response:
    """协议错误保持 OAuth JSON；事务服务决定何时可以交付成功凭证。"""
    try:
        parsed = await read_oauth_form(request, policy)
        if endpoint == "token" and parsed.payload.grant_type != EXCHANGE_GRANT_TYPE:
            result = await OAuthTokenService(get_session_factory(), policy).token_response(parsed)
        else:
            target = "exchange" if endpoint == "token" else endpoint
            result = await OAuthResourceService(get_session_factory(), policy).response(target, parsed)
    except OAuth2Error as error:
        log_protocol_result(endpoint, error.status_code, error.error)
        return protocol_error_response(error, policy)
    error_code = result.body.get("error") if isinstance(result.body, dict) else None
    log_protocol_result(endpoint, result.status_code, error_code)
    return protocol_http_response(result)


@router.post("/oauth/token")
async def oauth_token(request: Request, policy: Policy) -> Response:
    """公开客户端兑换/刷新与受信服务受控交换复用成熟协议和持久化围栏。"""
    return await handle_form(request, policy, "token")


@router.post("/oauth/introspect")
async def oauth_introspect(request: Request, policy: Policy) -> Response:
    """仅已注册且通过 Basic 认证的 MCP 服务可以自省用户 access。"""
    return await handle_form(request, policy, "introspection")


@router.post("/oauth/revoke")
async def oauth_revoke(request: Request, policy: Policy) -> Response:
    """客户端只能撤销自身授权，未知/他人 Token 维持统一成功响应。"""
    return await handle_form(request, policy, "revocation")
