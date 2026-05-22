"""文件功能：定义智能体后台运行任务与事件回放模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AiAgentRunTask(TimestampMixin, Base):
    """记录一次智能体 run 的后台执行状态。"""

    __tablename__ = "ai_agent_run_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    backend_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    component_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tool_scopes_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tool_auth_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tool_auth_max_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_requirement_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiAgentRunEvent(TimestampMixin, Base):
    """保存后台 run 的标准化事件，供前端断线后按序回放。"""

    __tablename__ = "ai_agent_run_events"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_ai_agent_run_events_task_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_run_tasks.task_id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
