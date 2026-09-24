"""文件功能：定义远程渲染 Worker 与调度状态模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONPayload as JSONType
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class RenderWorker(TimestampMixin, Base):
    """执行节点与实际槽位状态，以 (worker_id, epoch) 区分实例生命期。"""

    __tablename__ = "render_workers"
    __table_args__ = (UniqueConstraint("worker_id", "worker_epoch", name="uq_render_workers_id_epoch"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    worker_epoch: Mapped[str] = mapped_column(String(64), nullable=False)
    service_base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    isolated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    isolation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    render_profile_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slot_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slot_state: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RenderSchedulerState(TimestampMixin, Base):
    """多 Backend 下的统一调度状态，默认单行。"""

    __tablename__ = "render_scheduler_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    singleton_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default="global")
    cursor_category: Mapped[str] = mapped_column(String(32), nullable=False, default="interactive")
    cursor_workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cursor_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workspace_weights: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    global_concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workspace_concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    queue_size_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    workspace_queue_size_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class RenderResult(TimestampMixin, Base):
    """有界渲染结果与业务消费记录。"""

    __tablename__ = "render_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    render_profile_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    object_refs: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worker_epoch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
