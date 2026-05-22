"""文件功能：按预览作用域收集 Icon 资源名，并生成 Runtime 可消费的 static_icons 配置。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, PageFileType
from app.models.page import Page
from app.services.asset_service import get_driver
from app.services.icon_analysis_service import IconAnalysisService
from app.services.resource_reference_parser import DYNAMIC_RESOURCE_NAME, ResourceReferenceParser


class RuntimeIconService:
    """运行时图标服务，负责按预览对象收集图标依赖并生成最小配置集。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.storage_driver = get_driver()

    async def build_project_icon_config(
        self,
        *,
        workspace_id: int,
        project_icon_name: str | None,
        runtime_route_config: dict[str, object],
        pages: list[Page],
    ) -> dict[str, list[dict[str, object | None]]]:
        """收集整项目预览所需图标，并输出最小 static_icons 配置。"""

        icon_names: list[str] = []
        self._append_unique_name(icon_names, project_icon_name)
        self._extend_unique_names(icon_names, self._collect_route_icon_names(runtime_route_config))
        for page in pages:
            self._extend_unique_names(
                icon_names,
                self.collect_static_icon_names_from_source(
                    source_text=page.page_content,
                    file_type=page.file_type,
                    source_label=f"页面 {page.code}",
                ),
            )
        return await self.build_static_icon_config(workspace_id, icon_names)

    async def build_page_icon_config(self, *, page: Page) -> dict[str, list[dict[str, object | None]]]:
        """收集单页面预览入口页依赖的图标，并输出最小 static_icons 配置。"""

        icon_names = self.collect_static_icon_names_from_source(
            source_text=page.page_content,
            file_type=page.file_type,
            source_label=f"页面 {page.code}",
        )
        return await self.build_static_icon_config(page.workspace_id, icon_names)

    async def build_page_icon_config_from_modules(
        self,
        *,
        workspace_id: int,
        modules_data: Iterable[dict[str, str]],
    ) -> dict[str, list[dict[str, object | None]]]:
        """基于已发布模块图收集单页面预览依赖的图标，覆盖传递组件依赖。"""

        icon_names = self.collect_static_icon_names_from_modules(modules_data)
        return await self.build_static_icon_config(workspace_id, icon_names)

    async def build_component_icon_config(
        self,
        *,
        workspace_id: int,
        source_text: str,
        source_label: str,
    ) -> dict[str, list[dict[str, object | None]]]:
        """收集组件源码依赖的图标，并输出最小 static_icons 配置。"""

        icon_names = self.collect_static_icon_names_from_source(
            source_text=source_text,
            file_type=PageFileType.VUE.value,
            source_label=source_label,
        )
        return await self.build_static_icon_config(workspace_id, icon_names)

    async def build_component_icon_config_from_modules(
        self,
        *,
        workspace_id: int,
        modules_data: Iterable[dict[str, str]],
        extra_icon_names: Iterable[str] | None = None,
    ) -> dict[str, list[dict[str, object | None]]]:
        """基于组件模块图收集图标，并允许附带主题等额外静态图标。"""

        icon_names: list[str] = []
        if extra_icon_names is not None:
            self._extend_unique_names(icon_names, extra_icon_names)
        self._extend_unique_names(icon_names, self.collect_static_icon_names_from_modules(modules_data))
        return await self.build_static_icon_config(workspace_id, icon_names)

    async def build_project_icon_config_from_modules(
        self,
        *,
        workspace_id: int,
        project_icon_name: str | None,
        runtime_route_config: dict[str, object],
        modules_data: Iterable[dict[str, str]],
    ) -> dict[str, list[dict[str, object | None]]]:
        """基于项目发布模块图和路由元信息收集整项目预览/构建所需图标。"""

        icon_names: list[str] = []
        self._append_unique_name(icon_names, project_icon_name)
        self._extend_unique_names(icon_names, self._collect_route_icon_names(runtime_route_config))
        self._extend_unique_names(icon_names, self.collect_static_icon_names_from_modules(modules_data))
        return await self.build_static_icon_config(workspace_id, icon_names)

    async def build_static_icon_config(
        self,
        workspace_id: int,
        icon_names: Iterable[str],
    ) -> dict[str, list[dict[str, object | None]]]:
        """按图标名列表构建最小 `static_icons` 配置，并校验资源存在性。"""

        deduplicated_names = self._deduplicate_keep_order(icon_names)
        if not deduplicated_names:
            return {"static_icons": []}

        asset_items = await self._list_workspace_icon_assets(workspace_id)
        asset_name_map: dict[str, WorkspaceAsset] = {}
        for asset in asset_items:
            normalized_name = str(asset.name or "").strip()
            if normalized_name and normalized_name not in asset_name_map:
                asset_name_map[normalized_name] = asset

        missing_names = [name for name in deduplicated_names if name not in asset_name_map]
        if missing_names:
            raise AppException(
                status_code=400,
                code="PREVIEW_ICON_ASSET_MISSING",
                detail=f"以下 Icon 资源在当前工作空间中不存在：{', '.join(missing_names)}。",
            )

        return {
            "static_icons": [
                {
                    "name": icon_name,
                    "src": icon_name,
                    "analysis": await self._resolve_icon_analysis(asset_name_map[icon_name]),
                }
                for icon_name in deduplicated_names
            ]
        }

    @classmethod
    def collect_static_icon_names_from_source(
        cls,
        *,
        source_text: str,
        file_type: PageFileType | str,
        source_label: str,
    ) -> list[str]:
        """从单份 Vue 源码中提取静态 Icon 名称，动态 :name 直接报错。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else str(file_type)
        if normalized_file_type != PageFileType.VUE.value:
            return []

        icon_names: list[str] = []
        template_content = ResourceReferenceParser.extract_template_content(source_text)
        if not template_content:
            return icon_names

        resource_items = ResourceReferenceParser.collect_vue_component_resource_items(source_text)
        for component_name, resource_name in resource_items:
            if component_name != "Icon":
                continue
            if resource_name == DYNAMIC_RESOURCE_NAME:
                raise AppException(
                    status_code=400,
                    code="PREVIEW_ICON_NAME_DYNAMIC_UNSUPPORTED",
                    detail=(
                        f"{source_label} 中存在无法静态解析的 Icon 组件动态 :name 表达式。"
                        "预览仅支持字符串字面量，或同一 Vue 文件顶层 const 数组对象字面量中可静态枚举的字段，"
                        "例如 v-for=\"item in items\" 搭配 :name=\"item.icon\"；不要使用 computed、函数返回、"
                        "imported data、拼接或条件表达式生成图标名。"
                    ),
                )
            cls._append_unique_name(icon_names, resource_name)
        return icon_names

    @classmethod
    def collect_static_icon_names_from_modules(cls, modules_data: Iterable[dict[str, str]]) -> list[str]:
        """从 release_modules 快照中提取全部静态 Icon 名，覆盖页面和组件的传递依赖。"""

        icon_names: list[str] = []
        for module_item in modules_data:
            logical_path = str(module_item.get("logical_path") or "").strip()
            file_type = Path(logical_path).suffix.lower().lstrip(".")
            if not file_type:
                continue
            source_text = str(module_item.get("content") or "")
            cls._extend_unique_names(
                icon_names,
                cls.collect_static_icon_names_from_source(
                    source_text=source_text,
                    file_type=file_type,
                    source_label=f"模块 {logical_path or '<unknown>'}",
                ),
            )
        return icon_names

    @classmethod
    def _collect_route_icon_names(cls, runtime_route_config: dict[str, object]) -> list[str]:
        """从 Runtime 路由配置中递归收集项目导航使用到的 icon 名称。"""

        result: list[str] = []
        for route_item in runtime_route_config.get("routes", []) or []:
            cls._collect_route_icon_names_recursive(result, route_item)
        return result

    @classmethod
    def _collect_route_icon_names_recursive(cls, result: list[str], route_item: object) -> None:
        """递归扫描单个路由节点及其子节点的 meta.icon。"""

        if not isinstance(route_item, dict):
            return

        meta = route_item.get("meta")
        if isinstance(meta, dict):
            cls._append_unique_name(result, meta.get("icon"))

        for child in route_item.get("children", []) or []:
            cls._collect_route_icon_names_recursive(result, child)

    async def _list_workspace_icon_assets(self, workspace_id: int) -> list[WorkspaceAsset]:
        """读取工作空间内全部图标资产，供图标名存在性校验使用。"""

        return list(
            (
                await self.session.execute(
                    select(WorkspaceAsset)
                    .where(WorkspaceAsset.workspace_id == workspace_id)
                    .where(WorkspaceAsset.asset_type == AssetType.ICON.value)
                    .order_by(WorkspaceAsset.created_at.desc(), WorkspaceAsset.id.desc())
                )
            ).scalars()
        )

    async def _resolve_icon_analysis(self, asset: WorkspaceAsset) -> dict[str, Any] | None:
        """解析单个图标资产的结构化分析信息，并为历史资产做懒回填。"""

        if asset.analysis_metadata is not None:
            return asset.analysis_metadata

        if str(asset.asset_type or "").strip() != AssetType.ICON.value:
            return None

        try:
            content = await self.storage_driver.read_content(asset.workspace_id, asset.file_name)
        except Exception:
            return None

        analysis_metadata = IconAnalysisService.analyze_icon_asset(
            file_name=asset.original_name,
            content_type=None,
            content=content,
        )
        asset.analysis_metadata = analysis_metadata
        return analysis_metadata

    @staticmethod
    def _append_unique_name(target: list[str], value: object) -> None:
        """将单个图标名按保序去重方式追加到结果列表。"""

        normalized_value = str(value or "").strip()
        if normalized_value and normalized_value not in target:
            target.append(normalized_value)

    @classmethod
    def _extend_unique_names(cls, target: list[str], values: Iterable[str]) -> None:
        """将一组图标名按保序去重方式追加到结果列表。"""

        for value in values:
            cls._append_unique_name(target, value)

    @staticmethod
    def _deduplicate_keep_order(values: Iterable[str]) -> list[str]:
        """在保留原顺序的前提下去重，保证 static_icons 输出稳定。"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized_value = str(value or "").strip()
            if not normalized_value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            result.append(normalized_value)
        return result
