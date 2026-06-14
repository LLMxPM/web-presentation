"""文件功能：验证内容助手会话隔离、工具授权与 BFF pause/continue 代理行为。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from httpx import AsyncClient
from agno.db.base import SessionType
from agno.media import Image
from agno.models.message import Message
from agno.models.response import ToolExecution
from agno.run.agent import RunCompletedEvent, RunContentEvent, RunEvent, RunInput, RunOutput
from agno.run import RunContext
from agno.run.base import RunStatus
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunEvent, TeamRunInput, TeamRunOutput
from agno.session.agent import AgentSession
from agno.session.summary import SessionSummary
from agno.session.team import TeamSession
from agno.team import TeamMode
from agno.tools.function import FunctionCall
from agno.utils.events import create_tool_call_started_event

from app.ai.agent import (
    AGENT_COORDINATOR_AGENT_ID,
    AgentRuntimeContext,
    COMPONENT_MANAGER_AGENT_ID,
    RESOURCE_MANAGER_AGENT_ID,
    build_agent_coordinator_agent,
)
from app.ai.agent.component_manager import build_component_manager_agent
from app.ai.agent.resource_manager import build_resource_manager_agent
from app.ai.agent.runtime_context import build_scope_context_text
from app.ai.agent_factory import AIAgentFactory
from app.ai.auth_tokens import (
    COMPONENT_TOOL_DELETE_SCOPES,
    COMPONENT_TOOL_READ_SCOPES,
    COMPONENT_TOOL_WRITE_SCOPES,
    PAGE_TOOL_READ_SCOPES,
    PAGE_TOOL_WRITE_SCOPES,
    PROJECT_TOOL_READ_SCOPES,
    PROJECT_TOOL_WRITE_SCOPES,
    RESOURCE_TOOL_READ_SCOPES,
    RESOURCE_TOOL_WRITE_SCOPES,
    build_agent_access_token,
    build_agent_tool_token,
)
from app.ai.history_policy import build_history_policy
from app.ai.registry import AgentRegistry
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.session_facade import (
    AgentSessionFacade,
    _apply_user_feedback_selections,
    _build_run_requirement_from_tool_execution_payload,
    _extract_pending_requirement,
    _extract_tool_error_info,
    _iter_raw_sse_payloads,
    _prepare_team_run_output_for_agno_continue,
    _resolve_requirement_payload,
)
from app.ai.tools.component import build_component_manager_tools
from app.ai.tools.component.component_detail_prompt import build_component_detail_prompt
from app.ai.tools.disclosure import (
    build_unified_agent_tools,
    get_tool_group_definitions,
    resolve_unified_tool_scopes,
)
from app.ai.tools.page.get_page_content import (
    build_get_page_content_tool,
    build_page_content_prompt,
)
from app.ai.tools.page.apply_page_edits import build_apply_page_edits_tool
from app.ai.tools.project import build_project_tools
from app.ai.tools.resource import build_resource_manager_tools
from app.ai.tools.shared import calculate_source_hash
from app.ai.tools.shared.page_patch import apply_unified_diff, apply_unified_diff_with_repair
from app.ai.tools.workspace.assets.list_workspace_font_assets import build_list_workspace_font_assets_tool
from app.ai.tools.workspace.assets.list_workspace_render_assets import build_list_workspace_render_assets_tool
from app.ai.tools.workspace.components.get_workspace_component_usage import build_get_workspace_component_usage_tool
from app.ai.tools.workspace.components.list_workspace_components import build_list_workspace_components_tool
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.user import User
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.schemas.agent import AgentContextStatusItem, AgentPendingRequirement, AgentRunEvent, AgentScopeContext
from app.schemas.component import WorkspaceComponentItem
from app.schemas.page import PageItem
from app.services.auth_service import AuthContext
from app.services.token_service import TokenService

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def _async_value(value: object) -> object:
    """把普通值包装为异步返回值，便于替换服务方法。"""

    return value


def _patch_runtime_diagnostics(monkeypatch, *, success: bool = True) -> list[dict[str, object]]:
    """替换 Runtime 诊断调用，记录 apply 内置校验是否触发。"""

    calls: list[dict[str, object]] = []

    async def fake_dispatch(
        self,
        *,
        artifact_id: str,
        diagnostics_token: str,
        label: str | None = None,
    ) -> dict[str, object]:
        _ = self
        calls.append({"artifact_id": artifact_id, "diagnostics_token": diagnostics_token, "label": label})
        if success:
            return {
                "success": True,
                "status": "passed",
                "artifact_id": artifact_id,
                "summary": "代码检查通过。",
                "diagnostics": [],
            }
        return {
            "success": False,
            "status": "failed",
            "artifact_id": artifact_id,
            "summary": "发现 1 个错误。",
            "diagnostics": [
                {
                    "severity": "error",
                    "source": "runtime",
                    "code": "RUNTIME_TEST_FAILED",
                    "message": "测试诊断失败。",
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.runtime_diagnostics_client.RuntimeDiagnosticsClient.dispatch_artifact_diagnostics",
        fake_dispatch,
    )
    return calls


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建一个工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _build_empty_context_status(session_id: str, *, retained_recent_message_count: int = 0) -> AgentContextStatusItem:
    """构造 runtime snapshot 测试所需的最小上下文状态。"""

    return AgentContextStatusItem(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        compression_enabled=True,
        compression_required=False,
        summary_available=False,
        summary=None,
        topics=[],
        summary_updated_at=None,
        context_window_tokens=4096,
        max_output_tokens=1024,
        history_token_ratio=0.4,
        compression_target_ratio=0.1,
        safety_margin_tokens=256,
        current_input_tokens=0,
        fixed_context_tokens=0,
        history_budget_tokens=2048,
        compression_target_tokens=512,
        estimated_history_tokens=0,
        retained_recent_history_tokens=0,
        retained_recent_message_count=retained_recent_message_count,
    )


async def _create_project(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    page_width: int | None = None,
    page_height: int | None = None,
    base_font_size: str | None = None,
    icon_default_stroke_width: int | None = None,
    style_spec_markdown: str | None = None,
) -> int:
    """创建一个项目并返回主键。"""

    payload = {"workspace_id": workspace_id, "name": name, "status": "active"}
    if page_width is not None:
        payload["page_width"] = page_width
    if page_height is not None:
        payload["page_height"] = page_height
    if base_font_size is not None:
        payload["base_font_size"] = base_font_size
    if icon_default_stroke_width is not None:
        payload["icon_default_stroke_width"] = icon_default_stroke_width
    if style_spec_markdown is not None:
        payload["style_spec_markdown"] = style_spec_markdown
    response = await authenticated_client.post(
        "/api/projects",
        json=payload,
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_page(
    authenticated_client: AsyncClient,
    *,
    workspace_id: int,
    project_id: int,
    title: str,
    content: str,
) -> int:
    """创建一个页面并返回主键。"""

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": content,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def _build_page_item(*, page_id: int, content: str, speaker_notes: str | None = None) -> PageItem:
    """构造测试所需的最小页面对象，供暂停需求解析单测复用。"""

    now = datetime.now(tz=UTC)
    return PageItem(
        id=page_id,
        code=f"PG{page_id}",
        page_content=content,
        current_version_no=1,
        file_type=PageFileType.VUE,
        title="测试页面",
        summary=None,
        speaker_notes=speaker_notes,
        status=RecordStatus.ACTIVE,
        workspace_id=1,
        project_id=1,
        created_at=now,
        updated_at=now,
        created_by=1,
        updated_by=1,
    )


def _build_component_item(*, component_id: int, content: str) -> WorkspaceComponentItem:
    """构造测试所需的最小组件对象，供组件详情提示渲染单测复用。"""

    now = datetime.now(tz=UTC)
    return WorkspaceComponentItem(
        id=component_id,
        workspace_id=1,
        workspace_name=None,
        code=f"CMP{component_id}",
        content=content,
        preview_schema=None,
        current_version_no=0,
        draft_base_version_no=0,
        has_unpublished_changes=True,
        published_at=None,
        file_type=PageFileType.VUE,
        name="测试组件",
        import_name="TestComponent",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        summary=None,
        status=RecordStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        created_by=1,
        updated_by=1,
    )


def _build_auth_context() -> AuthContext:
    """构造工具调用测试使用的管理员上下文。"""

    return AuthContext(
        user=User(
            id=1,
            username="admin",
            password_hash="fake",
            display_name="平台系统管理员",
            status="active",
        ),
        session_token="session-token",
        backend_session_id="42",
    )


async def _build_tool_run_context(
    *,
    current: AuthContext,
    tool_scopes: tuple[str, ...],
    workspace_id: int,
    project_id: int | None = None,
    page_id: int | None = None,
    component_id: int | None = None,
) -> RunContext:
    """构造带签名工具 token 授权的 Agno RunContext。"""

    source = "editor-agent-sidebar"
    run_id = f"run-tool-test-{uuid4()}"
    session_id = f"session-tool-test-{uuid4()}"
    scope_type = "component" if component_id is not None else "page" if page_id is not None else "project" if project_id is not None else "workspace"
    tool_token = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        source=source,
        scopes=tool_scopes,
    )
    return RunContext(
        run_id=run_id,
        session_id=session_id,
        dependencies={
            "run_id": run_id,
            "session_id": session_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "user_id": current.user.id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "component_id": component_id,
            "backend_session_id": current.backend_session_id,
            "role": "admin",
            "source": source,
            "scope_type": scope_type,
            "tool_auth_token": tool_token,
            "tool_scopes": list(tool_scopes),
        },
    )


def _find_tool(tools, name: str):  # type: ignore[no-untyped-def]
    """按工具名从 Agno Function 列表中取出工具。"""

    return next(tool for tool in tools if tool.name == name)


async def test_agent_token_should_embed_audience_and_scope() -> None:
    """Agent Token 应包含约定 audience 和运行范围，不再携带工具访问令牌。"""

    fake_user = User(
        id=1,
        username="admin",
        password_hash="fake",
        display_name="平台系统管理员",
        status="active",
    )
    current = AuthContext(
        user=fake_user,
        session_token="session-token",
        backend_session_id="42",
    )

    agent_access_token = build_agent_access_token(
        current,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        session_id="session-1",
        workspace_id=11,
        project_id=21,
        page_id=31,
        role="admin",
    )
    agent_claims = TokenService.verify_signed_token(agent_access_token, audience="backend-agentos")
    assert "tool_access_token" not in agent_claims
    assert agent_claims["page_id"] == 31
    assert f"agents:{AGENT_COORDINATOR_AGENT_ID}:run" in agent_claims["scopes"]


async def test_agent_registry_should_expose_coordinator_and_component_manager() -> None:
    """Agent 注册表应暴露统一智能体和组件助手入口。"""

    registry = AgentRegistry(AIAgentFactory(agno_db=None, session_factory=None))
    descriptors = {item.id: item for item in registry.list_descriptors()}

    assert list(descriptors) == [AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID]
    assert len({descriptor.icon for descriptor in descriptors.values()}) == 3
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].icon == "content-spark"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].entry_kind == "team"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].llm_slot == "agent_coordinator"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].scope_type == "workspace"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].icon == "component-blocks"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].entry_kind == "agent"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].llm_slot == "component_manager"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].scope_type == "workspace"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].icon == "resource-images"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].entry_kind == "agent"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].llm_slot == "resource_manager"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].scope_type == "workspace"


async def test_agent_coordinator_availability_should_require_project_scope(authenticated_client: AsyncClient) -> None:
    """内容助手只能在具体项目范围启动，工作空间范围仅保留其他专长助手。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 内容助手项目限制工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 内容助手项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 内容助手页面",
        content="<template><div>content agent</div></template>",
    )

    workspace_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "scope_type": "workspace"},
    )
    assert workspace_agents_response.status_code == 200
    workspace_agents = {item["id"]: item for item in workspace_agents_response.json()}
    assert workspace_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is False
    assert workspace_agents[AGENT_COORDINATOR_AGENT_ID]["unavailable_reason"] == "内容助手需要进入具体项目后才能启动。"
    assert workspace_agents[COMPONENT_MANAGER_AGENT_ID]["available"] is True
    assert workspace_agents[RESOURCE_MANAGER_AGENT_ID]["available"] is True

    project_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project"},
    )
    assert project_agents_response.status_code == 200
    project_agents = {item["id"]: item for item in project_agents_response.json()}
    assert project_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is True

    page_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "project_id": project_id, "page_id": page_id, "scope_type": "page"},
    )
    assert page_agents_response.status_code == 200
    page_agents = {item["id"]: item for item in page_agents_response.json()}
    assert page_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is True

    workspace_session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "工作空间内容助手会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert workspace_session_response.status_code == 409
    assert workspace_session_response.json()["code"] == "AI_AGENT_SCOPE_UNAVAILABLE"

    project_session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "项目内容助手会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert project_session_response.status_code == 201


async def test_tool_run_task_auth_should_refresh_window_and_reject_invalid_scope(
    authenticated_client: AsyncClient,
) -> None:
    """工具授权应来自 run task，成功校验后刷新短租约并拒绝缺失 scope。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth",
            session_id="session-tool-auth",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权测试",
            tool_scopes=COMPONENT_TOOL_DELETE_SCOPES,
        )
        original_expiry = task.tool_auth_expires_at
        original_max_expiry = task.tool_auth_max_expires_at
        await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={"tool_auth_expires_at": datetime.now(UTC) + timedelta(seconds=1)},
        )

        context, claims = await service.authorize_tool_call(
            run_id="run-tool-auth",
            user_id=current.user.id,
            session_id="session-tool-auth",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            backend_session_id=current.backend_session_id,
            source="editor-agent-sidebar",
            required_scopes=COMPONENT_TOOL_DELETE_SCOPES,
        )
        assert context["workspace_id"] == workspace_id
        assert claims["sub"] == f"user:{current.user.id}"
        refreshed_task = await service.get_task_by_run(run_id=task.run_id, user_id=current.user.id)
        assert refreshed_task is not None
        assert refreshed_task.tool_auth_expires_at is not None
        assert original_expiry is not None
        assert refreshed_task.tool_auth_expires_at > original_expiry - timedelta(seconds=5)
        assert refreshed_task.tool_auth_max_expires_at == original_max_expiry

        try:
            await service.authorize_tool_call(
                run_id="run-tool-auth",
                user_id=current.user.id,
                session_id="session-tool-auth",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                backend_session_id=current.backend_session_id,
                source="editor-agent-sidebar",
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_SCOPE_DENIED"
        else:
            raise AssertionError("缺少工具 scope 时应拒绝调用。")


async def test_tool_run_task_auth_should_reject_expired_and_mismatched_context(
    authenticated_client: AsyncClient,
) -> None:
    """工具授权应拒绝过期授权、终态任务和上下文不匹配。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权拒绝工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-reject",
            session_id="session-tool-auth-reject",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权拒绝测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )

        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source="other-source",
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_CONTEXT_MISMATCH"
        else:
            raise AssertionError("source 不匹配时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={"tool_auth_expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        )
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_AUTH_EXPIRED"
        else:
            raise AssertionError("短租约过期时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "tool_auth_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "tool_auth_max_expires_at": datetime.now(UTC) - timedelta(seconds=1),
            },
        )
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_AUTH_EXPIRED"
        else:
            raise AssertionError("绝对上限过期时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "tool_auth_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "tool_auth_max_expires_at": datetime.now(UTC) + timedelta(minutes=10),
            },
        )
        await service.mark_terminal(task=task, status="completed", content="done")
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_RUN_INACTIVE"
        else:
            raise AssertionError("终态任务不应允许工具调用。")


