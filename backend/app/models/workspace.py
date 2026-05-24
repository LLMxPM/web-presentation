"""文件功能：定义工作空间与项目的层级数据模型。"""

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RecordStatus, WorkspaceMemberRole
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin


class Workspace(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """工作空间实体，作为项目的直接父级。"""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RecordStatus] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    default_theme_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="workspace")


class WorkspaceMember(TimestampMixin, AuditMixin, Base):
    """工作空间成员关系，首期用于私有空间隔离并为后续协作预留。"""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkspaceMemberRole.OWNER.value,
        server_default=text("'owner'"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RecordStatus.ACTIVE.value,
        server_default=text("'active'"),
        index=True,
    )


class Project(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """项目实体，归属于某个工作空间，但与页面资源库解耦。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    status: Mapped[RecordStatus] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_width: Mapped[int] = mapped_column(Integer, nullable=False, default=1920, server_default=text("1920"))
    page_height: Mapped[int] = mapped_column(Integer, nullable=False, default=1080, server_default=text("1080"))
    base_font_size: Mapped[str] = mapped_column(String(32), nullable=False, default="20px", server_default=text("'20px'"))
    icon_default_stroke_width: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default=text("2"))
    show_pdf_export_button: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    menu_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="preview", server_default=text("'preview'"))
    theme_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    theme_config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    style_spec_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    build_extra_assets_json: Mapped[Mapping[str, Any] | None] = mapped_column(JSON, nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
