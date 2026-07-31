"""文件功能：定义工作空间级字体族与字体文件模型，字体文件（face）挂载在字体族（family）下供主题引用。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WorkspaceFontFamily(TimestampMixin, Base):
    """工作空间字体族，作为字体管理与主题绑定的单元，名称在工作空间内唯一。"""

    __tablename__ = "workspace_font_families"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_workspace_font_families_workspace_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    faces: Mapped[list["WorkspaceFontConfig"]] = relationship(
        back_populates="family",
        order_by="WorkspaceFontConfig.id",
    )


class WorkspaceFontConfig(TimestampMixin, Base):
    """工作空间字体文件（face）注册表，一条记录对应字体族下一个字体资产及其 @font-face 声明。"""

    __tablename__ = "workspace_font_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "asset_id", name="uq_workspace_font_configs_workspace_asset"),
        UniqueConstraint("workspace_id", "asset_name", name="uq_workspace_font_configs_workspace_asset_name"),
        UniqueConstraint("family_id", "font_weight", "font_style", name="uq_workspace_font_configs_family_face"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("workspace_font_families.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id"), nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    font_format: Mapped[str] = mapped_column(String(32), nullable=False)
    font_weight: Mapped[str] = mapped_column(String(32), nullable=False, server_default="400")
    font_style: Mapped[str] = mapped_column(String(32), nullable=False, server_default="normal")
    font_display: Mapped[str] = mapped_column(String(32), nullable=False, server_default="swap")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")

    family: Mapped[WorkspaceFontFamily] = relationship(back_populates="faces", lazy="joined")

    @property
    def font_family(self) -> str:
        """从所属字体族派生 family 名，保持既有读取方（响应序列化、Bundle 构建）语义。"""

        return self.family.name if self.family is not None else ""