async def test_tool_auth_should_reset_window_when_paused_run_continues(
    authenticated_client: AsyncClient,
) -> None:
    """继续 paused run 时应从当前时间重开工具授权窗口和绝对上限。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权继续工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-continue",
            session_id="session-tool-auth-continue",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权继续测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        expired_at = datetime.now(UTC) - timedelta(hours=1)
        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "status": "paused",
                "tool_auth_expires_at": expired_at,
                "tool_auth_max_expires_at": expired_at,
            },
        )

        continued_at = datetime.now(UTC)
        task = await service.mark_running(task=task, reset_tool_auth=True)

        assert task.status == "running"
        assert task.tool_auth_expires_at is not None
        assert task.tool_auth_max_expires_at is not None
        refreshed_expires_at = task.tool_auth_expires_at
        if refreshed_expires_at.tzinfo is None:
            refreshed_expires_at = refreshed_expires_at.replace(tzinfo=UTC)
        assert refreshed_expires_at > continued_at
        assert task.tool_auth_max_expires_at > task.tool_auth_expires_at

        context, _ = await service.authorize_tool_call(
            run_id=task.run_id,
            user_id=current.user.id,
            session_id=task.session_id,
            agent_id=task.agent_id,
            backend_session_id=current.backend_session_id,
            source=task.source,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        assert context["workspace_id"] == workspace_id


async def test_replayed_pause_event_after_continue_should_not_disable_tool_auth(
    authenticated_client: AsyncClient,
) -> None:
    """继续 paused run 后，旧 pause 事件回放不应把 task 再次写回暂停态。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 继续回放 Pause 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 继续回放 Pause 项目")
    current = _build_auth_context()
    run_id = "run-tool-auth-replayed-pause"
    session_id = "session-tool-auth-replayed-pause"
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-route-confirm-continue",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="editor-page-detail",
            ),
            input_summary="继续后回放 pause 测试",
            tool_scopes=(*PROJECT_TOOL_READ_SCOPES, *PROJECT_TOOL_WRITE_SCOPES),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id),
        )
        await service.mark_paused(task=task, pending_requirement=requirement)
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="context.status", run_id=run_id, session_id=session_id, data={}),
        )
        task = await service.mark_running(task=task, reset_tool_auth=True)

        replayed = await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.paused",
                run_id=run_id,
                session_id=session_id,
                data={"requirement": requirement.model_dump(mode="json")},
            ),
        )
        task = await service.get_task_by_run(run_id=run_id, user_id=current.user.id)
        assert task is not None

        assert replayed is None
        assert task.status == "running"
        assert task.pending_requirement_json is None
        context, _ = await service.authorize_tool_call(
            run_id=run_id,
            user_id=current.user.id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            backend_session_id=current.backend_session_id,
            source="editor-page-detail",
            required_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        assert context["project_id"] == project_id
        events = await service.list_events_after(
            run_id=run_id,
            user_id=current.user.id,
            after_sequence=0,
        )

    assert [event.event for event in events] == ["run.started", "run.paused", "context.status"]


async def test_continue_non_paused_run_should_not_reset_tool_auth(
    authenticated_client: AsyncClient,
) -> None:
    """非 paused run 调 continue 应保持原错误，并且不能重置工具授权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 非暂停继续授权工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-non-paused",
            session_id="session-tool-auth-non-paused",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="非暂停继续授权测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        original_expiry = task.tool_auth_expires_at
        original_max_expiry = task.tool_auth_max_expires_at

    response = await authenticated_client.post(
        f"/api/ai/runs/{task.run_id}/continue",
        json={"tool_execution": {}},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "AI_SESSION_RUN_NOT_PAUSED"
    async with get_session_factory()() as session:
        persisted = await AiAgentRunService(session).get_task_by_run(run_id=task.run_id, user_id=current.user.id)
    assert persisted is not None
    assert persisted.status == "pending"
    assert persisted.tool_auth_expires_at == original_expiry
    assert persisted.tool_auth_max_expires_at == original_max_expiry


async def test_component_and_coordinator_agents_should_register_expected_tools() -> None:
    """当前开放 Agent 应注册组件管理工具与内容助手当前路由业务工具。"""

    component_agent = build_component_manager_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )
    component_tools = {tool.name: tool for tool in component_agent.tools}
    assert component_agent.store_events is True
    assert component_agent.events_to_skip == [RunEvent.run_content]
    assert "list_runtime_kit_capabilities" in component_tools
    assert "get_runtime_kit_capability" in component_tools
    assert "list_resource_assets" in component_tools
    assert "get_resource_asset_content" in component_tools
    assert "list_resource_tags" in component_tools
    assert "create_component_draft" not in component_tools
    assert "preview_component_edits" not in component_tools
    assert component_tools["create_component"].requires_confirmation is False
    assert component_tools["apply_component_edits"].requires_confirmation is False
    assert component_tools["update_component_metadata"].requires_confirmation is False
    assert component_tools["publish_component"].requires_confirmation is False
    assert component_tools["delete_component"].requires_confirmation is True
    component_instruction_text = "\n".join(component_agent.instructions)
    assert "封装 Runtime Kit 能力" in component_instruction_text
    assert "主题 Tailwind 样式" in component_instruction_text
    assert "内容助手复用" in component_instruction_text
    assert "font-heading" in component_instruction_text
    assert "bg-background" in component_instruction_text
    assert "primary、secondary、invert" in component_instruction_text
    assert "link、link-hover、link-visited" in component_instruction_text
    assert "ThemeLogo 组件" in component_instruction_text
    assert "themeLogo、themeInvertLogo、themeStyles" in component_instruction_text
    assert "不要硬编码主题 Logo 路径" in component_instruction_text

    coordinator = build_agent_coordinator_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )
    assert coordinator.mode == TeamMode.coordinate
    assert coordinator.store_events is True
    assert coordinator.events_to_skip == [
        RunEvent.run_content,
        TeamRunEvent.run_content,
        TeamRunEvent.run_intermediate_content,
    ]
    assert {member.id for member in coordinator.members} == {COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID}
    assert all(member.store_events is True for member in coordinator.members)
    assert all(member.events_to_skip == [RunEvent.run_content] for member in coordinator.members)
    coordinator_tools = {tool.name: tool for tool in coordinator.tools}
    coordinator_tool_names = set(coordinator_tools)
    assert "get_page_content" in coordinator_tool_names
    assert "list_workspace_styles" not in coordinator_tool_names
    assert "get_workspace_style" not in coordinator_tool_names
    assert "get_project_style_config" in coordinator_tool_names
    assert coordinator_tools["update_project_style_config"].requires_confirmation is True
    assert "list_workspace_components" in coordinator_tool_names
    assert "get_workspace_component_usage" in coordinator_tool_names
    assert "list_resource_assets" in coordinator_tool_names
    assert "get_resource_asset_content" in coordinator_tool_names
    assert "list_resource_tags" in coordinator_tool_names
    assert "list_components" not in coordinator_tool_names
    assert "get_component_detail" not in coordinator_tool_names
    assert "list_component_versions" not in coordinator_tool_names
    assert "get_component_dependencies" not in coordinator_tool_names
    assert "list_runtime_kit_capabilities" in coordinator_tool_names
    assert "get_runtime_kit_capability" in coordinator_tool_names
    assert "create_component" not in coordinator_tool_names
    assert "apply_component_edits" not in coordinator_tool_names
    assert "publish_component" not in coordinator_tool_names
    assert "delete_component" not in coordinator_tool_names
    assert "create_resource_asset" not in coordinator_tool_names
    assert "apply_resource_content_diff" not in coordinator_tool_names
    assert "archive_resource_asset" not in coordinator_tool_names
    assert "request_tool_disclosure" not in coordinator_tool_names
    coordinator_instruction_text = "\n".join(coordinator.instructions)
    assert "主执行助手" in coordinator_instruction_text
    assert "不要为了形式化协作而委派" in coordinator_instruction_text
    assert "Runtime Kit 能力事实、已发布组件用法和资源读取由你直接查询" in coordinator_instruction_text
    assert "font-heading、font-body、font-code" in coordinator_instruction_text
    assert "bg-background" in coordinator_instruction_text
    assert "accent1 到 accent6" in coordinator_instruction_text
    assert "primary、secondary、invert" in coordinator_instruction_text
    assert "link、link-hover、link-visited" in coordinator_instruction_text
    assert "ThemeLogo 组件" in coordinator_instruction_text
    assert "themeLogo、themeInvertLogo、themeStyles" in coordinator_instruction_text
    assert "不要硬编码主题 Logo 路径" in coordinator_instruction_text
    assert "公开 import_path" in coordinator_instruction_text
    assert "@runtime-kit/components/" not in coordinator_instruction_text
    assert "AssetRenderer" not in coordinator_instruction_text
    assert "DefaultCoverPage" not in coordinator_instruction_text
    assert "DefaultContentPage" not in coordinator_instruction_text

    resource_agent = build_resource_manager_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-asset-library",
        ),
    )
    resource_tools = {tool.name: tool for tool in resource_agent.tools}
    assert resource_agent.store_events is True
    assert resource_agent.events_to_skip == [RunEvent.run_content]
    assert "list_resource_assets" in resource_tools
    assert "preview_resource_references" not in resource_tools
    assert "create_resource_asset" in resource_tools
    assert "archive_resource_asset" in resource_tools
    assert "delete_resource_asset" not in resource_tools
    assert resource_tools["create_resource_asset"].requires_confirmation is False
    assert resource_tools["apply_resource_content_diff"].requires_confirmation is False
    assert resource_tools["archive_resource_asset"].requires_confirmation is False
    assert any("资源库" in instruction for instruction in resource_agent.instructions)


async def test_resource_list_tool_should_return_active_non_history_assets_by_tag(
    authenticated_client: AsyncClient,
) -> None:
    """资源列表工具应只给 LLM 返回 active 非历史资源摘要，并支持标签过滤。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源列表过滤工作空间")
    create_brand_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "brand_icon",
            "original_name": "brand_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "description": "品牌主 Logo，用于封面页。",
            "tags": ["品牌", "首页"],
        },
    )
    assert create_brand_response.status_code == 200
    brand_asset_id = create_brand_response.json()["id"]

    create_other_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "other_icon",
            "original_name": "other_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2"/></svg>',
            "description": "非品牌图标。",
            "tags": ["其他"],
        },
    )
    assert create_other_response.status_code == 200

    update_brand_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{brand_asset_id}/content",
        json={
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3 3"/></svg>',
            "change_note": "生成历史副本",
        },
    )
    assert update_brand_response.status_code == 200

    create_archived_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "archived_icon",
            "original_name": "archived_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 4"/></svg>',
            "description": "已归档品牌图标。",
            "tags": ["品牌"],
        },
    )
    assert create_archived_response.status_code == 200
    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{create_archived_response.json()['id']}/archive",
        json={"archive_reason": "测试归档"},
    )
    assert archive_response.status_code == 200

    list_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "list_resource_assets")
    parameters = list_tool.parameters["properties"]
    assert "tag" in parameters
    assert "status" not in parameters
    assert "include_history" not in parameters
    assert "history_only" not in parameters

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    result = await list_tool.entrypoint(run_context, tag="品牌", limit=10)

    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == brand_asset_id
    assert item["description"] == "品牌主 Logo，用于封面页。"
    assert item["tags"] == ["品牌", "首页"]
    assert "url" not in item
    assert "status" not in item
    assert "source_asset_id" not in item
    assert "history_kind" not in item


async def test_resource_create_tool_should_support_svg_image_asset(
    authenticated_client: AsyncClient,
) -> None:
    """资源助手创建工具应能把非图标 SVG 保存为 image 内容资源。"""

    workspace_id = await _create_workspace(authenticated_client, "AI SVG 图片资源工作空间")
    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await create_tool.entrypoint(
        run_context,
        asset_type="image",
        name="hero_illustration",
        original_name="illustration.svg",
        content='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><rect width="960" height="540" fill="#f8fafc"/></svg>',
        description="资源助手生成的封面 SVG 图片。",
        tags=["AI", "插画"],
    )

    assert result["success"] is True
    asset = result["asset"]
    assert asset["asset_type"] == "image"
    assert asset["asset_role"] == "content"
    assert asset["render_type"] == "image"
    assert asset["original_name"] == "illustration.svg"
    assert asset["content_editable"] is True
    assert asset["analysis_metadata"] is None


def test_resource_create_tool_should_repair_stringified_tags_before_validation() -> None:
    """资源创建工具应在校验前修复模型把 tags 数组二次编码成字符串的参数。"""

    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    tags_schema = create_tool.parameters["properties"]["tags"]
    assert tags_schema["anyOf"][0]["type"] == "array"

    function_call = FunctionCall(
        function=create_tool,
        arguments={"tags": '["物理学", "电磁学", "麦克斯韦方程组", "物理学"]'},
    )
    assert create_tool.pre_hook is not None
    create_tool.pre_hook(fc=function_call)

    assert function_call.arguments == {"tags": ["物理学", "电磁学", "麦克斯韦方程组"]}


async def test_resource_member_write_tool_should_accept_member_token_from_coordinator_run(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """内容助手委派资源助手时，资源写入工具应能使用成员助手 token 授权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源成员授权工作空间")
    now = datetime.now(UTC)

    async def fake_create_content_asset(self, workspace_id: int, **kwargs):  # type: ignore[no-untyped-def]
        """替换真实对象存储写入，只保留工具授权链路验证。"""

        asset_type = str(getattr(kwargs["asset_type"], "value", kwargs["asset_type"]))
        content = str(kwargs["content"])
        return SimpleNamespace(
            id=801,
            workspace_id=workspace_id,
            name=kwargs["name"],
            file_name="mass-energy-equation.tex",
            original_name=kwargs["original_name"],
            description=kwargs.get("description"),
            file_size=len(content.encode("utf-8")),
            file_hash="fake-formula-hash",
            content_type="text/plain",
            asset_type=asset_type,
            tags=kwargs.get("tags") or [],
            analysis_metadata=None,
            render_metadata=None,
            status=RecordStatus.ACTIVE.value,
            archived_at=None,
            archive_reason=None,
            source_asset_id=None,
            history_kind=None,
            font_config=None,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr("app.services.asset_service.AssetService.create_content_asset", fake_create_content_asset)
    current = _build_auth_context()
    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    run_context = await _build_tool_run_context(
        current=current,
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    dependencies = run_context.dependencies
    assert dependencies is not None
    member_scopes = AgentSessionFacade._resolve_tool_scopes(agent_id=RESOURCE_MANAGER_AGENT_ID)
    dependencies["member_tool_auth_tokens"] = {
        RESOURCE_MANAGER_AGENT_ID: build_agent_tool_token(
            current,
            run_id=dependencies["run_id"],
            session_id=dependencies["session_id"],
            agent_id=RESOURCE_MANAGER_AGENT_ID,
            workspace_id=workspace_id,
            project_id=None,
            page_id=None,
            component_id=None,
            source=dependencies["source"],
            scopes=member_scopes,
        )
    }
    dependencies["member_tool_scopes"] = {RESOURCE_MANAGER_AGENT_ID: list(member_scopes)}

    result = await create_tool.entrypoint(
        run_context,
        asset_type="formula",
        name="mass-energy-equation",
        original_name="mass-energy-equation.tex",
        content="\\[ E = mc^{2} \\]",
        description="爱因斯坦质能方程，揭示质量与能量的等价关系",
        tags=["physics", "relativity", "einstein"],
    )

    assert result["success"] is True
    asset = result["asset"]
    assert asset["asset_type"] == "formula"
    assert asset["original_name"] == "mass-energy-equation.tex"


async def test_workspace_component_usage_tools_should_not_require_page_scope(
    authenticated_client: AsyncClient,
) -> None:
    """工作空间组件查询和用法工具只应依赖 workspace_id，不要求当前页面上下文。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件用法工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "营销卡片",
            "import_name": "MarketingCard",
            "content": "<template><section>Card</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    publish_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"release_name": None, "change_note": "发布测试版本"},
    )
    assert publish_response.status_code == 200
    published_component = publish_response.json()

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        page_id=None,
    )
    list_tool = build_list_workspace_components_tool(get_session_factory())
    usage_tool = build_get_workspace_component_usage_tool(get_session_factory())

    list_result = await list_tool.entrypoint(run_context, limit=10)
    usage_result = await usage_tool.entrypoint(run_context, component_code=published_component["code"])

    assert list_result == {
        "source": "workspace_all",
        "fallback_reason": "no_project_context",
        "total": 1,
        "items": [
            {
                "name": "营销卡片",
                "import_name": "MarketingCard",
                "description": None,
                "component_code": published_component["code"],
                "current_version_no": 1,
            }
        ],
    }
    assert usage_result["component_code"] == published_component["code"]
    assert usage_result["import_path"] == f"@workspace-components/{published_component['code']}/v/1"


async def test_workspace_component_list_tool_should_default_to_project_suggested_components(
    authenticated_client: AsyncClient,
) -> None:
    """内容助手组件列表工具默认应优先返回项目建议组件，并在为空时回退全库。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议组件空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议组件项目")
    suggested_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "推荐指标卡",
            "import_name": "SuggestedMetricCard",
            "content": "<template><section>Suggested</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert suggested_response.status_code == 200
    suggested_publish_response = await authenticated_client.post(
        f"/api/components/{suggested_response.json()['id']}/publish",
        json={"release_name": None, "change_note": "发布建议组件"},
    )
    assert suggested_publish_response.status_code == 200
    suggested_component = suggested_publish_response.json()
    general_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "全库图表",
            "import_name": "GeneralChartBlock",
            "content": "<template><section>General</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert general_response.status_code == 200
    general_publish_response = await authenticated_client.post(
        f"/api/components/{general_response.json()['id']}/publish",
        json={"release_name": None, "change_note": "发布全库组件"},
    )
    assert general_publish_response.status_code == 200
    general_component = general_publish_response.json()
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-components",
        json={"component_ids": [suggested_component["id"]]},
    )
    assert save_response.status_code == 200

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    list_tool = build_list_workspace_components_tool(get_session_factory())

    suggested_result = await list_tool.entrypoint(run_context, limit=10)
    fallback_result = await list_tool.entrypoint(run_context, keyword="全库", limit=10)
    all_result = await list_tool.entrypoint(run_context, scope="all", limit=10)

    assert suggested_result["source"] == "project_suggested"
    assert suggested_result["fallback_reason"] is None
    assert [item["component_code"] for item in suggested_result["items"]] == [suggested_component["code"]]
    assert fallback_result["source"] == "workspace_all"
    assert fallback_result["fallback_reason"] == "suggested_filter_empty"
    assert [item["component_code"] for item in fallback_result["items"]] == [general_component["code"]]
    assert all_result["source"] == "workspace_all"
    assert all_result["fallback_reason"] is None
    assert {item["component_code"] for item in all_result["items"]} == {
        suggested_component["code"],
        general_component["code"],
    }


async def test_workspace_render_assets_tool_should_include_video_assets(
    authenticated_client: AsyncClient,
) -> None:
    """页面资源查询工具应把视频作为可渲染内容资源返回。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 视频资源工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 视频资源项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 视频资源页面",
        content="<template><div>video</div></template>",
    )
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("intro.mp4", b"fake-intro-video", "video/mp4")},
        data={"asset_type": "video", "tags": '["演示"]', "name": "intro_video"},
    )
    assert upload_response.status_code == 200

    list_tool = build_list_workspace_render_assets_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )
    result = await list_tool.entrypoint(run_context, render_type="video", limit=10)

    assert result == [
        {
            "name": "intro_video",
            "extension": "mp4",
            "type": "video",
            "description": None,
        }
    ]


def test_coordinator_should_expose_component_resource_and_runtime_kit_read_tools() -> None:
    """内容助手直接工具应暴露组件、资源和 Runtime Kit 只读查询能力。"""

    definitions = get_tool_group_definitions(session_factory=get_session_factory())
    assert "content_read" in definitions
    content_read_tools = set(definitions["content_read"].tool_keys)
    assert {
        "get_page_content",
        "get_project_style_config",
        "list_project_pages",
        "get_project_route_tree",
        "preview_project_route_tree",
    } <= content_read_tools
    component_read_tools = set(definitions["component_read"].tool_keys)
    assert component_read_tools == {"list_workspace_components", "get_workspace_component_usage"}
    runtime_kit_tools = set(definitions["runtime_kit"].tool_keys)
    assert runtime_kit_tools == {"list_runtime_kit_capabilities", "get_runtime_kit_capability"}
    resource_read_tools = set(definitions["resource_read"].tool_keys)
    assert resource_read_tools == {"list_resource_assets", "get_resource_asset_content", "list_resource_tags"}
    assert "list_workspace_render_assets" not in content_read_tools
    assert "list_workspace_icon_assets" not in content_read_tools
    assert "list_workspace_font_assets" not in content_read_tools
    assert "list_components" not in component_read_tools
    assert "get_component_detail" not in component_read_tools
    assert "list_component_versions" not in component_read_tools
    assert "get_component_dependencies" not in component_read_tools
    assert "component_write" not in definitions
    assert "resource_write" not in definitions

    coordinator_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
    )
    assert COMPONENT_TOOL_READ_SCOPES[0] in coordinator_scopes
    assert RESOURCE_TOOL_READ_SCOPES[0] in coordinator_scopes
    assert COMPONENT_TOOL_WRITE_SCOPES[0] not in coordinator_scopes
    assert COMPONENT_TOOL_DELETE_SCOPES[0] not in coordinator_scopes
    assert RESOURCE_TOOL_WRITE_SCOPES[0] not in coordinator_scopes


async def test_coordinator_runtime_kit_tools_should_query_agent_capabilities(
    authenticated_client: AsyncClient,
) -> None:
    """内容助手应能直接查询开放给 Agent 的 Runtime Kit 能力。"""

    workspace_id = await _create_workspace(authenticated_client, "内容助手 Runtime Kit 工作空间")
    tools = build_unified_agent_tools(session_factory=get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    list_tool = _find_tool(tools, "list_runtime_kit_capabilities")
    listed = await list_tool.entrypoint(run_context, keyword="page", limit=100)
    names = {item["name"] for item in listed["items"]}
    assert "usePageSize.v1" in names

    detail_tool = _find_tool(tools, "get_runtime_kit_capability")
    detail = await detail_tool.entrypoint(run_context, name="DefaultContainer.v1", kind="component")
    assert detail["import_path"] == "@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue"
    assert "agent" in detail["audiences"]

    asset_image_detail = await detail_tool.entrypoint(run_context, name="AssetImage", kind="component")
    assert asset_image_detail["name"] == "AssetImage.v1"
    assert asset_image_detail["import_path"] == "@runtime-kit/public/components/assets/AssetImage.v1.vue"
    asset_image_text = json.dumps(asset_image_detail, ensure_ascii=False)
    assert "外层图片框" in asset_image_text
    assert "fit 控制 object-fit" in asset_image_text


def test_component_manager_should_receive_component_write_tool_scopes() -> None:
    """组件助手应固定获得组件读写删除、资源读取和代码检查工具权限。"""

    component_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        enabled_tool_groups=(),
    )
    assert COMPONENT_TOOL_READ_SCOPES[0] in component_scopes
    assert COMPONENT_TOOL_WRITE_SCOPES[0] in component_scopes
    assert COMPONENT_TOOL_DELETE_SCOPES[0] in component_scopes
    assert RESOURCE_TOOL_READ_SCOPES[0] in component_scopes


def test_ai_session_scope_should_use_hierarchical_route_containment() -> None:
    """session scope 应按 workspace/project/page/component 层级判断当前路由是否可运行。"""

    page_route_scope = AgentScopeContext(
        scope_type="page",
        workspace_id=11,
        project_id=21,
        page_id=31,
        source="editor-page-detail",
    )
    component_route_scope = AgentScopeContext(
        scope_type="component",
        workspace_id=11,
        component_id=91,
        source="editor-component-library",
    )

    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "workspace", "workspace_id": 11},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "project", "workspace_id": 11, "project_id": 21},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "page", "workspace_id": 11, "project_id": 21, "page_id": 31},
        page_route_scope,
    )
    assert not AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "page", "workspace_id": 11, "project_id": 21, "page_id": 32},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "component", "workspace_id": 11, "component_id": 91},
        component_route_scope,
    )
    assert not AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "component", "workspace_id": 11, "component_id": 92},
        component_route_scope,
    )


def test_ai_run_scope_should_prefer_run_metadata_over_session_scope() -> None:
    """继续 paused run 时应优先使用 run 创建时记录的运行上下文。"""

    run = RunOutput(
        run_id="run-original-scope",
        session_id="session-project",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        status=RunStatus.paused,
        metadata={
            "run_scope": {
                "scope_type": "page",
                "workspace_id": 11,
                "project_id": 21,
                "page_id": 31,
                "source": "editor-page-detail",
            },
        },
    )

    resolved_scope = AgentSessionFacade._resolve_run_scope(
        run,
        fallback_metadata={"scope_type": "project", "workspace_id": 11, "project_id": 21},
    )

    assert resolved_scope is not None
    assert resolved_scope.scope_type == "page"
    assert resolved_scope.page_id == 31


