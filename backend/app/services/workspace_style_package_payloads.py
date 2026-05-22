"""文件功能：整理样式离线包的业务载荷、归一化规则与内容一致性辅助判断。"""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig
from app.models.workspace_style import WorkspaceStyle
from app.schemas.theme import ThemePalette
from app.schemas.workspace_style import WorkspaceStyleCreateRequest
from app.services.workspace_style_package_format import PackageAsset, WorkspaceStylePackageFormat
from app.services.workspace_theme_service import DEFAULT_THEME_BODY_FONT, DEFAULT_THEME_CODE_FONT, DEFAULT_THEME_HEADING_FONT

STYLE_KEY_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class WorkspaceStylePackagePayloads:
    """样式离线包载荷工具，负责生成可序列化字段和稳定比较载荷。"""

    @staticmethod
    def build_style_payload(style: WorkspaceStyle) -> dict[str, Any]:
        """构建不含数据库 ID 的样式离线包载荷。"""

        return {
            "key": style.key,
            "name": style.name,
            "description": style.description,
            "page_width": style.page_width,
            "page_height": style.page_height,
            "base_font_size": style.base_font_size,
            "icon_default_stroke_width": style.icon_default_stroke_width,
            "show_pdf_export_button": style.show_pdf_export_button,
            "menu_mode": style.menu_mode,
            "theme_key": style.theme_key,
            "style_spec_markdown": style.style_spec_markdown,
        }

    @staticmethod
    def build_asset_payload(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建资源离线包载荷。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "file_hash": asset.file_hash,
            "description": asset.description,
            "tags": asset.tags or [],
            "analysis_metadata": asset.analysis_metadata,
            "render_metadata": asset.render_metadata,
        }

    @staticmethod
    def build_font_payload(font_config: WorkspaceFontConfig) -> dict[str, Any]:
        """构建字体配置离线包载荷。"""

        return {
            "asset_name": font_config.asset_name,
            "font_family": font_config.font_family,
            "font_format": font_config.font_format,
            "font_weight": font_config.font_weight,
            "font_style": font_config.font_style,
            "font_display": font_config.font_display,
            "status": font_config.status,
        }

    @staticmethod
    def normalize_style_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """按现有样式创建请求规则归一化离线包样式载荷。"""

        package_payload = dict(payload)
        package_payload.setdefault("style_spec_markdown", "")
        return WorkspaceStyleCreateRequest.model_validate(package_payload).model_dump(mode="json")

    @staticmethod
    def normalize_theme_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """归一化离线包主题载荷，确保比较和导入稳定。"""

        key = str(payload.get("key") or "").strip().lower()
        name = str(payload.get("name") or "").strip()
        if not key or len(key) > 64 or not STYLE_KEY_PATTERN.match(key):
            raise ValueError("主题 key 必须是 1-64 位小写字母、数字、下划线或连字符。")
        if not name or len(name) > 128:
            raise ValueError("主题名称必须是 1-128 位文本。")
        description = payload.get("description")
        if description is not None:
            description = str(description)
            if len(description) > 2000:
                raise ValueError("主题描述不能超过 2000 字。")

        return {
            "key": key,
            "name": name,
            "description": description,
            "logo_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("logo_asset_name")),
            "invert_logo_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("invert_logo_asset_name")),
            "project_icon_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("project_icon_asset_name")),
            "logo_path": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("logo_path")),
            "invert_logo_path": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("invert_logo_path")),
            "project_icon_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("project_icon_name")),
            "heading_font_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("heading_font_asset_name")),
            "body_font_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("body_font_asset_name")),
            "code_font_asset_name": WorkspaceStylePackageFormat.normalize_optional_name(payload.get("code_font_asset_name")),
            "heading_font_label": str(payload.get("heading_font_label") or DEFAULT_THEME_HEADING_FONT).strip(),
            "body_font_label": str(payload.get("body_font_label") or DEFAULT_THEME_BODY_FONT).strip(),
            "code_font_label": str(payload.get("code_font_label") or DEFAULT_THEME_CODE_FONT).strip(),
            "palette": ThemePalette.model_validate(payload.get("palette")).model_dump(mode="python"),
        }

    @staticmethod
    def build_package_asset_lookup(package_assets: list[PackageAsset]) -> dict[str, PackageAsset]:
        """按资源 name 建立包内资源索引。"""

        return {
            str(item.metadata.get("name") or "").strip(): item
            for item in package_assets
            if str(item.metadata.get("name") or "").strip()
        }

    @staticmethod
    def font_config_matches(existing: WorkspaceFontConfig, payload: dict[str, Any]) -> bool:
        """判断目标工作空间已有字体配置是否与离线包一致。"""

        return all(
            str(getattr(existing, field) or "").strip() == str(payload.get(field) or "").strip()
            for field in ["asset_name", "font_family", "font_format", "font_weight", "font_style", "font_display", "status"]
        )

    @staticmethod
    def assert_unique_asset_hash_metadata(assets: list[WorkspaceAsset]) -> None:
        """避免同一 hash 对应多个逻辑资源时无法按 v1 包格式表达。"""

        by_hash: dict[str, str] = {}
        for asset in assets:
            existing_name = by_hash.get(asset.file_hash)
            if existing_name is not None and existing_name != asset.name:
                raise AppException(
                    status_code=409,
                    code="WORKSPACE_STYLE_PACKAGE_ASSET_HASH_CONFLICT",
                    detail=(
                        f"资源 {existing_name} 与 {asset.name} 使用同一文件 hash，"
                        "初版样式离线包无法表达一份文件对应多个资源名，请先调整资源。"
                    ),
                )
            by_hash[asset.file_hash] = asset.name

    @staticmethod
    def build_export_filename(styles: list[WorkspaceStyle]) -> str:
        """生成样式离线包下载文件名。"""

        first_key = styles[0].key if styles else "styles"
        suffix = f"-and-{len(styles) - 1}" if len(styles) > 1 else ""
        return f"workspace-styles-{first_key}{suffix}.zip"
