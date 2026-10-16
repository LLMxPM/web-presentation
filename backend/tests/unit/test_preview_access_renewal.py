"""文件功能：测试 preview artifact 短期票据生成与登录会话续签接口 (W04)。"""

from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_current_user
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.main import app
from app.models.user import User
from app.services.auth_service import AuthContext
from app.services.preview_service import PreviewService
from app.services.project_service import ProjectService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_current_user():
    user = User(id=42, username="testuser", display_name="Test User", password_hash="hash", preview_size_presets=[])
    return AuthContext(user=user, session_token="mock-token", backend_session_id="mock-session-id")


@pytest.mark.asyncio
async def test_preview_artifact_renewal_success(mock_session, mock_current_user, monkeypatch):
    """测试通过合法登录会话为存在的 artifact 续签预览票据成功。"""

    artifact_id = "art-renew-123"
    manifest = {
        "artifact_id": artifact_id,
        "preview_kind": "project",
        "owner_scope": {
            "scope_type": "project",
            "project_id": "100",
            "workspace_id": "1",
        },
        "entry_descriptor": {"entry_type": "route", "route": "/page-1"},
        "asset_base_url": "/assets",
        "assets": {},
        "modules": {},
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    # 模拟项目权限检查通过
    async def mock_project_get(self, project_id, user_id):
        assert project_id == 100
        assert user_id == 42
        mock_proj = AsyncMock()
        mock_proj.id = 100
        mock_proj.workspace_id = 1
        return mock_proj

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(ProjectService, "get", mock_project_get)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/preview-artifacts/{artifact_id}/access")
            assert resp.status_code == 200
            data = resp.json()
            assert data["artifact_id"] == artifact_id
            assert "token" in data
            assert "expires_at" in data
            assert "/preview/artifacts/" in data["preview_url"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["workspace_component", "workspace_asset", "runtime_kit_component"])
async def test_renewal_preserves_scope_claims_and_artifact_deadline(scope, monkeypatch):
    """续签不得丢失组件/资源的必需声明，也不能超过快照剩余期限。"""
    from datetime import timedelta
    from app.core.time_utils import utc_now
    from app.services.preview_service import PreviewService
    from app.services.workspace_service import WorkspaceService

    deadline = utc_now() + timedelta(seconds=30)
    manifest = {
        "owner_scope": {"scope_type": scope, "workspace_id": "1", "asset_id": "7", "component_code": "card", "component_version_no": 2},
        "preview_kind": "component" if scope != "workspace_asset" else "asset",
        "entry_descriptor": {"entry_type": "component_host"}, "asset_base_url": "http://backend/preview/artifacts/rt_1/assets",
        "runtime_kit_component_name": "Card", "runtime_kit_manifest_version": "1", "artifact_expires_at": deadline.isoformat(),
    }
    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", AsyncMock(return_value=manifest))
    monkeypatch.setattr(WorkspaceService, "ensure_access", AsyncMock())
    result = await PreviewService(AsyncMock()).renew_preview_access(artifact_id="rt_1", user_id=1)
    claims = TokenService.verify_preview_context_token(result.token)
    assert claims["exp"] <= int(deadline.timestamp())
    if scope == "workspace_component":
        assert claims["component_code"] == "card" and claims["component_version_no"] == 2
    elif scope == "workspace_asset":
        assert claims["asset_id"] == "7"
    else:
        assert claims["component_source"] == "runtime_kit" and claims["runtime_kit_component_name"] == "Card"


@pytest.mark.asyncio
async def test_preview_artifact_renewal_expired(mock_session, mock_current_user, monkeypatch):
    """测试 artifact 过期后请求续签返回 410 PREVIEW_ARTIFACT_EXPIRED。"""

    artifact_id = "art-expired-999"

    async def mock_get_manifest(self, aid):
        return None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/preview-artifacts/{artifact_id}/access")
            assert resp.status_code == 410
            data = resp.json()
            assert data["code"] == "PREVIEW_ARTIFACT_EXPIRED"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_preview_artifact_renewal_permission_denied(mock_session, mock_current_user, monkeypatch):
    """测试若用户不再具备项目权限时续签被拒绝。"""

    artifact_id = "art-no-perm"
    manifest = {
        "artifact_id": artifact_id,
        "preview_kind": "project",
        "owner_scope": {
            "scope_type": "project",
            "project_id": "200",
            "workspace_id": "1",
        },
        "entry_descriptor": {"entry_type": "route", "route": "/"},
        "asset_base_url": "/assets",
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    async def mock_project_get(self, project_id, user_id):
        raise AppException(status_code=403, code="PROJECT_ACCESS_DENIED", detail="无权访问该项目。")

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(ProjectService, "get", mock_project_get)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/preview-artifacts/{artifact_id}/access")
            assert resp.status_code == 403
            data = resp.json()
            assert data["code"] == "PROJECT_ACCESS_DENIED"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner_scope",
    [{}, {"workspace_id": "abc"}, {"project_id": 0}],
)
async def test_renewal_should_fail_closed_without_verifiable_owner_scope(
    mock_session,
    mock_current_user,
    monkeypatch,
    owner_scope,
):
    """快照缺少可校验的归属信息（缺失或非法）时不得签发票据。"""

    artifact_id = "art-no-scope"
    manifest = {
        "artifact_id": artifact_id,
        "preview_kind": "project",
        "owner_scope": owner_scope,
        "entry_descriptor": {"entry_type": "route", "route": "/"},
        "asset_base_url": "/assets",
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/preview-artifacts/{artifact_id}/access")
            assert resp.status_code == 404
            assert resp.json()["code"] == "FILE_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_workspace_preview_artifact_renewal_success(mock_session, mock_current_user, monkeypatch):
    """测试工作空间级预览（无 project_id）通过 WorkspaceService.ensure_access 成功续签。"""

    from app.services.workspace_service import WorkspaceService
    from app.models.workspace import Workspace

    artifact_id = "art-ws-renew-456"
    manifest = {
        "artifact_id": artifact_id,
        "preview_kind": "component",
        "owner_scope": {
            "scope_type": "workspace",
            "workspace_id": "77",
        },
        "entry_descriptor": {"entry_type": "component", "component_name": "TestComp"},
        "asset_base_url": "/assets",
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    called_ensure_access = []

    async def mock_ensure_access(self, workspace_id, *, user_id):
        called_ensure_access.append((workspace_id, user_id))
        return Workspace(id=workspace_id, name="WS", code="WS")

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(WorkspaceService, "ensure_access", mock_ensure_access)

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/preview-artifacts/{artifact_id}/access")
            assert resp.status_code == 200
            data = resp.json()
            assert data["artifact_id"] == artifact_id
            assert len(called_ensure_access) == 1
            assert called_ensure_access[0] == (77, 42)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