async def test_project_page_tools_should_create_and_update_metadata(authenticated_client: AsyncClient) -> None:
    """项目页面工具应能创建页面并维护页面名称与说明。"""

    workspace_id = await _create_workspace(authenticated_client, "项目页面工具工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "项目页面工具项目")
    tools = build_project_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    create_tool = _find_tool(tools, "create_project_page")
    page_content = "<template>\n  <main>占位页面</main>\n</template>\n"
    created = await create_tool.entrypoint(
        run_context,
        title="新建页面",
        summary="用于后续细化的占位页面",
        speaker_notes="创建时的演讲备注",
        page_content=page_content,
    )
    assert created["success"] is True
    assert created["title"] == "新建页面"
    assert created["speaker_notes"] == "创建时的演讲备注"
    assert created["project_id"] == project_id

    get_response = await authenticated_client.get(f"/api/pages/{created['page_id']}")
    assert get_response.status_code == 200
    page_payload = get_response.json()
    assert page_payload["page_content"] == page_content
    assert page_payload["summary"] == "用于后续细化的占位页面"
    assert page_payload["speaker_notes"] == "创建时的演讲备注"

    update_tool = _find_tool(tools, "update_page_metadata")
    updated = await update_tool.entrypoint(
        run_context,
        page_id=created["page_id"],
        title="更新后的页面",
        summary="",
        change_note="更新页面标题并清空说明",
    )
    assert updated["success"] is True
    assert updated["title"] == "更新后的页面"
    assert updated["summary"] == ""
    assert updated["speaker_notes"] == "创建时的演讲备注"

    updated_response = await authenticated_client.get(f"/api/pages/{created['page_id']}")
    assert updated_response.status_code == 200
    updated_payload = updated_response.json()
    assert updated_payload["title"] == "更新后的页面"
    assert updated_payload["summary"] == ""
    assert updated_payload["speaker_notes"] == "创建时的演讲备注"

    notes_updated = await update_tool.entrypoint(
        run_context,
        page_id=created["page_id"],
        speaker_notes="单独更新后的演讲备注",
        change_note="更新演讲者备注",
    )
    assert notes_updated["success"] is True
    assert notes_updated["speaker_notes"] == "单独更新后的演讲备注"


async def test_project_route_tools_should_list_project_pages_with_user_context(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由页面列表工具应把授权用户透传给页面服务。"""

    workspace_id = await _create_workspace(authenticated_client, "项目路由页面列表工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "项目路由页面列表项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="路由候选页面",
        content="<template><main>路由候选</main></template>",
    )
    tools = build_project_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    list_tool = _find_tool(tools, "list_project_pages")
    result = await list_tool.entrypoint(run_context, keyword="路由候选", limit=10)

    assert result["total"] == 1
    assert result["items"][0]["page_id"] == page_id
    assert result["items"][0]["title"] == "路由候选页面"


async def test_project_style_config_tools_should_read_and_update_with_confirmation(
    authenticated_client: AsyncClient,
) -> None:
    """项目样式配置工具应只暴露真实画布、基础字号、主题摘要与样式规范。"""

    workspace_id = await _create_workspace(authenticated_client, "项目样式工具工作空间")
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "项目样式工具项目",
            "description": "用于内容助手读取项目描述。",
            "status": "active",
            "page_width": 1280,
            "page_height": 720,
            "base_font_size": "16px",
            "icon_default_stroke_width": 2,
            "show_pdf_export_button": True,
            "menu_mode": "preview",
            "style_spec_markdown": "## 版式\r\n- 使用清晰标题。",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    tools = build_project_tools(get_session_factory())
    tool_names = {tool.name for tool in tools}
    assert "list_workspace_styles" not in tool_names
    assert "get_workspace_style" not in tool_names

    read_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    get_tool = _find_tool(tools, "get_project_style_config")
    config = await get_tool.entrypoint(read_context)
    assert config["page_width"] == 1280
    assert config["page_height"] == 720
    assert config["base_font_size"] == "16px"
    assert config["theme"]["palette"]["text"]["primary"] == "#0D286A"
    assert config["theme"]["typography"]["headingfont"] == "system-ui"
    assert config["style_spec_markdown"] == "## 版式\n- 使用清晰标题。"
    assert "project" not in config
    assert "style_config" not in config
    assert "authoring_width" not in config
    assert "authoring_height" not in config
    assert "theme_key" not in config
    assert "theme_config_yaml" not in config
    assert "effective_app_config" not in config
    assert "effective_theme_config" not in config

    write_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    update_tool = _find_tool(tools, "update_project_style_config")
    assert update_tool.requires_confirmation is True
    updated = await update_tool.entrypoint(
        write_context,
        style_spec_markdown="## 新规范\n- 使用克制留白。",
    )
    assert updated["success"] is True
    assert updated["style_spec_markdown"] == "## 新规范\n- 使用克制留白。"
    assert "project" not in updated
    assert "style_config" not in updated

    persisted_response = await authenticated_client.get(f"/api/projects/{project_id}")
    assert persisted_response.status_code == 200
    persisted = persisted_response.json()
    assert persisted["page_width"] == 1280
    assert persisted["page_height"] == 720
    assert persisted["base_font_size"] == "16px"
    assert persisted["menu_mode"] == "preview"
    assert persisted["style_spec_markdown"] == "## 新规范\n- 使用克制留白。"


async def test_project_page_tools_should_reject_invalid_scope_or_payload(authenticated_client: AsyncClient) -> None:
    """项目页面工具应拒绝空页面源码、缺少项目上下文和跨项目元数据修改。"""

    workspace_id = await _create_workspace(authenticated_client, "项目页面工具拒绝工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "目标项目")
    other_project_id = await _create_project(authenticated_client, workspace_id, "其他项目")
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=other_project_id,
        title="其他项目页面",
        content="<template><div>other</div></template>",
    )
    tools = build_project_tools(get_session_factory())
    valid_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    create_tool = _find_tool(tools, "create_project_page")
    try:
        await create_tool.entrypoint(valid_context, title="空内容页面", page_content="   ")
    except AppException as exc:
        assert exc.code == "AI_PAGE_CONTENT_REQUIRED"
    else:
        raise AssertionError("创建页面时 page_content 为空应拒绝。")

    missing_project_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=None,
    )
    try:
        await create_tool.entrypoint(
            missing_project_context,
            title="缺项目页面",
            page_content="<template><div>draft</div></template>",
        )
    except AppException as exc:
        assert exc.code == "AI_TOOL_SCOPE_REQUIRED"
    else:
        raise AssertionError("缺少 project_id 时应拒绝创建项目页面。")

    update_tool = _find_tool(tools, "update_page_metadata")
    try:
        await update_tool.entrypoint(valid_context, page_id=other_page_id, title="越权更新")
    except AppException as exc:
        assert exc.code == "AI_PAGE_SCOPE_DENIED"
    else:
        raise AssertionError("跨项目页面元数据修改应拒绝。")


async def test_component_manager_runtime_kit_tools_should_query_agent_capabilities(authenticated_client: AsyncClient) -> None:
    """组件管理 Runtime Kit 工具应只读查询开放给 Agent 的能力目录。"""

    workspace_id = await _create_workspace(authenticated_client, "Runtime Kit 工具工作空间")
    tools = build_component_manager_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    list_tool = _find_tool(tools, "list_runtime_kit_capabilities")
    listed = await list_tool.entrypoint(run_context, keyword="page", limit=100)
    names = {item["name"] for item in listed["items"]}
    assert "usePageSize.v1" in names
    assert all(item["import_path"].startswith("@runtime-kit/") for item in listed["items"])
    assert all("/internal/" not in item["import_path"] for item in listed["items"])

    component_listed = await list_tool.entrypoint(run_context, kind="component", keyword="Icon")
    component_names = {item["name"] for item in component_listed["items"]}
    assert "Icon.v1" in component_names

    font_listed = await list_tool.entrypoint(run_context, keyword="font", limit=100)
    font_capability_names = {item["name"] for item in font_listed["items"]}
    assert "useAssetFontFamily.v1" in font_capability_names
    assert "resolveAssetFontFamily.v1" in font_capability_names

    detail_tool = _find_tool(tools, "get_runtime_kit_capability")
    icon_detail = await detail_tool.entrypoint(run_context, name="Icon.v1", kind="component")
    assert icon_detail["import_path"] == "@runtime-kit/public/components/primitives/Icon.v1.vue"
    assert len(icon_detail["usage"]) >= 1
    assert len(icon_detail["constraints"]) >= 1

    asset_drawio_detail = await detail_tool.entrypoint(run_context, name="AssetDrawio.v1", kind="component")
    asset_drawio_props = asset_drawio_detail["preview_schema"]["props"]
    assert "content" in asset_drawio_props
    assert "fallback" not in asset_drawio_props
    assert "fallback" not in json.dumps(asset_drawio_detail, ensure_ascii=False)
    assert "name 与 content 二选一" in "\n".join(asset_drawio_detail["constraints"])

    asset_video_detail = await detail_tool.entrypoint(run_context, name="AssetVideo.v1", kind="component")
    asset_video_props = asset_video_detail["preview_schema"]["props"]
    assert "fallback" not in asset_video_props
    assert "posterFallback" not in asset_video_props
    assert "fallback" not in json.dumps(asset_video_detail, ensure_ascii=False)

    util_detail = await detail_tool.entrypoint(run_context, name="resolveResourcePath.v1")
    assert util_detail["kind"] == "util"
    assert util_detail["import_path"] == "@runtime-kit/public/utils/assets.v1"
    assert "/internal/" not in util_detail["import_path"]

    theme_detail = await detail_tool.entrypoint(run_context, name="useTheme.v1")
    assert theme_detail["kind"] == "composable"
    assert theme_detail["import_path"] == "@runtime-kit/public/composables/theme/useTheme.v1"


async def test_get_component_detail_tool_should_render_source(
    authenticated_client: AsyncClient,
) -> None:
    """组件详情工具应返回原始源码和草稿锁字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件详情工具工作空间")
    component_content = "<template>\n  <article>detail</article>\n</template>\n"
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "详情测试组件",
            "import_name": "DetailTestComponent",
            "content": component_content,
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    detail_tool = _find_tool(build_component_manager_tools(get_session_factory()), "get_component_detail")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    result = await detail_tool.entrypoint(run_context, component_id=component_id)

    assert "组件名称：详情测试组件" in result.content
    assert "源码引用名：DetailTestComponent" in result.content
    assert "draft_hash（草稿内容指纹）：" in result.content
    assert "base_published_version_no（草稿基线版本号）：0" in result.content
    assert "源码：" in result.content
    assert "行号版源码：" not in result.content
    assert "0001 |" not in result.content
    assert component_content in result.content


async def test_update_component_metadata_tool_should_not_require_import_name(
    authenticated_client: AsyncClient,
) -> None:
    """组件元数据工具未改引用名时应允许省略 import_name。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件元数据工具工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "元数据测试组件",
            "import_name": "MetadataTestComponent",
            "content": "<template><article>metadata</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    metadata_tool = _find_tool(build_component_manager_tools(get_session_factory()), "update_component_metadata")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await metadata_tool.entrypoint(
        run_context,
        component_id=component_id,
        summary="更新后的组件说明",
    )

    assert result["success"] is True
    assert result["component"]["import_name"] == "MetadataTestComponent"
    assert result["component"]["summary"] == "更新后的组件说明"


async def test_apply_component_edits_should_reject_stale_draft_hash(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件草稿内容变化后，旧 draft_hash 不应继续写入。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件草稿指纹工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "草稿指纹组件",
            "import_name": "DraftHashComponent",
            "content": "<template><article>v1</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(f"/api/components/{component_id}/publish", json={})
    assert publish_response.status_code == 200
    stale_hash = calculate_source_hash(publish_response.json()["content"])
    update_response = await authenticated_client.patch(
        f"/api/components/{component_id}",
        json={"content": "<template><article>draft changed</article></template>"},
    )
    assert update_response.status_code == 200
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    try:
        await apply_tool.entrypoint(
            run_context,
            component_id=component_id,
            edits=[{"type": "replace_exact", "old_text": "draft changed", "new_text": "after"}],
            base_draft_hash=stale_hash,
            base_published_version_no=1,
        )
    except AppException as exc:
        assert exc.code == "AI_COMPONENT_DRAFT_STALE"
        assert "组件草稿已变化" in exc.detail
    else:
        raise AssertionError("旧 draft_hash 应被拒绝。")
    assert runtime_calls == []


async def test_apply_component_edits_should_reject_stale_draft_base_after_restore(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件草稿从历史版本恢复后，旧草稿基线版本号不应继续写入。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件草稿基线工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "草稿基线组件",
            "import_name": "DraftBaseComponent",
            "content": "<template><article>v1</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    assert (await authenticated_client.post(f"/api/components/{component_id}/publish", json={})).status_code == 200
    assert (
        await authenticated_client.patch(
            f"/api/components/{component_id}",
            json={"content": "<template><article>v2</article></template>"},
        )
    ).status_code == 200
    publish_v2_response = await authenticated_client.post(f"/api/components/{component_id}/publish", json={})
    assert publish_v2_response.status_code == 200
    restore_response = await authenticated_client.post(f"/api/components/{component_id}/versions/1/restore-to-draft", json={})
    assert restore_response.status_code == 200
    restored = restore_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    try:
        await apply_tool.entrypoint(
            run_context,
            component_id=component_id,
            edits=[{"type": "replace_exact", "old_text": "v1", "new_text": "after"}],
            base_draft_hash=calculate_source_hash(restored["content"]),
            base_published_version_no=publish_v2_response.json()["draft_base_version_no"],
        )
    except AppException as exc:
        assert exc.code == "AI_COMPONENT_DRAFT_BASE_STALE"
        assert "组件草稿基线已变化" in exc.detail
    else:
        raise AssertionError("旧 base_published_version_no 应被拒绝。")
    assert runtime_calls == []


async def test_apply_component_edits_should_allow_new_unpublished_component(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """新建未发布组件应使用 draft_base_version_no=0 和 draft_hash 正常写入草稿。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 未发布组件 Edits 工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "未发布组件",
            "import_name": "UnpublishedComponent",
            "content": "<template><article>draft</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await apply_tool.entrypoint(
        run_context,
        component_id=component["id"],
        edits=[{"type": "replace_exact", "old_text": "draft", "new_text": "updated"}],
        base_draft_hash=calculate_source_hash(component["content"]),
        base_published_version_no=0,
    )

    assert result["success"] is True
    assert result["version_no"] == 0
    assert result["component"]["draft_base_version_no"] == 0
    assert result["component"]["has_unpublished_changes"] is True
    assert "updated" in result["component"]["content"]
    assert runtime_calls


async def test_apply_component_edits_should_return_diagnostics_without_saving(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件 apply 内置 Runtime validate 失败时，应返回诊断且不保存草稿。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch, success=False)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件 Validate 失败工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "Validate 失败组件",
            "import_name": "ValidateFailComponent",
            "content": "<template><article>draft</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await apply_tool.entrypoint(
        run_context,
        component_id=component["id"],
        edits=[{"type": "replace_exact", "old_text": "draft", "new_text": "updated"}],
        base_draft_hash=calculate_source_hash(component["content"]),
        base_published_version_no=0,
    )

    component_response = await authenticated_client.get(f"/api/components/{component['id']}")
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "RUNTIME_TEST_FAILED"
    assert "updated" in str(result["canonical_diff"])
    assert result["edits_applied"] == 1
    assert runtime_calls
    assert component_response.json()["content"] == component["content"]


async def test_apply_component_edits_should_reject_invalid_edits_before_validate(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件 edits 命中失败时，应在 Runtime validate 前返回结构化诊断。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件 Edits 失败工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "Edits 失败组件",
            "import_name": "EditFailComponent",
            "content": "<template><article>draft</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await apply_tool.entrypoint(
        run_context,
        component_id=component["id"],
        edits=[{"type": "replace_exact", "old_text": "missing", "new_text": "updated"}],
        base_draft_hash=calculate_source_hash(component["content"]),
        base_published_version_no=0,
    )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert runtime_calls == []


async def test_publish_component_tool_should_create_reusable_version(
    authenticated_client: AsyncClient,
) -> None:
    """组件发布工具应把当前草稿发布为可引用的正式版本。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件发布工具工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "发布测试组件",
            "import_name": "PublishTestComponent",
            "content": "<template><article>publish</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_tool = _find_tool(build_component_manager_tools(get_session_factory()), "publish_component")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await publish_tool.entrypoint(
        run_context,
        component_id=component_id,
        release_name="首版",
        change_note="AI 助手发布测试版本",
    )

    assert result["success"] is True
    assert result["component"]["current_version_no"] == 1
    assert result["component"]["has_unpublished_changes"] is False
    assert result["import_usage"]["import_path"] == f"@workspace-components/{result['component']['code']}/v/1"
    assert "PublishTestComponent" in result["import_usage"]["import_statement"]


async def test_workspace_font_asset_tool_should_return_runtime_font_fields(authenticated_client: AsyncClient) -> None:
    """字体资源查询工具应返回 Agent 生成字体声明所需的资源名和字体族。"""

    workspace_id = await _create_workspace(authenticated_client, "字体工具工作空间")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("BrandSerif.woff2", b"font-data-tool", "font/woff2")},
        data={"asset_type": "font", "tags": "[]", "name": "BrandSerif"},
    )
    assert asset_response.status_code == 200
    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_response.json()["id"],
            "font_family": "Brand Serif",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200

    tool = build_list_workspace_font_assets_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        page_id=1,
    )
    result = await tool.entrypoint(run_context, keyword="Brand", limit=10)

    assert result[0]["asset_name"] == "BrandSerif"
    assert result[0]["font_family"] == "Brand Serif"
    assert result[0]["font_weight"] == "400"


async def test_apply_unified_diff_should_apply_and_reject_invalid_patch() -> None:
    """Unified Diff 应能正确应用，并在冲突时拒绝执行。"""

    current_content = "<template><div>draft</div></template>\n"
    valid_patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1 +1 @@\n"
        "-<template><div>draft</div></template>\n"
        "+<template><div>after-confirm</div></template>\n"
    )
    assert apply_unified_diff(current_content, valid_patch) == "<template><div>after-confirm</div></template>\n"

    invalid_patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1 +1 @@\n"
        "-<template><div>other</div></template>\n"
        "+<template><div>after-confirm</div></template>\n"
    )
    try:
        apply_unified_diff(current_content, invalid_patch)
    except AppException as exc:
        assert exc.code == "AI_PAGE_DIFF_CONFLICT"
        assert "hunk #1" in exc.detail
        assert "期望" in exc.detail
        assert "实际为" in exc.detail
    else:
        raise AssertionError("冲突 patch 应抛出统一错误。")


async def test_apply_unified_diff_should_ignore_crlf_differences() -> None:
    """当前源码和 patch 即使混用 CRLF/LF，也应先统一为 LF 再应用。"""

    current_content = "<template>\r\n  <div>draft</div>\r\n</template>\r\n"
    patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1,3 +1,3 @@\n"
        " <template>\n"
        "-  <div>draft</div>\n"
        "+  <div>after-confirm</div>\n"
        " </template>\n"
    )

    assert apply_unified_diff(current_content, patch) == "<template>\n  <div>after-confirm</div>\n</template>\n"


async def test_apply_unified_diff_with_repair_should_relocate_misaligned_hunk() -> None:
    """当 hunk 起始行号轻微漂移但旧内容完整时，应能自动重定位并重建 canonical diff。"""

    current_content = "alpha\nbeta\ngamma\ndelta\n"
    misaligned_patch = (
        "--- a/page.vue\n"
        "+++ b/page.vue\n"
        "@@ -2,2 +2,2 @@\n"
        " gamma\n"
        "-delta\n"
        "+zeta\n"
    )

    patch_result = apply_unified_diff_with_repair(current_content, misaligned_patch)

    assert patch_result.repaired is True
    assert patch_result.next_content == "alpha\nbeta\ngamma\nzeta\n"
    assert patch_result.canonical_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-delta\n+zeta\n" in patch_result.canonical_diff


async def test_apply_unified_diff_should_allow_missing_final_lf_on_last_patch_line() -> None:
    """patch 最后一条 hunk 行若仅缺少尾随 LF，也应能正常应用。"""

    current_content = "alpha\nbeta\ngamma\n"
    patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+zeta\n"
        " gamma"
    )

    assert apply_unified_diff(current_content, patch) == "alpha\nzeta\ngamma\n"


async def test_apply_unified_diff_with_repair_should_allow_missing_final_lf_on_last_window_line() -> None:
    """自动重定位时，旧内容窗口最后一行若只缺少尾随 LF，也应能匹配成功。"""

    current_content = "head\nalpha\nbeta\ngamma\n"
    misaligned_patch = (
        "--- a/page.vue\n"
        "+++ b/page.vue\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+zeta\n"
        " gamma"
    )

    patch_result = apply_unified_diff_with_repair(current_content, misaligned_patch)

    assert patch_result.repaired is True
    assert patch_result.next_content == "head\nalpha\nzeta\ngamma\n"
    assert patch_result.canonical_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-beta\n+zeta\n" in patch_result.canonical_diff


async def test_get_page_content_prompt_should_render_source() -> None:
    """页面源码读取工具应向模型提供原始源码文本。"""

    page_item = _build_page_item(
        page_id=88,
        content="<template>\n  <div>hello</div>\n</template>\n",
        speaker_notes="演讲时强调 hello 页面。",
    )
    prompt = build_page_content_prompt(page_item)

    assert "页面源信息：" in prompt
    assert "目标页面 ID：88" in prompt
    assert "演讲者备注：演讲时强调 hello 页面。" in prompt
    assert "源码：" in prompt
    assert "行号版源码：" not in prompt
    assert "```vue" not in prompt
    assert "0001 |" not in prompt
    assert "<template>\n  <div>hello</div>\n</template>\n" in prompt
    assert "直接复制源码中的真实片段作为 old_text、anchor_text 或 content" in prompt
    assert "每个 edit 对象必须包含 type 字段" in prompt


def test_get_component_detail_prompt_should_render_source() -> None:
    """组件详情读取工具应向模型提供原始源码和草稿锁字段。"""

    component = _build_component_item(
        component_id=18,
        content="<template>\n  <section>hello</section>\n</template>\n",
    )
    prompt = build_component_detail_prompt(component)

    assert "组件编码：CMP18" in prompt
    assert "源码引用名：TestComponent" in prompt
    assert "draft_hash（草稿内容指纹）：" in prompt
    assert "base_published_version_no（草稿基线版本号）：0" in prompt
    assert "源码：" in prompt
    assert "行号版源码：" not in prompt
    assert "```vue" not in prompt
    assert "0001 |" not in prompt
    assert "<template>\n  <section>hello</section>\n</template>\n" in prompt
    assert "直接复制源码中的真实片段作为 old_text、anchor_text 或 content" in prompt


async def test_get_page_content_tool_should_render_page_canvas_config(
    authenticated_client: AsyncClient,
) -> None:
    """页面源码读取工具应把真实画布尺寸和基础字号写入返回文本。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面尺寸工具工作空间")
    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "AI 页面尺寸工具项目",
        page_width=1366,
        page_height=768,
        base_font_size="18px",
        icon_default_stroke_width=3,
        style_spec_markdown="## 页面规范\n- 保持网格对齐。",
    )
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="尺寸上下文页面",
        content="<template><div>size</div></template>",
    )
    tool = build_get_page_content_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )
    run_context.dependencies["page_width"] = 1366
    run_context.dependencies["page_height"] = 768
    run_context.dependencies["base_font_size"] = "18px"

    result = await tool.entrypoint(run_context)

    assert "当前页面画布尺寸（page_width / page_height）：1366 x 768 px" in result.content
    assert "当前项目基础字号（base_font_size）：18px" in result.content
    assert "base_font_size 作用：text-base 等于该值" in result.content
    assert "page_width/page_height 不参与该换算" in result.content
    assert "固定尺度说明：直接写 px、rem 或 Tailwind arbitrary values 不会随 base_font_size 自动变化" in result.content
    assert "按真实画布编写" in result.content
    assert "px、rem 或 Tailwind arbitrary values" in result.content
    assert "authoring_width" not in result.content
    assert "作者画布" not in result.content
    assert "当前项目默认图标规格" not in result.content
    assert "<template><div>size</div></template>" in result.content
    assert "0001 |" not in result.content


