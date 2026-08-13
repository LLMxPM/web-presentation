"""文件功能：验证智能体会话只按工作空间与智能体筛选，不再接受项目 scope。"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentSession


async def test_ai_sessions_should_list_workspace_sessions_only(authenticated_client: AsyncClient) -> None:
    """同一工作空间的内容助手会话统一展示，其他空间与归档会话不可见。"""

    workspace_id = await _create_workspace(authenticated_client, "会话范围工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "会话范围项目")
    await _create_page(authenticated_client, workspace_id, project_id, "会话范围页面")
    other_workspace_id = await _create_workspace(authenticated_client, "其他会话范围工作空间")
    await _create_project(authenticated_client, other_workspace_id, "其他会话范围项目")

    project_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="项目会话",
        workspace_id=workspace_id,
    )
    page_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="页面会话",
        workspace_id=workspace_id,
    )
    workspace_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="工作空间会话",
        workspace_id=workspace_id,
    )
    deleted_session = await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="已删除会话",
        workspace_id=workspace_id,
    )
    removed_agent_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "旧组件助手会话",
            "workspace_id": workspace_id,
        },
    )
    assert removed_agent_response.status_code == 404
    assert removed_agent_response.json()["code"] == "AI_AGENT_NOT_FOUND"
    await _create_agent_session(
        authenticated_client,
        agent_id="agent-coordinator",
        session_name="其他工作空间会话",
        workspace_id=other_workspace_id,
    )
    await _mark_session_deleted(deleted_session)

    workspace_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "agent_id": "agent-coordinator",
        },
    )
    assert workspace_response.status_code == 200
    assert {item["session_id"] for item in workspace_response.json()} == {workspace_session, project_session, page_session}


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
    workspace_id: int,
) -> str:
    """创建智能体会话并返回 session_id。"""

    llm_config_id = await _create_llm_config(client)
    response = await client.post(
        "/api/ai/sessions",
        json={
            "agent_id": agent_id,
            "session_name": session_name,
            "workspace_id": workspace_id,
            "llm_config_id": llm_config_id,
        },
    )
    assert response.status_code == 201
    return str(response.json()["session_id"])


async def _create_llm_config(client: AsyncClient) -> int:
    """创建会话列表测试使用的显式模型配置。"""

    provider_response = await client.post(
        "/api/ai/chat-provider-configs",
        json={
            "name": "会话列表测试供应商",
            "catalog_provider_key": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-session-scope",
        },
    )
    assert provider_response.status_code == 201
    provider_id = provider_response.json()["id"]

    response = await client.post(
        "/api/ai/chat-model-configs",
        json={
            "name": "会话列表测试模型",
            "provider_config_id": provider_id,
            "model_id": "gpt-4.1-mini",
            "capability_override": {"supports_tool_call": True},
            "advanced_config": {},
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
