"""文件功能：定义智能体会话图片附件模型，用于记录用户上传和工具输出图片的对象存储与模型 URL 状态。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RecordStatus
from app.models.mixins import AuditMixin, TimestampMixin


class AiAgentImageAttachment(TimestampMixin, AuditMixin, Base):
    """记录 Agent 视觉输入图片附件，统一覆盖用户上传与工具输出。"""

    __tablename__ = "ai_agent_image_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="user_upload", index=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_url_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_url_last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owned_object: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    promoted_asset_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_assets.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)
