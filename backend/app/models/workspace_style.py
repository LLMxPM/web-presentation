"""文件功能：定义工作空间样式库模型，保存可复用的项目展示配置与样式规范。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin


class WorkspaceStyle(TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """工作空间样式实体，仅作为复制填充模板，不与项目建立持久关联。"""

    __tablename__ = "workspace_styles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_workspace_styles_workspace_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_width: Mapped[int] = mapped_column(Integer, nullable=False, default=1920, server_default=text("1920"))
    page_height: Mapped[int] = mapped_column(Integer, nullable=False, default=1080, server_default=text("1080"))
    base_font_size: Mapped[str] = mapped_column(String(32), nullable=False, default="20px", server_default=text("'20px'"))
    icon_default_stroke_width: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default=text("2"))
    show_pdf_export_button: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    menu_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="preview", server_default=text("'preview'"))
    theme_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    style_spec_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
