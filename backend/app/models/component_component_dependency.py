"""文件功能：定义组件版本到其他组件版本或 Runtime 本地模块的源码依赖索引。"""

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ComponentVersionComponentDependency(TimestampMixin, Base):
    """组件版本源码依赖索引，记录远程组件版本和 Runtime 公共本地模块引用。"""

    __tablename__ = "component_version_component_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "component_version_id",
            "dependency_kind",
            "dependency_component_version_id",
            "runtime_module_path",
            name="uq_component_version_component_dependencies_unique_dependency",
        ),
        Index("ix_cvcd_comp_id", "component_id"),
        Index("ix_cvcd_cver_id", "component_version_id"),
        Index("ix_cvcd_dep_comp_id", "dependency_component_id"),
        Index("ix_cvcd_dep_cver_id", "dependency_component_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_components.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_version_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    dependency_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_components.id", ondelete="CASCADE"),
        nullable=True,
    )
    dependency_component_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_component_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    dependency_component_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dependency_component_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_module_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    runtime_kit_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_kit_base_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_kit_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_kit_import_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
