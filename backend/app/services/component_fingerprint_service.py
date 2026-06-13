"""文件功能：计算工作空间组件发布版本与离线包组件的稳定内容指纹。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.component_preview_schema import parse_component_preview_schema_text
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.services.component_resource_index_service import ComponentResourceIndexService
from app.services.workspace_font_service import WorkspaceFontService

FINGERPRINT_SCHEMA_VERSION = 1
_WORKSPACE_COMPONENT_REF_PATTERN = re.compile(
    r"@workspace-components/(?P<component_code>[A-Za-z0-9_-]+)/v/(?P<version_no>\d+)(?:\.vue)?"
)


@dataclass(frozen=True, slots=True)
class ComponentFingerprintResult:
    """组件指纹计算结果。"""

    content_hash: str
    preview_schema_hash: str
    component_fingerprint: str
    fingerprint_schema_version: int = FINGERPRINT_SCHEMA_VERSION


class ComponentFingerprintService:
    """按统一规则计算组件源码、预览 schema、依赖、资源和字体配置指纹。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)

    async def ensure_workspace_component_version_fingerprint(
        self,
        *,
        component: WorkspaceComponent,
        version: WorkspaceComponentVersion,
        asset_names_override: list[str] | None = None,
    ) -> ComponentFingerprintResult:
        """确保指定组件版本拥有当前 schema 的指纹字段，并返回计算结果。"""

        if (
            asset_names_override is None
            and version.content_hash
            and version.preview_schema_hash
            and version.component_fingerprint
            and version.fingerprint_schema_version == FINGERPRINT_SCHEMA_VERSION
        ):
            return ComponentFingerprintResult(
                content_hash=version.content_hash,
                preview_schema_hash=version.preview_schema_hash,
                component_fingerprint=version.component_fingerprint,
                fingerprint_schema_version=FINGERPRINT_SCHEMA_VERSION,
            )

        result = await self.calculate_workspace_component_version_fingerprint(
            component=component,
            version=version,
            visiting=set(),
            asset_names_override=asset_names_override,
        )
        version.content_hash = result.content_hash
        version.preview_schema_hash = result.preview_schema_hash
        version.component_fingerprint = result.component_fingerprint
        version.fingerprint_schema_version = result.fingerprint_schema_version
        await self.session.flush()
        return result

    async def calculate_workspace_component_version_fingerprint(
        self,
        *,
        component: WorkspaceComponent,
        version: WorkspaceComponentVersion,
        visiting: set[int],
        asset_names_override: list[str] | None = None,
    ) -> ComponentFingerprintResult:
        """递归计算数据库中组件发布版本的稳定指纹。"""

        if version.id in visiting:
            raise AppException(
                status_code=409,
                code="COMPONENT_FINGERPRINT_DEPENDENCY_CYCLE",
                detail=f"组件 {component.code} v{version.version_no} 存在循环依赖，无法计算指纹。",
            )
        visiting.add(version.id)
        dependency_fingerprints = await self._resolve_workspace_dependency_fingerprints(
            workspace_id=component.workspace_id,
            source_label=f"组件 {component.code} v{version.version_no}",
            source_texts=[version.content, version.preview_schema or ""],
            visiting=visiting,
        )
        visiting.remove(version.id)

        asset_hashes = await self._resolve_workspace_asset_hashes(
            workspace_id=component.workspace_id,
            asset_names=(
                list(asset_names_override)
                if asset_names_override is not None
                else self._collect_static_asset_names(version.content, version.preview_schema)
            ),
        )
        font_signatures = await self._resolve_workspace_font_signatures(
            workspace_id=component.workspace_id,
            font_asset_names=WorkspaceFontService.collect_declared_font_asset_names([version.content]),
        )
        return self._build_fingerprint_result(
            file_type=str(version.file_type),
            content=version.content,
            preview_schema=version.preview_schema,
            dependency_fingerprints=dependency_fingerprints,
            asset_hashes=asset_hashes,
            font_signatures=font_signatures,
        )

    async def ensure_current_workspace_fingerprints(self, workspace_id: int) -> None:
        """为目标工作空间缺少指纹的当前发布版本做按需补算，失败的历史组件会被跳过。"""

        result = await self.session.execute(
            select(WorkspaceComponent, WorkspaceComponentVersion)
            .join(
                WorkspaceComponentVersion,
                WorkspaceComponentVersion.component_id == WorkspaceComponent.id,
            )
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.current_version_no > 0)
            .where(WorkspaceComponentVersion.version_no == WorkspaceComponent.current_version_no)
            .where(
                (WorkspaceComponentVersion.component_fingerprint.is_(None))
                | (WorkspaceComponentVersion.fingerprint_schema_version != FINGERPRINT_SCHEMA_VERSION)
            )
        )
        for component, version in result.all():
            try:
                await self.ensure_workspace_component_version_fingerprint(component=component, version=version)
            except AppException:
                continue

    async def list_current_components_by_fingerprint(
        self,
        *,
        workspace_id: int,
        component_fingerprint: str,
    ) -> list[WorkspaceComponent]:
        """按当前发布版本指纹查找可复用的启用组件。"""

        await self.ensure_current_workspace_fingerprints(workspace_id)
        result = await self.session.scalars(
            select(WorkspaceComponent)
            .join(
                WorkspaceComponentVersion,
                WorkspaceComponentVersion.component_id == WorkspaceComponent.id,
            )
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.current_version_no > 0)
            .where(WorkspaceComponentVersion.version_no == WorkspaceComponent.current_version_no)
            .where(WorkspaceComponentVersion.component_fingerprint == component_fingerprint)
            .order_by(WorkspaceComponent.import_name.asc(), WorkspaceComponent.id.asc())
        )
        return list(result.all())

    def calculate_package_component_fingerprints(
        self,
        *,
        package_components: list[Any],
        package_assets: list[Any],
        font_configs: list[dict[str, Any]],
    ) -> dict[tuple[str, int], ComponentFingerprintResult]:
        """按包内依赖拓扑计算离线包组件指纹。"""

        asset_hashes_by_name = {
            str(item.metadata.get("name") or "").strip(): str(item.metadata.get("file_hash") or "").strip()
            for item in package_assets
            if str(item.metadata.get("name") or "").strip()
        }
        font_config_by_asset_name = {
            str(item.get("asset_name") or "").strip(): item
            for item in font_configs
            if str(item.get("asset_name") or "").strip()
        }
        component_results: dict[tuple[str, int], ComponentFingerprintResult] = {}
        for package_component in self._topological_sort_package_components(package_components):
            key = (package_component.source_component_code, package_component.source_version_no)
            dependency_fingerprints = {
                dependency: component_results[dependency].component_fingerprint
                for dependency in package_component.dependencies
                if dependency in component_results
            }
            asset_hashes = self._resolve_package_asset_hashes(
                package_component=package_component,
                asset_hashes_by_name=asset_hashes_by_name,
            )
            font_signatures = self._resolve_package_font_signatures(
                content=package_component.content,
                asset_hashes_by_name=asset_hashes_by_name,
                font_config_by_asset_name=font_config_by_asset_name,
            )
            component_results[key] = self._build_fingerprint_result(
                file_type=str(package_component.metadata.get("file_type") or "vue"),
                content=package_component.content,
                preview_schema=package_component.preview_schema,
                dependency_fingerprints=dependency_fingerprints,
                asset_hashes=asset_hashes,
                font_signatures=font_signatures,
            )
        return component_results

    @classmethod
    def _build_fingerprint_result(
        cls,
        *,
        file_type: str,
        content: str,
        preview_schema: str | None,
        dependency_fingerprints: dict[tuple[str, int], str],
        asset_hashes: dict[str, str],
        font_signatures: list[dict[str, str]],
    ) -> ComponentFingerprintResult:
        """基于规范化载荷生成源码 hash、预览 schema hash 与组件总指纹。"""

        normalized_content = normalize_text_to_lf(content or "")
        canonical_content = cls._replace_component_refs_with_fingerprints(normalized_content, dependency_fingerprints)
        canonical_preview_schema = cls._canonical_preview_schema(preview_schema, dependency_fingerprints)
        content_hash = cls._sha256_text(normalized_content)
        preview_schema_hash = cls._sha256_text(canonical_preview_schema)
        fingerprint_payload = {
            "schema_version": FINGERPRINT_SCHEMA_VERSION,
            "file_type": str(file_type or "").strip() or "vue",
            "content": canonical_content,
            "preview_schema": canonical_preview_schema,
            "dependencies": sorted(set(dependency_fingerprints.values())),
            "assets": [
                {"name": name, "file_hash": asset_hashes[name]}
                for name in sorted(asset_hashes)
            ],
            "fonts": sorted(font_signatures, key=lambda item: item["asset_name"]),
        }
        component_fingerprint = cls._sha256_text(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        return ComponentFingerprintResult(
            content_hash=content_hash,
            preview_schema_hash=preview_schema_hash,
            component_fingerprint=component_fingerprint,
        )

    async def _resolve_workspace_dependency_fingerprints(
        self,
        *,
        workspace_id: int,
        source_label: str,
        source_texts: list[str],
        visiting: set[int],
    ) -> dict[tuple[str, int], str]:
        """解析源码和预览 schema 中的组件引用，并递归获取依赖组件指纹。"""

        result: dict[tuple[str, int], str] = {}
        for component_code, version_no in self._collect_component_refs(source_texts):
            dependency_component = await self.component_repository.get_by_code(component_code)
            if dependency_component is None or dependency_component.workspace_id != workspace_id:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_FINGERPRINT_DEPENDENCY_MISSING",
                    detail=f"{source_label} 的依赖组件不存在：{component_code} v{version_no}。",
                )
            dependency_version = await self.component_version_repository.get_by_component_and_version(
                dependency_component.id,
                version_no,
            )
            if dependency_version is None:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_FINGERPRINT_DEPENDENCY_VERSION_MISSING",
                    detail=f"{source_label} 的依赖组件版本不存在：{component_code} v{version_no}。",
                )
            dependency_result = await self.ensure_workspace_component_version_fingerprint(
                component=dependency_component,
                version=dependency_version,
            )
            result[(component_code, version_no)] = dependency_result.component_fingerprint
        return result

    async def _resolve_workspace_asset_hashes(self, *, workspace_id: int, asset_names: list[str]) -> dict[str, str]:
        """把工作空间资源名解析为文件 hash。"""

        names = sorted({name for name in asset_names if name})
        if not names:
            return {}
        rows = await self.session.scalars(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name.in_(names))
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        )
        assets = {asset.name: asset.file_hash for asset in rows.all()}
        missing = [name for name in names if name not in assets]
        if missing:
            raise AppException(
                status_code=409,
                code="COMPONENT_FINGERPRINT_ASSET_MISSING",
                detail=f"组件指纹计算缺少资源：{', '.join(missing)}。",
            )
        return assets

    async def _resolve_workspace_font_signatures(
        self,
        *,
        workspace_id: int,
        font_asset_names: list[str],
    ) -> list[dict[str, str]]:
        """把工作空间字体声明解析为稳定字体配置签名。"""

        names = sorted({name for name in font_asset_names if name})
        if not names:
            return []
        result = await self.session.execute(
            select(WorkspaceFontConfig, WorkspaceAsset)
            .join(WorkspaceAsset, WorkspaceAsset.id == WorkspaceFontConfig.asset_id)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_name.in_(names))
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        )
        signatures = {
            font_config.asset_name: self._build_font_signature(font_config, asset.file_hash)
            for font_config, asset in result.all()
        }
        missing = [name for name in names if name not in signatures]
        if missing:
            raise AppException(
                status_code=409,
                code="COMPONENT_FINGERPRINT_FONT_MISSING",
                detail=f"组件指纹计算缺少字体配置：{', '.join(missing)}。",
            )
        return [signatures[name] for name in names]

    @classmethod
    def _resolve_package_asset_hashes(
        cls,
        *,
        package_component: Any,
        asset_hashes_by_name: dict[str, str],
    ) -> dict[str, str]:
        """把包内组件资源名解析为包内资源 hash。"""

        metadata = getattr(package_component, "metadata", {}) or {}
        declared_asset_names = getattr(package_component, "asset_names", None)
        if declared_asset_names is None or ("asset_names" not in metadata and not declared_asset_names):
            asset_names = cls._collect_static_asset_names(package_component.content, package_component.preview_schema)
        else:
            asset_names = sorted({str(name).strip() for name in declared_asset_names if str(name).strip()})
        result: dict[str, str] = {}
        missing: list[str] = []
        for name in asset_names:
            file_hash = asset_hashes_by_name.get(name)
            if not file_hash:
                missing.append(name)
                continue
            result[name] = file_hash
        if missing:
            raise AppException(
                status_code=409,
                code="COMPONENT_FINGERPRINT_PACKAGE_ASSET_MISSING",
                detail=f"组件 {package_component.source_component_code} 指纹计算缺少包内资源：{', '.join(missing)}。",
            )
        return result

    @classmethod
    def _resolve_package_font_signatures(
        cls,
        *,
        content: str,
        asset_hashes_by_name: dict[str, str],
        font_config_by_asset_name: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        """把包内组件字体声明解析为包内字体签名。"""

        signatures: list[dict[str, str]] = []
        for asset_name in WorkspaceFontService.collect_declared_font_asset_names([content]):
            font_config = font_config_by_asset_name.get(asset_name)
            file_hash = asset_hashes_by_name.get(asset_name)
            if font_config is None or not file_hash:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_FINGERPRINT_PACKAGE_FONT_MISSING",
                    detail=f"组件指纹计算缺少包内字体配置：{asset_name}。",
                )
            signatures.append(cls._build_font_signature_from_payload(font_config, file_hash))
        return signatures

    @staticmethod
    def _build_font_signature(font_config: WorkspaceFontConfig, file_hash: str) -> dict[str, str]:
        """从数据库字体配置生成稳定签名。"""

        return {
            "asset_name": font_config.asset_name,
            "file_hash": file_hash,
            "font_family": font_config.font_family,
            "font_format": font_config.font_format,
            "font_weight": font_config.font_weight,
            "font_style": font_config.font_style,
            "font_display": font_config.font_display,
            "status": font_config.status,
        }

    @staticmethod
    def _build_font_signature_from_payload(payload: dict[str, Any], file_hash: str) -> dict[str, str]:
        """从离线包字体配置生成稳定签名。"""

        return {
            "asset_name": str(payload.get("asset_name") or "").strip(),
            "file_hash": file_hash,
            "font_family": str(payload.get("font_family") or "").strip(),
            "font_format": str(payload.get("font_format") or "").strip(),
            "font_weight": str(payload.get("font_weight") or "").strip(),
            "font_style": str(payload.get("font_style") or "").strip(),
            "font_display": str(payload.get("font_display") or "").strip(),
            "status": str(payload.get("status") or "").strip(),
        }

    @staticmethod
    def _collect_static_asset_names(content: str, preview_schema: str | None) -> list[str]:
        """收集组件源码和 preview_schema 中的静态资源名。"""

        items = ComponentResourceIndexService.collect_version_resource_items(
            content=content or "",
            preview_schema=preview_schema,
        )
        return sorted({
            resource_name
            for _, resource_name in items
            if resource_name and resource_name != "__DYNAMIC__"
        })

    @staticmethod
    def _collect_component_refs(source_texts: list[str]) -> list[tuple[str, int]]:
        """从源码文本集合中收集工作空间组件引用。"""

        refs: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for source_text in source_texts:
            for match in _WORKSPACE_COMPONENT_REF_PATTERN.finditer(source_text or ""):
                key = (match.group("component_code"), int(match.group("version_no")))
                if key in seen:
                    continue
                seen.add(key)
                refs.append(key)
        return refs

    @classmethod
    def _replace_component_refs_with_fingerprints(
        cls,
        source_text: str,
        dependency_fingerprints: dict[tuple[str, int], str],
    ) -> str:
        """把本地组件 import 路径替换为依赖组件指纹占位。"""

        def replace(match: re.Match[str]) -> str:
            key = (match.group("component_code"), int(match.group("version_no")))
            fingerprint = dependency_fingerprints.get(key)
            if not fingerprint:
                return match.group(0)
            return f"@workspace-component-fingerprint/{fingerprint}"

        return _WORKSPACE_COMPONENT_REF_PATTERN.sub(replace, source_text or "")

    @classmethod
    def _canonical_preview_schema(
        cls,
        preview_schema: str | None,
        dependency_fingerprints: dict[tuple[str, int], str],
    ) -> str:
        """将 preview_schema 解析为稳定 JSON，并替换组件引用为指纹占位。"""

        parsed_schema = parse_component_preview_schema_text(preview_schema) or {}
        stable_text = json.dumps(parsed_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        replaced_text = cls._replace_component_refs_with_fingerprints(stable_text, dependency_fingerprints)
        return replaced_text

    @staticmethod
    def _topological_sort_package_components(components: list[Any]) -> list[Any]:
        """按包内组件依赖拓扑排序，依赖组件排在使用方前面。"""

        component_map = {(item.source_component_code, item.source_version_no): item for item in components}
        ordered: list[Any] = []
        visited: set[tuple[str, int]] = set()
        visiting: set[tuple[str, int]] = set()

        def visit(component: Any) -> None:
            key = (component.source_component_code, component.source_version_no)
            if key in visited:
                return
            if key in visiting:
                raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_CYCLE_DETECTED", detail="分享包组件依赖存在循环。")
            visiting.add(key)
            for dependency in component.dependencies:
                dependency_component = component_map.get(dependency)
                if dependency_component is not None:
                    visit(dependency_component)
            visiting.remove(key)
            visited.add(key)
            ordered.append(component)

        for component in components:
            visit(component)
        return ordered

    @staticmethod
    def _sha256_text(value: str) -> str:
        """计算 UTF-8 文本 SHA-256。"""

        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
