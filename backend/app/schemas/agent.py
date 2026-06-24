"""文件功能：定义 Editor 内容助手使用的请求、响应、会话命名与流式事件模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import SchemaBase


class AgentScopeContext(SchemaBase):
    """描述一次 Agent 交互绑定的业务范围，兼容旧页面级 metadata。"""

    scope_type: Literal["workspace", "project", "page", "component"] = "page"
    workspace_id: int
    project_id: int | None = None
    page_id: int | None = None
    component_id: int | None = None
    workspace_name: str | None = None
    project_name: str | None = None
    page_title: str | None = None
    component_name: str | None = None
    source: str = "editor-page-detail"


class AgentDescriptor(SchemaBase):
    """返回给 Editor 的 Agent 描述信息。"""

    id: str
    name: str
    icon: str
    summary: str
    default_session_name: str
    capabilities: list[str] = Field(default_factory=list)
    scope_type: Literal["workspace", "project", "page", "component"]
    entry_kind: Literal["agent", "team"] = "agent"
    available: bool = True
    unavailable_reason: str | None = None
    llm_slot: str | None = None
    llm_binding_ready: bool = False
    bound_llm_name: str | None = None
    bound_provider_label: str | None = None
    supports_image_input: bool = False
    prompt_customized: bool = False
    enabled_tool_count: int = 0
    disabled_tool_count: int = 0
    scope: AgentScopeContext


class AgentSessionItem(SchemaBase):
    """Agent 会话列表项。"""

    session_id: str
    agent_id: str
    session_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessageItem(SchemaBase):
    """Agent 会话消息项，统一给 Editor 渲染消息流。"""

    id: str
    run_id: str | None = None
    role: Literal["user", "assistant", "tool"]
    content: str
    reasoning_content: str | None = None
    created_at: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: Any | None = None
    tool_call_error: bool | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list["AgentMessageAttachmentItem"] = Field(default_factory=list)


class AgentImageAttachmentItem(SchemaBase):
    """返回给 Editor 的会话图片附件信息。"""

    id: int
    session_id: str
    source_kind: Literal["user_upload", "tool_output"] = "user_upload"
    original_name: str
    content_type: str
    file_size: int
    sha256: str
    url: str
    preview_available: bool = True
    promoted_asset_id: int | None = None
    status: str
    created_at: str | None = None


class AgentMessageAttachmentItem(SchemaBase):
    """会话历史消息中展示的图片附件摘要。"""

    id: int
    source_kind: Literal["user_upload", "tool_output"] = "user_upload"
    original_name: str
    content_type: str
    file_size: int
    url: str
    preview_available: bool = True
    promoted_asset_id: int | None = None


class AgentImageAttachmentPromoteRequest(BaseModel):
    """将会话图片附件保存为工作空间资源的请求体。"""

    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    tags: list[str] = Field(default_factory=list)
    overwrite: bool = False


class AgentContextStatusItem(SchemaBase):
    """Agent 会话上下文预算、压缩状态与摘要详情。"""

    session_id: str
    agent_id: str
    compression_enabled: bool
    compression_required: bool
    compression_status: Literal["idle", "compressing", "compressed", "failed"] = "idle"
    compression_method: Literal["none", "model", "deterministic_fallback"] = "none"
    compression_error_message: str | None = None
    summary_available: bool
    summary: str | None = None
    topics: list[str] = Field(default_factory=list)
    summary_updated_at: str | None = None
    context_window_tokens: int
    max_output_tokens: int
    history_token_ratio: float
    compression_target_ratio: float
    safety_margin_tokens: int
    current_input_tokens: int
    fixed_context_tokens: int
    history_budget_tokens: int
    compression_target_tokens: int
    estimated_history_tokens: int
    retained_recent_history_tokens: int
    retained_recent_message_count: int
    context_input_budget_tokens: int
    context_used_tokens: int
    context_remaining_tokens: int
    last_input_tokens: int
    last_output_tokens: int
    last_total_tokens: int
    last_reasoning_tokens: int


class AgentSuggestedPatch(SchemaBase):
    """待确认写入动作附带的页面改动建议。"""

    tool_name: str
    target_page_id: int
    change_note: str | None = None
    proposed_content: str
    unified_diff: str


class AgentPendingRequirement(SchemaBase):
    """表示当前 run 暂停后等待用户决策的 HITL 动作。"""

    id: str | None = None
    kind: Literal["confirmation", "user_feedback"] = "confirmation"
    run_id: str
    session_id: str
    member_agent_id: str | None = None
    member_agent_name: str | None = None
    member_run_id: str | None = None
    tool_name: str | None = None
    tool_execution: dict[str, Any] = Field(default_factory=dict)
    suggested_patch: AgentSuggestedPatch | None = None
    user_feedback_schema: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class AgentRunEvent(SchemaBase):
    """给 Editor 流式分发的统一事件载荷。"""

    event: str
    run_id: str | None = None
    session_id: str | None = None
    content: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    sequence: int | None = None
    event_index: int | None = None


AgentActiveRunStatus = Literal["pending", "running", "paused", "cancelling", "completed", "cancelled", "failed"]


class AgentActiveRunItem(SchemaBase):
    """当前会话最近一次智能体运行状态。"""

    run_id: str
    session_id: str
    agent_id: str
    status: AgentActiveRunStatus
    pending_requirement: AgentPendingRequirement | None = None
    content: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    cancel_requested_at: str | None = None
    event_index: int = -1


class AgentRunStartResponse(SchemaBase):
    """启动后台 run 后返回给 Editor 的订阅游标。"""

    run_id: str
    session_id: str
    status: Literal["pending", "running"] = "pending"
    event_index: int = -1


class AgentTimelineToolItem(SchemaBase):
    """时间线中的工具调用详情，独立于 assistant 消息存在。"""

    tool_call_id: str | None = None
    tool_name: str
    member_agent_id: str | None = None
    member_agent_name: str | None = None
    member_run_id: str | None = None
    status: Literal["running", "completed", "error"]
    input_payload: Any | None = None
    output_payload: Any | None = None
    message: str = ""


class AgentTimelineItem(SchemaBase):
    """按 session/run/event_index 派生的会话时间线项。"""

    id: str
    session_id: str
    run_id: str
    kind: Literal["message", "reasoning", "tool", "run_status", "requirement"]
    role: Literal["user", "assistant"] | None = None
    event_index: int | None = None
    order_index: int
    content: str | None = None
    status: str | None = None
    tool: AgentTimelineToolItem | None = None
    attachments: list[AgentMessageAttachmentItem] = Field(default_factory=list)
    source: Literal["message", "event", "synthetic"]
    created_at: str | None = None


class AgentMemberRunItem(SchemaBase):
    """内容助手委派成员助手后形成的子 run 运行明细。"""

    parent_run_id: str
    run_id: str
    agent_id: str
    agent_name: str | None = None
    status: AgentActiveRunStatus
    created_at: str | None = None
    updated_at: str | None = None
    delegate_tool_call_id: str | None = None
    input_prompt: str | None = None
    output_prompt: str | None = None
    timeline_items: list[AgentTimelineItem] = Field(default_factory=list)


class AgentSessionRuntimeSnapshot(SchemaBase):
    """会话运行时快照，供 Editor 刷新和切会话后一次性恢复状态。"""

    session: AgentSessionItem
    timeline_items: list[AgentTimelineItem] = Field(default_factory=list)
    member_runs: list[AgentMemberRunItem] = Field(default_factory=list)
    context_status: AgentContextStatusItem
    active_run: AgentActiveRunItem | None = None
    last_run: AgentActiveRunItem | None = None
    pending_requirement: AgentPendingRequirement | None = None
    event_index: int = -1
    pending_attachments: list[AgentImageAttachmentItem] = Field(default_factory=list)


class CreateAgentSessionRequest(BaseModel):
    """创建 Agent 会话的请求体。"""

    agent_id: str = "agent-coordinator"
    session_name: str | None = Field(default=None, max_length=128)
    scope: AgentScopeContext
    llm_config_id: int | None = Field(default=None, ge=1)


class RenameAgentSessionRequest(BaseModel):
    """重命名或自动命名 Agent 会话的请求体。"""

    session_name: str | None = Field(default=None, min_length=1, max_length=128)
    autogenerate: bool = False

    @model_validator(mode="after")
    def validate_payload(self) -> "RenameAgentSessionRequest":
        """确保请求至少提供一个命名来源，避免产生空操作。"""

        if self.autogenerate:
            return self
        if self.session_name:
            return self
        raise ValueError("session_name 与 autogenerate 至少提供其一。")


class AgentRunRequest(BaseModel):
    """向 Agent 发送消息并启动一次 run 的请求体。"""

    run_id: str | None = Field(default=None, max_length=64)
    message: str = ""
    image_attachment_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_message_or_images(self) -> "AgentRunRequest":
        """允许图片-only run，但不允许空消息且无图片附件。"""

        if self.message.strip() or self.image_attachment_ids:
            return self
        raise ValueError("message 与 image_attachment_ids 至少提供其一。")


class AgentContinueRunRequest(BaseModel):
    """继续一个已暂停 run 的请求体。"""

    decision: Literal["confirm", "reject"] | None = None
    note: str | None = Field(default=None, max_length=255)
    tool_execution: dict[str, Any] = Field(default_factory=dict)
    feedback_selections: list[dict[str, Any]] = Field(default_factory=list)


class AgentCancelRunRequest(BaseModel):
    """中断一个仍在执行中的 run 的请求体。"""

    force: bool = False
    tool_call_id: str | None = Field(default=None, max_length=255)


class AgentCancelRunResponse(SchemaBase):
    """返回给 Editor 的 run 中断结果。"""

    run_id: str
    session_id: str
    cancel_requested: bool = True
