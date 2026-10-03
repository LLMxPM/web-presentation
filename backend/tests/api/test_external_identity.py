"""文件功能：验证 PAT whoami 兼容、外部主体权限对等及未接入委托认证时的拒绝行为。"""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import get_external_auth_context
from app.core.time_utils import utc_now
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.external_principal import DelegatedCredential, ExternalPrincipal


@pytest.fixture
async def identity_targets(app_session: AsyncSession) -> tuple[str, User, int]:
    """建立独立用户、具体空间与只读 PAT，返回身份测试所需公共标识。"""

    user = User(username="identity-user", password_hash="hash", display_name="身份测试",
                role="workspace_user", preview_size_presets=build_default_preview_size_presets())
    app_session.add(user)
    await app_session.flush()
    workspace = Workspace(code="identity-space", name="身份空间", created_by=user.id, updated_by=user.id)
    app_session.add(workspace)
    await app_session.flush()
    app_session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner", status="active"))
    await app_session.flush()
    token = await ApiAccessTokenService(app_session).create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(name="身份 PAT", workspace_ids=[workspace.id], scopes=["workspace:read", "project:read"]),
    )
    await app_session.commit()
    return token.token, user, workspace.id


async def test_whoami_preserves_pat_fields_and_public_source(client: AsyncClient, identity_targets: tuple[str, User, int]) -> None:
    """旧 token 字段与空间列表兼容，新增来源仅包含公共信息。"""

    token, user, workspace_id = identity_targets
    response = await client.get("/api/v1/auth/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == user.id
    assert set(body["token"]) == {"id", "name", "token_public_id", "scopes", "expires_at", "all_workspaces"}
    assert body["token"]["name"] == "身份 PAT"
    assert body["token"]["all_workspaces"] is False
    assert body["credential"] == {"type": "pat", "public_id": body["token"]["token_public_id"], "expires_at": body["token"]["expires_at"]}
    assert [space["id"] for space in body["workspaces"]] == [workspace_id]
    assert token not in response.text


async def test_verified_delegated_adapter_uses_same_routes_and_permissions(
    client: AsyncClient, identity_targets: tuple[str, User, int], app_session: AsyncSession,
) -> None:
    """仅替换认证依赖验证未来适配边界，不表示真实委托 Bearer 已可用。"""

    token, user, workspace_id = identity_targets
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)}
    pat_capabilities = await client.get(f"/api/v1/workspaces/{workspace_id}/capabilities", headers=headers)
    principal = ExternalPrincipal(
        user=user,
        credential=DelegatedCredential(public_id="delegated-1", grant_id="grant-1", client_id="client-1", service_id="mcp-1",
                                       issuer="https://platform.example", audience="https://platform.example/api/v1", expires_at=utc_now() + timedelta(seconds=60)),
        workspace_ids=frozenset({workspace_id}), scopes=frozenset({"workspace:read", "project:read"}),
    )
    app = client._transport.app
    app.dependency_overrides[get_external_auth_context] = lambda: principal
    try:
        delegated = await client.get(f"/api/v1/workspaces/{workspace_id}/capabilities", headers=headers)
        assert delegated.json() == pat_capabilities.json()
        identity = (await client.get("/api/v1/auth/whoami")).json()
        assert identity["token"] is None
        assert identity["credential"]["type"] == "delegated"
        assert identity["credential"]["grant_id"] == "grant-1"
        assert [space["id"] for space in identity["workspaces"]] == [workspace_id]
        assert (await client.get("/api/v1/projects", headers=headers)).status_code == 200
        denied = await client.post("/api/v1/projects", headers=headers, json={"name": "不能写入"})
        assert denied.status_code == 403
        assert denied.json()["code"] == "INSUFFICIENT_SCOPE"
        outside = await client.get("/api/v1/projects", headers={"X-Workspace-ID": "99999"})
        assert outside.status_code == 403
        assert outside.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"
        member = await app_session.scalar(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id,
        ))
        member.status = "archived"
        await app_session.commit()
        exited = await client.get("/api/v1/projects", headers=headers)
        assert exited.status_code == 403
        assert exited.json()["code"] == "PERMISSION_DENIED"
    finally:
        app.dependency_overrides.pop(get_external_auth_context, None)


@pytest.mark.parametrize("token", ["delegated:forged", "eyJhbGciOiJub25lIn0.e30.", "wp_pat_invalid.jwt"])
async def test_unimplemented_or_invalid_credentials_cannot_fallback(client: AsyncClient, token: str) -> None:
    """来源声明、未签名 JWT 和无效 PAT 均不能在当前唯一 PAT 验证器中被接受。"""

    response = await client.get("/api/v1/auth/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
