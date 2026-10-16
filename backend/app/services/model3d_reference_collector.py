"""文件功能：从页面与组件版本的模块闭包递归收集 model3d 资源引用，产出可冻结绑定的资源集合。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.repositories.component_resource_index_repository import ComponentResourceIndexRepository
from app.repositories.module_dependency_repository import ModuleDependencyRepository
from app.services.asset_binding_service import AssetBindingService
from app.services.resource_reference_parser import DYNAMIC_RESOURCE_NAME

_MODEL_COMPONENT_NAME = "AssetModel"


@dataclass(slots=True)
class Model3dReferenceCollection:
    """三维引用收集结果：去重后的当前根资源与未解析动态引用标记。"""

    assets: list[WorkspaceAsset] = field(default_factory=list)
    dynamic_unresolved: bool = False


class Model3dReferenceCollector:
    """递归收集页面/组件版本自身与组件版本闭包中的三维资源引用。

    只解析静态资源名；`AssetModel` 的动态 name 不猜测覆盖，统一标记为未解析，
    由调用方决定警告或阻断语义。收集结果仅含 active 根资源，历史副本不参与。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.component_resource_repository = ComponentResourceIndexRepository(session)

    async def collect_for_page_version(
        self,
        *,
        workspace_id: int,
        page_version_id: int,
        static_resource_items: Iterable[tuple[str, str]],
    ) -> Model3dReferenceCollection:
        """收集页面版本自身与其组件版本闭包中的三维资源。"""

        dependency_items = await self.module_dependency_repository.list_page_version_dependencies(page_version_id)
        root_component_version_ids = [
            int(item.component_version_id)
            for item in dependency_items
            if item.component_version_id is not None
        ]
        return await self._collect(
            workspace_id=workspace_id,
            static_resource_items=static_resource_items,
            root_component_version_ids=root_component_version_ids,
        )

    async def collect_for_component_version(
        self,
        *,
        workspace_id: int,
        component_version_id: int,
        static_resource_items: Iterable[tuple[str, str]],
    ) -> Model3dReferenceCollection:
        """收集组件版本自身与其依赖组件版本闭包中的三维资源。"""

        dependency_items = await self.module_dependency_repository.list_component_version_dependencies(component_version_id)
        root_component_version_ids = [
            int(item.dependency_component_version_id)
            for item in dependency_items
            if item.dependency_component_version_id is not None
        ]
        return await self._collect(
            workspace_id=workspace_id,
            static_resource_items=static_resource_items,
            root_component_version_ids=root_component_version_ids,
        )

    async def list_owner_live_asset_tokens(self, *, workspace_id: int, owner_kind: str, owner_key: str) -> list[str]:
        """按绑定名集合解析当前实时文件身份，返回排序后的 name:file_hash 指纹 token 列表。

        绑定名集合来自版本冻结（含组件闭包），哈希取当前 active 根资源；
        供截图/渲染指纹使用：资源替换后摘要随之变化，旧文件版本的临时产物不会当作当前结果复用。
        """

        bindings = await AssetBindingService(self.session).list_owner_bindings(owner_kind, owner_key)
        names = sorted(
            {str(item.resource_name or "").strip() for item in bindings if str(item.resource_name or "").strip()}
        )
        if not names:
            return []
        assets = await self._load_active_model3d_assets(workspace_id=workspace_id, names=names)
        return [
            f"{name}:{assets[name].file_hash}" if name in assets else f"{name}:missing"
            for name in names
        ]

    async def _load_active_model3d_assets(
        self,
        *,
        workspace_id: int,
        names: Iterable[str],
    ) -> dict[str, WorkspaceAsset]:
        """按资源名批量加载当前 active 三维根资源，按创建时间取最新同名记录。"""

        normalized_names = sorted({str(name or "").strip() for name in names if str(name or "").strip()})
        if not normalized_names:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.source_asset_id.is_(None))
                    .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                    .where(WorkspaceAsset.asset_type == AssetType.MODEL3D.value)
                    .where(WorkspaceAsset.name.in_(normalized_names))
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

    async def _collect(
        self,
        *,
        workspace_id: int,
        static_resource_items: Iterable[tuple[str, str]],
        root_component_version_ids: Iterable[int],
    ) -> Model3dReferenceCollection:
        """展开组件版本闭包并解析静态资源名对应的三维根资源。"""

        pairs: list[tuple[str, str]] = [(str(component), str(resource)) for component, resource in static_resource_items]
        queued = [int(item) for item in root_component_version_ids]
        visited: set[int] = set()
        while queued:
            version_id = queued.pop(0)
            if version_id in visited:
                continue
            visited.add(version_id)
            resource_rows = await self.component_resource_repository.list_component_resources_by_version(version_id)
            for row in resource_rows:
                pairs.append((str(row.component_name), str(row.resource_name)))
            dependency_items = await self.module_dependency_repository.list_component_version_dependencies(version_id)
            for item in dependency_items:
                if item.dependency_component_version_id is not None:
                    queued.append(int(item.dependency_component_version_id))
        return await self._resolve(workspace_id=workspace_id, pairs=pairs)

    async def _resolve(self, *, workspace_id: int, pairs: Iterable[tuple[str, str]]) -> Model3dReferenceCollection:
        """把静态资源名解析为当前 active 的三维根资源，动态引用只做标记。"""

        names: set[str] = set()
        dynamic_unresolved = False
        for component_name, resource_name in pairs:
            normalized_name = str(resource_name or "").strip()
            if not normalized_name:
                continue
            if normalized_name == DYNAMIC_RESOURCE_NAME:
                if str(component_name or "").strip() == _MODEL_COMPONENT_NAME:
                    dynamic_unresolved = True
                continue
            names.add(normalized_name)
        if not names:
            return Model3dReferenceCollection(assets=[], dynamic_unresolved=dynamic_unresolved)

        deduplicated = await self._load_active_model3d_assets(workspace_id=workspace_id, names=names)
        return Model3dReferenceCollection(assets=list(deduplicated.values()), dynamic_unresolved=dynamic_unresolved)
