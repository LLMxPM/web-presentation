"""文件功能：从页面/组件版本索引闭包解析资源的当前身份 token，供截图与渲染指纹判断资源替换。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.repositories.component_resource_index_repository import ComponentResourceIndexRepository
from app.repositories.module_dependency_repository import ModuleDependencyRepository
from app.repositories.page_component_index_repository import PageComponentIndexRepository
from app.services.resource_reference_parser import DYNAMIC_RESOURCE_NAME


@dataclass(slots=True)
class OwnerResourceTokens:
    """单个 owner 的资源实时身份结果：排序后的身份 token 与是否引用三维资源。"""

    tokens: list[str] = field(default_factory=list)
    has_model3d: bool = False


class OwnerResourceTokenResolver:
    """解析页面/组件版本闭包内全部资源名的当前身份，输出 asset:name:file_hash 指纹 token。

    版本索引与依赖索引不可变，重复解析结果稳定；动态资源名不猜测覆盖，不计入 token。
    资源缺失时以 missing 标记显式入指纹，替换资源后 token 变化触发缓存失效。
    批量入口按层批量查询闭包，避免逐 owner N+1。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.component_resource_repository = ComponentResourceIndexRepository(session)
        self.page_resource_repository = PageComponentIndexRepository(session)

    async def resolve_page_version_tokens(
        self,
        *,
        workspace_id: int,
        page_version_id: int,
    ) -> OwnerResourceTokens:
        """解析单个页面版本自身与组件闭包中的资源身份。"""

        resolved = await self.resolve_page_version_tokens_bulk(
            workspace_id=workspace_id,
            page_version_ids=[page_version_id],
        )
        return resolved.get(int(page_version_id), OwnerResourceTokens())

    async def resolve_page_version_tokens_bulk(
        self,
        *,
        workspace_id: int,
        page_version_ids: Iterable[int],
    ) -> dict[int, OwnerResourceTokens]:
        """批量解析多个页面版本的资源身份；页面索引、依赖与组件闭包各按层批量查询。"""

        normalized = [int(item) for item in dict.fromkeys(page_version_ids)]
        if not normalized:
            return {}
        page_rows = await self.page_resource_repository.list_component_resources_by_versions(normalized)
        page_deps = await self.module_dependency_repository.list_page_version_dependency_component_version_ids_bulk(
            normalized
        )
        names_by_owner: dict[int, set[str]] = {key: set() for key in normalized}
        initial_frontier: dict[int, set[int]] = {}
        for key in normalized:
            for row in page_rows.get(key, []):
                self._add_name(names_by_owner[key], row.resource_name)
            initial_frontier[key] = {int(item) for item in page_deps.get(key, [])}
        closure_names = await self._collect_component_closure_names(initial_frontier)
        for key, names in closure_names.items():
            names_by_owner[key].update(names)
        return await self._build_tokens(workspace_id=workspace_id, names_by_owner=names_by_owner)

    async def resolve_component_version_tokens(
        self,
        *,
        workspace_id: int,
        component_version_id: int,
    ) -> OwnerResourceTokens:
        """解析单个组件版本自身与依赖闭包中的资源身份。"""

        key = int(component_version_id)
        closure_names = await self._collect_component_closure_names({key: {key}})
        resolved = await self._build_tokens(
            workspace_id=workspace_id,
            names_by_owner={key: closure_names.get(key, set())},
        )
        return resolved.get(key, OwnerResourceTokens())

    async def _collect_component_closure_names(
        self,
        initial_frontier: dict[int, set[int]],
    ) -> dict[int, set[str]]:
        """按层展开组件版本闭包，累计各 owner 触达版本的资源名；每层最多两次批量查询。"""

        names_by_owner: dict[int, set[str]] = {key: set() for key in initial_frontier}
        pending: dict[int, set[int]] = {key: set(ids) for key, ids in initial_frontier.items()}
        expanded: set[int] = set()
        while True:
            fresh = sorted({version_id for ids in pending.values() for version_id in ids if version_id not in expanded})
            if not fresh:
                break
            expanded.update(fresh)
            resource_rows = await self.component_resource_repository.list_component_resources_by_versions(fresh)
            dependency_map = await self.module_dependency_repository.list_component_version_dependency_version_ids_bulk(
                fresh
            )
            for owner_key, ids in pending.items():
                for version_id in ids & set(fresh):
                    for row in resource_rows.get(version_id, []):
                        self._add_name(names_by_owner[owner_key], row.resource_name)
                    pending[owner_key].update(
                        item for item in dependency_map.get(version_id, []) if item not in expanded
                    )
        return names_by_owner

    async def _build_tokens(
        self,
        *,
        workspace_id: int,
        names_by_owner: dict[int, set[str]],
    ) -> dict[int, OwnerResourceTokens]:
        """把各 owner 的资源名集合解析为当前身份 token，缺失资源显式记入。"""

        all_names = sorted({name for names in names_by_owner.values() for name in names})
        assets = await self._load_active_assets(workspace_id=workspace_id, names=all_names)
        resolved: dict[int, OwnerResourceTokens] = {}
        for owner_key, names in names_by_owner.items():
            tokens: list[str] = []
            has_model3d = False
            for name in sorted(names):
                asset = assets.get(name)
                if asset is None:
                    tokens.append(f"asset:{name}:missing")
                    continue
                tokens.append(f"asset:{name}:{asset.file_hash}")
                if str(asset.asset_type) == AssetType.MODEL3D.value:
                    has_model3d = True
            resolved[owner_key] = OwnerResourceTokens(tokens=tokens, has_model3d=has_model3d)
        return resolved

    async def _load_active_assets(
        self,
        *,
        workspace_id: int,
        names: list[str],
    ) -> dict[str, WorkspaceAsset]:
        """按资源名批量加载当前 active 根资源，按创建时间取最新同名记录。"""

        if not names:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.source_asset_id.is_(None))
                    .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
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
    def _add_name(target: set[str], resource_name: str | None) -> None:
        """加入有效静态资源名；空名与动态占位符不进入指纹。"""

        name = str(resource_name or "").strip()
        if not name or name == DYNAMIC_RESOURCE_NAME:
            return
        target.add(name)
