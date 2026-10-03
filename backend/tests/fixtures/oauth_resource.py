"""文件功能：提供受信 MCP 服务、自省/交换请求及已批准授权的测试凭证夹具。"""

import base64

import pytest
from app.core.security import hash_password
from app.models.oauth_registration import OAuthMcpService
from app.services.oauth.request import ProtocolRequest
from app.services.oauth.resource_protocol import ACCESS_TOKEN_TYPE, EXCHANGE_GRANT_TYPE
from app.services.oauth.token_service import OAuthTokenService

from tests.fixtures.oauth import POLICY, request_data, token_request


@pytest.fixture
async def mcp_access(oauth_database) -> dict:
    """预注册受信服务并模拟已获用户确认的授权码兑换，不冒充浏览器确认验收。"""
    async with oauth_database() as session:
        session.add(
            OAuthMcpService(
                service_id="mcp-service",
                name="测试 MCP 服务",
                secret_hash=hash_password("service-secret"),
                resource=POLICY.mcp_resource,
                api_audience=POLICY.api_audience,
            )
        )
        await session.commit()
    issued = await OAuthTokenService(oauth_database, POLICY).token_response(
        token_request(request_data())
    )
    assert issued.status_code == 200
    return issued.body


def service_request(
    data: dict[str, str], *, service_id="mcp-service", secret="service-secret", extra=()
) -> ProtocolRequest:
    """使用真实 HTTP Basic 表达服务认证；重复参数不能提前丢弃。"""
    basic = base64.b64encode(f"{service_id}:{secret}".encode()).decode()
    return ProtocolRequest(
        method="POST",
        uri=POLICY.issuer + "/oauth/token",
        pairs=[*data.items(), *extra],
        headers={"Authorization": "Basic " + basic},
    )


def exchange_data(access: str, **changes) -> dict[str, str]:
    """构造标准 RFC 8693 字段，首期使用 resource 指定唯一目标。"""
    return {
        "grant_type": EXCHANGE_GRANT_TYPE,
        "subject_token": access,
        "subject_token_type": ACCESS_TOKEN_TYPE,
        "requested_token_type": ACCESS_TOKEN_TYPE,
        "resource": POLICY.api_audience,
        "scope": "page:read",
        **changes,
    }