async def test_get_page_content_tool_should_accept_explicit_page_id(
    authenticated_client: AsyncClient,
) -> None:
    """页面源码读取工具应允许显式读取当前项目内指定页面。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 显式页面读取工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 显式页面读取项目")
    context_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="上下文页面",
        content="<template><div>context</div></template>",
    )
    target_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="目标页面",
        content="<template><div>target</div></template>",
    )
    tool = build_get_page_content_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=context_page_id,
    )

    result = await tool.entrypoint(run_context, page_id=target_page_id)

    assert "读取方式：工具参数 page_id" in result.content
    assert f"目标页面 ID：{target_page_id}" in result.content
    assert f"上下文页面 ID：{context_page_id}" in result.content
    assert "<template><div>target</div></template>" in result.content
    assert "0001 |" not in result.content


async def test_apply_page_edits_tool_should_accept_explicit_page_id(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面 edits 写入工具应允许在项目上下文中显式指定目标页面。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 显式页面写入工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 显式页面写入项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="显式写入目标页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is True
    assert result["page_id"] == page_id
    assert result["version_no"] == 2
    assert result["edits_applied"] == 1
    assert runtime_calls


async def test_apply_page_edits_should_return_diagnostics_without_saving(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面 apply 内置 Runtime validate 失败时，应返回诊断且不保存新版本。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch, success=False)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Validate 失败工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Validate 失败项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="Validate 失败页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    page_response = await authenticated_client.get(f"/api/pages/{page_id}")
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "RUNTIME_TEST_FAILED"
    assert "new" in str(result["canonical_diff"])
    assert result["edits_applied"] == 1
    assert runtime_calls
    assert page_response.json()["current_version_no"] == 1
    assert page_response.json()["page_content"] == "<template><main>old</main></template>"


async def test_apply_page_edits_should_reject_invalid_edits_before_validate(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面 edits 命中失败时，应在 Runtime validate 前返回结构化诊断。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Edits 失败工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Edits 失败项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="Edits 失败页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "missing", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert runtime_calls == []


async def test_apply_page_edits_tool_should_reject_page_outside_context(authenticated_client: AsyncClient) -> None:
    """页面 edits 写入工具应拒绝跨项目 page_id，避免显式参数越权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面写入边界工作空间")
    source_project_id = await _create_project(authenticated_client, workspace_id, "AI 页面写入来源项目")
    other_project_id = await _create_project(authenticated_client, workspace_id, "AI 页面写入其他项目")
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=other_project_id,
        title="其他项目页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=source_project_id,
    )

    try:
        await tool.entrypoint(
            run_context,
            page_id=other_page_id,
            edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
            base_version_no=1,
        )
    except AppException as exc:
        assert exc.code == "AI_TOOL_CONTEXT_MISMATCH"
        assert "目标页面不属于当前工具上下文绑定的项目" in exc.detail
    else:
        raise AssertionError("跨项目 page_id 应被拒绝。")


async def test_apply_page_edits_should_reject_stale_base_version(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面 edits 写入应使用 current_version_no 做乐观锁。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Edits 乐观锁工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Edits 乐观锁项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="页面 Edits 乐观锁",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    try:
        await tool.entrypoint(
            run_context,
            page_id=page_id,
            edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
            base_version_no=0,
        )
    except AppException as exc:
        assert exc.code == "AI_PAGE_BASE_VERSION_STALE"
        assert "页面版本已变化" in exc.detail
    else:
        raise AssertionError("旧 base_version_no 应被拒绝。")
    assert runtime_calls == []

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is True
    assert result["version_no"] == 2
    assert result["edits_applied"] == 1
    assert runtime_calls


async def test_agent_runtime_context_should_include_page_canvas_config(
    authenticated_client: AsyncClient,
) -> None:
    """运行时上下文应从页面绑定项目读取真实画布和基础字号。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 运行上下文尺寸工作空间")
    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "AI 运行上下文尺寸项目",
        page_width=1600,
        page_height=900,
        base_font_size="18px",
        icon_default_stroke_width=3,
        style_spec_markdown="## 页面规范\n- 保持网格对齐。",
    )
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="运行上下文尺寸页面",
        content="<template><div>context</div></template>",
    )

    async with get_session_factory()() as session:
        runtime_context = await build_agent_runtime_context(
            session=session,
            scope=AgentScopeContext(
                scope_type="page",
                workspace_id=workspace_id,
                page_id=page_id,
                source="editor-page-detail",
            ),
        )

    assert runtime_context.project_id == project_id
    assert runtime_context.page_width == 1600
    assert runtime_context.page_height == 900
    assert runtime_context.base_font_size == "18px"
    assert runtime_context.style_spec_markdown == "## 页面规范\n- 保持网格对齐。"
    scope_text = build_scope_context_text(runtime_context)
    assert "当前页面画布尺寸（page_width / page_height）：1600 x 900 px" in scope_text
    assert "当前项目基础字号（base_font_size）：18px" in scope_text
    assert "base_font_size 是页面 Tailwind 字号和间距的基础尺度" in scope_text
    assert "page_width/page_height 不参与该换算" in scope_text
    assert "px、rem 或 Tailwind arbitrary values 属于固定 CSS 尺度" in scope_text
    assert "不会随 base_font_size 自动变化" in scope_text
    assert "按真实画布编写 Vue 与 Tailwind" in scope_text
    assert "px、rem 或 Tailwind arbitrary values" in scope_text
    assert "authoring_width" not in scope_text
    assert "作者画布" not in scope_text
    assert "当前项目默认图标规格" not in scope_text
    assert "当前项目样式规范" in scope_text
    assert "保持网格对齐" in scope_text


async def test_agent_runtime_context_should_include_project_suggested_reference_assets(
    authenticated_client: AsyncClient,
) -> None:
    """页面或项目会话上下文应默认带入项目建议引用内容资源精简摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议资源上下文空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议资源上下文项目")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": "hero_illustration",
            "original_name": "hero.svg",
            "description": "首页主视觉插图",
            "content": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\"><rect width=\"16\" height=\"16\"/></svg>",
            "tags": ["不应进入上下文"],
        },
    )
    assert asset_response.status_code == 200
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [asset_response.json()["id"]]},
    )
    assert save_response.status_code == 200
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="建议资源页面",
        content="<template><div>context</div></template>",
    )

    async with get_session_factory()() as session:
        runtime_context = await build_agent_runtime_context(
            session=session,
            scope=AgentScopeContext(
                scope_type="page",
                workspace_id=workspace_id,
                page_id=page_id,
                source="editor-page-detail",
            ),
        )

    assert [item["name"] for item in runtime_context.suggested_reference_assets] == ["hero_illustration"]
    assert set(runtime_context.suggested_reference_assets[0]) == {
        "id",
        "name",
        "original_name",
        "description",
        "asset_type",
        "content_editable",
    }
    scope_text = build_scope_context_text(runtime_context)
    assert "以下为项目建议引用资源" in scope_text
    assert "需要使用资源素材时，建议优先考虑这些资源" in scope_text
    assert "hero_illustration" in scope_text
    assert "url" not in scope_text
    assert "tags" not in scope_text
    assert "不应进入上下文" not in scope_text


async def test_project_suggested_reference_assets_tool_should_return_slim_items(
    authenticated_client: AsyncClient,
) -> None:
    """项目建议引用资源工具应要求项目上下文，并返回不含 URL 和标签的精简字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议资源工具空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议资源工具项目")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "mermaid",
            "name": "process_flow",
            "original_name": "process.mmd",
            "description": "流程图素材",
            "content": "flowchart TD\n  A[开始] --> B[结束]",
            "tags": ["不应返回"],
        },
    )
    assert asset_response.status_code == 200
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [asset_response.json()["id"]]},
    )
    assert save_response.status_code == 200

    tool_item = _find_tool(build_resource_manager_tools(get_session_factory()), "list_project_suggested_reference_assets")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    result = await tool_item.entrypoint(run_context)

    assert result["total"] == 1
    assert result["items"][0]["name"] == "process_flow"
    assert set(result["items"][0]) == {"id", "name", "original_name", "description", "asset_type", "content_editable"}

    missing_project_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    try:
        await tool_item.entrypoint(missing_project_context)
    except AppException as error:
        assert error.code == "AI_TOOL_SCOPE_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("缺少 project_id 时应拒绝调用项目建议资源工具。")


async def test_agent_tool_dependencies_and_scope_summary_should_include_page_canvas_config() -> None:
    """工具依赖和当前范围摘要应包含真实画布和基础字号。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = _build_auth_context()
    runtime_context = AgentRuntimeContext(
        scope_type="page",
        workspace_id=11,
        project_id=21,
        page_id=31,
        page_width=1600,
        page_height=900,
        base_font_size="18px",
        style_spec_markdown="## 规范\n- 使用统一标题。",
        source="editor-page-detail",
    )
    dependencies = facade._build_tool_dependencies(
        scope=AgentScopeContext(
            scope_type="page",
            workspace_id=11,
            project_id=21,
            page_id=31,
            source="editor-page-detail",
        ),
        session_id="session-page-size",
        run_id="run-page-size",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        runtime_context=runtime_context,
        session_metadata={},
        agent_config=None,  # type: ignore[arg-type]
    )
    assert dependencies["page_width"] == 1600
    assert dependencies["page_height"] == 900
    assert dependencies["base_font_size"] == "18px"
    assert "authoring_width" not in dependencies
    assert "authoring_height" not in dependencies
    assert "icon_default_size" not in dependencies
    assert "icon_default_stroke_width" not in dependencies
    assert dependencies["style_spec_markdown"] == "## 规范\n- 使用统一标题。"
    assert "page_size" not in dependencies
    assert dependencies["run_id"] == "run-page-size"
    assert "tool_access_token" not in dependencies
    assert "allowed_tool_groups" not in dependencies
    assert "tool_group_catalog" not in dependencies
    assert RESOURCE_TOOL_WRITE_SCOPES[0] not in dependencies["tool_scopes"]
    assert set(dependencies["member_tool_auth_tokens"]) == {COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID}
    assert COMPONENT_TOOL_WRITE_SCOPES[0] in dependencies["member_tool_scopes"][COMPONENT_MANAGER_AGENT_ID]
    assert RESOURCE_TOOL_WRITE_SCOPES[0] in dependencies["member_tool_scopes"][RESOURCE_MANAGER_AGENT_ID]


async def test_ai_sessions_should_list_workspace_sessions_and_gate_new_runs(authenticated_client: AsyncClient) -> None:
    """会话列表按工作空间返回，只有创建新 run 时才校验路由必须落在 session scope 内。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 页面一",
        content="<template><div>page-one</div></template>",
    )
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 页面二",
        content="<template><div>page-two</div></template>",
    )

    create_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "页面一会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    session_id = created_payload["session_id"]
    assert created_payload["metadata"]["scope_type"] == "page"
    assert created_payload["metadata"]["workspace_name"] == "AI 页面工作空间"
    assert created_payload["metadata"]["project_name"] == "AI 页面项目"
    assert created_payload["metadata"]["page_title"] == "AI 页面一"

    list_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    other_list_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert other_list_response.status_code == 200
    other_list_payload = other_list_response.json()
    assert len(other_list_payload) == 1
    assert other_list_payload[0]["metadata"]["page_title"] == "AI 页面一"

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    assert messages_response.json() == []

    cross_route_messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert cross_route_messages_response.status_code == 200
    assert cross_route_messages_response.json() == []

    out_of_scope_run_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "这条消息不应启动新 run"},
    )
    assert out_of_scope_run_response.status_code == 409
    assert out_of_scope_run_response.json()["code"] == "AI_SESSION_ROUTE_OUT_OF_SCOPE"


async def test_ai_session_context_status_should_return_budget_and_summary(authenticated_client: AsyncClient) -> None:
    """上下文状态接口应返回模型预算、压缩目标和 Agno 会话摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 上下文工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 上下文项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 上下文页面",
        content="<template><div>context</div></template>",
    )
    config_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "上下文模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-context",
            "context_window_tokens": 4096,
            "max_output_tokens": 1024,
            "history_token_ratio": 0.4,
            "compression_target_ratio": 0.1,
            "advanced_config_json": {},
        },
    )
    assert config_response.status_code == 201
    bind_response = await authenticated_client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": config_response.json()["id"]},
    )
    assert bind_response.status_code == 200
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "上下文会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(
        app.state.ai_db.get_session,
        session_id,
        SessionType.TEAM,
        "1",
        True,
    )
    assert isinstance(session_model, TeamSession)
    session_model.summary = SessionSummary(summary="用户希望持续优化页面视觉。", topics=["页面优化"])
    session_model.upsert_run(
        TeamRunOutput(
            run_id="run-context-status",
            session_id=session_id,
            team_id=AGENT_COORDINATOR_AGENT_ID,
            messages=[
                Message(role="user", content="请优化页面" + "细节" * 200),
                Message(role="assistant", content="已记录优化方向" + "结果" * 200),
            ],
            status=RunStatus.completed,
        )
    )
    await asyncio.to_thread(app.state.ai_db.upsert_session, session_model)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/context-status",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_available"] is True
    assert payload["summary"] == "用户希望持续优化页面视觉。"
    assert payload["topics"] == ["页面优化"]
    assert payload["history_budget_tokens"] > payload["compression_target_tokens"]
    assert payload["compression_target_ratio"] == 0.1


async def test_ai_run_routes_should_stream_direct_page_apply(authenticated_client: AsyncClient, monkeypatch) -> None:
    """BFF 应直接透传页面改写工具的完成事件，而不是先进入确认暂停。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 流式工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 流式项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 流式页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "运行会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        return {
            "session_id": session_id,
            "metadata": scope.model_dump(mode="json"),
            "chat_history": [],
        }

    def fake_run_raw_sse(self, **kwargs: object):  # type: ignore[no-untyped-def]
        run_id = str(kwargs.get("run_id") or "run-1")

        async def generator():
            for event_index, payload in enumerate([
                {
                    "event": "ToolCallCompleted",
                    "run_id": run_id,
                    "session_id": session_id,
                    "event_index": 0,
                    "tool": {
                        "tool_call_id": "tool-1",
                        "tool_name": "apply_page_edits",
                        "result": {
                            "success": True,
                            "message": "页面代码已更新并生成新版本。",
                            "page_code": "PG1",
                            "version_no": 2,
                            "edits_applied": 1,
                        },
                    },
                },
                {
                    "event": "RunCompleted",
                    "run_id": run_id,
                    "session_id": session_id,
                    "event_index": 1,
                    "content": "已完成写回。",
                },
            ]):
                payload["event_index"] = event_index
                yield (
                    f"event: {payload['event']}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                ).encode("utf-8")

        return generator()

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.run_raw_sse", fake_run_raw_sse)

    stream_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "帮我优化一下页面"},
    )
    assert stream_response.status_code == 200
    assert "event: ToolCallCompleted" in stream_response.text
    assert "event: RunCompleted" in stream_response.text
    assert "event: RunPaused" not in stream_response.text
    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [item["event_index"] for item in event_payloads] == [0, 1]


async def test_ai_stream_should_mark_cancelled_and_close_upstream_when_client_interrupts() -> None:
    """客户端中断 SSE 消费时，应关闭 Agno 上游流、标记 run 取消并释放 session 锁。"""

    class BlockingAgnoStream:
        """模拟永不主动结束的 Agno async iterator，并记录 aclose 调用。"""

        def __init__(self) -> None:
            self.closed = False
            self.iterating = asyncio.Event()

        def __aiter__(self) -> "BlockingAgnoStream":
            return self

        async def __anext__(self) -> object:
            self.iterating.set()
            await asyncio.sleep(60)
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed = True

    class ActiveStream:
        """提供 _stream_agno_events 需要的 run_id 与 stream 字段。"""

        def __init__(self, stream: BlockingAgnoStream) -> None:
            self.stream = stream
            self.run_id = "run-abort-1"

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="test")
    lock = asyncio.Lock()
    agno_stream = BlockingAgnoStream()
    marked_runs: list[tuple[str, RunStatus, str]] = []

    async def fake_ensure_session_access(**_: object) -> dict[str, object]:
        return {}

    def fake_get_session_run_lock(**_: object) -> asyncio.Lock:
        return lock

    async def fake_build_context_status_event(**kwargs: object) -> AgentRunEvent:
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=str(kwargs.get("session_id") or ""),
            data={},
        )

    def fake_normalize_event(**_: object) -> AgentRunEvent | None:
        return None

    async def fake_mark_run_terminal(
        *,
        run_id: str,
        status: RunStatus,
        content: str,
        **_: object,
    ) -> None:
        marked_runs.append((run_id, status, content))

    async def fake_stream_builder() -> ActiveStream:
        return ActiveStream(agno_stream)

    facade.ensure_session_access = fake_ensure_session_access  # type: ignore[method-assign]
    facade._get_session_run_lock = fake_get_session_run_lock  # type: ignore[method-assign]
    facade._build_context_status_event = fake_build_context_status_event  # type: ignore[method-assign]
    facade._normalize_event = fake_normalize_event  # type: ignore[method-assign]
    facade._mark_run_terminal = fake_mark_run_terminal  # type: ignore[method-assign]

    events = facade._stream_agno_events(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        session_id="session-abort-1",
        scope=scope,
        runtime_context=object(),  # type: ignore[arg-type]
        stream_builder=fake_stream_builder,
    )

    first_event = await events.__anext__()
    assert first_event.event == "context.status"
    assert lock.locked()

    next_event_task = asyncio.create_task(events.__anext__())
    await agno_stream.iterating.wait()
    next_event_task.cancel()
    try:
        await next_event_task
    except asyncio.CancelledError:
        pass
    else:  # pragma: no cover - 失败分支只用于让断言信息更清晰
        raise AssertionError("流式消费任务应被取消。")

    assert agno_stream.closed is True
    assert marked_runs == [
        ("run-abort-1", RunStatus.cancelled, "流式连接已断开，本次运行已停止。"),
    ]
    assert not lock.locked()


async def test_ai_paused_session_messages_should_be_visible(authenticated_client: AsyncClient, monkeypatch) -> None:
    """写页面导致 run 暂停时，消息历史仍应可被前端重新读取。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 暂停消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 暂停消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 暂停消息页面",
        content="<template><div>draft</div></template>",
    )

    paused_session = AgentSession(
        session_id="paused-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "暂停会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-paused-1",
                session_id="paused-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="帮我替换页面图标"),
                    Message(role="assistant", content="我先查看页面内容并生成 diff。"),
                ],
                status=RunStatus.paused,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "paused-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return paused_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/paused-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    expected_created_at = datetime.fromtimestamp(paused_session.runs[0].messages[0].created_at, tz=UTC).isoformat()
    assert response.json() == [
            {
                "id": paused_session.runs[0].messages[0].id,
                "run_id": "run-paused-1",
                "role": "user",
            "content": "帮我替换页面图标",
            "reasoning_content": None,
            "created_at": expected_created_at,
            "tool_name": None,
            "tool_call_id": None,
            "tool_args": None,
            "tool_call_error": None,
            "tool_calls": [],
            "attachments": [],
        },
            {
                "id": paused_session.runs[0].messages[1].id,
                "run_id": "run-paused-1",
                "role": "assistant",
            "content": "我先查看页面内容并生成 diff。",
            "reasoning_content": None,
            "created_at": expected_created_at,
            "tool_name": None,
            "tool_call_id": None,
            "tool_args": None,
            "tool_call_error": None,
            "tool_calls": [],
            "attachments": [],
        },
    ]


