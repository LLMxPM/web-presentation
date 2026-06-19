"""文件功能：提供组件分享包服务复用的 payload、文件名和校验辅助方法。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig
from app.models.workspace_component import WorkspaceComponent


class ComponentSharePackageHelperMixin:
    """承载分享包服务的静态辅助方法，降低主服务文件体积。"""

    @staticmethod
    def _build_asset_payload(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建 asset.json 内容。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "file_hash": asset.file_hash,
            "description": asset.description,
            "tags": asset.tags or [],
            "render_metadata": asset.render_metadata,
        }

    @staticmethod
    def _build_asset_manifest_entry(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建 manifest.assets 中的资源摘要。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "file_hash": asset.file_hash,
        }

    @staticmethod
    def _build_font_config_payload(font_config: WorkspaceFontConfig) -> dict[str, Any]:
        """构建字体配置分享包载荷。"""

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
    def _font_config_matches(existing: WorkspaceFontConfig, payload: dict[str, Any]) -> bool:
        """判断目标工作空间已有字体配置是否与分享包一致。"""

        return all(
            str(getattr(existing, field) or "").strip() == str(payload.get(field) or "").strip()
            for field in ["asset_name", "font_family", "font_format", "font_weight", "font_style", "font_display", "status"]
        )

    @staticmethod
    def _assert_unique_asset_hash_metadata(assets: list[WorkspaceAsset]) -> None:
        """避免同一 hash 对应多个逻辑资源时无法按 v1 包格式表达。"""

        by_hash: dict[str, str] = {}
        for asset in assets:
            existing_name = by_hash.get(asset.file_hash)
            if existing_name is not None and existing_name != asset.name:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_SHARE_ASSET_HASH_CONFLICT",
                    detail=(
                        f"资源 {existing_name} 与 {asset.name} 使用同一文件 hash，"
                        "初版分享包无法表达一份文件对应多个资源名，请先调整资源。"
                    ),
                )
            by_hash[asset.file_hash] = asset.name

    @staticmethod
    def _safe_archive_filename(name: str) -> str:
        """把资源展示文件名规整为 Zip 内单文件名。"""

        filename = Path(str(name or "asset.bin").replace("\\", "/")).name
        return filename or "asset.bin"

    @staticmethod
    def _dump_json(value: Any) -> str:
        """按项目约定输出 UTF-8 友好的格式化 JSON。"""

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """把输入值转为整数，失败时返回空。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_export_filename(root_components: list[WorkspaceComponent]) -> str:
        """生成分享包下载文件名。"""

        first_code = root_components[0].code if root_components else "components"
        suffix = f"-and-{len(root_components) - 1}" if len(root_components) > 1 else ""
        return f"workspace-components-{first_code}{suffix}.zip"
