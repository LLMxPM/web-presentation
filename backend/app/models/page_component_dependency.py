"""文件功能：定义页面版本到组件版本/Runtime 本地模块的源码依赖索引。"""

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PageVersionComponentDependency(TimestampMixin, Base):
    """页面版本源码依赖索引，记录远程组件版本和 Runtime 公共本地模块引用。"""

    __tablename__ = "page_version_component_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "page_version_id",
            "dependency_kind",
            "component_version_id",
            "runtime_module_path",
            name="uq_page_version_component_dependencies_unique_dependency",
        ),
        Index("ix_pvcd_page_id", "page_id"),
        Index("ix_pvcd_pver_id", "page_version_id"),
        Index("ix_pvcd_comp_id", "component_id"),
        Index("ix_pvcd_cver_id", "component_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    page_version_id: Mapped[int] = mapped_column(
        ForeignKey("page_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    component_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_components.id", ondelete="CASCADE"),
        nullable=True,
    )
    component_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_component_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    component_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_module_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    runtime_kit_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_kit_base_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_kit_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_kit_import_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
