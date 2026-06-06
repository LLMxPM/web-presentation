"""文件功能：定义工作空间组件发布版本实体，保存不可变组件源码、预览 schema 与内容指纹快照。"""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PageFileType
from app.models.mixins import TimestampMixin


class WorkspaceComponentVersion(TimestampMixin, Base):
    """工作空间组件发布版本实体，记录某个组件可被外部引用的不可变版本。"""

    __tablename__ = "workspace_component_versions"
    __table_args__ = (
        UniqueConstraint("component_id", "version_no", name="uq_workspace_component_versions_component_version"),
        Index("ix_workspace_component_versions_component_fingerprint", "component_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    release_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_type: Mapped[PageFileType] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    preview_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
