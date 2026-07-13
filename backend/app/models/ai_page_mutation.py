"""文件功能：定义 AI 页面创建与修改的持久化批次和任务模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AiPageMutationBatch(TimestampMixin, Base):
    """聚合同一 AI run step 中的页面写工具，负责一次性恢复模型推理。"""

    __tablename__ = "ai_page_mutation_batches"
    __table_args__ = (
        UniqueConstraint("run_id", "run_step", name="uq_ai_page_mutation_batches_run_step"),
    )

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    run_step: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    requirement_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # 每次认领/恢复续跑均递增；用于阻断过期协调器把模型结果写回运行态。
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiPageMutationJob(TimestampMixin, Base):
    """保存单次 AI 页面创建或修改任务，不重复持久化工具参数中的页面源码。"""

    __tablename__ = "ai_page_mutation_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "tool_call_id", name="uq_ai_page_mutation_jobs_run_tool_call"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("ai_page_mutation_batches.batch_id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_runs.run_id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_agent_sessions.session_id"), nullable=False, index=True)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    base_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
