"""文件功能：定义发布与草稿态模型及其对应的模块快照模型。"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Release(TimestampMixin, Base):
    """发布/草稿记录，用于承载全项目预览时的固定配置快照。"""

    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manifest: Mapped[Mapping[str, Any]] = mapped_column(JSON, nullable=False)
    config_bundle: Mapped[Mapping[str, Any]] = mapped_column(JSON, nullable=False)


class ReleaseModule(TimestampMixin, Base):
    """跟发布强绑定的页面源码不可变快照。"""

    __tablename__ = "release_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False, index=True)
    logical_path: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(255), nullable=False)
