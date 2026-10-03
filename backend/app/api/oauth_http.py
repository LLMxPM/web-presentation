"""文件功能：适配有界 OAuth 表单、协议响应和显式 Editor Origin 校验。"""

from urllib.parse import parse_qsl

from authlib.oauth2.rfc6749.errors import InvalidRequestError, OAuth2Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.oauth_config import resolve_oauth_policy
from app.services.oauth.issuer_extension import ExplicitIssuerParameter
from app.services.oauth.protocol import McpAuthorizationServer, ProtocolResponse
from app.services.oauth.request import ProtocolRequest

PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}


def get_oauth_policy():
    """关闭时 fail-closed，发现和协议端点不能退回 SPA 或其它凭证规则。"""
    policy = resolve_oauth_policy(get_settings())
    if policy is None:
        raise AppException(404, "OAUTH_DISABLED", "远程 MCP OAuth 尚未启用。", headers=PRIVATE_HEADERS)
    return policy


def require_oauth_origin(request: Request) -> None:
    """所有 Cookie 写入口必须携带精确的受信 Editor Origin，不能从 Host 派生。"""
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] != get_settings().oauth_editor_origin:
        raise AppException(403, "OAUTH_ORIGIN_INVALID", "授权操作来源无效。", headers=PRIVATE_HEADERS)


def protocol_http_response(result: ProtocolResponse) -> Response:
    """只有持久化服务返回的协议结果才交付，统一阻止缓存和 Referer 泄漏。"""
    headers = {**dict(result.headers), **PRIVATE_HEADERS}
    if isinstance(result.body, dict):
        return JSONResponse(result.body, status_code=result.status_code, headers=headers)
    return Response(result.body, status_code=result.status_code, headers=headers)


def protocol_error_response(error: OAuth2Error, policy) -> Response:
    """保留 Authlib 标准 OAuth 错误，并为库已经验证的错误回调补充 issuer 扩展。"""
    server = McpAuthorizationServer(client=None)
    request = ProtocolRequest(method="GET", uri=policy.issuer + "/oauth/authorize", pairs=[])
    result = server.handle_error_response(request, error)
    ExplicitIssuerParameter(policy.issuer).add_issuer_parameter(server, result)
    return protocol_http_response(result)


async def read_oauth_form(request: Request, policy) -> ProtocolRequest:
    """只接受 POST urlencoded 单一来源表单；逐块限制为 16 KiB，拒绝重复参数。"""
    if request.url.query or request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise InvalidRequestError("A form encoded POST body is required.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16 * 1024:
            raise InvalidRequestError("Request body is too large.")
    try:
        pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=32)
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidRequestError() from error
    return ProtocolRequest(method="POST", uri=policy.issuer + request.url.path, pairs=pairs, headers=request.headers)
