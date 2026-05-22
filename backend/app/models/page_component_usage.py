"""文件功能：定义页面版本组件使用索引模型，用于统计每个版本使用了哪些组件。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PageVersionComponentUsage(TimestampMixin, Base):
    """页面版本组件使用索引实体，按版本记录出现过的组件集合。"""

    __tablename__ = "page_version_component_usages"
    __table_args__ = (
        UniqueConstraint("page_version_id", "component_name", name="uq_page_version_component_usages_version_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    page_version_id: Mapped[int] = mapped_column(
        ForeignKey("page_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_name: Mapped[str] = mapped_column(String(128), nullable=False)
