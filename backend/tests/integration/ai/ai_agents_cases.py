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










































































































































async def _collect_chunks(stream) -> list[bytes]:  # type: ignore[no-untyped-def]
    """收集异步字节流，供 raw SSE 收束测试验证不会卡住。"""

    return [chunk async for chunk in stream]






































































































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

__all__ = [name for name in globals() if not name.startswith("__")]
