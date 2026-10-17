"""文件功能：维护资源占用绑定与持有，保护在途任务与短生命周期产物引用的资源文件不被删除。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.asset_binding import AssetReferenceBinding
from app.models.enums import AssetType, RecordStatus

logger = logging.getLogger(__name__)

OWNER_KIND_RELEASE = "release"
OWNER_KIND_RENDER_REQUEST = "render_request"
OWNER_KIND_PREVIEW_ARTIFACT = "preview_artifact"

OWNER_KINDS = frozenset(
    {
        OWNER_KIND_RELEASE,
        OWNER_KIND_RENDER_REQUEST,
        OWNER_KIND_PREVIEW_ARTIFACT,
    }
)


class AssetBindingService:
    """统一维护资源占用绑定：按当前资源重建 owner 持有、释放、删除保护与过期对账。

    持有只表达"owner 执行或存活期间引用的文件不可删除"，指向当前根资源记录；
    不冻结内容、不阻塞替换、不支撑历史还原。临时持有必须携带到期时间，
    由过期对账循环兜底释放。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bind_owner_model3d_assets(
        self,
        *,
        workspace_id: int,
        owner_kind: str,
        owner_key: str,
        asset_metadata: Mapping[str, Mapping[str, object]] | None,
        expires_at: datetime,
    ) -> list[AssetReferenceBinding]:
        """按 manifest 声明的三维资源名解析当前根资源，整体重建 owner 的持有。

        资源缺失时跳过该条绑定，不阻断产物创建；同一 owner 的重复调用以最后一次为准。
        调用方在同一事务中提交，保证绑定与 owner 状态原子可见。
        """

        self._ensure_owner_kind(owner_kind)
        required_names = sorted(
            {
                str(name).strip()
                for name, meta in (asset_metadata or {}).items()
                if str(name or "").strip()
                and str((meta or {}).get("render_type") or "") == AssetType.MODEL3D.value
            }
        )
        assets = await self._load_active_model3d_assets(workspace_id=workspace_id, names=required_names)
        bindings = [
            AssetReferenceBinding(
                workspace_id=workspace_id,
                owner_kind=owner_kind,
                owner_key=str(owner_key),
                resource_name=name,
                asset_id=int(assets[name].id),
                file_hash=str(assets[name].file_hash or ""),
                expires_at=expires_at,
            )
            for name in required_names
            if name in assets
        ]
        await self.session.execute(
            delete(AssetReferenceBinding)
            .where(AssetReferenceBinding.owner_kind == owner_kind)
            .where(AssetReferenceBinding.owner_key == str(owner_key))
        )
        for binding in bindings:
            self.session.add(binding)
        await self.session.flush()
        return bindings

    async def bind_preview_artifact_model3d_assets(
        self,
        *,
        workspace_id: int,
        artifact_id: str,
        asset_metadata: Mapping[str, Mapping[str, object]],
        expires_at: datetime | None = None,
    ) -> None:
        """为预览类 artifact 中的三维资源建立临时持有并立即提交，artifact 到期后由对账释放。

        页面/组件/资源三类预览 artifact 共用本入口：expires_at 缺省时按预览 artifact TTL 推导。
        提交在本方法内完成；调用方须保证传入会话上没有未提交的中间写入，
        否则会被顺带提交（与既有行为一致，绑定失败不会回滚已提交的 artifact）。
        """

        if expires_at is None:
            expires_at = utc_now() + timedelta(seconds=get_settings().runtime_preview_artifact_ttl_seconds)
        bindings = await self.bind_owner_model3d_assets(
            workspace_id=workspace_id,
            owner_kind=OWNER_KIND_PREVIEW_ARTIFACT,
            owner_key=artifact_id,
            asset_metadata=asset_metadata,
            expires_at=expires_at,
        )
        if bindings:
            await self.session.commit()

    async def release_owner(self, owner_kind: str, owner_key: str) -> int:
        """释放 owner 的全部绑定，返回删除条数；重复释放保持幂等。"""

        return await self.release_owners(owner_kind, [owner_key])

    async def release_owners(self, owner_kind: str, owner_keys: Sequence[str]) -> int:
        """批量释放多个 owner 的绑定，返回删除条数；已释放或不存在的 owner 直接跳过。"""

        self._ensure_owner_kind(owner_kind)
        normalized = {str(key).strip() for key in owner_keys if str(key).strip()}
        if not normalized:
            return 0
        result = await self.session.execute(
            delete(AssetReferenceBinding)
            .where(AssetReferenceBinding.owner_kind == owner_kind)
            .where(AssetReferenceBinding.owner_key.in_(normalized))
        )
        return int(result.rowcount or 0)

    async def release_expired(self, *, now: datetime | None = None, limit: int = 500) -> int:
        """清理已过期的临时持有，返回释放条数；持有均带到期时间，由本对账兜底回收。"""

        moment = now or utc_now()
        expired_ids = list(
            (
                await self.session.execute(
                    select(AssetReferenceBinding.id)
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

    async def protected_asset_ids(self, asset_ids: Sequence[int]) -> set[int]:
        """查询给定资产记录集合中仍被绑定持有的 id，供删除保护与 blob 清理判定。"""

        normalized = {int(item) for item in asset_ids}
        if not normalized:
            return set()
        # 已过期但尚未被对账循环清理的行不再提供保护，避免到期持有继续阻塞删除。
        result = await self.session.execute(
            select(AssetReferenceBinding.asset_id)
            .where(AssetReferenceBinding.asset_id.in_(normalized))
            .where(AssetReferenceBinding.expires_at >= utc_now())
            .distinct()
        )
        return {int(item) for item in result.scalars().all()}

    async def _load_active_model3d_assets(
        self,
        *,
        workspace_id: int,
        names: list[str],
    ) -> dict[str, WorkspaceAsset]:
        """按资源名批量加载当前 active 三维根资源，按创建时间取最新同名记录。"""

        if not names:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.source_asset_id.is_(None))
                    .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                    .where(WorkspaceAsset.asset_type == AssetType.MODEL3D.value)
                    .where(WorkspaceAsset.name.in_(names))
                    .order_by(WorkspaceAsset.created_at.desc(), WorkspaceAsset.id.desc())
                )
            )
            .scalars()
            .all()
        )
        deduplicated: dict[str, WorkspaceAsset] = {}
        for asset in rows:
            deduplicated.setdefault(str(asset.name), asset)
        return deduplicated

    @staticmethod
    def _ensure_owner_kind(owner_kind: str) -> None:
        """校验 owner 种类合法，避免写入未知绑定类型。"""

        if owner_kind not in OWNER_KINDS:
            raise AppException(status_code=400, code="ASSET_BINDING_OWNER_INVALID", detail="资源绑定 owner 种类不合法。")


async def run_asset_binding_expiry_loop(session_factory: Callable[..., AsyncSession]) -> None:
    """后台循环：定期释放过期的资源持有，保证 artifact/请求到期后文件可按规则回收。

    持有均带到期时间；artifact 与渲染请求的显式释放仍是主路径，
    本循环兜底 TTL 到期与进程崩溃遗留。
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
        except Exception as exc:
            logger.warning("资源绑定过期对账循环异常: %s", exc, exc_info=True)
            await asyncio.sleep(5.0)
