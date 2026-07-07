"""文件功能：验证 AI 项目路由与页面列表工具的真实调用契约。"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import PROJECT_TOOL_READ_SCOPES, build_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.project.project_routes import build_list_project_pages_tool
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthContext


async def test_list_project_pages_tool_should_exclude_archived_pages(
    authenticated_client: AsyncClient,
) -> None:
    """项目页面列表工具只返回启用页面，并按过滤后的结果统计 total。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 路由页面过滤工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 路由页面过滤项目")
    active_page = await _create_page(authenticated_client, workspace_id, project_id, "启用页面", "active")
    archived_page = await _create_page(authenticated_client, workspace_id, project_id, "归档页面", "archived")
    tool = build_list_project_pages_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(workspace_id=workspace_id, project_id=project_id),
        limit=100,
    )

    returned_page_ids = [item["page_id"] for item in result["items"]]
    assert result["total"] == 1
    assert returned_page_ids == [active_page["id"]]
    assert archived_page["id"] not in returned_page_ids
    assert {item["status"] for item in result["items"]} == {"active"}


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回 ID。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_page(
    authenticated_client: AsyncClient,
    workspace_id: int,
    project_id: int,
    title: str,
    status: str,
) -> dict[str, Any]:
    """按指定状态创建测试页面。"""

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": f"<template><main>{title}</main></template>",
            "file_type": "vue",
            "status": status,
        },
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _build_tool_run_context(*, workspace_id: int, project_id: int) -> AgentToolContext:
    """构造项目读取工具需要的运行上下文和签名 token。"""

    current = _build_auth_context()
    run_id = "project-route-tool-run"
    session_id = "project-route-tool-session"
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
