"""文件功能：定义远程渲染 attempt 模型，记录一次物理执行与槽位占用。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.indexes import partial_index
from app.db.types import JSONPayload as JSONType
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class RenderAttempt(TimestampMixin, Base):
    """一次物理渲染执行记录。"""

    __tablename__ = "render_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", "attempt_no", name="uq_render_attempts_request_no"),
        partial_index(
            "uq_render_attempts_worker_epoch_active",
            ("worker_id", "worker_epoch"),
            "active_occupancy = 1",
            unique=True,
        ),
        Index("ix_render_attempts_status", "status"),
        Index("ix_render_attempts_worker_epoch", "worker_id", "worker_epoch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("render_requests.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worker_epoch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slot_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="reserved")
    cleanup_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # 1 表示该 attempt 仍占用 Worker/epoch 槽位；终态清理后置 0。
    active_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    request_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatch_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_descriptor: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    environment_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cleaned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # 占用租约到期时间：超时后由协调器收敛 unknown/悬挂 attempt，避免容量永久泄漏。
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
