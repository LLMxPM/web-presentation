"""文件功能：定义平台自有智能体会话、运行、事件、消息、工具与 HITL 运行态模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin, TimestampMixin


class AiAgentSession(TimestampMixin, AuditMixin, Base):
    """保存 Editor 智能体会话及其业务范围，作为平台会话事实源。"""

    __tablename__ = "ai_agent_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_components.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class AiAgentRun(TimestampMixin, Base):
    """记录一次平台智能体运行的状态、输入、上下文与恢复游标。"""

    __tablename__ = "ai_agent_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_components.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    input_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    message_history_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_requirement_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiAgentRunEvent(TimestampMixin, Base):
    """持久化平台智能体事件，支撑 SSE 回放和 runtime snapshot 重建。"""

    __tablename__ = "ai_agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "event_index", name="uq_ai_agent_run_events_run_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AiAgentMessage(TimestampMixin, Base):
    """保存会话中可展示消息与 Pydantic AI 历史消息片段。"""

    __tablename__ = "ai_agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attachments_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AiAgentToolCall(TimestampMixin, Base):
    """记录平台可展示工具调用详情，独立于模型消息保存。"""

    __tablename__ = "ai_agent_tool_calls"
    __table_args__ = (
        UniqueConstraint("run_id", "tool_call_id", name="uq_ai_agent_tool_calls_run_tool_call"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    member_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_payload_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    output_payload_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiAgentRequirement(TimestampMixin, Base):
    """保存待用户处理的确认、反馈或外部工具结果请求。"""

    __tablename__ = "ai_agent_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    member_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    member_agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    member_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    resolved_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiAgentMemberRun(TimestampMixin, Base):
    """记录由总控智能体显式委派产生的成员运行。"""

    __tablename__ = "ai_agent_member_runs"

    member_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    parent_run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    delegate_tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
