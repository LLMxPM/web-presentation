"""文件功能：测试 Web 端 PAT 配置管理接口的更新、权限隔离与安全请求头契约。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


async def _seed_admin_token(session, suffix: str) -> tuple[int, int]:
    """为接口测试创建一个管理员可管理的 PAT 与工作空间。"""

    user = await session.scalar(select(User).where(User.username == "admin"))
    assert user is not None
    workspace = Workspace(
        code=f"ws-api-token-{suffix}",
        name=f"API Token Workspace {suffix}",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
        )
    )
    await session.flush()
    token_result = await ApiAccessTokenService(session).create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(
            name=f"Token {suffix}",
            workspace_ids=[workspace.id],
            scopes=["workspace:read"],
            expires_in_days=30,
        ),
    )
    await session.commit()
    return token_result.id, workspace.id


@pytest.mark.asyncio
async def test_update_access_token_configuration(authenticated_client: AsyncClient) -> None:
    """测试 PAT 更新接口能在保留密钥的同时替换工作空间与 Scope 配置。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        assert user.role == UserRole.PLATFORM_ADMIN.value

        first_workspace = Workspace(
            code="ws-api-token-update-first",
            name="First API Token Workspace",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        second_workspace = Workspace(
            code="ws-api-token-update-second",
            name="Second API Token Workspace",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add_all([first_workspace, second_workspace])
        await session.flush()
        session.add_all(
            [
                WorkspaceMember(
                    workspace_id=first_workspace.id,
                    user_id=user.id,
                    role="owner",
                    status=RecordStatus.ACTIVE.value,
                ),
                WorkspaceMember(
                    workspace_id=second_workspace.id,
                    user_id=user.id,
                    role="owner",
                    status=RecordStatus.ACTIVE.value,
                ),
            ]
        )
        await session.flush()
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Web API Token",
                workspace_ids=[first_workspace.id],
                scopes=["workspace:read"],
                expires_in_days=30,
            ),
        )
        await session.commit()

        token_id = token_result.id
        token_secret = token_result.token
        second_workspace_id = second_workspace.id

    response = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={
            "name": "Updated Web API Token",
            "workspace_ids": [second_workspace_id],
            "all_workspaces": False,
            "scopes": ["project:read"],
            "expires_in_days": None,
        },
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Web API Token"
    assert response.json()["workspace_ids"] == [second_workspace_id]
    assert response.json()["scopes"] == ["project:read"]
    assert response.json()["expires_at"] is None
    listed = await authenticated_client.get("/api/access-tokens")
    assert listed.status_code == 200
    assert listed.json()["max_active_tokens"] > 0

    # 更新配置不应轮换密钥，原 Token 应继续可用于 Bearer 鉴权。
    session_factory = get_session_factory()
    async with session_factory() as session:
        authenticated = await ApiAccessTokenService(session).authenticate_pat(token_secret)
        assert authenticated.name == "Updated Web API Token"
        assert authenticated.workspaces[0].workspace_id == second_workspace_id


@pytest.mark.asyncio
async def test_update_access_token_rejects_csrf_and_invalid_payload(authenticated_client: AsyncClient) -> None:
    """测试更新接口拒绝缺少来源的请求和不完整的授权参数。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        token_id, workspace_id = await _seed_admin_token(session, "validation")

    missing_origin = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={"name": "No Origin"},
    )
    assert missing_origin.status_code == 403
    assert missing_origin.json()["code"] == "CSRF_CHECK_FAILED"

    invalid_scope = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={"scopes": ["not-a-scope"]},
        headers={"Origin": "http://testserver"},
    )
    assert invalid_scope.status_code == 422

    incomplete_workspace = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={"workspace_ids": [workspace_id]},
        headers={"Origin": "http://testserver"},
    )
    assert incomplete_workspace.status_code == 422


@pytest.mark.asyncio
async def test_update_access_token_rejects_revoked_token(authenticated_client: AsyncClient) -> None:
    """测试已吊销 PAT 不能通过更新接口重新启用。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        token_id, _workspace_id = await _seed_admin_token(session, "revoked")
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        await ApiAccessTokenService(session).revoke_token(user_id=user.id, token_id=token_id)

    response = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={"name": "Should Fail"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PAT_REVOKED"


@pytest.mark.asyncio
async def test_update_access_token_rejects_non_member_workspace(authenticated_client: AsyncClient) -> None:
    """测试 PAT 不能授权当前用户未加入的工作空间。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        token_id, _workspace_id = await _seed_admin_token(session, "non-member")
        other_user = User(
            username="pat_non_member_owner",
            password_hash="hash123",
            display_name="PAT Non Member Owner",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(other_user)
        await session.flush()
        other_workspace = Workspace(
            code="ws-api-token-outside",
            name="Non Member Workspace",
            created_by=other_user.id,
            updated_by=other_user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(other_workspace)
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=other_workspace.id,
                user_id=other_user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            )
        )
        await session.commit()
        other_workspace_id = other_workspace.id

    response = await authenticated_client.patch(
        f"/api/access-tokens/{token_id}",
        json={
            "workspace_ids": [other_workspace_id],
            "all_workspaces": False,
        },
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_access_token_hides_other_user_token(authenticated_client: AsyncClient) -> None:
    """测试当前用户不能通过更新接口探测或修改其他用户的 PAT。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        other_user = User(
            username="pat_other_owner",
            password_hash="hash123",
            display_name="PAT Other Owner",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(other_user)
        await session.flush()
        workspace = Workspace(
            code="ws-api-token-other-owner",
            name="Other Owner Workspace",
            created_by=other_user.id,
            updated_by=other_user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=other_user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            )
        )
        await session.flush()
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=other_user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Other User Token",
                workspace_ids=[workspace.id],
                scopes=["workspace:read"],
                expires_in_days=30,
            ),
        )
        await session.commit()
        other_token_id = token_result.id

    response = await authenticated_client.patch(
        f"/api/access-tokens/{other_token_id}",
        json={"name": "Should Not Update"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 404
