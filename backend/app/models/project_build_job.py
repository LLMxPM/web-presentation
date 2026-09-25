"""文件功能：定义项目整包构建任务模型，用于记录异步构建状态、attempt 身份与租约。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class ProjectBuildJob(TimestampMixin, Base):
    """项目整包构建任务记录。"""

    __tablename__ = "project_build_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    snapshot_release_id: Mapped[int] = mapped_column(ForeignKey("releases.id"), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_entry_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # --- 持久领取、attempt 身份与租约字段 ---
    # attempt_id 标识当前执行尝试；产物对象键与限权令牌都绑定该值，迟到上传据此被拒绝。
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # 总 deadline：超过后即使仍有重试预算也不再重试，避免任务无限拉长。
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    @property
    def artifact_proxy_url(self) -> str | None:
        """返回构建产物公开代理入口；任务尚无产物时返回空。"""

        if not self.artifact_storage_key:
            return None
        settings = get_settings()
        return f"{settings.backend_public_base_url.rstrip('/')}/build-artifacts/{self.project_id}/{self.id}/"
