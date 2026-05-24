"""文件功能：定义项目路由树模型，承载项目级分组与页面路由的结构化持久化。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProjectRouteType
from app.models.mixins import AuditMixin, TimestampMixin


class ProjectRoute(TimestampMixin, AuditMixin, Base):
    """项目路由节点实体，支持两级树结构和页面绑定。"""

    __tablename__ = "project_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_routes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    route: Mapped[str] = mapped_column(String(128), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True)
    route_type: Mapped[ProjectRouteType] = mapped_column(String(32), nullable=False)
    group_title: Mapped[str | None] = mapped_column(String(128), nullable=True)

    parent: Mapped["ProjectRoute | None"] = relationship(
        "ProjectRoute",
        remote_side="ProjectRoute.id",
        back_populates="children",
    )
    children: Mapped[list["ProjectRoute"]] = relationship(
        "ProjectRoute",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

