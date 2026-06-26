"""文件功能：验证 AI 工作空间组件读取工具的返回契约。"""

from __future__ import annotations

import json

from httpx import AsyncClient

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import COMPONENT_TOOL_READ_SCOPES, build_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.workspace.components import (
    build_get_workspace_component_usage_tool,
    build_list_workspace_components_tool,
)
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthContext

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def test_workspace_component_tools_should_return_public_usage_contract(
    authenticated_client: AsyncClient,
) -> None:
    """组件读取工具应暴露类型和公开引用契约，不返回组件源码。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工作空间组件工具空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 工作空间组件工具项目")
    component = await _create_published_component(authenticated_client, workspace_id)
    await _save_project_suggested_components(authenticated_client, project_id, [component["id"]])

    current = _build_auth_context()
    run_context = _build_tool_run_context(current=current, workspace_id=workspace_id, project_id=project_id)
    list_tool = build_list_workspace_components_tool(get_session_factory())
    usage_tool = build_get_workspace_component_usage_tool(get_session_factory())

    list_result = await list_tool.entrypoint(run_context)
    item = list_result["items"][0]
    assert list_result["source"] == "project_suggested"
    assert item["component_code"] == component["code"]
    assert item["component_type"] == "内容组件"

    usage_result = await usage_tool.entrypoint(run_context, component_code=component["code"])
    assert usage_result["component_code"] == component["code"]
    assert usage_result["component_type"] == "内容组件"
    assert usage_result["current_version_no"] == component["current_version_no"]
    assert json.loads(usage_result["preview_schema"]) == json.loads(CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA)
    assert usage_result["import_path"] == (
        f"@workspace-components/{component['code']}/v/{component['current_version_no']}"
    )
    assert "content" not in usage_result


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回 ID。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_published_component(authenticated_client: AsyncClient, workspace_id: int) -> dict:
    """创建并发布一个内容组件，返回发布后的组件摘要。"""

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "AI 工具测试组件",
            "import_name": "AiToolTestBlock",
            "component_type": "内容组件",
            "summary": "用于验证 AI 工具返回契约。",
            "content": "<template><section>usage source should stay private</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200, create_response.text
    component = create_response.json()
    publish_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"release_name": None, "change_note": "测试发布"},
    )
    assert publish_response.status_code == 200, publish_response.text
    return publish_response.json()


async def _save_project_suggested_components(
    authenticated_client: AsyncClient,
    project_id: int,
    component_ids: list[int],
) -> None:
    """保存项目建议组件，供列表工具默认 suggested 范围读取。"""

    response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-components",
        json={"component_ids": component_ids},
    )
    assert response.status_code == 200, response.text


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


def _build_tool_run_context(
    *,
    current: AuthContext,
    workspace_id: int,
    project_id: int,
) -> AgentToolContext:
    """构造组件读取工具上下文，包含读权限 token。"""

    run_id = "workspace-component-tool-run"
    session_id = "workspace-component-tool-session"
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
        scopes=COMPONENT_TOOL_READ_SCOPES,
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id=str(current.user.id),
        dependencies=dependencies,
    )
