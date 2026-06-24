"""文件功能：验证智能体会话列表 exact 与 workspace 范围查询模式。"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentSession


async def test_ai_sessions_should_support_exact_and_workspace_scope_modes(authenticated_client: AsyncClient) -> None:
    """会话列表应默认精确匹配 scope，并可按工作空间返回同智能体全量会话。"""

    workspace_id = await _create_workspace(authenticated_client, "会话范围工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "会话范围项目")
    page_id = await _create_page(authenticated_client, workspace_id, project_id, "会话范围页面")
    other_workspace_id = await _create_workspace(authenticated_client, "其他会话范围工作空间")
    other_project_id = await _create_project(authenticated_client, other_workspace_id, "其他会话范围项目")

    project_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="项目会话",
        scope={
            "scope_type": "project",
            "workspace_id": workspace_id,
            "project_id": project_id,
            "source": "editor-agent-sidebar",
        },
    )
    page_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="页面会话",
        scope={
            "scope_type": "page",
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
    )
    deleted_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="已删除会话",
        scope={
            "scope_type": "project",
            "workspace_id": workspace_id,
            "project_id": project_id,
            "source": "editor-agent-sidebar",
        },
    )
    await _create_agent_session(
        authenticated_client,
        agent_id="component-manager",
        session_name="其他智能体会话",
        scope={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "source": "editor-component-library",
        },
    )
    await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="其他工作空间会话",
        scope={
            "scope_type": "project",
            "workspace_id": other_workspace_id,
            "project_id": other_project_id,
            "source": "editor-agent-sidebar",
        },
    )
    await _mark_session_deleted(deleted_session)

    exact_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "scope_type": "project",
            "source": "editor-agent-sidebar",
            "agent_id": "agent-coordinator",
        },
    )
    assert exact_response.status_code == 200
    assert {item["session_id"] for item in exact_response.json()} == {project_session}

    workspace_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "scope_type": "project",
            "source": "editor-agent-sidebar",
            "agent_id": "agent-coordinator",
            "scope_mode": "workspace",
        },
    )
    assert workspace_response.status_code == 200
    assert {item["session_id"] for item in workspace_response.json()} == {project_session, page_session}


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_project(client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回 ID。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_page(client: AsyncClient, workspace_id: int, project_id: int, title: str) -> int:
    """创建测试页面并返回 ID。"""

    response = await client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": "<template><div>测试页面</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_agent_session(
    client: AsyncClient,
    *,
    agent_id: str,
    session_name: str,
    scope: dict[str, object],
) -> str:
    """创建智能体会话并返回 session_id。"""

    llm_config_id = await _create_llm_config(client)
    response = await client.post(
        "/api/ai/sessions",
        json={
            "agent_id": agent_id,
            "session_name": session_name,
            "scope": scope,
            "llm_config_id": llm_config_id,
        },
    )
    assert response.status_code == 201
    return str(response.json()["session_id"])


async def _create_llm_config(client: AsyncClient) -> int:
    """创建会话列表测试使用的显式模型配置。"""

    response = await client.post(
        "/api/ai/llm-configs",
        json={
            "name": "会话列表测试模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-session-scope",
            "advanced_config_json": {},
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def _mark_session_deleted(session_id: str) -> None:
    """直接标记会话删除，用于验证列表过滤 deleted_at。"""

    async with get_session_factory()() as session:
        model = await session.get(AiAgentSession, session_id)
        assert model is not None
        model.deleted_at = datetime.now(UTC)
        await session.commit()
