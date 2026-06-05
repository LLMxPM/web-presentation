"""文件功能：定义样式库建议组件关联模型，记录样式模板可推荐复用的组件。"""

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WorkspaceStyleSuggestedComponent(TimestampMixin, Base):
    """工作空间样式与已发布组件的有序关联，应用样式时复制到项目快照。"""

    __tablename__ = "workspace_style_suggested_components"
    __table_args__ = (
        UniqueConstraint("style_id", "component_id", name="uq_workspace_style_suggested_components_style_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    style_id: Mapped[int] = mapped_column(ForeignKey("workspace_styles.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
