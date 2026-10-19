"""文件功能：登记待发布截图对象及页面范围内的历史内容映射，支持崩溃后回收。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class PageScreenshotArtifact(TimestampMixin, Base):
    """页面提交前先登记对象持有，提交时原子绑定页面；过期未绑定对象可回收。"""

    __tablename__ = "page_screenshot_artifacts"
    __table_args__ = (Index("ix_screenshot_artifacts_page_hash", "page_id", "sha256"),)

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