async def test_ai_session_messages_should_preserve_tool_metadata(authenticated_client: AsyncClient, monkeypatch) -> None:
    """会话消息读取应保留 Agno 持久化的工具调用参数与调用 ID，供前端回放详情。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 工具消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 工具消息页面",
        content="<template><div>draft</div></template>",
    )

    tool_session = AgentSession(
        session_id="tool-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具消息会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-tool-1",
                session_id="tool-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(
                        role="assistant",
                        content="我先读取资源列表。",
                        tool_calls=[
                            {
                                "id": "tool-assets-1",
                                "type": "function",
                                "function": {
                                    "name": "list_workspace_render_assets",
                                    "arguments": f'{{"workspace_id": {workspace_id}, "limit": 20}}',
                                },
                            }
                        ],
                    ),
                    Message(
                        role="tool",
                        content='{"total": 2, "items": ["hero.png", "cover.png"]}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-1",
                        tool_args={"workspace_id": workspace_id, "limit": 20},
                    ),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "tool-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return tool_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id="tool-session-1",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=2,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        "/api/ai/sessions/tool-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assistant_message = messages[0]
    tool_message = messages[1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["tool_calls"] == [
        {
            "id": "tool-assets-1",
            "type": "function",
            "function": {
                "name": "list_workspace_render_assets",
                "arguments": f'{{"workspace_id": {workspace_id}, "limit": 20}}',
            },
        }
    ]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_name"] == "list_workspace_render_assets"
    assert tool_message["tool_call_id"] == "tool-assets-1"
    assert tool_message["tool_args"] == {"workspace_id": workspace_id, "limit": 20}
    assert tool_message["tool_call_error"] is None
    assert tool_message["tool_calls"] == []

    runtime_response = await authenticated_client.get(
        "/api/ai/sessions/tool-session-1/runtime",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert runtime_response.status_code == 200
    runtime_payload = runtime_response.json()
    assert "messages" not in runtime_payload
    assert "tool_details" not in runtime_payload
    timeline_items = runtime_payload["timeline_items"]
    assert [(item["kind"], item["role"]) for item in timeline_items] == [("message", "assistant"), ("tool", None), ("run_status", None)]
    assert timeline_items[1]["tool"]["tool_call_id"] == "tool-assets-1"
    assert timeline_items[1]["tool"]["tool_name"] == "list_workspace_render_assets"


async def test_ai_session_messages_should_hide_system_and_split_reasoning(authenticated_client: AsyncClient, monkeypatch) -> None:
    """会话历史不返回 system 消息，并把 thinking 内容拆成独立字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 思考消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 思考消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 思考消息页面",
        content="<template><div>draft</div></template>",
    )

    reasoning_session = AgentSession(
        session_id="reasoning-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "思考消息会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-reasoning-1",
                session_id="reasoning-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="system", content="内部系统提示"),
                    Message(role="user", content="你好"),
                    Message(role="assistant", content="<think>先判断用户意图</think>\n你好！", reasoning_content="模型原生思考"),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "reasoning-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return reasoning_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/reasoning-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "\n你好！"
    assert messages[1]["reasoning_content"] == "模型原生思考\n\n先判断用户意图"


async def test_ai_session_messages_should_hide_agno_context_note(authenticated_client: AsyncClient, monkeypatch) -> None:
    """Agno 为图片上下文注入的 Take note 消息不应渲染成用户消息。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 框架消息过滤工作空间")
    context_note_session = AgentSession(
        session_id="context-note-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "框架消息过滤会话"},
        metadata={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "source": "editor-agent-sidebar",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-context-note-1",
                session_id="context-note-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="真实用户输入"),
                    Message(
                        role="user",
                        content="Take note of the following content",
                        images=[Image(content=b"fake-image", mime_type="image/png")],
                    ),
                    Message(role="assistant", content="真实助手回复"),
                    Message(role="assistant", content="历史注入回复", from_history=True),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "context-note-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return context_note_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/context-note-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["content"] for item in messages] == ["真实用户输入", "真实助手回复"]
    assert [item["role"] for item in messages] == ["user", "assistant"]


async def test_ai_cancelled_raw_run_should_preserve_input_and_streamed_content(authenticated_client: AsyncClient) -> None:
    """raw SSE 取消后若 Agno 未写 messages，应补偿真实输入和已展示内容。"""

    workspace_id = await _create_workspace(authenticated_client, "AI raw 取消补偿工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI raw 取消补偿项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI raw 取消补偿页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "raw 取消补偿会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-raw-cancel-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=TeamRunOutput(
            run_id=run_id,
            session_id=session_id,
            team_id=AGENT_COORDINATOR_AGENT_ID,
            user_id="1",
            input=TeamRunInput(input_content="真实取消输入"),
            status=RunStatus.cancelled,
            content=f"Run {run_id} was cancelled",
        ),
    )

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    async with get_session_factory()() as db_session:
        facade = AgentSessionFacade(app=app, current=_build_auth_context(), session=db_session)
        await facade._preserve_cancelled_raw_run_messages(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            run_id=run_id,
            fallback_user_message="兜底输入不应优先",
            assistant_content="已流出的正文。",
            reasoning_content="已展示 reasoning。",
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "真实取消输入"
    assert messages[1]["content"] == "已流出的正文。"
    assert messages[1]["reasoning_content"] == "已展示 reasoning。"

    session_detail = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_detail, TeamSession)
    run = session_detail.get_run(run_id)
    assert run is not None
    assert run.metadata is not None
    assert run.metadata["user_cancel_preserved"] is True


async def test_ai_cancelled_session_messages_should_lazy_preserve_input_and_run_content(
    authenticated_client: AsyncClient,
) -> None:
    """读取消息时应懒补偿 cancelled run 中已持久化但未写入 messages 的内容。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 懒补偿工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "懒补偿会话",
            "scope": {
                "workspace_id": workspace_id,
                "scope_type": "workspace",
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-lazy-cancel-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id="1",
            input=RunInput(input_content="创建一个复杂组件"),
            status=RunStatus.cancelled,
            content="已经完成设计和代码校验，准备创建组件。",
            reasoning_content="先分析需求，再准备调用创建工具。",
            messages=[],
        ),
    )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "创建一个复杂组件"
    assert messages[1]["content"] == "已经完成设计和代码校验，准备创建组件。"
    assert messages[1]["reasoning_content"] == "先分析需求，再准备调用创建工具。"


async def test_ai_raw_sse_cancelled_event_should_trigger_preservation() -> None:
    """raw SSE 收到 Agno 取消终态时，应把跟踪到的用户输入和 delta 交给补偿流程。"""

    class FakeRawEvent:
        """提供 Agno SSE formatter 所需的 event 与 to_dict。"""

        def __init__(self, **payload: object) -> None:
            self.event = str(payload.get("event"))
            self._payload = payload
            for key, value in payload.items():
                setattr(self, key, value)

        def to_dict(self) -> dict[str, object]:
            return dict(self._payload)

    async def fake_raw_stream():
        yield FakeRawEvent(event="TeamRunStarted", run_id="run-raw-event", session_id="session-raw-event")
        yield FakeRawEvent(
            event="TeamRunContent",
            run_id="run-raw-event",
            session_id="session-raw-event",
            content="已输出正文",
        )
        yield FakeRawEvent(
            event="ReasoningContentDelta",
            run_id="run-raw-event",
            session_id="session-raw-event",
            reasoning_content="已输出思考",
        )
        yield FakeRawEvent(event="TeamRunCancelled", run_id="run-raw-event", session_id="session-raw-event")

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id="run-raw-event")

    preserved_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_preserve(**kwargs: object) -> None:
        preserved_payloads.append(dict(kwargs))

    facade._preserve_cancelled_raw_run_messages = fake_preserve

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-event",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message="真实用户输入",
            stream_builder=fake_stream_builder,
        )
    ]

    assert len(chunks) == 4
    assert preserved_payloads == [
        {
            "session_id": "session-raw-event",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "run_id": "run-raw-event",
            "fallback_user_message": "真实用户输入",
            "assistant_content": "已输出正文",
            "reasoning_content": "已输出思考",
        }
    ]


async def test_ai_raw_sse_string_stream_should_trigger_cancelled_preservation() -> None:
    """raw SSE 若已被 Agno 格式化为字符串，流结束后仍应尝试按 DB 状态补偿取消消息。"""

    async def fake_raw_stream():
        yield "event: TeamRunStarted\ndata: {\"run_id\":\"run-raw-string\"}\n\n"
        yield "event: TeamRunCancelled\ndata: {\"run_id\":\"run-raw-string\"}\n\n"

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id="run-raw-string")

    preserved_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_preserve(**kwargs: object) -> None:
        preserved_payloads.append(dict(kwargs))

    facade._preserve_cancelled_raw_run_messages = fake_preserve

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-string",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message="字符串流用户输入",
            stream_builder=fake_stream_builder,
        )
    ]

    assert len(chunks) == 2
    assert preserved_payloads == [
        {
            "session_id": "session-raw-string",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "run_id": "run-raw-string",
            "fallback_user_message": "字符串流用户输入",
            "assistant_content": None,
            "reasoning_content": None,
        }
    ]


async def test_ai_raw_sse_object_events_should_continue_existing_event_index() -> None:
    """非 background 原始事件包装时，应沿用已有 run.events 游标继续编号。"""

    class FakeRawEvent:
        """提供 Agno SSE formatter 所需的 event 与 to_dict。"""

        def __init__(self, **payload: object) -> None:
            self.event = str(payload.get("event"))
            self._payload = payload
            for key, value in payload.items():
                setattr(self, key, value)

        def to_dict(self) -> dict[str, object]:
            return dict(self._payload)

    run_id = "run-continue-index"
    session_id = "session-continue-index"
    session_detail = TeamSession(
        session_id=session_id,
        team_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        team_data={"team_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            TeamRunOutput(
                run_id=run_id,
                session_id=session_id,
                team_id=AGENT_COORDINATOR_AGENT_ID,
                events=[
                    {"event": "TeamRunStarted", "run_id": run_id},
                    {"event": "TeamRunPaused", "run_id": run_id},
                ],
                status=RunStatus.running,
            )
        ],
    )

    async def fake_raw_stream():
        yield FakeRawEvent(event="TeamRunContent", run_id=run_id, session_id=session_id, content="继续输出")
        yield FakeRawEvent(event="TeamRunCompleted", run_id=run_id, session_id=session_id, content="完成")

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id=run_id)

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(session_detail)

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message=None,
            stream_builder=fake_stream_builder,
        )
    ]

    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for chunk in chunks
        for line in chunk.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert [payload["event_index"] for payload in event_payloads] == [2, 3]


async def test_ai_raw_continue_exception_should_mark_resolved_confirmation_error() -> None:
    """continue raw SSE 异常时，应按已提交确认清理目标 run 并返回带 run_id 的错误事件。"""

    async def fake_stream_builder() -> SimpleNamespace:
        raise AppException(status_code=500, code="AI_FAKE_CONTINUE_FAILED", detail="继续执行失败")

    marked_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_mark_terminal(**kwargs: object) -> None:
        marked_payloads.append(dict(kwargs))

    facade._mark_run_terminal = fake_mark_terminal

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-continue-error",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message=None,
            expected_run_id="run-raw-continue-error",
            resolved_tool_execution={
                "tool_call_id": "tool-confirm-error",
                "tool_name": "apply_page_edits",
                "confirmed": True,
            },
            stream_builder=fake_stream_builder,
        )
    ]

    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for chunk in chunks
        for line in chunk.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert event_payloads[0]["run_id"] == "run-raw-continue-error"
    assert event_payloads[0]["error_type"] == "AI_FAKE_CONTINUE_FAILED"
    assert marked_payloads[0]["run_id"] == "run-raw-continue-error"
    assert marked_payloads[0]["status"] == RunStatus.error
    assert marked_payloads[0]["resolved_tool_execution"]["tool_call_id"] == "tool-confirm-error"


async def test_ai_raw_sse_should_stop_and_release_lock_after_pause_event() -> None:
    """raw SSE 收到暂停事件后应收束本轮流，避免 HITL 提交后保持 loading。"""

    run_id = f"run-raw-pause-{uuid4()}"
    session_id = f"session-raw-pause-{uuid4()}"
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade.ensure_session_access = lambda **_: _async_value(AgentSession(session_id=session_id, agent_id=COMPONENT_MANAGER_AGENT_ID, user_id="1"))
    marked_payloads: list[dict[str, object]] = []
    preserve_payloads: list[dict[str, object]] = []

    async def fake_set_existing_run_status(**kwargs: object) -> None:
        marked_payloads.append(dict(kwargs))

    async def fake_preserve_cancelled_raw_run_messages(**kwargs: object) -> None:
        preserve_payloads.append(dict(kwargs))
        return None

    async def paused_then_waits():
        payload = {
            "event": "RunPaused",
            "run_id": run_id,
            "session_id": session_id,
            "requirements": [
                {
                    "id": "req-raw-pause",
                    "tool_execution": {
                        "tool_call_id": "tool-raw-pause",
                        "tool_name": "ask_user",
                        "requires_user_input": True,
                        "user_feedback_schema": [
                            {
                                "question": "是否继续？",
                                "header": "继续",
                                "options": [{"label": "继续"}, {"label": "停止"}],
                                "multi_select": False,
                            }
                        ],
                    },
                }
            ],
        }
        yield f"event: RunPaused\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        await asyncio.Event().wait()

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=paused_then_waits(), run_id=run_id)

    facade._set_existing_run_status = fake_set_existing_run_status
    facade._preserve_cancelled_raw_run_messages = fake_preserve_cancelled_raw_run_messages
    lock = facade._get_session_run_lock(session_id=session_id, agent_id=COMPONENT_MANAGER_AGENT_ID)

    chunks = await asyncio.wait_for(
        _collect_chunks(
            facade._stream_agno_raw_sse(
                session_id=session_id,
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library"),
                stream_builder=fake_stream_builder,
            )
        ),
        timeout=1,
    )
    parsed_events = [parsed for chunk in chunks for parsed in _iter_raw_sse_payloads(chunk)]

    assert [(event_name, payload.get("run_id")) for payload, event_name in parsed_events] == [("RunPaused", run_id)]
    assert marked_payloads[0]["run_id"] == run_id
    assert marked_payloads[0]["status"] == RunStatus.paused
    assert preserve_payloads == []
    assert not lock.locked()


async def _collect_chunks(stream) -> list[bytes]:  # type: ignore[no-untyped-def]
    """收集异步字节流，供 raw SSE 收束测试验证不会卡住。"""

    return [chunk async for chunk in stream]


