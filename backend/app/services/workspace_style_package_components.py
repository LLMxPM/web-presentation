"""文件功能：处理样式离线包中的建议组件导出载荷、预检、导入复用和样式关联映射。"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_style import WorkspaceStyle
from app.schemas.workspace_style import WorkspaceStylePackageComponentSummary
from app.services.component_share_package_service import ComponentSharePackageService, PackageComponent
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_style_package_format import PackageAsset, PackageStyle, WorkspaceStylePackageFormat


class WorkspaceStylePackageComponentService:
    """样式包组件辅助服务，复用组件分享包结构并维护源组件到目标组件的映射。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def collect_style_suggested_components(
        self,
        workspace_id: int,
        styles: list[WorkspaceStyle],
    ) -> dict[int, list[WorkspaceComponent]]:
        """按样式读取建议组件，导出时只把直接关联组件作为根组件。"""

        suggested_component_service = SuggestedComponentService(self.session)
        result: dict[int, list[WorkspaceComponent]] = {}
        for style in styles:
            result[style.id] = await suggested_component_service.list_style_components(workspace_id, style.id)
        return result

    @staticmethod
    def deduplicate_components(components: Any) -> list[WorkspaceComponent]:
        """按组件 ID 去重并保留样式中的首次出现顺序。"""

        result: list[WorkspaceComponent] = []
        seen_ids: set[int] = set()
        for component in components:
            if component.id in seen_ids:
                continue
            seen_ids.add(component.id)
            result.append(component)
        return result

    @staticmethod
    def build_style_suggested_component_payloads(components: list[WorkspaceComponent]) -> list[dict[str, Any]]:
        """构建样式载荷中的建议组件引用，保留源组件 code/version 以便导入后建立映射。"""

        return [
            {
                "source_component_code": component.code,
                "source_version_no": component.current_version_no,
                "code": component.code,
                "name": component.name,
                "import_name": component.import_name,
                "component_type": component.component_type,
                "summary": component.summary,
                "current_version_no": component.current_version_no,
            }
            for component in components
        ]

    def parse_package_components(self, archive_content: bytes) -> list[PackageComponent]:
        """从样式包中解析可选 components 目录，格式复用组件分享包结构。"""

        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_content))
        except zipfile.BadZipFile as error:
            raise AppException(status_code=400, code="WORKSPACE_STYLE_PACKAGE_INVALID", detail="上传文件不是合法 Zip。") from error

        component_package_service = ComponentSharePackageService(self.session)
        with archive:
            names = {
                WorkspaceStylePackageFormat.normalize_zip_name(item.filename)
                for item in archive.infolist()
                if not item.is_dir()
            }
            manifest = WorkspaceStylePackageFormat.read_object_json(archive, "manifest.json")
            component_codes = ComponentSharePackageService._resolve_package_component_codes(manifest, names)
            return [
                component_package_service._read_package_component(archive, component_code)
                for component_code in component_codes
            ]

    async def build_component_summaries(
        self,
        workspace_id: int,
        package_components: list[PackageComponent],
        package_assets: list[PackageAsset],
        font_configs: list[dict[str, Any]],
        errors: list[str],
    ) -> list[WorkspaceStylePackageComponentSummary]:
        """构建样式包内组件预检摘要，并判断目标工作空间中创建或复用动作。"""

        component_package_service = ComponentSharePackageService(self.session)
        actions = await component_package_service._build_component_import_actions(
            workspace_id=workspace_id,
            package_components=package_components,
            package_assets=package_assets,
            font_configs=font_configs,
            errors=errors,
        )
        return [
            self._to_style_component_summary(summary)
            for summary in component_package_service._build_component_summaries(actions)
        ]

    async def validate_component_imports(
        self,
        workspace_id: int,
        package_components: list[PackageComponent],
        errors: list[str],
    ) -> None:
        """校验样式包组件 import 边界、包内依赖闭包和目标组件复用冲突。"""

        component_package_service = ComponentSharePackageService(self.session)
        seen_import_names: set[str] = set()
        component_key_set = {
            (item.source_component_code, item.source_version_no)
            for item in package_components
        }
        for package_component in package_components:
            import_name = str(package_component.metadata.get("import_name") or "").strip()
            if import_name in seen_import_names:
                errors.append(f"样式包内存在重复 import_name：{import_name}。")
            seen_import_names.add(import_name)

            try:
                parsed = component_package_service.component_version_service.dependency_service.parse_dependencies(
                    package_component.content,
                    source_label=f"样式包组件 {package_component.source_component_code}",
                    importer_module_path=(
                        f"src/workspace-components/{package_component.source_component_code}"
                        f"/v/{package_component.source_version_no}.vue"
                    ),
                )
            except AppException as error:
                errors.append(str(error.detail))
                continue
            for component_code, version_no in parsed.component_imports:
                if (component_code, version_no) not in component_key_set:
                    errors.append(f"组件 {package_component.source_component_code} 依赖缺失：{component_code} v{version_no}。")

    def validate_package_component_integrity(
        self,
        package_styles: list[PackageStyle],
        package_components: list[PackageComponent],
        package_assets: list[PackageAsset],
        font_configs: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        """校验组件闭包、字体资源和样式建议组件引用。"""

        component_package_service = ComponentSharePackageService(self.session)
        component_package_service._validate_package_dependency_closure(package_components, errors)
        component_package_service._validate_package_font_assets(
            SimpleNamespace(assets=package_assets, font_configs=font_configs),
            errors,
        )
        self.validate_style_suggested_component_references(package_styles, package_components, errors)

    def validate_style_suggested_component_references(
        self,
        package_styles: list[PackageStyle],
        package_components: list[PackageComponent],
        errors: list[str],
    ) -> None:
        """校验新格式样式建议组件引用均能在包内组件闭包中找到。"""

        component_key_set = {
            (item.source_component_code, item.source_version_no)
            for item in package_components
        }
        for package_style in package_styles:
            style_key = str(package_style.payload.get("key") or "").strip()
            raw_items = package_style.payload.get("suggested_components")
            if not isinstance(raw_items, list):
                continue
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                component_key = self.extract_package_component_key(raw_item)
                if component_key is None:
                    continue
                if component_key not in component_key_set:
                    errors.append(
                        f'样式 "{style_key}" 引用的建议组件不在离线包组件中：'
                        f"{component_key[0]} v{component_key[1]}。"
                    )

    async def import_or_reuse_components(
        self,
        workspace_id: int,
        package_components: list[PackageComponent],
        package_assets: list[PackageAsset],
        font_configs: list[dict[str, Any]],
        operator_id: int,
    ) -> tuple[dict[tuple[str, int], WorkspaceComponent], list[WorkspaceStylePackageComponentSummary]]:
        """导入样式包组件；目标工作空间已有同指纹组件时直接建立映射。"""

        component_package_service = ComponentSharePackageService(self.session)
        _, component_mapping, component_summaries = await component_package_service.import_or_reuse_components(
            workspace_id,
            package_components,
            package_assets,
            font_configs,
            operator_id,
            release_name="样式包导入",
            change_note_prefix="从样式离线包导入",
        )
        return component_mapping, [
            self._to_style_component_summary(summary)
            for summary in component_summaries
        ]

    async def resolve_style_suggested_component_ids(
        self,
        workspace_id: int,
        package_style: PackageStyle,
        component_mapping: dict[tuple[str, int], WorkspaceComponent],
    ) -> list[int]:
        """把样式载荷中的源组件引用解析为目标工作空间组件 ID。"""

        raw_suggested_components = package_style.payload.get("suggested_components")
        suggested_component_summaries = raw_suggested_components if isinstance(raw_suggested_components, list) else []
        component_ids: list[int] = []
        seen_ids: set[int] = set()
        legacy_summaries: list[dict[str, Any]] = []
        for item in suggested_component_summaries:
            if not isinstance(item, dict):
                continue
            component_key = self.extract_package_component_key(item)
            if component_key is None:
                legacy_summaries.append(item)
                continue
            component = component_mapping.get(component_key)
            if component is None or component.id in seen_ids:
                continue
            seen_ids.add(component.id)
            component_ids.append(component.id)

        if legacy_summaries:
            legacy_ids = await SuggestedComponentService(self.session).find_package_component_ids(workspace_id, legacy_summaries)
            for component_id in legacy_ids:
                if component_id in seen_ids:
                    continue
                seen_ids.add(component_id)
                component_ids.append(component_id)
        return component_ids

    @staticmethod
    def extract_package_component_key(payload: dict[str, Any]) -> tuple[str, int] | None:
        """从新格式建议组件摘要中读取源组件 code/version。"""

        source_code = str(payload.get("source_component_code") or payload.get("code") or "").strip()
        version_no = (
            WorkspaceStylePackageFormat.coerce_int(payload.get("source_version_no"))
            or WorkspaceStylePackageFormat.coerce_int(payload.get("current_version_no"))
            or 0
        )
        if not source_code or version_no <= 0:
            return None
        return source_code, version_no

    @staticmethod
    def _to_style_component_summary(summary: Any) -> WorkspaceStylePackageComponentSummary:
        """把组件分享包摘要转换为样式包组件摘要。"""

        return WorkspaceStylePackageComponentSummary(
            source_component_code=summary.source_component_code,
            source_version_no=summary.source_version_no,
            name=summary.name,
            import_name=summary.import_name,
            component_type=summary.component_type,
            dependencies=list(summary.dependencies),
            component_fingerprint=summary.component_fingerprint,
            matched_component_id=summary.matched_component_id,
            matched_component_code=summary.matched_component_code,
            action=summary.action,
            match_reason=summary.match_reason,
        )
