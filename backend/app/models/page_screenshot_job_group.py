"""文件功能：定义页面截图任务组及成员关系，使复用任务可归属多个批次。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PageScreenshotJobGroup(TimestampMixin, Base):
    """持久化一次批量截图请求，即使批次为空也保留可查询记录。"""

    __tablename__ = "page_screenshot_job_groups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PageScreenshotJobGroupItem(Base):
    """记录任务组与截图任务的多对多成员关系。"""

    __tablename__ = "page_screenshot_job_group_items"
    __table_args__ = (
        UniqueConstraint("group_id", "job_id", name="uq_page_screenshot_job_group_items_group_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("page_screenshot_job_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("page_screenshot_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
