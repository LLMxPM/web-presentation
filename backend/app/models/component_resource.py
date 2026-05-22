"""文件功能：定义组件发布版本中的 Icon/Asset 资源参数索引。"""

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ComponentVersionComponentResource(TimestampMixin, Base):
    """组件版本资源参数索引实体，记录组件源码和 preview_schema 中的资源名集合。"""

    __tablename__ = "component_version_component_resources"
    __table_args__ = (
        UniqueConstraint(
            "component_version_id",
            "component_name",
            "resource_attr",
            "resource_name",
            name="uq_component_version_component_resources_unique_resource",
        ),
        Index("ix_cvcr_workspace_id", "workspace_id"),
        Index("ix_cvcr_component_id", "component_id"),
        Index("ix_cvcr_component_version_id", "component_version_id"),
        Index("ix_cvcr_workspace_component_resource", "workspace_id", "component_name", "resource_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_components.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_version_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_attr: Mapped[str] = mapped_column(String(64), nullable=False, default="name", server_default="name")
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
