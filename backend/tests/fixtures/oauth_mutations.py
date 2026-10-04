"""文件功能：在 OAuth 专属 SQLite/PG 数据库内准备真实业务路由与委托创作测试数据。"""

from datetime import timedelta

import pytest
from app.core.time_utils import utc_now
from app.db.base import Base
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.models.page import Page
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.oauth.protocol import credential_digest
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from tests.fixtures.oauth import POLICY, REDIRECT, VERIFIER, request_data
from tests.fixtures.oauth_resource import exchange_data, service_request

SCOPES = ["page:read", "page:write", "component:read", "component:write"]
SOURCE = "<template><div>原始内容</div></template>"


@pytest.fixture
async def oauth_mutation_client(oauth_http_client, mcp_access):
    """仅扩充隔离库表及真实授权 Scope，不启动 Worker，也不替换业务写入或身份验证。"""
    client, factory, _ = oauth_http_client
    async with factory.kw["bind"].begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        (await session.get(OAuthClient, "desktop")).scopes = SCOPES
        (await session.get(OAuthGrant, "grant-1")).scopes = SCOPES
        # 为已批准的完整 Grant 准备一次性授权码；旧凭证不扩权，新凭证走真实 HTTP 兑换。
        session.add(
            OAuthAuthorizationCode(
                code_hash=credential_digest("mutation-code"),
                grant_id="grant-1",
                redirect_uri=REDIRECT,
                scopes=SCOPES,
                code_challenge=create_s256_code_challenge(VERIFIER),
                code_challenge_method="S256",
                created_at=utc_now(),
                expires_at=utc_now() + timedelta(seconds=POLICY.code_ttl_seconds),
            )
        )
        session.add(
            Project(
                id=1,
                workspace_id=1,
                code="mutation-project",
                name="创作项目",
                theme_config_yaml="{}",
                created_by=1,
            )
        )
        await session.flush()
        session.add(
            Page(
                id=1,
                workspace_id=1,
                project_id=1,
                code="mutation-page",
                title="测试页面",
                page_content=SOURCE,
                created_by=1,
            )
        )
        session.add(
            WorkspaceComponent(
                id=1,
                workspace_id=1,
                code="mutation-component",
                name="测试组件",
                import_name="TestCard",
                content=SOURCE,
                created_by=1,
            )
        )
        await session.commit()
        pat = await ApiAccessTokenService(session).create_token(
            user_id=1,
            payload=ApiAccessTokenCreateRequest(
                name="创作对拍 PAT",
                workspace_ids=[1],
                scopes=SCOPES,
            ),
        )
    issued = await client.post("/oauth/token", data=request_data(code="mutation-code"))
    assert issued.status_code == 200, issued.text
    yield client, factory, issued.json(), pat.token


async def delegate_headers(
    client, access: str, *, scopes: list[str] = SCOPES, key: str = "mutation-key"
) -> dict[str, str]:
    """通过真实 HTTP 服务认证交换给定 Scope，不注入 ExternalPrincipal。"""
    response = await client.post(
        "/oauth/token",
        data=exchange_data(access, scope=" ".join(scopes)),
        headers=dict(service_request({}).headers),
    )
    assert response.status_code == 200, response.text
    return {
        "Authorization": "Bearer " + response.json()["access_token"],
        "X-Workspace-ID": "1",
        "Idempotency-Key": key,
    }


async def refresh_access(client, refresh: str) -> dict:
    """使用原客户端真实 HTTP 轮换，返回新 MCP access/refresh。"""
    response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "desktop",
            "resource": POLICY.mcp_resource,
            "refresh_token": refresh,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def other_user_access(client, factory) -> dict:
    """创建第二用户/空间的批准 Grant，并通过真实授权码兑换发行独立凭证。"""
    async with factory() as session:
        session.add(
            User(
                id=2,
                username="other-user",
                display_name="另一用户",
                password_hash="unused",
                preview_size_presets=[],
            )
        )
        session.add(Workspace(id=2, code="other-space", name="另一空间"))
        await session.flush()
        session.add(WorkspaceMember(workspace_id=2, user_id=2))
        session.add(
            Project(
                id=2,
                workspace_id=2,
                code="other-project",
                name="另一项目",
                theme_config_yaml="{}",
                created_by=2,
            )
        )
        session.add(
            OAuthGrant(
                grant_id="grant-2",
                user_id=2,
                client_id="desktop",
                issuer=POLICY.issuer,
                resource=POLICY.mcp_resource,
                workspace_ids=[2],
                scopes=SCOPES,
            )
        )
        await session.flush()
        session.add(
            OAuthAuthorizationCode(
                code_hash=credential_digest("other-code"),
                grant_id="grant-2",
                redirect_uri=REDIRECT,
                scopes=SCOPES,
                code_challenge=create_s256_code_challenge(VERIFIER),
                code_challenge_method="S256",
                created_at=utc_now(),
                expires_at=utc_now() + timedelta(seconds=POLICY.code_ttl_seconds),
            )
        )
        await session.commit()
    issued = await client.post("/oauth/token", data=request_data(code="other-code"))
    assert issued.status_code == 200, issued.text
    return issued.json()


async def submit_edit(client, access: str, kind: str, *, key="submit") -> dict:
    """真实提交页面/组件编辑并返回 202 Job；仅用于隔离队列边界验证。"""
    entity = "page" if kind == "page" else "component"
    payload = {
        entity + "_id": 1,
        "base_version_no": 1 if kind == "page" else 0,
        "edits": [{"type": "replace", "old_text": "原始", "new_text": "新"}],
    }
    headers = await delegate_headers(client, access, key=key)
    response = await client.post(
        f"/api/v1/jobs/mutations/{entity}s/edits", json=payload, headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()