async def test_ai_coordinator_session_messages_should_be_visible(authenticated_client: AsyncClient, monkeypatch) -> None:
    """统一智能体使用 AgentSession 持久化时，历史消息应能被会话接口读取。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 总控消息工作空间")
    agent_session = AgentSession(
        session_id="agent-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "智能体会话"},
        metadata={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "project_id": None,
            "page_id": None,
            "component_id": None,
            "source": "editor-agent-sidebar",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="agent-run-1",
                session_id="agent-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="你好"),
                    Message(role="assistant", content="你好！很高兴为你服务。"),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "agent-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return agent_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/agent-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-agent-sidebar",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert [item["content"] for item in messages] == ["你好", "你好！很高兴为你服务。"]


async def test_ai_agent_run_events_should_be_normalized_for_editor() -> None:
    """Agno Agent 事件应转换成前端已支持的统一 SSE 事件名。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    content_event = facade._normalize_event(
        raw_event=RunContentEvent(run_id="agent-run-1", session_id="agent-session-1", content="<think>组织回复</think>你好"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    completed_event = facade._normalize_event(
        raw_event=RunCompletedEvent(run_id="agent-run-1", session_id="agent-session-1", content="完成"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    content_completed_event = facade._normalize_event(
        raw_event={
            "event": "RunContentCompleted",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": "一段内容已完成",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    output_event = facade._normalize_event(
        raw_event=RunOutput(run_id="agent-run-1", session_id="agent-session-1", agent_id=AGENT_COORDINATOR_AGENT_ID, content="完成"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    tool_event = facade._normalize_event(
        raw_event={
            "event": "ToolCallCompleted",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": "apply_component_edits(component_id=6, edits=..., change_note=...) completed in 0.0111s.",
            "tool": {
                "tool_name": "apply_component_edits",
                "tool_call_id": "tool-call-1",
                "result": {
                    "success": True,
                    "component_id": 6,
                    "preview": {"changed_files": ["Component.vue"]},
                },
            },
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert content_event is not None
    assert content_event.event == "message.delta"
    assert content_event.content == "你好"
    assert content_event.data["reasoning_content"] == "组织回复"
    assert completed_event is not None
    assert completed_event.event == "run.completed"
    assert completed_event.content == "完成"
    assert content_completed_event is None
    assert output_event is not None
    assert output_event.event == "run.completed"
    assert output_event.content == "完成"
    assert tool_event is not None
    assert tool_event.event == "tool.completed"
    assert tool_event.data["result"] == {
        "success": True,
        "component_id": 6,
        "preview": {"changed_files": ["Component.vue"]},
    }
    assert tool_event.data["message"].endswith("completed in 0.0111s.")


async def test_ai_run_output_with_pending_feedback_should_be_normalized_as_paused() -> None:
    """RunOutput 即使被 Agno 标记完成，未解决 ask_user requirement 仍应恢复为暂停态。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-component-library",
    )
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-1",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "options": [
                        {"label": "首屏", "description": "只调整第一屏。"},
                        {"label": "全页面", "description": "整体调整。"},
                    ],
                    "multi_select": False,
                }
            ],
        }
    )

    event = facade._normalize_event(
        raw_event=RunOutput(
            run_id="run-feedback-paused",
            session_id="session-feedback-paused",
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.completed,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
        runtime_context=runtime_context,
        session_id="session-feedback-paused",
    )

    assert event is not None
    assert event.event == "run.paused"
    requirement = event.data["requirement"]
    assert requirement["kind"] == "user_feedback"
    assert requirement["tool_name"] == "ask_user"
    assert requirement["user_feedback_schema"][0]["question"] == "这次优先调整哪个区域？"


async def test_ai_stream_delta_should_preserve_markdown_boundaries() -> None:
    """流式 delta 不应被 trim 掉开头换行，否则列表会在输出过程中粘到上一段。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    content_event = facade._normalize_event(
        raw_event=RunContentEvent(
            run_id="agent-run-1",
            session_id="agent-session-1",
            content="\n\n- **页面标题**：234234",
        ),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert content_event is not None
    assert content_event.event == "message.delta"
    assert content_event.content == "\n\n- **页面标题**：234234"


async def test_ai_reasoning_stream_delta_should_preserve_newline_boundaries() -> None:
    """reasoning 流式片段应保留换行边界，避免思考过程完成后才重新排版。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    reasoning_event = facade._normalize_event(
        raw_event={
            "event": "RunContent",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": None,
            "reasoning_content": "\n\n- **检查页面**：确认当前路由",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    newline_event = facade._normalize_event(
        raw_event={
            "event": "RunContent",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": None,
            "reasoning_content": "\n",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert reasoning_event is not None
    assert reasoning_event.event == "message.delta"
    assert reasoning_event.data["reasoning_content"] == "\n\n- **检查页面**：确认当前路由"
    assert newline_event is not None
    assert newline_event.event == "message.delta"
    assert newline_event.data["reasoning_content"] == "\n"


async def test_extract_pending_requirement_should_fallback_to_paused_tools() -> None:
    """RunPaused 若未携带 requirements，也应能从 tools 兜底出确认动作。"""

    current_page = _build_page_item(page_id=31, content="<template><div>old</div></template>\n")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-tools-only",
            "session_id": "session-tools-only",
            "tools": [
                {
                    "tool_call_id": "tool-1",
                    "tool_name": "apply_page_edits",
                    "requires_confirmation": True,
                    "tool_args": {
                        "edits": [
                            {
                                "type": "replace_exact",
                                "old_text": "<template><div>old</div></template>",
                                "new_text": "<template><div>new</div></template>",
                            }
                        ],
                        "change_note": "替换页面内容",
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.run_id == "run-paused-tools-only"
    assert requirement.session_id == "session-tools-only"
    assert requirement.tool_name == "apply_page_edits"
    assert requirement.suggested_patch is not None
    assert requirement.suggested_patch.proposed_content == "<template><div>new</div></template>\n"
    assert requirement.suggested_patch.change_note == "替换页面内容"


async def test_extract_pending_requirement_should_keep_pause_when_edits_preview_fails() -> None:
    """edits 预览生成失败时，不应吞掉暂停动作，而应返回可提示前端的 note。"""

    current_page = _build_page_item(page_id=32, content="<template><div>old</div></template>")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-bad-edits",
            "session_id": "session-bad-edits",
            "requirements": [
                {
                    "id": "requirement-1",
                    "tool_execution": {
                        "tool_call_id": "tool-bad",
                        "tool_name": "apply_page_edits",
                        "requires_confirmation": True,
                        "tool_args": {
                            "edits": [
                                {
                                    "type": "replace_exact",
                                    "old_text": "<template><div>missing</div></template>",
                                    "new_text": "<template><div>new</div></template>",
                                }
                            ],
                            "change_note": "错误 edits 预览",
                        },
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.tool_name == "apply_page_edits"
    assert requirement.suggested_patch is None
    assert requirement.note is not None
    assert "无法预生成 edits 预览" in requirement.note


async def test_extract_pending_requirement_should_build_canonical_diff_from_edits() -> None:
    """暂停态若拿到 edits，应下发后端生成的 canonical diff 给前端确认。"""

    current_page = _build_page_item(page_id=66, content="alpha\nbeta\ngamma\ndelta\n")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-edits",
            "session_id": "session-edits",
            "requirements": [
                {
                    "id": "requirement-edits",
                    "tool_execution": {
                        "tool_call_id": "tool-edits",
                        "tool_name": "apply_page_edits",
                        "requires_confirmation": True,
                        "tool_args": {
                            "edits": [{"type": "replace_exact", "old_text": "delta\n", "new_text": "zeta\n"}],
                            "change_note": "修正发展愿景描述",
                        },
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.suggested_patch is not None
    assert requirement.suggested_patch.proposed_content == "alpha\nbeta\ngamma\nzeta\n"
    assert requirement.suggested_patch.unified_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-delta\n+zeta\n" in requirement.suggested_patch.unified_diff
    assert "edits" in requirement.tool_execution["tool_args"]


async def test_extract_pending_requirement_should_support_user_feedback_questions() -> None:
    """ask_user 暂停态应被提取为结构化提问，并强制按单选下发。"""

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-feedback",
            "session_id": "session-feedback",
            "requirements": [
                {
                    "id": "requirement-feedback",
                    "tool_execution": {
                        "tool_call_id": "tool-ask",
                        "tool_name": "ask_user",
                        "tool_args": {},
                        "requires_user_input": True,
                    },
                    "user_feedback_schema": [
                        {
                            "question": "这次优先调整哪个区域？",
                            "header": "范围",
                            "multi_select": True,
                            "options": [
                                {"label": "首屏", "description": "只调整第一屏。"},
                                {"label": "全页面", "description": "整体调整。"},
                            ],
                        },
                        {
                            "question": "视觉风格倾向是什么？",
                            "header": "风格",
                            "options": [
                                {"label": "克制"},
                                {"label": "醒目"},
                            ],
                        },
                    ],
                }
            ],
        },
        runtime_context=AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
    )

    assert requirement is not None
    assert requirement.kind == "user_feedback"
    assert requirement.tool_name == "ask_user"
    assert len(requirement.user_feedback_schema) == 2
    assert requirement.user_feedback_schema[0]["multi_select"] is False
    assert requirement.tool_execution["requires_user_input"] is True
    assert requirement.tool_execution["user_feedback_schema"][0]["question"] == "这次优先调整哪个区域？"


def test_apply_user_feedback_selections_should_write_preset_and_custom_answers() -> None:
    """继续 ask_user 时，应把预设选项和自定义回答都写回 Agno ToolExecution。"""

    updated = _apply_user_feedback_selections(
        {
            "tool_name": "ask_user",
            "tool_call_id": "tool-ask",
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "multi_select": False,
                    "options": [
                        {"label": "首屏", "description": "只调整第一屏。"},
                        {"label": "全页面", "description": "整体调整。"},
                    ],
                },
                {
                    "question": "视觉风格倾向是什么？",
                    "header": "风格",
                    "multi_select": False,
                    "options": [
                        {"label": "克制"},
                        {"label": "醒目"},
                    ],
                },
            ],
        },
        [
            {"question": "这次优先调整哪个区域？", "selected_label": "首屏", "custom_text": None},
            {"question": "视觉风格倾向是什么？", "selected_label": None, "custom_text": "保留当前图标风格"},
        ],
    )

    assert updated["requires_user_input"] is True
    assert updated["answered"] is True
    assert updated["user_feedback_schema"][0]["selected_options"] == ["首屏"]
    assert updated["user_feedback_schema"][0]["options"][0]["selected"] is True
    assert updated["user_feedback_schema"][1]["selected_options"] == ["用户补充：保留当前图标风格"]
    assert all(option["selected"] is False for option in updated["user_feedback_schema"][1]["options"])
    requirement = _build_run_requirement_from_tool_execution_payload(updated)
    assert requirement.tool_execution is not None
    assert requirement.tool_execution.answered is True
    assert requirement.tool_execution.requires_user_input is False
    assert requirement.tool_execution.external_execution_required is True
    assert requirement.tool_execution.result is not None
    assert "首屏" in requirement.tool_execution.result
    assert "保留当前图标风格" in requirement.tool_execution.result
    assert requirement.external_execution_result == requirement.tool_execution.result
    assert requirement.is_resolved() is True


def test_ai_continue_requirement_should_persist_confirmation_decision() -> None:
    """确认/拒绝 HITL 时 RunRequirement 与 ToolExecution 都应带上用户决策。"""

    confirmed = _build_run_requirement_from_tool_execution_payload(
        {
            "tool_call_id": "tool-confirmed",
            "tool_name": "apply_project_route_tree",
            "requires_confirmation": True,
            "confirmed": True,
        }
    )
    assert confirmed.confirmation is True
    assert confirmed.tool_execution is not None
    assert confirmed.tool_execution.confirmed is True
    assert confirmed.is_resolved() is True

    rejected = _build_run_requirement_from_tool_execution_payload(
        {
            "tool_call_id": "tool-rejected",
            "tool_name": "apply_project_route_tree",
            "requires_confirmation": True,
            "confirmed": False,
            "confirmation_note": "用户拒绝执行。",
        }
    )
    assert rejected.confirmation is False
    assert rejected.confirmation_note == "用户拒绝执行。"
    assert rejected.tool_execution is not None
    assert rejected.tool_execution.confirmed is False
    assert rejected.tool_execution.confirmation_note == "用户拒绝执行。"
    assert rejected.is_resolved() is True


def test_team_run_output_continue_should_support_agent_tool_events() -> None:
    """Agno Team continue 复用 Agent 工具事件 helper 时，不应因缺少 agent_id 失败。"""

    run = TeamRunOutput(
        run_id="team-continue-run",
        session_id="team-continue-session",
        team_id=AGENT_COORDINATOR_AGENT_ID,
        team_name="内容助手",
    )
    patched_run = _prepare_team_run_output_for_agno_continue(
        run,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        agent_name="内容助手",
    )

    assert patched_run is run
    event = create_tool_call_started_event(
        run,
        ToolExecution(
            tool_call_id="tool-confirm-route",
            tool_name="apply_project_route_tree",
            tool_args={},
        ),
    )
    assert event.agent_id == AGENT_COORDINATOR_AGENT_ID
    assert event.agent_name == "内容助手"


async def test_extract_tool_error_info_should_keep_structured_code() -> None:
    """ToolCallError 若携带结构化错误对象，应保留 message 与 code。"""

    message, code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
        payload={
            "error": {
                "code": "AI_PAGE_DIFF_CONFLICT",
                "detail": "Unified Diff 无法应用：上下文内容不匹配。",
            }
        },
        tool_execution={
            "tool_name": "apply_page_edits",
            "tool_call_id": "tool-error-1",
        },
    )

    assert code == "AI_PAGE_DIFF_CONFLICT"
    assert message == "Unified Diff 无法应用：上下文内容不匹配。"
    assert repair_attempted is False
    assert repair_succeeded is False
    assert repair_reason is None


async def test_extract_tool_error_info_should_parse_repair_metadata_from_json_string() -> None:
    """ToolCallError 若只携带 JSON 字符串错误体，也应解包 repair 结构化字段。"""

    message, code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
        payload={
            "error": json.dumps(
                {
                    "message": "Unified Diff 无法应用：上下文内容不匹配。 自动重定位失败：hunk #1 未找到窗口。",
                    "code": "AI_PAGE_DIFF_CONFLICT",
                    "repair_attempted": True,
                    "repair_succeeded": False,
                    "repair_reason": "hunk #1 未找到窗口。",
                },
                ensure_ascii=False,
            )
        },
        tool_execution={
            "tool_name": "apply_page_edits",
            "tool_call_id": "tool-error-2",
        },
    )

    assert code == "AI_PAGE_DIFF_CONFLICT"
    assert message == "Unified Diff 无法应用：上下文内容不匹配。 自动重定位失败：hunk #1 未找到窗口。"
    assert repair_attempted is True
    assert repair_succeeded is False
    assert repair_reason == "hunk #1 未找到窗口。"


async def test_ai_active_run_cancel_route_should_proxy_interrupt_request(authenticated_client: AsyncClient, monkeypatch) -> None:
    """BFF 应暴露 session 级 run 中断接口，并代理给当前 active run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 中断工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 中断项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 中断页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "中断会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        return {
            "session_id": session_id,
            "metadata": scope.model_dump(mode="json"),
            "chat_history": [],
        }

    async def fake_cancel_active_run(  # type: ignore[no-untyped-def]
        self,
        *,
        session_id: str,
        agent_id: str,
        scope,
        force: bool = False,
        tool_call_id: str | None = None,
    ):
        assert session_id
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        assert force is False
        assert tool_call_id is None
        return {
            "run_id": "run-interrupt-1",
            "session_id": session_id,
            "cancel_requested": True,
        }

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.cancel_active_run", fake_cancel_active_run)

    cancel_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={
            "session_id": session_id,
        },
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json() == {
        "run_id": "run-interrupt-1",
        "session_id": session_id,
        "cancel_requested": True,
    }


async def test_ai_active_run_cancel_should_not_fail_when_agno_cancel_returns_false(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Agno graceful cancel 返回 False 时，BFF 仍应进入 cancelling 并允许 force 兜底清理。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Graceful Cancel 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Graceful Cancel 项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Graceful Cancel 页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Graceful Cancel 会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-cancel-false"
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="需要取消的长任务",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id, data={}),
        )

    cancel_calls: list[str] = []

    def fake_cancel_run(cancel_run_id: str) -> bool:
        cancel_calls.append(cancel_run_id)
        return False

    monkeypatch.setattr("app.ai.run_background.AgnoAgent.cancel_run", fake_cancel_run)
    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    manager = app.state.ai_run_manager
    dummy_task = asyncio.create_task(asyncio.sleep(3600))
    manager._tasks[run_id] = dummy_task  # noqa: SLF001
    try:
        cancel_response = await authenticated_client.post(
            f"/api/ai/sessions/{session_id}/active-run/cancel",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
            json={"session_id": session_id},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["run_id"] == run_id
        assert cancel_calls == [run_id]

        active_response = await authenticated_client.get(
            f"/api/ai/sessions/{session_id}/active-run",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
        )
        assert active_response.status_code == 200
        active_payload = active_response.json()
        assert active_payload["status"] == "cancelling"
        assert active_payload["cancel_requested_at"] is not None

        force_response = await authenticated_client.post(
            f"/api/ai/sessions/{session_id}/active-run/cancel",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
            json={"session_id": session_id, "force": True},
        )
        assert force_response.status_code == 200
        assert force_response.json()["run_id"] == run_id

        final_response = await authenticated_client.get(
            f"/api/ai/sessions/{session_id}/active-run",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
        )
        assert final_response.status_code == 200
        assert final_response.json() is None
        async with get_session_factory()() as db_session:
            service = AiAgentRunService(db_session)
            task = await service.get_task_by_run(run_id=run_id, user_id=1)
            ignored_event = await service.append_event(
                run_id=run_id,
                event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id, data={}),
            )
            events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)
        assert task is not None
        assert task.status == "cancelled"
        assert ignored_event is None
        assert [event.event for event in events] == ["run.started", "run.cancelling", "run.cancelled"]
    finally:
        manager._tasks.pop(run_id, None)  # noqa: SLF001
        dummy_task.cancel()
        await asyncio.gather(dummy_task, return_exceptions=True)


async def test_ai_user_cancel_should_preserve_streamed_delta_in_agno_history(authenticated_client: AsyncClient) -> None:
    """用户主动停止时，应把已流出的 assistant 文本补写进 Agno 历史。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止保留工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 停止保留项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 停止保留页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "停止保留会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-preserve-cancel"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[
                Message(role="assistant", content="旧历史回复", from_history=True),
                Message(role="user", content="请生成一段长内容"),
            ],
        ),
    )
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="请生成一段长内容",
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="第一段，"),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="第二段。"),
        )
        await service.mark_cancelling(task=task)

    response = await authenticated_client.post(
        f"/api/ai/runs/{run_id}/cancel",
        json={"force": True},
    )
    assert response.status_code == 200

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["assistant", "user", "assistant"]
    assert messages[-1]["content"] == "第一段，第二段。"

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_detail = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_detail, TeamSession)
    run = session_detail.get_run(run_id)
    assert run is not None
    assert run.content == "第一段，第二段。"
    assert run.metadata is not None
    assert run.metadata["user_cancel_preserved"] is True


async def test_ai_user_cancel_should_preserve_full_user_input_and_reasoning(authenticated_client: AsyncClient) -> None:
    """用户停止首轮会话时，应完整保留用户输入、正文与已展示 reasoning。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止保留完整输入工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 停止保留完整输入项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 停止保留完整输入页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "停止保留完整输入会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-preserve-full-input"
    long_message = "请详细分析停止后是否保留历史。" * 80
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary=long_message,
            input_payload_json=build_agent_run_input_payload(message=long_message, image_attachment_ids=[]),
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="message.delta",
                run_id=run_id,
                session_id=session_id,
                content="",
                data={"reasoning_content": "先判断取消时机。"},
            ),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="已经输出的正文。"),
        )
        await service.mark_cancelling(task=task)

    response = await authenticated_client.post(f"/api/ai/runs/{run_id}/cancel", json={"force": True})
    assert response.status_code == 200

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == long_message
    assert messages[1]["content"] == "已经输出的正文。"
    assert messages[1]["reasoning_content"] == "先判断取消时机。"
    assert messages[0]["run_id"] == run_id
    assert messages[1]["run_id"] == run_id


async def test_ai_cancelled_runtime_snapshot_should_restore_tool_timeline(authenticated_client: AsyncClient, monkeypatch) -> None:
    """停止前的工具事件应从 runtime snapshot 恢复，且不伪造成 Agno tool 消息。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止工具恢复工作空间")
    session_id = "cancelled-tool-timeline-session"
    run_id = "run-preserve-tool-details"
    cancelled_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "停止工具恢复会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"workspace_id": workspace_id}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 2}},
                    },
                ],
                status=RunStatus.cancelled,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "cancelled-tool-timeline-session"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return cancelled_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=0,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    runtime_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={
            "workspace_id": workspace_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert runtime_response.status_code == 200, runtime_response.text
    runtime_payload = runtime_response.json()
    assert "messages" not in runtime_payload
    assert "tool_details" not in runtime_payload
    timeline_items = runtime_payload["timeline_items"]
    tool_items = [item for item in timeline_items if item["kind"] == "tool"]
    assert len(tool_items) == 1
    tool_item = tool_items[0]
    assert tool_item["run_id"] == run_id
    assert tool_item["tool"]["tool_name"] == "list_workspace_render_assets"
    assert tool_item["tool"]["status"] == "completed"
    assert tool_item["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert tool_item["tool"]["output_payload"] == {"total": 2}


async def test_ai_runtime_snapshot_should_attach_delegate_member_runs(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """delegate_task_to_member 触发的成员 run 应独立进入 member_runs，并从父时间线隐藏子工具。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 成员运行快照工作空间")
    session_id = "delegate-member-run-session"
    parent_run_id = "parent-run-delegate-member"
    member_run_id = "member-run-resource-manager"
    timeline_session = TeamSession(
        session_id=session_id,
        team_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "成员运行快照会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        team_data={"team_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            TeamRunOutput(
                run_id=parent_run_id,
                session_id=session_id,
                team_id=AGENT_COORDINATOR_AGENT_ID,
                team_name="内容助手",
                created_at=10,
                messages=[Message(role="user", content="整理资源")],
                events=[
                    {
                        "event": "TeamToolCallStarted",
                        "run_id": parent_run_id,
                        "tool": {
                            "tool_call_id": "delegate-call-resource",
                            "tool_name": "delegate_task_to_member",
                            "tool_args": {"member_id": RESOURCE_MANAGER_AGENT_ID, "task": "整理资源"},
                        },
                    },
                    {
                        "event": "TeamToolCallCompleted",
                        "run_id": parent_run_id,
                        "tool": {
                            "tool_call_id": "delegate-call-resource",
                            "tool_name": "delegate_task_to_member",
                            "result": {"success": True},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": member_run_id,
                        "parent_run_id": parent_run_id,
                        "agent_id": RESOURCE_MANAGER_AGENT_ID,
                        "agent_name": "资源助手",
                        "tool": {
                            "tool_call_id": "child-tool-list-assets",
                            "tool_name": "list_workspace_render_assets",
                            "tool_args": {"workspace_id": workspace_id},
                            "result": {"total": 2},
                        },
                    },
                ],
                member_responses=[
                    RunOutput(
                        run_id=member_run_id,
                        parent_run_id=parent_run_id,
                        session_id=session_id,
                        agent_id=RESOURCE_MANAGER_AGENT_ID,
                        agent_name="资源助手",
                        created_at=11,
                        messages=[Message(role="assistant", content="已整理资源。")],
                        events=[
                            {
                                "event": "ToolCallStarted",
                                "run_id": member_run_id,
                                "parent_run_id": parent_run_id,
                                "agent_id": RESOURCE_MANAGER_AGENT_ID,
                                "agent_name": "资源助手",
                                "tool": {
                                    "tool_call_id": "child-tool-list-assets",
                                    "tool_name": "list_workspace_render_assets",
                                    "tool_args": {"workspace_id": workspace_id},
                                },
                            },
                            {
                                "event": "ToolCallCompleted",
                                "run_id": member_run_id,
                                "parent_run_id": parent_run_id,
                                "agent_id": RESOURCE_MANAGER_AGENT_ID,
                                "agent_name": "资源助手",
                                "tool": {
                                    "tool_call_id": "child-tool-list-assets",
                                    "tool_name": "list_workspace_render_assets",
                                    "result": {"total": 2},
                                },
                            },
                        ],
                        status=RunStatus.completed,
                    )
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "delegate-member-run-session"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=1,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    parent_tools = [item["tool"]["tool_name"] for item in payload["timeline_items"] if item["kind"] == "tool"]
    assert parent_tools == ["delegate_task_to_member"]

    member_runs = payload["member_runs"]
    assert len(member_runs) == 1
    member_run = member_runs[0]
    assert member_run["parent_run_id"] == parent_run_id
    assert member_run["run_id"] == member_run_id
    assert member_run["agent_id"] == RESOURCE_MANAGER_AGENT_ID
    assert member_run["agent_name"] == "资源助手"
    assert member_run["delegate_tool_call_id"] == "delegate-call-resource"
    child_tool_items = [item for item in member_run["timeline_items"] if item["kind"] == "tool"]
    assert len(child_tool_items) == 1
    assert child_tool_items[0]["tool"]["tool_name"] == "list_workspace_render_assets"
    assert child_tool_items[0]["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert child_tool_items[0]["tool"]["output_payload"] == {"total": 2}


async def test_ai_timeline_should_keep_separate_missing_call_id_pairs(authenticated_client: AsyncClient, monkeypatch) -> None:
    """缺少 tool_call_id 的连续同名工具调用应按 started/completed 配对，不应互相覆盖。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具配对工作空间")
    run_id = "run-tool-pairs-without-call-id"
    session_id = "session-tool-pairs-without-call-id"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具配对会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="连续读取资源")],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"page": 1}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 1}},
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"page": 2}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 2}},
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-tool-pairs-without-call-id"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=1,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    tool_items = [item for item in response.json()["timeline_items"] if item["kind"] == "tool"]
    assert len(tool_items) == 2
    assert [item["tool"]["input_payload"] for item in tool_items] == [{"page": 1}, {"page": 2}]
    assert [item["tool"]["output_payload"] for item in tool_items] == [{"total": 1}, {"total": 2}]
    assert all(item["tool"]["tool_call_id"] is None for item in tool_items)


async def test_ai_runtime_timeline_should_interleave_message_fallback_with_tool_events(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """刷新恢复时应按 run 事件轴合并 messages fallback，避免 tool/thinking/message 分桶堆叠。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 时间线顺序工作空间")
    run_id = "run-interleaved-timeline"
    session_id = "session-interleaved-timeline"
    ask_user_tool = {
        "tool_call_id": "tool-ask-1",
        "tool_name": "ask_user",
        "tool_args": {"question": "是否继续整理资源？"},
        "requires_user_input": True,
        "user_feedback_schema": [
            {
                "question": "是否继续整理资源？",
                "header": "继续",
                "options": [
                    {"label": "继续", "description": "继续整理资源。"},
                    {"label": "停止", "description": "停止当前任务。"},
                ],
                "multi_select": False,
            }
        ],
    }
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "时间线顺序会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="检查资源后再问我要不要继续"),
                    Message(role="assistant", content="我先读取资源。", reasoning_content="先确认资源范围。"),
                    Message(
                        role="tool",
                        content='{"total": 2}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-1",
                        tool_args={"workspace_id": workspace_id},
                    ),
                    Message(role="assistant", content="资源已读取，接下来确认下一步。"),
                ],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-1",
                            "tool_args": {"workspace_id": workspace_id},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-1",
                            "result": {"total": 2},
                        },
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": ask_user_tool,
                    },
                    {
                        "event": "RunPaused",
                        "run_id": run_id,
                        "session_id": session_id,
                        "requirements": [{"id": "req-ask-1", "tool_execution": ask_user_tool}],
                        "tools": [ask_user_tool],
                    },
                ],
                status=RunStatus.paused,
                tools=[ToolExecution.from_dict(ask_user_tool)],
                requirements=[RunRequirement(tool_execution=ToolExecution.from_dict(ask_user_tool))],
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-interleaved-timeline"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=4,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert [item["order_index"] for item in timeline_items] == list(range(len(timeline_items)))
    assert [
        (item["kind"], item["role"], item["content"], item["tool"]["tool_name"] if item["tool"] else None)
        for item in timeline_items
    ] == [
        ("message", "user", "检查资源后再问我要不要继续", None),
        ("reasoning", None, "先确认资源范围。", None),
        ("message", "assistant", "我先读取资源。", None),
        ("tool", None, None, "list_workspace_render_assets"),
        ("message", "assistant", "资源已读取，接下来确认下一步。", None),
        ("tool", None, None, "ask_user"),
        ("requirement", None, "是否继续整理资源？", None),
        ("run_status", None, "等待用户处理。", None),
    ]


async def test_ai_runtime_timeline_should_preserve_post_tool_assistant_message_from_history(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """工具前已有流式 assistant 时，工具后的 assistant message 仍应按工具锚点补齐。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具后消息补齐工作空间")
    run_id = "run-post-tool-assistant-fallback"
    session_id = "session-post-tool-assistant-fallback"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具后消息补齐会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="先读取资源，再告诉我结论"),
                    Message(role="assistant", content="我先读取资源。"),
                    Message(
                        role="tool",
                        content='{"total": 2, "items": ["a", "b"]}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-post-message",
                        tool_args={"workspace_id": workspace_id},
                        tool_call_error=False,
                    ),
                    Message(role="assistant", content="资源读取完成，共 2 个。"),
                ],
                events=[
                    {
                        "event": "RunContent",
                        "run_id": run_id,
                        "content": "我先读取资源。",
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-post-message",
                            "tool_args": {"workspace_id": workspace_id},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "content": "工具调用完成。",
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-post-message",
                        },
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-post-tool-assistant-fallback"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=4)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert [
        (item["kind"], item["role"], item["content"], item["tool"]["tool_name"] if item["tool"] else None)
        for item in timeline_items
    ] == [
        ("message", "user", "先读取资源，再告诉我结论", None),
        ("message", "assistant", "我先读取资源。", None),
        ("tool", None, None, "list_workspace_render_assets"),
        ("message", "assistant", "资源读取完成，共 2 个。", None),
        ("run_status", None, "运行已完成。", None),
    ]
    tool_item = next(item for item in timeline_items if item["kind"] == "tool")
    assert tool_item["status"] == "completed"
    assert tool_item["tool"]["status"] == "completed"
    assert tool_item["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert tool_item["tool"]["output_payload"] == {"total": 2, "items": ["a", "b"]}
    assert tool_item["tool"]["message"] == "工具调用完成。"


async def test_ai_runtime_timeline_should_split_alternating_reasoning_and_content_events(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """reasoning 与 assistant 交替流出时，刷新恢复后不应分别合并成两大块。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 思考正文交替工作空间")
    run_id = "run-alternating-reasoning-content"
    session_id = "session-alternating-reasoning-content"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "思考正文交替会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="分步说明")],
                events=[
                    {"event": "ReasoningContentDelta", "run_id": run_id, "reasoning_content": "先判断。"},
                    {"event": "RunContent", "run_id": run_id, "content": "第一步。"},
                    {"event": "ReasoningContentDelta", "run_id": run_id, "reasoning_content": "再确认。"},
                    {"event": "RunContent", "run_id": run_id, "content": "第二步。"},
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-alternating-reasoning-content"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=1)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    assert [
        (item["kind"], item["role"], item["content"])
        for item in response.json()["timeline_items"]
    ] == [
        ("message", "user", "分步说明"),
        ("reasoning", None, "先判断。"),
        ("message", "assistant", "第一步。"),
        ("reasoning", None, "再确认。"),
        ("message", "assistant", "第二步。"),
        ("run_status", None, "运行已完成。"),
    ]


async def test_ai_runtime_timeline_should_not_render_structured_completed_payload_as_assistant(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """RunCompleted 的结构化聚合内容不应在刷新后显示成 assistant 正文。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 聚合完成事件工作空间")
    run_id = "run-structured-completed-payload"
    session_id = "session-structured-completed-payload"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "聚合完成事件会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="返回结构化结果")],
                events=[
                    {
                        "event": "RunCompleted",
                        "run_id": run_id,
                        "content": '{"messages": [{"role": "assistant", "content": "完成"}], "tools": []}',
                    }
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-structured-completed-payload"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=1)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    assert [
        (item["kind"], item["role"], item["content"])
        for item in response.json()["timeline_items"]
    ] == [
        ("message", "user", "返回结构化结果"),
        ("run_status", None, "运行已完成。"),
    ]


async def test_ai_runtime_timeline_should_anchor_answered_ask_user_to_pause_event(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """已回答的 ask_user 应回锚到暂停位置，不应在完成后保留 pending requirement 或堆到尾部。"""

    workspace_id = await _create_workspace(authenticated_client, "AI ask_user 回锚工作空间")
    run_id = "run-answered-ask-user-timeline"
    session_id = "session-answered-ask-user-timeline"
    ask_user_questions = [
        {
            "question": "请为这个甘特图组件指定一个中文名称？",
            "header": "组件名称",
            "options": [
                {"label": "项目甘特图", "description": "适用于项目管理场景。"},
                {"label": "任务甘特图", "description": "适用于任务排期场景。"},
            ],
            "multi_select": False,
        }
    ]
    ask_user_tool = {
        "tool_call_id": "call-ask-user-1",
        "tool_name": "ask_user",
        "tool_args": {"questions": ask_user_questions},
        "requires_user_input": True,
        "user_feedback_schema": ask_user_questions,
    }
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "ask_user 回锚会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="创建甘特图"),
                    Message(
                        role="tool",
                        content='User feedback received: [{"question": "请为这个甘特图组件指定一个中文名称？", "selected": ["任务甘特图"]}]',
                        tool_name="ask_user",
                        tool_call_id="call-ask-user-1",
                        tool_args={"questions": ask_user_questions},
                    ),
                    Message(role="assistant", content="已按任务甘特图继续创建。"),
                ],
                events=[
                    {
                        "event": "RunPaused",
                        "run_id": run_id,
                        "session_id": session_id,
                        "requirements": [{"id": "req-ask-user-1", "tool_execution": ask_user_tool}],
                        "tools": [ask_user_tool],
                    },
                    {
                        "event": "RunContent",
                        "run_id": run_id,
                        "content": "已按任务甘特图继续创建。",
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-answered-ask-user-timeline"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=3,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert not any(item["kind"] == "requirement" for item in timeline_items)
    ask_user_items = [item for item in timeline_items if item["tool"] and item["tool"]["tool_name"] == "ask_user"]
    assert len(ask_user_items) == 1
    assert ask_user_items[0]["event_index"] == 0
    assert ask_user_items[0]["status"] == "completed"
    assert ask_user_items[0]["tool"]["output_payload"].startswith("User feedback received")
    assert [item["kind"] for item in timeline_items] == ["message", "tool", "message", "run_status"]


async def test_ai_error_should_not_preserve_streamed_delta_in_agno_history(authenticated_client: AsyncClient) -> None:
    """普通执行报错时，已流出的半截内容不应补写进 Agno 历史。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 报错丢弃工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 报错丢弃项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 报错丢弃页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "报错丢弃会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-error-no-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[Message(role="user", content="请生成一段长内容")],
        ),
    )
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="请生成一段长内容",
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="这段不应保留"),
        )
        await service.mark_terminal(task=task, status="failed", error_message="模型调用失败。")

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["user"]


async def test_ai_run_event_append_should_retry_sequence_conflict(
    authenticated_client: AsyncClient,
) -> None:
    """Redis Stream 追加事件时应生成严格递增的 sequence。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 事件重试工作空间")
    run_id = "run-event-retry"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id="session-event-retry",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="事件重试",
        )
        event = await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.cancelling", run_id=run_id, session_id="session-event-retry"),
        )
        events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert event is not None
    assert event.sequence == 1
    assert [item.sequence for item in events] == [1]


async def test_ai_mark_paused_should_not_duplicate_event_with_stale_task(
    authenticated_client: AsyncClient,
) -> None:
    """恢复 UI 使用旧 task 补偿暂停态时，不应重复写入同一 pause 事件序号。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 暂停竞态工作空间")
    run_id = "run-stale-mark-paused"
    session_id = "session-stale-mark-paused"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-stale-pause",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as stale_session:
        stale_service = AiAgentRunService(stale_session)
        stale_task = await stale_service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="暂停竞态",
        )
        await stale_service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id),
        )

        async with get_session_factory()() as fresh_session:
            fresh_service = AiAgentRunService(fresh_session)
            fresh_task = await fresh_service.get_task_by_run(run_id=run_id, user_id=1)
            assert fresh_task is not None
            await fresh_service.mark_paused(task=fresh_task, pending_requirement=requirement)

        restored_task = await stale_service.mark_paused(task=stale_task, pending_requirement=requirement)
        events = await stale_service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert restored_task.status == "paused"
    assert restored_task.event_sequence == 2
    assert [event.event for event in events] == ["run.started", "run.paused"]
    assert [event.sequence for event in events] == [1, 2]


