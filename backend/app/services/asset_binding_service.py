"""文件功能：维护资源引用绑定与持有，冻结版本/产物对资源文件版本的引用并支撑删除保护与过期清理。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.asset_binding import AssetReferenceBinding
from app.models.enums import AssetType, RecordStatus

logger = logging.getLogger(__name__)

OWNER_KIND_PAGE_VERSION = "page_version"
OWNER_KIND_COMPONENT_VERSION = "component_version"
OWNER_KIND_RELEASE = "release"
OWNER_KIND_RENDER_REQUEST = "render_request"
OWNER_KIND_PREVIEW_ARTIFACT = "preview_artifact"

OWNER_KINDS = frozenset(
    {
        OWNER_KIND_PAGE_VERSION,
        OWNER_KIND_COMPONENT_VERSION,
        OWNER_KIND_RELEASE,
        OWNER_KIND_RENDER_REQUEST,
        OWNER_KIND_PREVIEW_ARTIFACT,
    }
)

# 参考快照的 history_kind：不可写的归档副本，文件内容与根资源共享同一 blob。
HISTORY_KIND_REFERENCE_SNAPSHOT = "reference_snapshot"
_REFERENCE_SNAPSHOT_NAME_PREFIX = "__history__"


class AssetBindingService:
    """统一维护资源引用绑定：冻结快照、owner 绑定重建、释放、删除保护与过期对账。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_reference_snapshot(self, workspace_id: int, asset: WorkspaceAsset) -> WorkspaceAsset:
        """确保指定根资源当前文件版本存在参考快照记录；同文件同哈希复用，不复制 blob。

        快照名由资源 ID 与哈希前缀稳定派生并依赖 (workspace_id, name) 唯一约束兜底并发：
        并发创建冲突时回查复用，禁止为同一文件版本留下多条参考快照或删除仍被引用的记录。
        """

        if asset.source_asset_id is not None or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_HISTORY_WRITE_FORBIDDEN", detail="历史副本不可再建立参考快照。")
        existing = await self._find_reference_snapshot(workspace_id, asset)
        if existing is not None:
            return existing
        snapshot = WorkspaceAsset(
            workspace_id=workspace_id,
            name=f"{_REFERENCE_SNAPSHOT_NAME_PREFIX}{asset.id}_{str(asset.file_hash)[:8]}",
            file_name=asset.file_name,
            original_name=asset.original_name,
            description=asset.description,
            file_size=asset.file_size,
            file_hash=asset.file_hash,
            content_type=asset.content_type,
            asset_type=asset.asset_type,
            tags=list(asset.tags or []),
            analysis_metadata=asset.analysis_metadata,
            render_metadata=asset.render_metadata,
            status=RecordStatus.ARCHIVED.value,
            archived_at=utc_now(),
            archive_reason="版本引用快照。",
            source_asset_id=asset.id,
            history_kind=HISTORY_KIND_REFERENCE_SNAPSHOT,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(snapshot)
                await self.session.flush()
        except IntegrityError:
            existing = await self._find_reference_snapshot(workspace_id, asset)
            if existing is None:
                raise
            return existing
        return snapshot

    async def replace_owner_bindings(
        self,
        *,
        workspace_id: int,
        owner_kind: str,
        owner_key: str,
        assets: Sequence[WorkspaceAsset],
        expires_at: datetime | None = None,
    ) -> list[AssetReferenceBinding]:
        """按当前资源版本整体重建 owner 的全部绑定，先冻结参考快照再覆盖旧绑定。

        调用方在同一事务中提交；同一 owner 的重复调用以最后一次为准，不会留下重复绑定。
        """

        self._ensure_owner_kind(owner_kind)
        bindings: list[AssetReferenceBinding] = []
        seen_names: set[str] = set()
        for asset in assets:
            if not asset.name or asset.name in seen_names:
                continue
            seen_names.add(asset.name)
            snapshot = await self.ensure_reference_snapshot(workspace_id, asset)
            bindings.append(
                AssetReferenceBinding(
                    workspace_id=workspace_id,
                    owner_kind=owner_kind,
                    owner_key=str(owner_key),
                    resource_name=asset.name,
                    snapshot_asset_id=snapshot.id,
                    file_hash=str(asset.file_hash),
                    expires_at=expires_at,
                )
            )
        await self.session.execute(
            delete(AssetReferenceBinding)
            .where(AssetReferenceBinding.owner_kind == owner_kind)
            .where(AssetReferenceBinding.owner_key == str(owner_key))
        )
        for binding in bindings:
            self.session.add(binding)
        await self.session.flush()
        return bindings

    async def bind_owner_model3d_assets(
        self,
        *,
        workspace_id: int,
        owner_kind: str,
        owner_key: str,
        asset_metadata: Mapping[str, Mapping[str, object]] | None,
        expires_at: datetime | None = None,
    ) -> list[AssetReferenceBinding]:
        """按 manifest 资源元数据筛选三维资源并为 owner 建立持有；无三维资源时不产生绑定。"""

        self._ensure_owner_kind(owner_kind)
        names = sorted(
            str(name)
            for name, meta in (asset_metadata or {}).items()
            if str(name or "").strip()
            and str((meta or {}).get("render_type") or "") == AssetType.MODEL3D.value
        )
        if not names:
            return []
        assets = list(
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.source_asset_id.is_(None))
                    .where(WorkspaceAsset.asset_type == AssetType.MODEL3D.value)
                    .where(WorkspaceAsset.name.in_(names))
                )
            )
            .scalars()
            .all()
        )
        if not assets:
            return []
        return await self.replace_owner_bindings(
            workspace_id=workspace_id,
            owner_kind=owner_kind,
            owner_key=owner_key,
            assets=assets,
            expires_at=expires_at,
        )

    async def list_owner_bindings(self, owner_kind: str, owner_key: str) -> list[AssetReferenceBinding]:
        """列出指定 owner 的全部有效绑定。"""

        self._ensure_owner_kind(owner_kind)
        result = await self.session.execute(
            select(AssetReferenceBinding)
            .where(AssetReferenceBinding.owner_kind == owner_kind)
            .where(AssetReferenceBinding.owner_key == str(owner_key))
            .order_by(AssetReferenceBinding.resource_name.asc())
        )
        return list(result.scalars().all())

    async def owner_binding_hash_map(self, owner_kind: str, owner_key: str) -> dict[str, str]:
        """返回 owner 的 resource_name→file_hash 冻结映射，供历史预览与指纹复用。"""

        bindings = await self.list_owner_bindings(owner_kind, owner_key)
        return {item.resource_name: item.file_hash for item in bindings}

    async def resolve_binding_assets(
        self, bindings: Sequence[AssetReferenceBinding]
    ) -> dict[str, WorkspaceAsset]:
        """按绑定记录批量加载不可写快照资产，返回 resource_name→快照记录映射。"""

        snapshot_ids = {int(item.snapshot_asset_id) for item in bindings}
        if not snapshot_ids:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(WorkspaceAsset).where(WorkspaceAsset.id.in_(sorted(snapshot_ids)))
                )
            )
            .scalars()
            .all()
        )
        by_id = {int(asset.id): asset for asset in rows}
        return {
            item.resource_name: by_id[int(item.snapshot_asset_id)]
            for item in bindings
            if int(item.snapshot_asset_id) in by_id
        }

    async def release_owner(self, owner_kind: str, owner_key: str) -> int:
        """释放 owner 的全部绑定，返回删除条数；重复释放保持幂等。"""

        self._ensure_owner_kind(owner_kind)
        result = await self.session.execute(
            delete(AssetReferenceBinding)
            .where(AssetReferenceBinding.owner_kind == owner_kind)
            .where(AssetReferenceBinding.owner_key == str(owner_key))
        )
        return int(result.rowcount or 0)

    async def release_expired(self, *, now: datetime | None = None, limit: int = 500) -> int:
        """清理已过期的临时持有，返回释放条数；永久版本持有（expires_at 为空）不受影响。"""

        moment = now or utc_now()
        expired_ids = list(
            (
                await self.session.execute(
                    select(AssetReferenceBinding.id)
                    .where(AssetReferenceBinding.expires_at.is_not(None))
                    .where(AssetReferenceBinding.expires_at < moment)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not expired_ids:
            return 0
        result = await self.session.execute(delete(AssetReferenceBinding).where(AssetReferenceBinding.id.in_(expired_ids)))
        return int(result.rowcount or 0)

    async def protected_snapshot_asset_ids(self, asset_ids: Sequence[int]) -> set[int]:
        """查询给定资产记录集合中仍被绑定持有的 id，供删除保护与 blob 清理判定。"""

        normalized = {int(item) for item in asset_ids}
        if not normalized:
            return set()
        result = await self.session.execute(
            select(AssetReferenceBinding.snapshot_asset_id)
            .where(AssetReferenceBinding.snapshot_asset_id.in_(normalized))
            .distinct()
        )
        return {int(item) for item in result.scalars().all()}

    async def _find_reference_snapshot(self, workspace_id: int, asset: WorkspaceAsset) -> WorkspaceAsset | None:
        """按源资源与文件哈希查找已有参考快照。"""

        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.source_asset_id == asset.id)
            .where(WorkspaceAsset.file_hash == asset.file_hash)
            .where(WorkspaceAsset.history_kind == HISTORY_KIND_REFERENCE_SNAPSHOT)
        )

    @staticmethod
    def _ensure_owner_kind(owner_kind: str) -> None:
        """校验 owner 种类合法，避免写入未知绑定类型。"""

        if owner_kind not in OWNER_KINDS:
            raise AppException(status_code=400, code="ASSET_BINDING_OWNER_INVALID", detail="资源绑定 owner 种类不合法。")


async def run_asset_binding_expiry_loop(session_factory: Callable[..., AsyncSession]) -> None:
    """后台循环：定期释放过期的临时资源持有，保证 artifact/请求到期后文件可按规则回收。

    永久版本持有（页面/组件版本、Release）不设置 expires_at，不受该对账影响；
    artifact 与渲染请求的显式释放仍是主路径，本循环只兜底 TTL 到期与进程崩溃遗留。
    """

    interval = max(30.0, float(get_settings().runtime_artifact_sweep_interval_seconds))
    logger.info("资源绑定过期对账循环启动")
    while True:
        try:
            await asyncio.sleep(interval)
            async with session_factory() as session:
                released = await AssetBindingService(session).release_expired()
                await session.commit()
            if released:
                logger.info(
                    "资源绑定过期对账完成。",
                    extra={"event": "asset.binding.expired.released", "released": released},
                )
        except asyncio.CancelledError:
            logger.info("资源绑定过期对账循环已取消")
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("资源绑定过期对账循环异常: %s", exc, exc_info=True)
            await asyncio.sleep(5.0)
