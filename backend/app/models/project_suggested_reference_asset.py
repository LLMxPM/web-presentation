"""文件功能：定义项目建议引用资源关联模型，记录项目级 AI 素材偏好。"""

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ProjectSuggestedReferenceAsset(TimestampMixin, Base):
    """项目与工作空间内容资源的有序关联，供智能体上下文优先参考。"""

    __tablename__ = "project_suggested_reference_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_id", name="uq_project_suggested_reference_assets_project_asset"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
