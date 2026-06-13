"""文件功能：定义工作空间共享组件实体，管理组件草稿、发布状态、元数据与独立预览 schema。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin


class WorkspaceComponent(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """工作空间共享组件实体，当前行保存可编辑草稿，正式发布版另存版本表。"""

    __tablename__ = "workspace_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    preview_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    draft_base_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_type: Mapped[PageFileType] = mapped_column(String(32), nullable=False, default=PageFileType.VUE.value)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    import_name: Mapped[str] = mapped_column(String(64), nullable=False)
    component_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=WorkspaceComponentType.CONTENT_COMPONENT.value,
        server_default=WorkspaceComponentType.CONTENT_COMPONENT.value,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RecordStatus] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value)
