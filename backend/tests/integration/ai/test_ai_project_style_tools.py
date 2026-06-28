"""文件功能：覆盖 AI 项目样式工具的真实调用路径与样式规范按需返回行为。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import PROJECT_TOOL_READ_SCOPES, build_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.project.project_style_config import build_get_project_style_config_tool
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthContext


async def test_get_project_style_config_should_return_style_spec_only_when_requested(
    authenticated_client: AsyncClient,
) -> None:
    """读取项目样式配置时默认不重复返回已注入上下文的 style_spec_markdown。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 项目样式工具工作空间")
    style_spec = "## 版式\n- 标题保持简洁。"
    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "AI 项目样式工具项目",
        style_spec_markdown=style_spec,
    )
    tool = build_get_project_style_config_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id, project_id=project_id)

    default_result = await tool.entrypoint(run_context)

    assert default_result["page_width"]
    assert default_result["page_height"]
    assert default_result["base_font_size"]
    assert "theme" in default_result
    assert default_result["style_spec_markdown_in_runtime_context"] is True
    assert default_result["style_spec_markdown_length"] == len(style_spec)
    assert "style_spec_markdown" not in default_result

    full_result = await tool.entrypoint(run_context, include_style_spec_markdown=True)

    assert full_result["style_spec_markdown"] == style_spec
    assert full_result["style_spec_markdown_length"] == len(style_spec)


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_project(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    style_spec_markdown: str,
) -> int:
    """创建测试项目并返回 ID。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "status": "active",
            "style_spec_markdown": style_spec_markdown,
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def _build_tool_run_context(*, workspace_id: int, project_id: int) -> AgentToolContext:
    """构造项目样式读取工具需要的运行上下文和签名 token。"""

    current = _build_auth_context()
    run_id = "project-style-tool-run"
    session_id = "project-style-tool-session"
    dependencies = {
        "user_id": current.user.id,
        "agent_id": AGENT_COORDINATOR_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "page_id": None,
        "component_id": None,
        "source": "test",
        "backend_session_id": current.backend_session_id,
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=None,
        component_id=None,
        source="test",
        scopes=PROJECT_TOOL_READ_SCOPES,
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
