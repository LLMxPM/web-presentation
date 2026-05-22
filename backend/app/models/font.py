"""文件功能：定义工作空间级字体注册模型，用于把字体资产映射为可被主题引用的字体配置。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WorkspaceFontConfig(TimestampMixin, Base):
    """工作空间字体注册表，一条记录对应一个可供主题引用的字体资产。"""

    __tablename__ = "workspace_font_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "asset_id", name="uq_workspace_font_configs_workspace_asset"),
        UniqueConstraint("workspace_id", "asset_name", name="uq_workspace_font_configs_workspace_asset_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id"), nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    font_family: Mapped[str] = mapped_column(String(255), nullable=False)
    font_format: Mapped[str] = mapped_column(String(32), nullable=False)
    font_weight: Mapped[str] = mapped_column(String(32), nullable=False, server_default="400")
    font_style: Mapped[str] = mapped_column(String(32), nullable=False, server_default="normal")
    font_display: Mapped[str] = mapped_column(String(32), nullable=False, server_default="swap")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