async def test_ai_mark_paused_should_not_reopen_terminal_run(
    authenticated_client: AsyncClient,
) -> None:
    """已完成 run 不应被 Agno 陈旧 requirement 重新覆盖成 paused。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 终态保护工作空间")
    run_id = "run-terminal-mark-paused"
    session_id = "session-terminal-mark-paused"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-terminal-pause",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="终态保护",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id),
        )
        restored_task = await service.mark_paused(task=task, pending_requirement=requirement)
        events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert restored_task.status == "completed"
    assert restored_task.pending_requirement_json is None
    assert [event.event for event in events] == ["run.completed"]


async def test_ai_session_stream_should_reject_second_active_run_in_same_session(authenticated_client: AsyncClient) -> None:
    """同一 Agno session 已存在非终态 run 时，应拒绝启动新 run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Session 串行工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Session 串行项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Session 串行页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Session 串行会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-active-session",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
        ),
    )

    second_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "同会话第二个 run"},
    )
    assert second_response.status_code == 409
    assert second_response.json()["code"] == "AI_SESSION_RUN_ACTIVE"


async def test_ai_session_stream_should_allow_different_session_when_another_session_is_running(authenticated_client: AsyncClient) -> None:
    """一个 session 的 active run 不应阻塞另一个 session 发起 run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Session 并行工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Session 并行项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Session 并行页面",
        content="<template><div>draft</div></template>",
    )

    session_ids: list[str] = []
    for index in range(2):
        session_response = await authenticated_client.post(
            "/api/ai/sessions",
            json={
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
                "session_name": f"后台并行会话 {index}",
                "scope": {
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                    "page_id": page_id,
                    "source": "editor-page-detail",
                },
            },
        )
        assert session_response.status_code == 201
        session_ids.append(session_response.json()["session_id"])

    await _append_test_run(
        authenticated_client,
        session_id=session_ids[0],
        run=RunOutput(
            run_id="run-other-session",
            session_id=session_ids[0],
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_ids[1]}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "另一个 session 可以启动"},
    )
    assert response.status_code == 200
    assert "AI_LLM_SLOT_UNBOUND" in response.text


async def test_ai_session_active_run_should_return_paused_requirement(authenticated_client: AsyncClient) -> None:
    """active-run 应从 Agno session.runs 读取 paused 状态并提取待确认动作。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Active Run 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Active Run 项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Active Run 页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Active Run 会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-paused-active",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.paused,
            tools=[
                ToolExecution.from_dict(
                    {
                        "tool_name": "apply_page_edits",
                        "tool_call_id": "tool-confirm-1",
                        "tool_args": {
                            "change_note": "测试确认",
                            "edits": [{"type": "replace_exact", "old_text": "draft", "new_text": "done"}],
                            "base_version_no": 1,
                        },
                        "requires_confirmation": True,
                    }
                )
            ],
        ),
    )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-paused-active"
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["tool_name"] == "apply_page_edits"
    assert payload["pending_requirement"]["tool_execution"]["tool_call_id"] == "tool-confirm-1"


async def test_ai_force_cancel_paused_confirmation_should_release_hitl(authenticated_client: AsyncClient) -> None:
    """强制释放工具确认 HITL 时，应取消 run 并清理确认 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Confirm 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Confirm 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    confirm_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-confirm",
            "tool_name": "delete_component",
            "tool_args": {"component_id": 1},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-force-confirm",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[confirm_tool],
            requirements=[RunRequirement(tool_execution=confirm_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-confirm"},
    )
    assert response.status_code == 200, response.text

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    assert active_response.json() is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run("run-force-confirm")
    assert run is not None
    assert run.status == RunStatus.cancelled
    assert not run.requirements
    assert run.tools[0].requires_confirmation is False
    assert run.tools[0].confirmed is False


async def test_ai_force_cancel_paused_feedback_should_release_hitl(authenticated_client: AsyncClient) -> None:
    """强制释放结构化提问 HITL 时，应取消 run 并清理回答 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Feedback 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Feedback 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-feedback",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "优先调整哪个区域？",
                    "header": "范围",
                    "options": [{"label": "首屏"}, {"label": "全页面"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-force-feedback",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-feedback"},
    )
    assert response.status_code == 200, response.text

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    assert active_response.json() is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run("run-force-feedback")
    assert run is not None
    assert run.status == RunStatus.cancelled
    assert not run.requirements
    assert run.tools[0].requires_user_input is False
    assert run.tools[0].answered is False


async def test_ai_force_cancel_paused_requirement_should_reject_stale_tool_call(
    authenticated_client: AsyncClient,
) -> None:
    """强制释放 HITL 时若 tool_call_id 已变化，应拒绝请求并保留原暂停态。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Stale 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Stale 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    confirm_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-current",
            "tool_name": "delete_component",
            "tool_args": {"component_id": 1},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-force-stale",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[confirm_tool],
            requirements=[RunRequirement(tool_execution=confirm_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-old"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "AI_RUN_REQUIREMENT_STALE"

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    payload = active_response.json()
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["tool_execution"]["tool_call_id"] == "tool-force-current"


async def test_ai_session_runtime_should_ignore_binary_images_in_active_run(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """runtime 快照恢复 active-run 时不应把历史图片 bytes 当 UTF-8 序列化。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Active Run 图片工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Active Run 图片项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Active Run 图片页面",
        content="<template><div>image</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Active Run 图片会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-active-image-bytes",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[
                Message(
                    role="user",
                    content="请分析这张图",
                    images=[Image(content=b"\x89PNG\r\n\x1a\n", mime_type="image/png", detail="auto")],
                )
            ],
        ),
    )

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=1,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["active_run"]["run_id"] == "run-active-image-bytes"
    assert payload["active_run"]["status"] == "running"
    assert payload["timeline_items"][0]["content"] == "请分析这张图"


async def test_ai_session_active_run_should_not_restore_requirement_from_completed_task(
    authenticated_client: AsyncClient,
) -> None:
    """completed task 应修正 Agno 终态残留，而不是恢复旧 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Feedback Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Feedback Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-completed-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-restore",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "options": [{"label": "首屏"}, {"label": "全页面"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.completed,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="触发结构化提问",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id, data={}),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload is None

    async with get_session_factory()() as db_session:
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
    assert task is not None
    assert task.status == "completed"
    assert task.pending_requirement_json is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert not run.requirements
    assert run.tools
    assert run.tools[0].requires_user_input is False
    assert run.tools[0].answered is True


async def test_ai_completed_confirmed_route_tool_should_cleanup_agno_hitl(
    authenticated_client: AsyncClient,
) -> None:
    """确认执行后的项目路由工具完成时，Agno session 不应残留旧确认弹窗。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Route HITL Cleanup 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Route HITL Cleanup 项目")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Route HITL Cleanup 会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-completed-route-confirm"
    route_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-route-confirm-cleanup",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.completed,
            tools=[route_tool],
            requirements=[RunRequirement(tool_execution=route_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="project",
        workspace_id=workspace_id,
        project_id=project_id,
        source="editor-agent-sidebar",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="确认路由树写入",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.completed",
                run_id=run_id,
                session_id=session_id,
                data={},
            ),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "scope_type": "project",
            "source": "editor-agent-sidebar",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_model, TeamSession)
    run = session_model.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert not run.requirements
    assert run.tools
    assert run.tools[0].requires_confirmation is False
    assert run.tools[0].confirmed is True


