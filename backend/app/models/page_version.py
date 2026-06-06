"""文件功能：定义页面版本链模型，支持源码与演讲备注的最新基线、向后 diff 与重点快照。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PageFileType, PageVersionStorageType
from app.models.mixins import TimestampMixin


class PageVersion(TimestampMixin, Base):
    """页面版本实体，记录页面源码在各个版本节点上的存储形式与元信息。"""

    __tablename__ = "page_versions"
    __table_args__ = (
        UniqueConstraint("page_id", "version_no", name="uq_page_versions_page_id_version_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    file_type: Mapped[PageFileType] = mapped_column(String(32), nullable=False)
    storage_type: Mapped[PageVersionStorageType] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    snapshot_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
