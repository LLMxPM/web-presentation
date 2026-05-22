"""文件功能：定义工作空间页面资源库模型，管理页面源码内容、文件类型与截图信息。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PageFileType, RecordStatus
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin


class Page(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """页面资源实体，仅管理元数据，不与工作空间或项目直接绑定。"""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    page_content: Mapped[str] = mapped_column(Text, nullable=False)
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    file_type: Mapped[PageFileType] = mapped_column(String(32), nullable=False, default=PageFileType.VUE.value)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RecordStatus] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    screenshot_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    screenshot_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenshot_config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    screenshot_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
