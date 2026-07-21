"""文件功能：定义图片生成持久化任务，支持幂等、租约、取消和外部续跑。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AiImageGenerationJob(TimestampMixin, Base):
    """记录单个 generate_image 工具调用的供应商任务与持久化输出。"""

    __tablename__ = "ai_image_generation_jobs"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_ai_image_generation_jobs_run_tool_call"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    deferred_tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    member_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_agent_member_runs.member_run_id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    model_config_id: Mapped[int] = mapped_column(ForeignKey("ai_llm_configs.id"), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    model_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    progress_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    continued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
