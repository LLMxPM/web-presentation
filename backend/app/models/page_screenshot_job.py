"""文件功能：定义页面截图异步任务模型，用于队列化截图执行和进度查询。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.indexes import partial_index
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class PageScreenshotJob(TimestampMixin, Base):
    """页面截图任务记录。"""

    __tablename__ = "page_screenshot_jobs"
    __table_args__ = (
        partial_index(
            "ix_page_screenshot_jobs_dedupe_active",
            (
                "page_id",
                "target_page_version_no",
                "config_hash",
                "viewport_width",
                "viewport_height",
                "motion_snapshot_hash",
            ),
            "status IN ('pending', 'running')",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    viewport_width: Mapped[int] = mapped_column(Integer, nullable=False)
    viewport_height: Mapped[int] = mapped_column(Integer, nullable=False)
    # 入队时固定的页面版本，避免旧任务在页面编辑后覆盖新版本截图。
    target_page_version_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 临时时间点截图与默认截图使用同一队列；空串表示默认 poster，避免改变既有去重语义。
    motion_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    motion_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    result_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_applied_motion_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    @property
    def motion_snapshot(self) -> dict[str, Any] | None:
        """响应只暴露规范化选择器，不暴露内部列名。"""

        return self.motion_snapshot_json

    @property
    def result_screenshot_id(self) -> str | None:
        """成功结果以内容 hash 标识，与既有截图内容接口一致。"""

        return self.result_sha256

    @property
    def applied_motion(self) -> dict[str, Any] | None:
        """返回有界采样回执；未采样或旧任务为 null。"""

        return self.result_applied_motion_json
