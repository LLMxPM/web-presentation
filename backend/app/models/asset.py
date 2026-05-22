"""文件功能：定义工作空间级别静态资源模型，用于承载基础资产、内容渲染资产与归档历史副本。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RecordStatus
from app.models.mixins import TimestampMixin


class WorkspaceAsset(TimestampMixin, Base):
    """工作空间内的静态资源，可供组装发布与预览。"""

    __tablename__ = "workspace_assets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_workspace_assets_workspace_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="icon")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default='[]')
    analysis_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    render_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RecordStatus.ACTIVE.value,
        server_default=RecordStatus.ACTIVE.value,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_asset_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_assets.id"), nullable=True, index=True)
    history_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
