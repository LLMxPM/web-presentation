"""文件功能：处理样式离线包中的建议组件导出载荷、预检、导入复用和样式关联映射。"""

from __future__ import annotations

import io
import re
import zipfile
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import generate_code
from app.core.component_preview_schema import validate_component_preview_schema_text
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import utc_now
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_style import WorkspaceStyle
from app.schemas.component import COMPONENT_IMPORT_NAME_PATTERN
from app.schemas.workspace_style import WorkspaceStylePackageComponentSummary
from app.services.component_share_package_service import ComponentSharePackageService, PackageComponent
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_component_service import CODE_PREFIX_COMPONENT
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
        errors: list[str],
    ) -> list[WorkspaceStylePackageComponentSummary]:
        """构建样式包内组件预检摘要，并判断目标工作空间中创建或复用动作。"""

        summaries: list[WorkspaceStylePackageComponentSummary] = []
        component_repository = ComponentSharePackageService(self.session).component_repository
        for component in package_components:
            metadata = component.metadata
            required_fields = ["name", "import_name", "component_type"]
            missing = [field for field in required_fields if not str(metadata.get(field) or "").strip()]
            if missing:
                errors.append(f"组件 {component.source_component_code} 元数据缺少字段：{', '.join(missing)}。")
            import_name = str(metadata.get("import_name") or "").strip()
            if not re.match(COMPONENT_IMPORT_NAME_PATTERN, import_name):
                errors.append(f"组件 {component.source_component_code} 的 import_name 不合法。")
            try:
                WorkspaceComponentType(str(metadata.get("component_type") or ""))
            except ValueError:
                errors.append(f"组件 {component.source_component_code} 的 component_type 不受支持。")

            action = "create"
            existing = await component_repository.get_active_by_import_name(
                workspace_id=workspace_id,
                import_name=import_name,
            )
            if existing is not None:
                if not self.can_reuse_existing_component(existing, component):
                    errors.append(f'目标工作空间已存在 import_name 为 {import_name} 但元数据不同或未发布的组件。')
                action = "reuse"
            summaries.append(
                WorkspaceStylePackageComponentSummary(
                    source_component_code=component.source_component_code,
                    source_version_no=component.source_version_no,
                    name=str(metadata.get("name") or "").strip(),
                    import_name=import_name,
                    component_type=str(metadata.get("component_type") or "").strip(),
                    dependencies=[f"{code}@v{version_no}" for code, version_no in component.dependencies],
                    action=action,
                )
            )
        return summaries

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

            existing = await component_package_service.component_repository.get_active_by_import_name(
                workspace_id=workspace_id,
                import_name=import_name,
            )
            if existing is not None and not self.can_reuse_existing_component(existing, package_component):
                errors.append(f'目标工作空间已存在 import_name 为 {import_name} 但不能作为样式包组件复用。')

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
        operator_id: int,
    ) -> dict[tuple[str, int], WorkspaceComponent]:
        """导入样式包组件；目标工作空间已有同 import_name 且可复用时直接建立映射。"""

        component_package_service = ComponentSharePackageService(self.session)
        component_mapping: dict[tuple[str, int], WorkspaceComponent] = {}
        for package_component in component_package_service._topological_sort_package_components(package_components):
            key = (package_component.source_component_code, package_component.source_version_no)
            import_name = str(package_component.metadata["import_name"]).strip()
            existing = await component_package_service.component_repository.get_active_by_import_name(
                workspace_id=workspace_id,
                import_name=import_name,
            )
            if existing is not None:
                component_mapping[key] = existing
                continue

            code_mapping = {
                component_key: component.code
                for component_key, component in component_mapping.items()
            }
            content = component_package_service._rewrite_component_imports(package_component.content, code_mapping)
            preview_schema = component_package_service._rewrite_component_imports(package_component.preview_schema or "", code_mapping)
            metadata = package_component.metadata
            now = utc_now()
            component = WorkspaceComponent(
                workspace_id=workspace_id,
                code=await generate_code(self.session, WorkspaceComponent, CODE_PREFIX_COMPONENT),
                content=normalize_text_to_lf(content),
                preview_schema=validate_component_preview_schema_text(preview_schema),
                current_version_no=0,
                draft_base_version_no=0,
                file_type=PageFileType.VUE.value,
                name=str(metadata["name"]).strip(),
                import_name=import_name,
                component_type=str(metadata.get("component_type") or WorkspaceComponentType.CONTENT_BLOCK.value),
                summary=metadata.get("summary"),
                status=RecordStatus.ACTIVE.value,
                created_by=operator_id,
                updated_by=operator_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(component)
            await self.session.flush()
            await component_package_service.component_version_service.publish_draft(
                component=component,
                operator_id=operator_id,
                release_name="样式包导入",
                change_note=f"从样式离线包导入：{package_component.source_component_code} v{package_component.source_version_no}",
            )
            component_mapping[key] = component
        return component_mapping

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
    def can_reuse_existing_component(existing: WorkspaceComponent, package_component: PackageComponent) -> bool:
        """判断目标工作空间已有组件是否可作为样式包组件复用。"""

        metadata = package_component.metadata
        return (
            existing.status == RecordStatus.ACTIVE.value
            and existing.deleted_at is None
            and existing.current_version_no > 0
            and existing.import_name == str(metadata.get("import_name") or "").strip()
            and existing.name == str(metadata.get("name") or "").strip()
            and existing.component_type == str(metadata.get("component_type") or "").strip()
        )
