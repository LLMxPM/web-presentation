"""文件功能：构建、预检和导入工作空间样式离线包，携带样式引用的主题、建议组件、资源与字体配置。"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import DEFAULT_CODE_RETRY_LIMIT, is_code_unique_integrity_error
from app.core.exceptions import AppException
from app.core.runtime_module_policy import load_runtime_kit_manifest
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_style import WorkspaceStyle
from app.models.workspace_theme import WorkspaceTheme
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workspace_style_repository import WorkspaceStyleRepository
from app.repositories.workspace_theme_repository import WorkspaceThemeRepository
from app.schemas.theme import ThemePalette
from app.schemas.workspace_style import (
    WorkspaceStyleImportResult,
    WorkspaceStyleImportValidationResult,
    WorkspaceStylePackageAssetSummary,
    WorkspaceStylePackageFontSummary,
    WorkspaceStylePackageStyleSummary,
    WorkspaceStylePackageThemeSummary,
)
from app.services.asset_service import AssetService
from app.services.component_fingerprint_service import ComponentFingerprintService
from app.services.component_share_package_service import ComponentSharePackageService, PackageComponent
from app.services.workspace_style_package_components import WorkspaceStylePackageComponentService
from app.services.workspace_style_package_format import (
    STYLE_PACKAGE_SCHEMA_VERSION,
    PackageAsset,
    PackageStyle,
    PackageTheme,
    ParsedStylePackage,
    WorkspaceStylePackageFormat,
)
from app.services.workspace_style_package_payloads import WorkspaceStylePackagePayloads
from app.services.suggested_component_service import SuggestedComponentService


class WorkspaceStylePackageService:
    """样式离线包服务，负责导出、预检和事务化导入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_repository = WorkspaceRepository(session)
        self.style_repository = WorkspaceStyleRepository(session)
        self.theme_repository = WorkspaceThemeRepository(session)
        self.asset_service = AssetService(session)

    async def export_package(self, *, workspace_id: int, style_ids: list[int]) -> tuple[bytes, str]:
        """按样式 ID 导出离线包，自动携带引用主题、建议组件及其依赖。"""

        if await self.workspace_repository.get_by_id(workspace_id) is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")

        styles = await self._load_export_styles(workspace_id, style_ids)
        themes = await self._collect_export_themes(workspace_id, styles)
        theme_assets, theme_font_configs = await self._collect_export_dependencies(workspace_id, list(themes.values()))
        style_component_service = WorkspaceStylePackageComponentService(self.session)
        suggested_components_by_style = await style_component_service.collect_style_suggested_components(workspace_id, styles)
        root_components = style_component_service.deduplicate_components(
            component
            for components in suggested_components_by_style.values()
            for component in components
        )
        component_package_service = ComponentSharePackageService(self.session)
        component_snapshots = await component_package_service._build_export_component_closure(root_components)
        component_assets = await component_package_service._collect_export_assets(workspace_id, component_snapshots)
        component_font_configs = await component_package_service._collect_export_font_configs(workspace_id, component_snapshots)
        assets = self._deduplicate_assets([*theme_assets, *component_assets])
        font_configs = self._deduplicate_font_configs([*theme_font_configs, *component_font_configs])
        WorkspaceStylePackagePayloads.assert_unique_asset_hash_metadata(assets)
        archive_content = await self._build_zip_archive(
            workspace_id=workspace_id,
            styles=styles,
            suggested_components_by_style=suggested_components_by_style,
            themes=list(themes.values()),
            assets=assets,
            font_configs=font_configs,
            component_snapshots=component_snapshots,
        )
        return archive_content, WorkspaceStylePackagePayloads.build_export_filename(styles)

    async def validate_import_package(self, *, workspace_id: int, archive_content: bytes) -> WorkspaceStyleImportValidationResult:
        """预检样式离线包，不写入数据库。"""

        parsed = WorkspaceStylePackageFormat.parse_package(archive_content)
        package_components = WorkspaceStylePackageComponentService(self.session).parse_package_components(archive_content)
        return await self._validate_parsed_package(workspace_id, parsed, package_components)

    async def import_package(self, *, workspace_id: int, archive_content: bytes, operator_id: int) -> WorkspaceStyleImportResult:
        """正式导入样式离线包，按资源、字体、主题、组件、样式顺序写入。"""

        parsed = WorkspaceStylePackageFormat.parse_package(archive_content)
        style_component_service = WorkspaceStylePackageComponentService(self.session)
        package_components = style_component_service.parse_package_components(archive_content)
        validation = await self._validate_parsed_package(workspace_id, parsed, package_components)
        if not validation.valid:
            raise AppException(
                status_code=400,
                code="WORKSPACE_STYLE_PACKAGE_INVALID",
                detail="样式离线包预检未通过：" + "；".join(validation.errors),
            )

        last_error: IntegrityError | None = None
        for _ in range(DEFAULT_CODE_RETRY_LIMIT):
            try:
                await self._import_assets(workspace_id, parsed.assets)
                await self._import_font_configs(workspace_id, parsed.font_configs)
                await self._import_themes(workspace_id, parsed.themes, operator_id)
                component_mapping, component_summaries = await style_component_service.import_or_reuse_components(
                    workspace_id,
                    package_components,
                    parsed.assets,
                    parsed.font_configs,
                    operator_id,
                )
                await self._import_styles(workspace_id, parsed.styles, operator_id, component_mapping)
                await self.session.commit()
                return WorkspaceStyleImportResult(
                    styles=validation.styles,
                    themes=validation.themes,
                    assets=validation.assets,
                    fonts=validation.fonts,
                    components=component_summaries,
                )
            except IntegrityError as error:
                await self.session.rollback()
                if not is_code_unique_integrity_error(error, WorkspaceComponent):
                    raise
                last_error = error

        raise AppException(
            status_code=409,
            code="CODE_GENERATION_CONFLICT",
            detail="业务编码生成遇到并发冲突，请稍后重试。",
        ) from last_error

    async def _load_export_styles(self, workspace_id: int, style_ids: list[int]) -> list[WorkspaceStyle]:
        """读取并校验待导出的样式。"""

        unique_ids = list(dict.fromkeys(int(item) for item in style_ids))
        styles: list[WorkspaceStyle] = []
        for style_id in unique_ids:
            style = await self.style_repository.get_by_id(workspace_id, style_id)
            if style is None:
                raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail=f"样式 {style_id} 不存在。")
            styles.append(style)
        return styles

    async def _collect_export_themes(self, workspace_id: int, styles: list[WorkspaceStyle]) -> dict[str, WorkspaceTheme]:
        """收集样式引用的主题。"""

        themes: dict[str, WorkspaceTheme] = {}
        for style in styles:
            theme_key = str(style.theme_key or "").strip()
            if not theme_key or theme_key in themes:
                continue
            theme = await self.theme_repository.get_by_key(workspace_id, theme_key)
            if theme is None:
                raise AppException(
                    status_code=409,
                    code="WORKSPACE_STYLE_THEME_MISSING",
                    detail=f'样式 "{style.name}" 引用的主题 "{theme_key}" 不存在，无法导出。',
                )
            themes[theme.key] = theme
        return themes

    async def _collect_export_dependencies(
        self,
        workspace_id: int,
        themes: list[WorkspaceTheme],
    ) -> tuple[list[WorkspaceAsset], list[WorkspaceFontConfig]]:
        """收集主题引用的资源和字体配置。"""

        assets_by_id: dict[int, WorkspaceAsset] = {}
        fonts_by_id: dict[int, WorkspaceFontConfig] = {}
        for theme in themes:
            for asset_id in [theme.logo_asset_id, theme.invert_logo_asset_id, theme.project_icon_asset_id]:
                if asset_id is None or asset_id in assets_by_id:
                    continue
                asset = await self._get_asset_or_raise(workspace_id, asset_id, theme.name)
                assets_by_id[asset.id] = asset

            for font_id in [theme.heading_font_id, theme.body_font_id, theme.code_font_id]:
                if font_id is None or font_id in fonts_by_id:
                    continue
                font_config = await self._get_font_config_or_raise(workspace_id, font_id, theme.name)
                font_asset = await self._get_asset_or_raise(workspace_id, font_config.asset_id, theme.name)
                assets_by_id[font_asset.id] = font_asset
                fonts_by_id[font_config.id] = font_config
        return list(assets_by_id.values()), list(fonts_by_id.values())

    @staticmethod
    def _deduplicate_assets(assets: list[WorkspaceAsset]) -> list[WorkspaceAsset]:
        """按资源 ID 去重并保留依赖收集顺序。"""

        result: list[WorkspaceAsset] = []
        seen_ids: set[int] = set()
        for asset in assets:
            if asset.id in seen_ids:
                continue
            seen_ids.add(asset.id)
            result.append(asset)
        return result

    @staticmethod
    def _deduplicate_font_configs(font_configs: list[WorkspaceFontConfig]) -> list[WorkspaceFontConfig]:
        """按字体配置 ID 去重并保留依赖收集顺序。"""

        result: list[WorkspaceFontConfig] = []
        seen_ids: set[int] = set()
        for font_config in font_configs:
            if font_config.id in seen_ids:
                continue
            seen_ids.add(font_config.id)
            result.append(font_config)
        return result

    async def _get_asset_or_raise(self, workspace_id: int, asset_id: int, theme_name: str) -> WorkspaceAsset:
        """读取主题依赖资源，不存在时阻断导出。"""

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            raise AppException(
                status_code=409,
                code="WORKSPACE_STYLE_PACKAGE_ASSET_MISSING",
                detail=f'主题 "{theme_name}" 引用的资源 {asset_id} 不存在，无法导出。',
            )
        return asset

    async def _get_font_config_or_raise(self, workspace_id: int, font_id: int, theme_name: str) -> WorkspaceFontConfig:
        """读取主题依赖字体配置，不存在时阻断导出。"""

        font_config = await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.id == font_id)
        )
        if font_config is None:
            raise AppException(
                status_code=409,
                code="WORKSPACE_STYLE_PACKAGE_FONT_MISSING",
                detail=f'主题 "{theme_name}" 引用的字体配置 {font_id} 不存在，无法导出。',
            )
        return font_config

    async def _build_zip_archive(
        self,
        *,
        workspace_id: int,
        styles: list[WorkspaceStyle],
        suggested_components_by_style: dict[int, list[WorkspaceComponent]],
        themes: list[WorkspaceTheme],
        assets: list[WorkspaceAsset],
        font_configs: list[WorkspaceFontConfig],
        component_snapshots: list[Any],
    ) -> bytes:
        """按标准目录结构生成样式离线包 Zip。"""

        buffer = io.BytesIO()
        component_package_service = ComponentSharePackageService(self.session)
        style_component_service = WorkspaceStylePackageComponentService(self.session)
        runtime_manifest_version = str(load_runtime_kit_manifest().get("version") or "")
        fingerprint_service = ComponentFingerprintService(self.session)
        for snapshot in component_snapshots:
            await fingerprint_service.ensure_workspace_component_version_fingerprint(
                component=snapshot.component,
                version=snapshot.version,
            )
        style_entries: list[dict[str, Any]] = []
        for style in styles:
            style_payload = WorkspaceStylePackagePayloads.build_style_payload(style)
            style_payload["suggested_components"] = style_component_service.build_style_suggested_component_payloads(
                suggested_components_by_style.get(style.id, [])
            )
            style_entries.append(style_payload)
        theme_entries = [await self._build_theme_payload(theme) for theme in themes]
        asset_entries = [WorkspaceStylePackagePayloads.build_asset_payload(asset) for asset in assets]
        font_entries = [WorkspaceStylePackagePayloads.build_font_payload(item) for item in font_configs]
        component_entries = [
            component_package_service._build_component_manifest_entry(snapshot)
            for snapshot in component_snapshots
        ]
        manifest = {
            "schema_version": STYLE_PACKAGE_SCHEMA_VERSION,
            "exported_at": utc_now().isoformat(),
            "runtime_kit_manifest_version": runtime_manifest_version,
            "styles": [
                {
                    "key": item["key"],
                    "name": item["name"],
                    "theme_key": item["theme_key"],
                    "suggested_component_count": len(item.get("suggested_components") or []),
                }
                for item in style_entries
            ],
            "themes": [
                {"key": item["key"], "name": item["name"]}
                for item in theme_entries
            ],
            "components": component_entries,
            "assets": [
                {
                    "name": item["name"],
                    "original_name": item["original_name"],
                    "asset_type": item["asset_type"],
                    "file_hash": item["file_hash"],
                }
                for item in asset_entries
            ],
            "fonts": font_entries,
        }

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", WorkspaceStylePackageFormat.dump_json(manifest))
            for style_payload in style_entries:
                archive.writestr(f"styles/{style_payload['key']}.json", WorkspaceStylePackageFormat.dump_json(style_payload))
            for theme_payload in theme_entries:
                archive.writestr(f"themes/{theme_payload['key']}.json", WorkspaceStylePackageFormat.dump_json(theme_payload))
            for snapshot in component_snapshots:
                base_path = f"components/{snapshot.component.code}"
                archive.writestr(
                    f"{base_path}/component.json",
                    WorkspaceStylePackageFormat.dump_json(component_package_service._build_component_payload(snapshot)),
                )
                archive.writestr(f"{base_path}/index.vue", normalize_text_to_lf(snapshot.version.content))
                archive.writestr(f"{base_path}/preview.schema.json", snapshot.version.preview_schema or "{}")
            for asset in assets:
                asset_payload = WorkspaceStylePackagePayloads.build_asset_payload(asset)
                asset_base_path = f"assets/{asset.file_hash}"
                archive.writestr(f"{asset_base_path}/asset.json", WorkspaceStylePackageFormat.dump_json(asset_payload))
                archive.writestr(
                    f"{asset_base_path}/{WorkspaceStylePackageFormat.safe_archive_filename(asset.original_name)}",
                    await self.asset_service.driver.read_content(workspace_id, asset.file_name),
                )
            archive.writestr("fonts/font-configs.json", WorkspaceStylePackageFormat.dump_json(font_entries))
        return buffer.getvalue()

    async def _validate_parsed_package(
        self,
        workspace_id: int,
        parsed: ParsedStylePackage,
        package_components: list[PackageComponent],
    ) -> WorkspaceStyleImportValidationResult:
        """对已解析离线包执行跨对象预检。"""

        if await self.workspace_repository.get_by_id(workspace_id) is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")

        errors: list[str] = []
        schema_version = WorkspaceStylePackageFormat.coerce_int(parsed.manifest.get("schema_version"))
        if schema_version != STYLE_PACKAGE_SCHEMA_VERSION:
            errors.append(f"样式离线包 schema_version 不受支持：{schema_version}。")

        asset_summaries = await self._build_asset_summaries(workspace_id, parsed.assets, errors)
        font_summaries = await self._build_font_summaries(workspace_id, parsed.font_configs, parsed.assets, errors)
        theme_summaries = await self._build_theme_summaries(workspace_id, parsed.themes, parsed.assets, parsed.font_configs, errors)
        style_summaries = await self._build_style_summaries(workspace_id, parsed.styles, parsed.themes, errors)
        style_component_service = WorkspaceStylePackageComponentService(self.session)
        component_summaries = await style_component_service.build_component_summaries(
            workspace_id,
            package_components,
            parsed.assets,
            parsed.font_configs,
            errors,
        )
        await style_component_service.validate_component_imports(workspace_id, package_components, errors)
        style_component_service.validate_package_component_integrity(
            parsed.styles,
            package_components,
            parsed.assets,
            parsed.font_configs,
            errors,
        )
        return WorkspaceStyleImportValidationResult(
            valid=not errors,
            schema_version=schema_version,
            styles=style_summaries,
            themes=theme_summaries,
            assets=asset_summaries,
            fonts=font_summaries,
            components=component_summaries,
            errors=errors,
        )

    async def _build_asset_summaries(
        self,
        workspace_id: int,
        package_assets: list[PackageAsset],
        errors: list[str],
    ) -> list[WorkspaceStylePackageAssetSummary]:
        """构建资源预检摘要，并校验同名资源冲突。"""

        summaries: list[WorkspaceStylePackageAssetSummary] = []
        seen_names: set[str] = set()
        for package_asset in package_assets:
            metadata = package_asset.metadata
            name = str(metadata.get("name") or "").strip()
            file_hash = str(metadata.get("file_hash") or "").strip()
            actual_hash = hashlib.sha256(package_asset.content).hexdigest()
            missing = [
                field
                for field in ["name", "original_name", "asset_type", "file_hash"]
                if not str(metadata.get(field) or "").strip()
            ]
            if missing:
                errors.append(f"资源元数据缺少字段：{', '.join(missing)}。")
            if name in seen_names:
                errors.append(f"离线包内存在重复资源 name：{name}。")
            seen_names.add(name)
            if file_hash != actual_hash:
                errors.append(f"资源 {name} 的 file_hash 与文件内容不一致。")
            try:
                asset_type = AssetType(str(metadata.get("asset_type") or ""))
                original_name = WorkspaceStylePackageFormat.safe_archive_filename(str(metadata.get("original_name") or "asset.bin"))
                AssetService._validate_asset_file_type(asset_type, original_name, metadata.get("content_type"))
                AssetService._validate_uploaded_asset_content(asset_type, original_name, package_asset.content)
            except ValueError:
                errors.append(f"资源 {name} 的 asset_type 不受支持。")
            except AppException as error:
                errors.append(str(error.detail))

            existing = await self._get_asset_by_name(workspace_id, name)
            action = "create"
            if existing is not None:
                if existing.file_hash != file_hash:
                    errors.append(f'目标工作空间已存在同名但内容不同的资源 "{name}"。')
                action = "reuse"
            summaries.append(
                WorkspaceStylePackageAssetSummary(
                    name=name,
                    original_name=str(metadata.get("original_name") or "").strip(),
                    asset_type=str(metadata.get("asset_type") or "").strip(),
                    file_hash=file_hash,
                    action=action,
                )
            )
        return summaries

    async def _build_font_summaries(
        self,
        workspace_id: int,
        font_configs: list[dict[str, Any]],
        package_assets: list[PackageAsset],
        errors: list[str],
    ) -> list[WorkspaceStylePackageFontSummary]:
        """构建字体预检摘要，并校验字体资产与同名配置冲突。"""

        summaries: list[WorkspaceStylePackageFontSummary] = []
        seen_names: set[str] = set()
        package_asset_by_name = WorkspaceStylePackagePayloads.build_package_asset_lookup(package_assets)
        for item in font_configs:
            asset_name = str(item.get("asset_name") or "").strip()
            missing = [
                field
                for field in ["asset_name", "font_family", "font_format", "font_weight", "font_style", "font_display", "status"]
                if not str(item.get(field) or "").strip()
            ]
            if missing:
                errors.append(f"字体配置缺少字段：{', '.join(missing)}。")
            if asset_name in seen_names:
                errors.append(f"离线包内存在重复字体配置：{asset_name}。")
            seen_names.add(asset_name)
            await self._validate_font_asset_available(workspace_id, asset_name, package_asset_by_name, errors)

            existing = await self._get_font_config_by_asset_name(workspace_id, asset_name)
            action = "create"
            if existing is not None:
                if not WorkspaceStylePackagePayloads.font_config_matches(existing, item):
                    errors.append(f'目标工作空间已存在同名但配置不同的字体 "{asset_name}"。')
                action = "reuse"
            summaries.append(
                WorkspaceStylePackageFontSummary(
                    asset_name=asset_name,
                    font_family=str(item.get("font_family") or "").strip(),
                    font_format=str(item.get("font_format") or "").strip(),
                    font_weight=str(item.get("font_weight") or "").strip(),
                    font_style=str(item.get("font_style") or "").strip(),
                    font_display=str(item.get("font_display") or "").strip(),
                    status=str(item.get("status") or "").strip(),
                    action=action,
                )
            )
        return summaries

    async def _build_theme_summaries(
        self,
        workspace_id: int,
        package_themes: list[PackageTheme],
        package_assets: list[PackageAsset],
        font_configs: list[dict[str, Any]],
        errors: list[str],
    ) -> list[WorkspaceStylePackageThemeSummary]:
        """构建主题预检摘要，并校验主题依赖与同 key 冲突。"""

        summaries: list[WorkspaceStylePackageThemeSummary] = []
        seen_keys: set[str] = set()
        package_asset_by_name = WorkspaceStylePackagePayloads.build_package_asset_lookup(package_assets)
        package_font_names = {str(item.get("asset_name") or "").strip() for item in font_configs if str(item.get("asset_name") or "").strip()}
        for package_theme in package_themes:
            try:
                payload = WorkspaceStylePackagePayloads.normalize_theme_payload(package_theme.payload)
            except (ValidationError, ValueError) as error:
                errors.append(f"主题载荷不合法：{error}")
                continue

            key = payload["key"]
            if key in seen_keys:
                errors.append(f"离线包内存在重复主题 key：{key}。")
            seen_keys.add(key)
            await self._validate_theme_asset_references(workspace_id, payload, package_asset_by_name, errors)
            await self._validate_theme_font_references(workspace_id, payload, package_font_names, errors)

            existing = await self.theme_repository.get_by_key(workspace_id, key)
            action = "create"
            if existing is not None:
                existing_payload = await self._build_theme_payload(existing)
                if WorkspaceStylePackageFormat.canonical_payload(existing_payload) != WorkspaceStylePackageFormat.canonical_payload(payload):
                    errors.append(f'目标工作空间已存在同 key 但内容不同的主题 "{key}"。')
                action = "reuse"
            summaries.append(
                WorkspaceStylePackageThemeSummary(
                    key=key,
                    name=str(payload["name"]),
                    action=action,
                )
            )
        return summaries

    async def _build_style_summaries(
        self,
        workspace_id: int,
        package_styles: list[PackageStyle],
        package_themes: list[PackageTheme],
        errors: list[str],
    ) -> list[WorkspaceStylePackageStyleSummary]:
        """构建样式预检摘要，并标识同 key 样式将被覆盖。"""

        summaries: list[WorkspaceStylePackageStyleSummary] = []
        seen_keys: set[str] = set()
        package_theme_keys: set[str] = set()
        for theme in package_themes:
            try:
                package_theme_keys.add(str(WorkspaceStylePackagePayloads.normalize_theme_payload(theme.payload)["key"]))
            except (ValidationError, ValueError):
                continue
        for package_style in package_styles:
            try:
                payload = WorkspaceStylePackagePayloads.normalize_style_payload(package_style.payload)
            except ValidationError as error:
                errors.append(f"样式载荷不合法：{error}")
                continue

            key = str(payload["key"])
            if key in seen_keys:
                errors.append(f"离线包内存在重复样式 key：{key}。")
            seen_keys.add(key)

            theme_key = str(payload.get("theme_key") or "").strip()
            if theme_key and theme_key not in package_theme_keys and await self.theme_repository.get_by_key(workspace_id, theme_key) is None:
                errors.append(f'样式 "{key}" 引用的主题 "{theme_key}" 不在离线包或目标工作空间中。')

            existing = await self.style_repository.get_by_key(workspace_id, key)
            action = "create"
            if existing is not None:
                action = "overwrite"
            summaries.append(
                WorkspaceStylePackageStyleSummary(
                    key=key,
                    name=str(payload["name"]),
                    theme_key=payload.get("theme_key"),
                    page_width=int(payload["page_width"]),
                    page_height=int(payload["page_height"]),
                    base_font_size=str(payload["base_font_size"]),
                    icon_default_stroke_width=int(payload["icon_default_stroke_width"]),
                    show_pdf_export_button=bool(payload["show_pdf_export_button"]),
                    menu_mode=str(payload["menu_mode"]),
                    style_spec_markdown=str(payload.get("style_spec_markdown") or ""),
                    action=action,
                )
            )
        return summaries

    async def _import_assets(self, workspace_id: int, package_assets: list[PackageAsset]) -> None:
        """导入或复用包内资源。"""

        for package_asset in package_assets:
            metadata = package_asset.metadata
            name = str(metadata["name"]).strip()
            if await self._get_asset_by_name(workspace_id, name) is not None:
                continue
            asset_type = AssetType(str(metadata["asset_type"]))
            content = package_asset.content
            file_hash = hashlib.sha256(content).hexdigest()
            original_name = WorkspaceStylePackageFormat.safe_archive_filename(str(metadata["original_name"]))
            AssetService._validate_asset_file_type(asset_type, original_name, metadata.get("content_type"))
            AssetService._validate_uploaded_asset_content(asset_type, original_name, content)
            ext = "".join(Path(original_name).suffixes)
            save_name = await self.asset_service.driver.upload(
                workspace_id,
                file_hash,
                ext,
                content,
                str(metadata.get("content_type") or "") or None,
            )
            self.session.add(
                WorkspaceAsset(
                    workspace_id=workspace_id,
                    name=name,
                    file_name=save_name,
                    original_name=original_name,
                    description=metadata.get("description"),
                    file_size=len(content),
                    file_hash=file_hash,
                    content_type=metadata.get("content_type"),
                    asset_type=asset_type.value,
                    tags=list(metadata.get("tags") or []),
                    analysis_metadata=metadata.get("analysis_metadata"),
                    render_metadata=metadata.get("render_metadata"),
                    status=RecordStatus.ACTIVE.value,
                )
            )
        await self.session.flush()

    async def _import_font_configs(self, workspace_id: int, font_configs: list[dict[str, Any]]) -> None:
        """导入或复用包内字体配置。"""

        for item in font_configs:
            asset_name = str(item["asset_name"]).strip()
            if await self._get_font_config_by_asset_name(workspace_id, asset_name) is not None:
                continue
            asset = await self._get_asset_by_name(workspace_id, asset_name)
            if asset is None:
                raise AppException(status_code=409, code="FONT_ASSET_NOT_FOUND", detail=f"字体资源 {asset_name} 不存在。")
            self.session.add(
                WorkspaceFontConfig(
                    workspace_id=workspace_id,
                    asset_id=asset.id,
                    asset_name=asset.name,
                    font_family=str(item["font_family"]).strip(),
                    font_format=str(item["font_format"]).strip(),
                    font_weight=str(item["font_weight"]).strip(),
                    font_style=str(item["font_style"]).strip(),
                    font_display=str(item["font_display"]).strip(),
                    status=str(item.get("status") or RecordStatus.ACTIVE.value),
                )
            )
        await self.session.flush()

    async def _import_themes(self, workspace_id: int, package_themes: list[PackageTheme], operator_id: int) -> None:
        """导入或复用包内主题。"""

        for package_theme in package_themes:
            payload = WorkspaceStylePackagePayloads.normalize_theme_payload(package_theme.payload)
            if await self.theme_repository.get_by_key(workspace_id, payload["key"]) is not None:
                continue

            logo_asset = await self._get_asset_by_name(workspace_id, str(payload.get("logo_asset_name") or ""))
            invert_logo_asset = await self._get_asset_by_name(workspace_id, str(payload.get("invert_logo_asset_name") or ""))
            project_icon_asset = await self._get_asset_by_name(workspace_id, str(payload.get("project_icon_asset_name") or ""))
            heading_font = await self._get_font_config_by_asset_name(workspace_id, str(payload.get("heading_font_asset_name") or ""))
            body_font = await self._get_font_config_by_asset_name(workspace_id, str(payload.get("body_font_asset_name") or ""))
            code_font = await self._get_font_config_by_asset_name(workspace_id, str(payload.get("code_font_asset_name") or ""))

            self.session.add(
                WorkspaceTheme(
                    workspace_id=workspace_id,
                    key=str(payload["key"]),
                    name=str(payload["name"]),
                    description=payload.get("description"),
                    logo_asset_id=logo_asset.id if logo_asset is not None else None,
                    invert_logo_asset_id=invert_logo_asset.id if invert_logo_asset is not None else None,
                    project_icon_asset_id=project_icon_asset.id if project_icon_asset is not None else None,
                    logo_path=logo_asset.name if logo_asset is not None else payload.get("logo_path"),
                    invert_logo_path=invert_logo_asset.name if invert_logo_asset is not None else payload.get("invert_logo_path"),
                    project_icon_name=project_icon_asset.name if project_icon_asset is not None else payload.get("project_icon_name"),
                    heading_font_id=heading_font.id if heading_font is not None else None,
                    body_font_id=body_font.id if body_font is not None else None,
                    code_font_id=code_font.id if code_font is not None else None,
                    heading_font_label=heading_font.font_family if heading_font is not None else str(payload["heading_font_label"]),
                    body_font_label=body_font.font_family if body_font is not None else str(payload["body_font_label"]),
                    code_font_label=code_font.font_family if code_font is not None else str(payload["code_font_label"]),
                    palette=payload["palette"],
                    created_by=operator_id,
                    updated_by=operator_id,
                )
            )
        await self.session.flush()

    async def _import_styles(
        self,
        workspace_id: int,
        package_styles: list[PackageStyle],
        operator_id: int,
        component_mapping: dict[tuple[str, int], WorkspaceComponent],
    ) -> None:
        """导入或覆盖包内样式，并按包内声明重建样式建议组件关联。"""

        for package_style in package_styles:
            payload = WorkspaceStylePackagePayloads.normalize_style_payload(package_style.payload)
            style = await self.style_repository.get_by_key(workspace_id, str(payload["key"]))
            if style is None:
                style = WorkspaceStyle(
                    workspace_id=workspace_id,
                    key=str(payload["key"]),
                    name=str(payload["name"]),
                    description=payload.get("description"),
                    page_width=int(payload["page_width"]),
                    page_height=int(payload["page_height"]),
                    base_font_size=str(payload["base_font_size"]),
                    icon_default_stroke_width=int(payload["icon_default_stroke_width"]),
                    show_pdf_export_button=bool(payload["show_pdf_export_button"]),
                    menu_mode=str(payload["menu_mode"]),
                    theme_key=payload.get("theme_key"),
                    style_spec_markdown=str(payload.get("style_spec_markdown") or ""),
                    created_by=operator_id,
                    updated_by=operator_id,
                )
                self.session.add(style)
                await self.session.flush()
            else:
                style.name = str(payload["name"])
                style.description = payload.get("description")
                style.page_width = int(payload["page_width"])
                style.page_height = int(payload["page_height"])
                style.base_font_size = str(payload["base_font_size"])
                style.icon_default_stroke_width = int(payload["icon_default_stroke_width"])
                style.show_pdf_export_button = bool(payload["show_pdf_export_button"])
                style.menu_mode = str(payload["menu_mode"])
                style.theme_key = payload.get("theme_key")
                style.style_spec_markdown = str(payload.get("style_spec_markdown") or "")
                style.updated_by = operator_id
            suggested_component_ids = await WorkspaceStylePackageComponentService(self.session).resolve_style_suggested_component_ids(
                workspace_id,
                package_style,
                component_mapping,
            )
            await SuggestedComponentService(self.session).replace_style_components(
                workspace_id,
                style.id,
                suggested_component_ids,
                commit=False,
            )
        await self.session.flush()

    async def _build_theme_payload(self, theme: WorkspaceTheme) -> dict[str, Any]:
        """构建不含数据库 ID 的主题离线包载荷。"""

        logo_asset = await self._get_asset_by_id_or_none(theme.workspace_id, theme.logo_asset_id)
        invert_logo_asset = await self._get_asset_by_id_or_none(theme.workspace_id, theme.invert_logo_asset_id)
        project_icon_asset = await self._get_asset_by_id_or_none(theme.workspace_id, theme.project_icon_asset_id)
        heading_font = await self._get_font_config_by_id_or_none(theme.workspace_id, theme.heading_font_id)
        body_font = await self._get_font_config_by_id_or_none(theme.workspace_id, theme.body_font_id)
        code_font = await self._get_font_config_by_id_or_none(theme.workspace_id, theme.code_font_id)
        return {
            "key": theme.key,
            "name": theme.name,
            "description": theme.description,
            "logo_asset_name": logo_asset.name if logo_asset is not None else None,
            "invert_logo_asset_name": invert_logo_asset.name if invert_logo_asset is not None else None,
            "project_icon_asset_name": project_icon_asset.name if project_icon_asset is not None else None,
            "logo_path": None if logo_asset is not None else theme.logo_path,
            "invert_logo_path": None if invert_logo_asset is not None else theme.invert_logo_path,
            "project_icon_name": None if project_icon_asset is not None else theme.project_icon_name,
            "heading_font_asset_name": heading_font.asset_name if heading_font is not None else None,
            "body_font_asset_name": body_font.asset_name if body_font is not None else None,
            "code_font_asset_name": code_font.asset_name if code_font is not None else None,
            "heading_font_label": theme.heading_font_label,
            "body_font_label": theme.body_font_label,
            "code_font_label": theme.code_font_label,
            "palette": ThemePalette.model_validate(theme.palette).model_dump(mode="python"),
        }

    async def _validate_font_asset_available(
        self,
        workspace_id: int,
        asset_name: str,
        package_asset_by_name: dict[str, PackageAsset],
        errors: list[str],
    ) -> None:
        """校验字体配置引用的字体资源可创建或复用。"""

        if not asset_name:
            return
        package_asset = package_asset_by_name.get(asset_name)
        if package_asset is not None:
            asset_type = str(package_asset.metadata.get("asset_type") or "").strip()
            if asset_type != AssetType.FONT.value:
                errors.append(f'字体配置 "{asset_name}" 引用的包内资源不是 font 类型。')
            return
        existing = await self._get_asset_by_name(workspace_id, asset_name)
        if existing is None:
            errors.append(f'字体配置 "{asset_name}" 缺少同名字体资源。')
        elif existing.asset_type != AssetType.FONT.value:
            errors.append(f'目标工作空间资源 "{asset_name}" 不是 font 类型，不能作为字体配置导入。')

    async def _validate_theme_asset_references(
        self,
        workspace_id: int,
        theme_payload: dict[str, Any],
        package_asset_by_name: dict[str, PackageAsset],
        errors: list[str],
    ) -> None:
        """校验主题引用的 logo 与项目图标资源。"""

        for field_name in ["logo_asset_name", "invert_logo_asset_name", "project_icon_asset_name"]:
            asset_name = str(theme_payload.get(field_name) or "").strip()
            if not asset_name:
                continue
            asset_type = await self._resolve_available_asset_type(workspace_id, asset_name, package_asset_by_name)
            if asset_type is None:
                errors.append(f'主题 "{theme_payload["key"]}" 引用的资源 "{asset_name}" 不在离线包或目标工作空间中。')
                continue
            allowed_types = {AssetType.ICON.value} if field_name == "project_icon_asset_name" else {AssetType.ICON.value, AssetType.IMAGE.value}
            if asset_type not in allowed_types:
                errors.append(f'主题 "{theme_payload["key"]}" 引用的资源 "{asset_name}" 类型不符合主题字段要求。')

    async def _validate_theme_font_references(
        self,
        workspace_id: int,
        theme_payload: dict[str, Any],
        package_font_names: set[str],
        errors: list[str],
    ) -> None:
        """校验主题引用的字体配置可创建或复用。"""

        for field_name in ["heading_font_asset_name", "body_font_asset_name", "code_font_asset_name"]:
            asset_name = str(theme_payload.get(field_name) or "").strip()
            if not asset_name:
                continue
            if asset_name in package_font_names:
                continue
            if await self._get_font_config_by_asset_name(workspace_id, asset_name) is None:
                errors.append(f'主题 "{theme_payload["key"]}" 引用的字体配置 "{asset_name}" 不在离线包或目标工作空间中。')

    async def _resolve_available_asset_type(
        self,
        workspace_id: int,
        asset_name: str,
        package_asset_by_name: dict[str, PackageAsset],
    ) -> str | None:
        """解析包内或目标工作空间中可用资源的类型。"""

        package_asset = package_asset_by_name.get(asset_name)
        if package_asset is not None:
            return str(package_asset.metadata.get("asset_type") or "").strip()
        existing = await self._get_asset_by_name(workspace_id, asset_name)
        return existing.asset_type if existing is not None else None

    async def _get_asset_by_name(self, workspace_id: int, name: str) -> WorkspaceAsset | None:
        """按资源逻辑名读取工作空间资源。"""

        normalized_name = str(name or "").strip()
        if not normalized_name:
            return None
        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name == normalized_name)
        )

    async def _get_asset_by_id_or_none(self, workspace_id: int, asset_id: int | None) -> WorkspaceAsset | None:
        """按 ID 读取工作空间资源，空 ID 返回空。"""

        if asset_id is None:
            return None
        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )

    async def _get_font_config_by_asset_name(self, workspace_id: int, asset_name: str) -> WorkspaceFontConfig | None:
        """按字体资源逻辑名读取字体配置。"""

        normalized_name = str(asset_name or "").strip()
        if not normalized_name:
            return None
        return await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_name == normalized_name)
        )

    async def _get_font_config_by_id_or_none(self, workspace_id: int, font_id: int | None) -> WorkspaceFontConfig | None:
        """按 ID 读取字体配置，空 ID 返回空。"""

        if font_id is None:
            return None
        return await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.id == font_id)
        )
