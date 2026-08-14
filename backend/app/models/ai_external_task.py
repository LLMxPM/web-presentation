"""文件功能：定义统一智能体外部任务 Batch、Task 与组件任务领域详情模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AiAgentExternalBatch(TimestampMixin, Base):
    """聚合同一父级或成员模型 step 的外部任务，并独占一次模型续跑。"""

    __tablename__ = "ai_agent_external_batches"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_ai_external_batches_run_sequence"),
        Index(
            "uq_ai_external_batches_resuming_run",
            "run_id",
            unique=True,
            sqlite_where=text("status = 'resuming'"),
            postgresql_where=text("status = 'resuming'"),
        ),
        Index(
            "uq_ai_external_batches_collecting_parent",
            "run_id",
            unique=True,
            sqlite_where=text("status = 'collecting' AND member_run_id IS NULL"),
            postgresql_where=text("status = 'collecting' AND member_run_id IS NULL"),
        ),
        Index(
            "uq_ai_external_batches_collecting_member",
            "member_run_id",
            unique=True,
            sqlite_where=text("status = 'collecting' AND member_run_id IS NOT NULL"),
            postgresql_where=text("status = 'collecting' AND member_run_id IS NOT NULL"),
        ),
    )

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    member_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_agent_member_runs.member_run_id"), nullable=True, index=True)
    requirement_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    group_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="collecting", index=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiAgentExternalTask(TimestampMixin, Base):
    """保存所有持久化外部工具任务共享的状态、租约、结果与调用标识。"""

    __tablename__ = "ai_agent_external_tasks"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_ai_external_tasks_run_tool_call"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_external_batches.batch_id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    member_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_agent_member_runs.member_run_id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    deferred_tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiComponentMutationTask(Base):
    """保存组件重任务领域参数，供独立Worker在重启后恢复执行。"""

    __tablename__ = "ai_component_mutation_tasks"

    task_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_external_tasks.task_id"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_components.id"), nullable=True, index=True)
    base_draft_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_published_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
