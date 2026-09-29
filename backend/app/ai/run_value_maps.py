"""文件功能：把 AI 运行态 ORM 模型映射为 Agent 接口 Schema。"""

from __future__ import annotations

from typing import Any

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.models.ai_agent_runtime import (
    AiAgentMessage,
    AiAgentRun,
    AiAgentSession,
    AiAgentToolCall,
)
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentContextStatusItem,
    AgentMessageAttachmentItem,
    AgentMessageItem,
    AgentPendingRequirement,
    AgentScopeContext,
    AgentSessionItem,
    AgentTimelineItem,
    AgentTimelineToolItem,
)


def iso(value):
    """把 datetime 转为带 UTC 偏移的接口字符串，历史 naive 值直接补 UTC。"""

    from app.core.time_utils import normalize_utc

    return normalize_utc(value).isoformat() if value is not None else None


def map_run_status(status: str) -> str:
    """把数据库状态映射为接口状态枚举。"""

    if status == "failed":
        return "failed"
    if status in {"pending", "running", "paused", "waiting_external", "cancelling", "completed", "cancelled"}:
        return status
    return "failed"


def map_session_item(model: AiAgentSession) -> AgentSessionItem:
    """把会话 ORM 映射为接口模型。"""

    return AgentSessionItem(
        session_id=model.session_id,
        agent_id=model.agent_id,
        workspace_id=model.workspace_id,
        session_name=model.session_name,
        focus_mode=model.focus_mode,
        pinned_project_id=model.pinned_project_id,
        work_scope_mode=model.work_scope_mode,
        allowed_project_ids=list(model.allowed_project_ids_json or []),
        focus_version=model.focus_version,
        created_at=iso(model.created_at),
        updated_at=iso(model.updated_at),
        metadata=dict(model.metadata_json or {}),
    )


def map_message_item(model: AiAgentMessage) -> AgentMessageItem:
    """把消息 ORM 映射为接口模型。"""

    return AgentMessageItem(
        id=str(model.id),
        run_id=model.run_id,
        role=model.role,  # type: ignore[arg-type]
        content=model.content,
        reasoning_content=model.reasoning_content,
        created_at=iso(model.created_at),
        attachments=[
            AgentMessageAttachmentItem.model_validate(item)
            for item in (model.attachments_json or [])
            if isinstance(item, dict)
        ],
    )


def map_active_run(model: AiAgentRun | None) -> AgentActiveRunItem | None:
    """把 run ORM 映射为 active/last run 接口模型。"""

    if model is None:
        return None
    pending_requirement = None
    if model.status in {"paused", "waiting_external"} and isinstance(model.pending_requirement_json, dict):
        pending_requirement = AgentPendingRequirement.model_validate(model.pending_requirement_json)
    run_input = model.input_payload_json or {}
    focus_payload = run_input.get("focus") if isinstance(run_input.get("focus"), dict) else {}
    return AgentActiveRunItem(
        run_id=model.run_id,
        session_id=model.session_id,
        agent_id=model.agent_id,
        status=map_run_status(model.status),
        focus=AgentScopeContext.model_validate({
            "scope_type": model.scope_type,
            "workspace_id": model.workspace_id,
            "project_id": model.project_id,
            "page_id": model.page_id,
            "component_id": model.component_id,
            "source": model.source,
            **focus_payload,
        }),
        work_scope_mode=str(run_input.get("work_scope_mode") or "workspace"),
        allowed_project_ids=list(run_input.get("allowed_project_ids") or []),
        focus_version=int(run_input.get("focus_version") or 0),
        pending_requirement=pending_requirement,
        content=model.content,
        created_at=iso(model.created_at),
        updated_at=iso(model.updated_at),
        cancel_requested_at=iso(model.cancel_requested_at),
        event_index=model.event_index,
        llm=dict(model.llm_config_snapshot_json) if isinstance(model.llm_config_snapshot_json, dict) else None,
        error_code=model.error_code,
        error_message=model.error_message,
    )


def build_context_status(
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext,
) -> AgentContextStatusItem:
    """构建无模型配置时的上下文状态兜底；真实 usage 缺失按 0 返回。"""

    _ = runtime_context
    return AgentContextStatusItem(
        session_id=session_id,
        agent_id=agent_id,
        compression_enabled=False,
        compression_required=False,
        compression_status="idle",
        compression_method="none",
        compression_error_message=None,
        summary_available=False,
        summary=None,
        topics=[],
        summary_updated_at=None,
        budget_policy_version="none",
        context_window_tokens=0,
        required_model_context_tokens=0,
        request_output_tokens=0,
        runtime_headroom_tokens=0,
        compression_trigger_tokens=0,
        max_output_tokens=0,
        history_token_ratio=0,
        compression_target_ratio=0,
        safety_margin_tokens=0,
        current_input_tokens=0,
        fixed_context_tokens=0,
        history_budget_tokens=0,
        compression_target_tokens=0,
        estimated_history_tokens=0,
        retained_recent_history_tokens=0,
        retained_recent_message_count=0,
        context_input_budget_tokens=0,
        context_used_tokens=0,
        context_remaining_tokens=0,
        last_input_tokens=0,
        last_output_tokens=0,
        last_total_tokens=0,
        last_reasoning_tokens=0,
    )


def tool_timeline_item(tool_call: AiAgentToolCall, *, order_index: int) -> AgentTimelineItem:
    """把工具调用映射为 timeline item。"""

    return AgentTimelineItem(
        id=f"tool-{tool_call.id}",
        session_id=tool_call.session_id,
        run_id=tool_call.run_id,
        kind="tool",
        role=None,
        event_index=None,
        order_index=order_index,
        content=None,
        status=tool_call.status,
        tool=AgentTimelineToolItem(
            tool_call_id=tool_call.tool_call_id,
            tool_name=tool_call.tool_name,
            status=tool_call.status if tool_call.status in {"running", "waiting_external", "completed", "error", "cancelled", "interrupted"} else "running",  # type: ignore[arg-type]
            input_payload=tool_call.input_payload_json,
            output_payload=tool_call.output_payload_json,
            message=tool_call.message or "",
        ),
        source="event",
        created_at=iso(tool_call.created_at),
    )


def scope_metadata(scope: AgentScopeContext) -> dict[str, Any]:
    """把 scope 转成会话 metadata。"""

    return scope.model_dump(mode="json")
