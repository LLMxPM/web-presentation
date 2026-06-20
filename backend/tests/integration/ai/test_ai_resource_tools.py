"""文件功能：覆盖 AI 资源工具的真实调用路径与可恢复业务错误返回。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.agent import RESOURCE_MANAGER_AGENT_ID
from app.ai.auth_tokens import RESOURCE_TOOL_READ_SCOPES, build_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.resource.resource_library import build_get_resource_asset_content_tool
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthContext


async def test_get_resource_asset_content_tool_should_return_recoverable_error_for_bitmap(
    authenticated_client: AsyncClient,
) -> None:
    """位图资源不可读取文本内容时，应返回可恢复错误和资源摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源读取错误工作空间")
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("bitmap.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "name": "bitmap_image", "tags": "[]"},
    )
    assert upload_response.status_code == 200, upload_response.text
    asset = upload_response.json()
    tool = build_get_resource_asset_content_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id)

    result = await tool.entrypoint(run_context, asset_id=asset["id"])

    assert result["success"] is False
    assert result["kind"] == "recoverable_tool_error"
    assert result["error"]["code"] == "ASSET_CONTENT_READ_UNSUPPORTED"
    assert result["data"]["asset"]["id"] == asset["id"]
    assert result["data"]["asset"]["content_editable"] is False


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


def _build_tool_run_context(*, workspace_id: int) -> AgentToolContext:
    """构造资源读取工具需要的运行上下文和签名 token。"""

    current = _build_auth_context()
    run_id = "resource-tool-run"
    session_id = "resource-tool-session"
    dependencies = {
        "user_id": current.user.id,
        "agent_id": RESOURCE_MANAGER_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "project_id": None,
        "page_id": None,
        "component_id": None,
        "source": "test",
        "backend_session_id": current.backend_session_id,
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=RESOURCE_MANAGER_AGENT_ID,
        workspace_id=workspace_id,
        project_id=None,
        page_id=None,
        component_id=None,
        source="test",
        scopes=RESOURCE_TOOL_READ_SCOPES,
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id=str(current.user.id),
        dependencies=dependencies,
    )


def _build_auth_context() -> AuthContext:
    """构造带管理员身份的测试鉴权上下文。"""

    return AuthContext(
        user=User(
            id=1,
            username="admin",
            password_hash="",
            display_name="管理员",
            role=UserRole.PLATFORM_ADMIN.value,
            preview_size_presets=[],
        ),
        session_token="test-session-token",
        backend_session_id="1",
    )