async def test_ai_session_active_run_should_restore_feedback_requirement_from_failed_task(
    authenticated_client: AsyncClient,
) -> None:
    """continue 失败后若 Agno 仍有未解决 ask_user，active-run 应恢复为 paused。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Feedback Failed Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Feedback Failed Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-failed-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-failed-restore",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "组件 default slot 的默认内容应如何处理？",
                    "header": "Slot 默认内容",
                    "options": [{"label": "完全清空"}, {"label": "保留占位"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.error,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="继续结构化提问失败",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.error",
                run_id=run_id,
                session_id=session_id,
                data={"message": "当前会话没有待继续的暂停运行。", "code": "AI_RUN_NOT_PAUSED"},
            ),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["kind"] == "user_feedback"
    assert payload["pending_requirement"]["tool_name"] == "ask_user"
    async with get_session_factory()() as db_session:
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
    assert task is not None
    assert task.status == "paused"
    assert task.pending_requirement_json is not None


async def test_ai_continue_active_events_should_accept_pending_requirement_on_failed_agno_run(monkeypatch) -> None:
    """Agno run 状态为 error 但 requirement 未解决时，continue 不应报没有暂停运行。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-continue",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "组件 default slot 的默认内容应如何处理？",
                    "header": "Slot 默认内容",
                    "options": [{"label": "完全清空"}, {"label": "保留占位"}],
                    "multi_select": False,
                }
            ],
        }
    )
    session_detail = AgentSession(
        session_id="continue-feedback-session",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-component-library"},
        runs=[
            RunOutput(
                run_id="continue-feedback-run",
                session_id="continue-feedback-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.error,
                tools=[ask_user_tool],
                requirements=[RunRequirement(tool_execution=ask_user_tool)],
            )
        ],
    )
    captured: dict[str, object] = {}

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_runtime_context(**_: object) -> AgentRuntimeContext:
        return AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")

    async def fake_continue_events(**kwargs: object):
        captured.update(kwargs)
        yield AgentRunEvent(
            event="run.continued",
            run_id="continue-feedback-run",
            session_id="continue-feedback-session",
            data={},
        )

    facade.ensure_session_access = fake_ensure_session_access
    facade.continue_events = fake_continue_events
    facade._session = SimpleNamespace()
    monkeypatch.setattr("app.ai.session_facade.build_agent_runtime_context", fake_build_agent_runtime_context)

    events = [
        event async for event in facade.continue_active_events(
            session_id="continue-feedback-session",
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library"),
            tool_execution={
                "tool_call_id": "tool-ask-continue",
                "tool_name": "ask_user",
            },
            decision=None,
            note=None,
            feedback_selections=[
                {
                    "question": "组件 default slot 的默认内容应如何处理？",
                    "selected_label": "完全清空",
                    "custom_text": None,
                }
            ],
            runtime_context=AgentRuntimeContext(
                scope_type="workspace",
                workspace_id=1,
                source="editor-component-library",
            ),
        )
    ]

    assert [event.event for event in events] == ["run.continued"]
    assert captured["run_id"] == "continue-feedback-run"
    merged_tool_execution = captured["tool_execution"]
    assert isinstance(merged_tool_execution, dict)
    assert merged_tool_execution["tool_call_id"] == "tool-ask-continue"
    assert merged_tool_execution["requires_user_input"] is True
    assert len(merged_tool_execution["user_feedback_schema"]) == 1


async def test_ai_stream_should_release_session_lock_after_pause_event() -> None:
    """后台流收到 run.paused 后应主动收束，避免待确认 run 长时间占住会话锁。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    session_id = f"pause-lock-session-{uuid4()}"
    run_id = f"pause-lock-run-{uuid4()}"
    agent_id = COMPONENT_MANAGER_AGENT_ID
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")
    runtime_context = AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")
    pause_payload = {
        "event": "RunPaused",
        "run_id": run_id,
        "session_id": session_id,
        "requirements": [
            {
                "tool_execution": {
                    "tool_call_id": "tool-pause-lock",
                    "tool_name": "delete_component",
                    "tool_args": {"component_id": 1},
                    "requires_confirmation": True,
                },
            }
        ],
    }

    async def fake_ensure_session_access(**_: object) -> object:
        return SimpleNamespace(metadata={})

    async def fake_context_status_event(**kwargs: object) -> AgentRunEvent:
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=session_id,
            data={},
        )

    async def paused_then_never_finishes():
        yield pause_payload
        await asyncio.Event().wait()

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=paused_then_never_finishes(), run_id=run_id)

    facade.ensure_session_access = fake_ensure_session_access
    facade._build_context_status_event = fake_context_status_event
    lock = facade._get_session_run_lock(session_id=session_id, agent_id=agent_id)

    async def collect_events() -> list[AgentRunEvent]:
        return [
            event
            async for event in facade._stream_agno_events(
                agent_id=agent_id,
                session_id=session_id,
                scope=scope,
                runtime_context=runtime_context,
                stream_builder=fake_stream_builder,
            )
        ]

    events = await asyncio.wait_for(collect_events(), timeout=1)

    assert [event.event for event in events] == ["context.status", "context.status", "run.paused"]
    assert not lock.locked()


async def test_ai_run_stream_should_refresh_context_status_at_message_checkpoints() -> None:
    """长 run 中内容完成和工具完成检查点应推送包含临时历史的上下文状态。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    session_id = "session-checkpoint-1"
    run_id = "run-checkpoint-1"
    agent_id = AGENT_COORDINATOR_AGENT_ID
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar")
    runtime_context = AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar")
    snapshots: list[list[tuple[str | None, object, str | None]]] = []

    async def fake_ensure_session_access(**_: object) -> object:
        return SimpleNamespace(metadata={})

    async def fake_context_status_event(**kwargs: object) -> AgentRunEvent:
        extra_history = list(kwargs.get("extra_history_messages") or [])
        snapshots.append([
            (
                getattr(message, "role", None),
                getattr(message, "content", None),
                getattr(message, "tool_name", None),
            )
            for message in extra_history
        ])
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=session_id,
            data={"message_count": len(extra_history)},
        )

    async def checkpoint_stream():
        yield {"event": "RunStarted", "run_id": run_id, "session_id": session_id, "agent_id": agent_id}
        yield {"event": "RunContent", "run_id": run_id, "session_id": session_id, "content": "第一段回复"}
        yield {"event": "RunContentCompleted", "run_id": run_id, "session_id": session_id, "content": "第一段回复"}
        yield {
            "event": "ToolCallStarted",
            "run_id": run_id,
            "session_id": session_id,
            "tool": {
                "tool_name": "list_workspace_components",
                "tool_call_id": "tool-call-1",
                "tool_args": {"workspace_id": 1},
            },
        }
        yield {
            "event": "ToolCallCompleted",
            "run_id": run_id,
            "session_id": session_id,
            "content": "list_workspace_components completed.",
            "tool": {
                "tool_name": "list_workspace_components",
                "tool_call_id": "tool-call-1",
                "result": {"total": 2},
            },
        }
        yield {"event": "RunCompleted", "run_id": run_id, "session_id": session_id, "content": "最终回复"}

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=checkpoint_stream(), run_id=run_id)

    facade.ensure_session_access = fake_ensure_session_access
    facade._build_context_status_event = fake_context_status_event

    events = [
        event
        async for event in facade._stream_agno_events(
            agent_id=agent_id,
            session_id=session_id,
            scope=scope,
            runtime_context=runtime_context,
            initial_history_messages=[SimpleNamespace(role="user", content="开始")],
            stream_builder=fake_stream_builder,
        )
    ]

    assert [event.event for event in events] == [
        "context.status",
        "run.started",
        "message.delta",
        "context.status",
        "tool.started",
        "tool.completed",
        "context.status",
        "context.status",
        "run.completed",
    ]
    assert snapshots[0] == [("user", "开始", None)]
    assert ("assistant", "第一段回复", None) in snapshots[1]
    assert ("tool", {"total": 2}, "list_workspace_components") in snapshots[2]
    assert ("assistant", "最终回复", None) in snapshots[3]


async def test_ai_startup_recovery_should_keep_interrupted_feedback_run_paused(
    authenticated_client: AsyncClient,
) -> None:
    """服务重启恢复时，已进入 ask_user 的 running task 不应被取消。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Startup Feedback Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Startup Feedback Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-startup-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-startup",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "预览 presets 中如何体现 slot 内容？",
                    "header": "Presets 策略",
                    "options": [{"label": "仅文字描述"}, {"label": "描述加源码"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="重启前进入结构化提问",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id, data={}),
        )

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    async with get_session_factory()() as db_session:
        recovered_count = await AiAgentRunService(db_session).recover_interrupted_tasks(ai_db=app.state.ai_db)
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
        events = await AiAgentRunService(db_session).list_events_after(
            run_id=run_id,
            user_id=1,
            after_sequence=0,
        )

    assert recovered_count >= 1
    assert task is not None
    assert task.status == "paused"
    assert task.pending_requirement_json is not None
    assert task.pending_requirement_json["kind"] == "user_feedback"
    assert [event.event for event in events] == ["run.started", "run.paused"]


async def test_ai_continue_stream_should_not_reinject_current_run_history() -> None:
    """继续 paused run 时不应重复注入当前 run 历史，避免 DeepSeek 工具链顺序校验失败。"""

    class EmptyAsyncIterator:
        """提供空的 Agno 事件流。"""

        def __aiter__(self) -> "EmptyAsyncIterator":
            return self

        async def __anext__(self) -> object:
            raise StopAsyncIteration

    class FakeAgent:
        """记录 continue_run 前的历史注入配置。"""

        def __init__(self) -> None:
            self.add_history_to_context = True
            self.add_history_value_when_continued: bool | None = None
            self.continue_kwargs: dict[str, object] = {}

        def acontinue_run(self, **kwargs: object) -> EmptyAsyncIterator:
            self.add_history_value_when_continued = self.add_history_to_context
            self.continue_kwargs = kwargs
            return EmptyAsyncIterator()

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade._registry = SimpleNamespace(
        get_descriptor=lambda agent_id: SimpleNamespace(id=agent_id, llm_slot="component_manager")
    )
    facade._agent_config_service = SimpleNamespace(
        get_effective_runtime_config=lambda agent_id: _async_value(SimpleNamespace())
    )
    facade._llm_service = SimpleNamespace(
        get_bound_config_or_raise=lambda slot: _async_value(SimpleNamespace(supports_image_input=False))
    )
    session_detail = AgentSession(
        session_id="continue-session-1",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-agent-sidebar"},
        runs=[
            RunOutput(
                run_id="continue-run-1",
                session_id="continue-session-1",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.paused,
                messages=[
                    Message(role="user", content="创建组件"),
                    Message(
                        role="assistant",
                        content="准备创建组件",
                        reasoning_content="先整理组件参数",
                        tool_calls=[
                            {
                                "id": "call-create-1",
                                "type": "function",
                                "function": {"name": "create_component", "arguments": "{}"},
                            }
                        ],
                    ),
                ],
            )
        ],
    )
    fake_agent = FakeAgent()

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_for_descriptor(*_: object, **__: object) -> tuple[FakeAgent, dict[str, object]]:
        return fake_agent, {}

    async def fake_set_existing_run_status(**_: object) -> None:
        return None

    async def fake_sync_requirement_decision(**_: object) -> None:
        return None

    facade.ensure_session_access = fake_ensure_session_access
    facade._resolve_run_session_metadata = lambda **kwargs: dict(kwargs["metadata"])
    facade._build_agent_for_descriptor = fake_build_agent_for_descriptor
    facade._build_tool_dependencies = lambda **_: {}
    facade._set_existing_run_status = fake_set_existing_run_status
    facade._sync_agno_requirement_decision_before_continue = fake_sync_requirement_decision

    builder = facade._build_continue_stream(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_id="continue-session-1",
        scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
        run_id="continue-run-1",
        updated_tool_execution={
            "tool_call_id": "call-create-1",
            "tool_name": "create_component",
            "confirmed": True,
        },
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )

    active_stream = await builder()

    assert active_stream.agent is fake_agent
    assert fake_agent.add_history_value_when_continued is False
    assert "updated_tools" not in fake_agent.continue_kwargs
    requirements = fake_agent.continue_kwargs["requirements"]
    assert len(requirements) == 1
    assert requirements[0].tool_execution.tool_call_id == "call-create-1"


async def test_ai_new_run_should_inject_cancelled_history_to_model_context() -> None:
    """新 run 构造模型上下文时应包含已补偿的 cancelled 历史，且不重复启用 Agno 默认历史。"""

    class EmptyAsyncIterator:
        """提供空的 Agno 事件流。"""

        def __aiter__(self) -> "EmptyAsyncIterator":
            return self

        async def __anext__(self) -> object:
            raise StopAsyncIteration

    class FakeAgent:
        """记录 arun 收到的历史注入参数。"""

        def __init__(self) -> None:
            self.add_history_to_context = True
            self.additional_input: list[Message] | None = None
            self.num_history_runs = None
            self.num_history_messages = 20
            self.max_tool_calls_from_history = 4
            self.system_message_role = "system"
            self.run_kwargs: dict[str, object] = {}

        def arun(self, *_: object, **kwargs: object) -> EmptyAsyncIterator:
            self.run_kwargs = kwargs
            return EmptyAsyncIterator()

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade._session = None
    facade._registry = SimpleNamespace(
        get_descriptor=lambda agent_id: SimpleNamespace(id=agent_id, llm_slot="component_manager")
    )
    facade._agent_config_service = SimpleNamespace(
        get_effective_runtime_config=lambda agent_id: _async_value(SimpleNamespace())
    )
    facade._llm_service = SimpleNamespace(
        get_bound_config_or_raise=lambda slot: _async_value(SimpleNamespace(supports_image_input=False))
    )
    session_detail = AgentSession(
        session_id="cancelled-history-session",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-agent-sidebar"},
        runs=[
            RunOutput(
                run_id="run-completed-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.completed,
                messages=[
                    Message(role="user", content="上一轮完整问题"),
                    Message(role="assistant", content="上一轮完整回答"),
                ],
            ),
            RunOutput(
                run_id="run-cancelled-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.cancelled,
                messages=[
                    Message(role="user", content="被停止的用户问题"),
                    Message(role="assistant", content="被停止前的局部回答", reasoning_content="已暴露思考"),
                ],
            ),
            RunOutput(
                run_id="run-cancelled-empty-messages",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.cancelled,
                input=RunInput(input_content="被停止但未写 messages 的问题"),
                content="被停止前已输出的回答",
                reasoning_content="被停止前已输出的思考",
                messages=[],
            ),
            RunOutput(
                run_id="run-error-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.error,
                messages=[Message(role="user", content="错误 run 不应进入模型历史")],
            ),
        ],
    )
    fake_agent = FakeAgent()

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_for_descriptor(*_: object, **__: object) -> tuple[FakeAgent, dict[str, object]]:
        return fake_agent, {}

    async def fake_upsert_run_marker(**_: object) -> None:
        return None

    facade.ensure_session_access = fake_ensure_session_access
    facade._resolve_run_session_metadata = lambda **kwargs: dict(kwargs["metadata"])
    facade._build_agent_for_descriptor = fake_build_agent_for_descriptor
    facade._build_tool_dependencies = lambda **_: {}
    facade._upsert_run_marker = fake_upsert_run_marker
    facade._ai_db = SimpleNamespace(upsert_session=lambda detail: None)

    builder = facade._build_run_stream(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_id="cancelled-history-session",
        scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
        message="继续处理",
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
        run_id="run-next",
    )

    active_stream = await builder()

    assert active_stream.agent is fake_agent
    assert fake_agent.add_history_to_context is False
    assert fake_agent.run_kwargs["add_history_to_context"] is False
    assert fake_agent.additional_input is not None
    assert [message.content for message in fake_agent.additional_input] == [
        "上一轮完整问题",
        "上一轮完整回答",
        "被停止的用户问题",
        "被停止前的局部回答",
        "被停止但未写 messages 的问题",
        "被停止前已输出的回答",
    ]
    assert all(message.from_history for message in fake_agent.additional_input)
    assert fake_agent.additional_input[-3].reasoning_content == "已暴露思考"
    assert fake_agent.additional_input[-1].reasoning_content == "被停止前已输出的思考"


def test_ai_resolve_requirement_payload_should_use_latest_active_requirement() -> None:
    """连续 HITL 暂停时应展示最新未处理动作，避免把旧 tool_call_id 再次提交给 Agno。"""

    requirement = _resolve_requirement_payload(
        {
            "requirements": [
                {
                    "id": "old-requirement",
                    "tool_execution": {
                        "tool_call_id": "call-old",
                        "tool_name": "apply_component_edits",
                        "requires_confirmation": True,
                    },
                },
                {
                    "id": "new-requirement",
                    "tool_execution": {
                        "tool_call_id": "call-new",
                        "tool_name": "update_component_metadata",
                        "requires_confirmation": True,
                    },
                },
            ],
        }
    )

    assert requirement is not None
    assert requirement["id"] == "new-requirement"
    assert requirement["tool_execution"]["tool_call_id"] == "call-new"


def test_ai_history_policy_should_scale_with_model_context_window() -> None:
    """动态历史策略应随模型上下文变化，不再固定为 20 条 run。"""

    class Config:
        def __init__(self, *, context_window_tokens: int) -> None:
            self.context_window_tokens = context_window_tokens
            self.max_output_tokens = 1024
            self.history_token_ratio = 0.5

    small_policy = build_history_policy(Config(context_window_tokens=4096), current_input="请改写页面")
    large_policy = build_history_policy(Config(context_window_tokens=128000), current_input="请改写页面")

    assert small_policy.num_history_messages < large_policy.num_history_messages
    assert small_policy.num_history_messages != 20


def test_ai_history_policy_should_trigger_compression_by_token_budget() -> None:
    """历史 token 超过预算时应触发压缩，并按压缩目标保留最近原文。"""

    class Config:
        context_window_tokens = 4096
        max_output_tokens = 1024
        history_token_ratio = 0.4
        compression_target_ratio = 0.1

    messages = [
        Message(role="user", content=f"第 {index} 条历史 " + "长文本" * 240)
        for index in range(24)
    ]

    policy = build_history_policy(Config(), current_input="继续", history_messages=messages)

    assert policy.compression_required is True
    assert policy.history_budget_tokens > policy.compression_target_tokens
    assert policy.estimated_history_tokens > policy.history_budget_tokens
    assert policy.retained_recent_history_tokens <= policy.compression_target_tokens
    assert 0 < policy.num_history_messages < len(messages)


def test_ai_history_policy_should_expand_budget_with_history_ratio() -> None:
    """提高历史上下文比例应增加历史预算，但压缩目标由独立比例控制。"""

    class Config:
        context_window_tokens = 32_000
        max_output_tokens = 4096
        compression_target_ratio = 0.2

        def __init__(self, history_token_ratio: float) -> None:
            self.history_token_ratio = history_token_ratio

    small_budget = build_history_policy(Config(0.2), current_input="继续")
    large_budget = build_history_policy(Config(0.7), current_input="继续")

    assert small_budget.history_budget_tokens < large_budget.history_budget_tokens
    assert large_budget.compression_target_tokens == 6400


async def _append_test_run(authenticated_client: AsyncClient, *, session_id: str, run: RunOutput | TeamRunOutput) -> None:
    """向测试应用的 Agno session.runs 写入 run，模拟已持久化运行状态。"""

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    if isinstance(session_model, TeamSession):
        if isinstance(run, RunOutput) and getattr(run, "agent_id", None) == AGENT_COORDINATOR_AGENT_ID:
            run = TeamRunOutput(
                run_id=run.run_id,
                session_id=run.session_id,
                team_id=AGENT_COORDINATOR_AGENT_ID,
                user_id=run.user_id,
                messages=run.messages,
                content=run.content,
                status=run.status,
                metadata=run.metadata,
                requirements=run.requirements,
                tools=run.tools,
            )
        session_model.upsert_run(run)
        await asyncio.to_thread(app.state.ai_db.upsert_session, session_model)
        return
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    session_model.upsert_run(run)
    await asyncio.to_thread(app.state.ai_db.upsert_session, session_model)


def _encode_sse(event: AgentRunEvent) -> bytes:
    """把测试用事件编码为简单 SSE 数据块。"""

    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n".encode("utf-8")
