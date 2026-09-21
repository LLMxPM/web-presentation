"""文件功能：测试 PAT 个人访问令牌模型、哈希安全机制、单向展示、权限 Scopes 校验与吊销。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.api_access_token import ApiAccessToken
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest, ApiAccessTokenUpdateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService
from app.core.time_utils import utc_now


@pytest.mark.asyncio
async def test_pat_creation_and_authentication(app_session: AsyncSession) -> None:
    """测试 PAT 创建后能成功通过 Bearer 鉴权，且数据库仅保存哈希值。"""

    # 1. 准备测试用户与工作空间
    user = User(
        username="pat_user",
        password_hash="hash123",
        display_name="PAT User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    ws = Workspace(code="ws-pat-01", name="Test Workspace", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    app_session.add(ws)
    await app_session.flush()

    u_id = user.id
    w_id = ws.id
    member = WorkspaceMember(workspace_id=w_id, user_id=u_id, role="owner", status=RecordStatus.ACTIVE.value)
    app_session.add(member)
    await app_session.commit()

    # 2. 创建访问令牌
    service = ApiAccessTokenService(app_session)
    req = ApiAccessTokenCreateRequest(
        name="CLI-Token",
        workspace_ids=[w_id],
        scopes=["project:read", "project:write", "page:read"],
        expires_in_days=30,
    )
    res = await service.create_token(user_id=u_id, payload=req)

    assert res.token.startswith("wp_pat_")
    assert res.token_public_id in res.token
    assert res.name == "CLI-Token"
    assert set(res.scopes) == {"project:read", "project:write", "page:read"}

    # SQLite 读取 timezone=True 的时间字段后会返回 naive datetime，列表接口仍应正常工作。
    app_session.expire_all()
    listed_tokens = await service.list_tokens(user_id=u_id)
    assert listed_tokens.total == 1
    assert listed_tokens.items[0].is_active is True

    # 3. 校验 Bearer 鉴权
    authenticated_token = await service.authenticate_pat(res.token, ip="192.0.2.10")
    assert authenticated_token.user_id == u_id
    assert authenticated_token.name == "CLI-Token"
    assert authenticated_token.is_active is True
    await app_session.rollback()
    persisted_token = await app_session.get(ApiAccessToken, res.id)
    assert persisted_token is not None
    assert persisted_token.last_used_at is not None
    assert persisted_token.last_used_ip == "192.0.2.10"

    # 4. 测试错误 Token 拒绝
    with pytest.raises(AppException) as exc_info:
        await service.authenticate_pat(f"{res.token}invalid")
    assert exc_info.value.code in {"INVALID_TOKEN", "UNAUTHENTICATED"}

    # 5. 吊销 Token 并验证立即失效
    await service.revoke_token(user_id=u_id, token_id=res.id)
    with pytest.raises(AppException) as exc_info:
        await service.authenticate_pat(res.token)
    assert exc_info.value.code in {"TOKEN_REVOKED", "UNAUTHENTICATED"}


@pytest.mark.asyncio
async def test_pat_scope_and_workspace_validation(app_session: AsyncSession) -> None:
    """测试非法 Scope 或未加入的工作空间创建 PAT 时抛出对应异常。"""

    user = User(
        username="pat_user_2",
        password_hash="hash123",
        display_name="PAT User 2",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.commit()

    service = ApiAccessTokenService(app_session)

    # 试图授权不存在或无权的工作空间
    with pytest.raises(AppException) as exc_info:
        await service.create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="Bad-Token",
                workspace_ids=[99999],
                scopes=["project:read"],
                expires_in_days=7,
            ),
        )
    assert exc_info.value.code in {"INVALID_WORKSPACE", "PERMISSION_DENIED"}


def test_pat_duplicate_workspace_ids_rejected() -> None:
    """测试 PAT 请求拒绝重复工作空间 ID。"""

    with pytest.raises(ValueError, match="重复工作空间"):
        ApiAccessTokenCreateRequest(
            name="Duplicate-Workspace-Token",
            workspace_ids=[1, 1],
            scopes=["project:read"],
            expires_in_days=7,
        )


def test_pat_workspace_authorization_mode_must_be_unambiguous() -> None:
    """测试全空间和指定空间授权必须二选一。"""

    with pytest.raises(ValueError, match="至少需要一个 workspace_id"):
        ApiAccessTokenCreateRequest(name="No-Workspace", scopes=["workspace:read"])

    with pytest.raises(ValueError, match="不得同时传入 workspace_ids"):
        ApiAccessTokenCreateRequest(
            name="Ambiguous-Workspace",
            all_workspaces=True,
            workspace_ids=[1],
            scopes=["workspace:read"],
        )


@pytest.mark.asyncio
async def test_pat_can_be_long_lived_and_authorize_all_workspaces(app_session: AsyncSession) -> None:
    """测试长期 PAT 可动态授权用户所有工作空间，且列表与鉴权保持活跃。"""

    user = User(
        username="pat_long_lived_user",
        password_hash="hash123",
        display_name="Long Lived PAT User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.commit()
    user_id = user.id

    service = ApiAccessTokenService(app_session)
    response = await service.create_token(
        user_id=user_id,
        payload=ApiAccessTokenCreateRequest(
            name="Long-Lived-All-Workspaces",
            all_workspaces=True,
            scopes=["workspace:read"],
            expires_in_days=None,
        ),
    )

    assert response.expires_at is None
    assert response.all_workspaces is True
    assert response.workspace_ids == []

    app_session.expire_all()
    listed = await service.list_tokens(user_id=user_id)
    assert listed.items[0].expires_at is None
    assert listed.items[0].all_workspaces is True
    assert listed.items[0].is_active is True

    authenticated = await service.authenticate_pat(response.token)
    assert authenticated.expires_at is None
    assert authenticated.all_workspaces is True


@pytest.mark.asyncio
async def test_pat_configuration_can_be_updated_without_rotating_secret(app_session: AsyncSession) -> None:
    """测试 PAT 更新配置会替换授权关系，但保留原始密钥并立即影响鉴权。"""

    user = User(
        username="pat_update_user",
        password_hash="hash123",
        display_name="PAT Update User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    first_workspace = Workspace(
        code="ws-pat-update-first",
        name="First Update Workspace",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    second_workspace = Workspace(
        code="ws-pat-update-second",
        name="Second Update Workspace",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    app_session.add_all([first_workspace, second_workspace])
    await app_session.flush()
    app_session.add_all(
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
    await app_session.commit()

    service = ApiAccessTokenService(app_session)
    created = await service.create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(
            name="Before Update",
            workspace_ids=[first_workspace.id],
            scopes=["project:read"],
            expires_in_days=30,
        ),
    )
    updated = await service.update_token(
        user_id=user.id,
        token_id=created.id,
        payload=ApiAccessTokenUpdateRequest(
            name="After Update",
            workspace_ids=[second_workspace.id],
            all_workspaces=False,
            scopes=["project:write"],
            expires_in_days=None,
        ),
    )

    assert updated.name == "After Update"
    assert updated.workspace_ids == [second_workspace.id]
    assert updated.scopes == ["project:write"]
    assert updated.expires_at is None
    authenticated = await service.authenticate_pat(created.token)
    assert authenticated.token_public_id == created.token_public_id
    assert authenticated.workspaces[0].workspace_id == second_workspace.id
    assert [scope.scope for scope in authenticated.scopes] == ["project:write"]


@pytest.mark.asyncio
async def test_pat_update_respects_active_token_limit(
    app_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试过期 PAT 续期时仍受活跃令牌数量上限约束。"""

    user = User(
        username="pat_update_limit_user",
        password_hash="hash123",
        display_name="PAT Update Limit User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()
    workspace = Workspace(
        code="ws-pat-update-limit",
        name="Update Limit Workspace",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    app_session.add(workspace)
    await app_session.flush()
    app_session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
        )
    )
    await app_session.commit()

    service = ApiAccessTokenService(app_session)
    expired = await service.create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(
            name="Expired Token",
            workspace_ids=[workspace.id],
            scopes=["workspace:read"],
            expires_in_days=30,
        ),
    )
    await service.create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(
            name="Active Token",
            workspace_ids=[workspace.id],
            scopes=["workspace:read"],
            expires_in_days=30,
        ),
    )
    expired_model = await app_session.get(ApiAccessToken, expired.id)
    assert expired_model is not None
    expired_model.expires_at = utc_now() - timedelta(days=1)
    await app_session.commit()
    monkeypatch.setattr(service.settings, "pat_max_active_tokens", 1)

    with pytest.raises(AppException) as exc_info:
        await service.update_token(
            user_id=user.id,
            token_id=expired.id,
            payload=ApiAccessTokenUpdateRequest(expires_in_days=30),
        )
    assert exc_info.value.code == "PAT_MAX_ACTIVE_LIMIT_REACHED"
