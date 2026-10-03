"""文件功能：验证 OAuth 显式信任地址、不同 audience 及绝对期限的配置约束。"""

import pytest
from app.services.oauth.policy import OAuthPolicy


def policy(**changes) -> OAuthPolicy:
    """构造独立测试发行边界。"""
    return OAuthPolicy(
        **{
            "issuer": "https://platform.test",
            "mcp_resource": "https://mcp.test/mcp",
            "api_audience": "https://platform.test/api/v1",
            **changes,
        }
    )


@pytest.mark.parametrize("field", ["issuer", "mcp_resource", "api_audience"])
@pytest.mark.parametrize(
    "value",
    [
        "http://platform.test",
        "https://user:secret@platform.test",
        "https://platform.test?aud=x",
        "https://platform.test#fragment",
    ],
)
def test_trust_addresses_reject_ambiguous_or_insecure_values(field, value) -> None:
    """每个信任地址都不能通过请求 Host、用户凭证、query 或片段切换身份。"""
    with pytest.raises(ValueError):
        policy(**{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"api_audience": "https://mcp.test/mcp"},
        {"code_ttl_seconds": 61},
        {"access_ttl_seconds": 0},
        {"delegated_ttl_seconds": 61},
        {"consent_ttl_seconds": True},
        {"refresh_lifetime_seconds": 30 * 24 * 60 * 60 + 1},
        {"credential_retention_seconds": -1},
        {"audit_retention_seconds": 1.5},
    ],
)
def test_audience_and_lifetime_limits(changes) -> None:
    """MCP 与 API 的 audience 不可相同；期限必须是上限内正整数。"""
    with pytest.raises(ValueError):
        policy(**changes)
