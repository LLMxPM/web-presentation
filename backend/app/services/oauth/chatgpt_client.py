"""文件功能：只获取并验证 ChatGPT 稳定 CIMD 文档，禁止任意 URL、跳转与宽泛回调。"""

import json

import httpx
from authlib.oauth2.rfc6749.errors import InvalidClientError

from app.core.external_operations import ALL_VALID_SCOPES
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.snapshots import ClientSnapshot

CHATGPT_CLIENT_ID = "https://chatgpt.com/oauth/client.json"
CHATGPT_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"
MAX_METADATA_BYTES = 16 * 1024


def validate_chatgpt_metadata(document: object, policy: OAuthPolicy) -> ClientSnapshot:
    """验证真实元数据的身份、回调和公开客户端能力；数组方法优先于旧单值偏好。"""
    if not isinstance(document, dict):
        raise InvalidClientError()
    methods = document.get("token_endpoint_auth_methods_supported")
    if methods is None:
        methods = [document.get("token_endpoint_auth_method")]
    grants = document.get("grant_types")
    if (
        document.get("client_id") != CHATGPT_CLIENT_ID
        or document.get("redirect_uris") != [CHATGPT_REDIRECT_URI]
        or not isinstance(methods, list)
        or "none" not in methods
        or not isinstance(grants, list)
        or not all(isinstance(item, str) for item in grants)
        or not {"authorization_code", "refresh_token"} <= set(grants)
        or document.get("response_types") != ["code"]
    ):
        raise InvalidClientError()
    return ClientSnapshot(
        client_id=CHATGPT_CLIENT_ID,
        redirect_uris=(CHATGPT_REDIRECT_URI,),
        scopes=frozenset(ALL_VALID_SCOPES),
        resource=policy.mcp_resource,
    )


async def fetch_chatgpt_client(client_id: str, policy: OAuthPolicy) -> ClientSnapshot:
    """仅访问写死的 HTTPS 文档，限制网络期限和响应大小，失败时不回退离线客户端。"""
    if client_id != CHATGPT_CLIENT_ID:
        raise InvalidClientError()
    try:
        async with (
            httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client,
            client.stream("GET", CHATGPT_CLIENT_ID) as response,
        ):
            if response.status_code != 200:
                raise InvalidClientError()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_METADATA_BYTES:
                    raise InvalidClientError()
        return validate_chatgpt_metadata(json.loads(body), policy)
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise InvalidClientError() from error
