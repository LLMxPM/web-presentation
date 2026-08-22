"""文件功能：测试 PAT 个人访问令牌模型、哈希安全机制、单向展示、权限 Scopes 校验与吊销。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.api_access_token import ApiAccessToken
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


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
