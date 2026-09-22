"""文件功能：定义远程渲染请求模型，作为渲染阶段唯一状态源与持久化队列。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class RenderRequest(TimestampMixin, Base):
    """统一渲染请求记录。"""

    __tablename__ = "render_requests"
    __table_args__ = (
        Index(
            "uq_render_requests_owner_stage_key",
            "logical_owner_key",
            "business_stage",
            "operation",
            "request_key",
            unique=True,
        ),
        Index("ix_render_requests_status_category", "status", "schedule_category"),
        Index("ix_render_requests_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_owner_key: Mapped[str] = mapped_column(String(128), nullable=False)
    business_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule_category: Mapped[str] = mapped_column(String(32), nullable=False, default="background")
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    component_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="domain_job")
    owner_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    render_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_ref: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    operation_options: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    viewport: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    render_profile_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
