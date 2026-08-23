"""文件功能：定义通用页面/组件异步变更任务（Mutation Job）模型与执行租约状态机。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utc_now
from app.db.base import Base
from app.models.api_idempotency_record import ApiIdempotencyRecord


class ApiMutationJob(Base):
    """通用页面与组件异步 Mutation 任务模型。"""

    __tablename__ = "api_mutation_jobs"
    __table_args__ = (
        Index("ix_mutation_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_mutation_jobs_workspace_target", "workspace_id", "target_id"),
        Index("ix_mutation_jobs_claim", "status", "next_attempt_at"),
        Index("ix_mutation_jobs_retry_of", "retry_of_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_idempotency_records.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    retry_of_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_mutation_jobs.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    idempotency_record: Mapped["ApiIdempotencyRecord"] = relationship()
