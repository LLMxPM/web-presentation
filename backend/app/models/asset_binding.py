"""文件功能：定义资源占用绑定模型，保护在途任务与短生命周期产物引用的资源文件不被删除。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import TimestampMixin


class AssetReferenceBinding(TimestampMixin, Base):
    """owner（Release、渲染请求、预览 artifact）对当前资源文件的短期占用。

    持有只保护文件记录不被删除，不冻结内容：指向当前根资源记录，替换资源不改变绑定目标，
    旧内容由替换时的归档副本兜底，历史版本按当前资源解析。expires_at 为必填到期时间，
    由清理对账释放；禁止绕过绑定直接删除仍被在途任务或产物引用的文件。
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
    asset_id: Mapped[int] = mapped_column(ForeignKey("workspace_assets.id"), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
