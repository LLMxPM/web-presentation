"""文件功能：定义工作空间主题库模型，承载主题主数据、项目图标与资源引用关系。"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin


class WorkspaceTheme(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """工作空间主题实体，维护主题主数据并通过资源 ID 关联 logo 与字体。"""

    __tablename__ = "workspace_themes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_workspace_themes_workspace_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_asset_id: Mapped[int | None] = mapped_column(ForeignKey("workspace_assets.id"), nullable=True, index=True)
    invert_logo_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_assets.id"),
        nullable=True,
        index=True,
    )
    project_icon_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_assets.id"),
        nullable=True,
        index=True,
    )
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invert_logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_icon_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    heading_font_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_font_configs.id"),
        nullable=True,
        index=True,
    )
    body_font_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_font_configs.id"),
        nullable=True,
        index=True,
    )
    code_font_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace_font_configs.id"),
        nullable=True,
        index=True,
    )
    heading_font_label: Mapped[str] = mapped_column(String(255), nullable=False)
    body_font_label: Mapped[str] = mapped_column(String(255), nullable=False)
    code_font_label: Mapped[str] = mapped_column(String(255), nullable=False)
    palette: Mapped[Mapping[str, Any]] = mapped_column(JSON, nullable=False)
