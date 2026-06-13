"""文件功能：定义项目级建议组件快照关联模型，记录内容助手默认组件查询范围。"""

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ProjectSuggestedComponent(TimestampMixin, Base):
    """项目与已发布工作空间组件的有序关联，作为应用样式后的建议组件快照。"""

    __tablename__ = "project_suggested_components"
    __table_args__ = (
        UniqueConstraint("project_id", "component_id", name="uq_project_suggested_components_project_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
