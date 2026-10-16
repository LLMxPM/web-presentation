"""文件功能：定义资源引用绑定模型，冻结版本与产物对资源文件版本的引用，支撑历史还原与删除保护。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class AssetReferenceBinding(TimestampMixin, Base):
    """owner（页面/组件版本、Release、渲染请求、预览 artifact）对资源名与文件哈希的冻结引用。

    永久版本持有 expires_at 为空；临时持有（预览 artifact、渲染请求）按 TTL 写入到期时间，
    由清理对账释放。snapshot_asset_id 指向不可写的参考快照记录：删除保护依赖真实外键与
    持有查询，禁止绕过绑定直接删除仍被历史版本引用的文件。
    """

    __tablename__ = "asset_reference_bindings"
    __table_args__ = (
        UniqueConstraint(
            "owner_kind",
            "owner_key",
            "resource_name",
            name="uq_asset_reference_bindings_owner_resource",
        ),
        Index("ix_asset_reference_bindings_workspace_owner", "workspace_id", "owner_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id"), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
