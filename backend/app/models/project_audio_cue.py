"""文件功能：定义项目级音频 cue 与工作空间音频资源的绑定关系。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ProjectAudioCueBinding(TimestampMixin, Base):
    """项目内唯一的 cue key 绑定，资源通过外键关联工作空间音频。"""

    __tablename__ = "project_audio_cue_bindings"
    __table_args__ = (
        UniqueConstraint("project_id", "cue_key", name="uq_project_audio_cue_bindings_project_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    cue_key: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id"), nullable=False, index=True)
    gain_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=text("100"),
    )
