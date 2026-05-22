"""文件功能：定义项目整包构建任务模型，用于记录异步构建状态与快照关联。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def artifact_proxy_url(self) -> str | None:
        """返回构建产物公开代理入口；任务尚无产物时返回空。"""

        if not self.artifact_storage_key:
            return None
        settings = get_settings()
        return f"{settings.backend_public_base_url.rstrip('/')}/build-artifacts/{self.project_id}/{self.id}/"
