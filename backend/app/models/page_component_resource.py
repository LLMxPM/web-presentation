"""文件功能：定义页面版本组件资源参数索引模型，用于统计 Icon/Asset 组件 name 参数。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PageVersionComponentResource(TimestampMixin, Base):
    """页面版本组件资源参数索引实体，按版本记录组件参数资源名集合。"""

    __tablename__ = "page_version_component_resources"
    __table_args__ = (
        UniqueConstraint(
            "page_version_id",
            "component_name",
            "resource_attr",
            "resource_name",
            name="uq_page_version_component_resources_unique_resource",
        ),
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
    resource_attr: Mapped[str] = mapped_column(String(64), nullable=False, default="name", server_default="name")
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
