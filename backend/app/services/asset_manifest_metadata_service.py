"""文件功能：生成 Runtime manifest 中资源元数据摘要，避免下发完整渲染元数据。"""

from __future__ import annotations

from typing import Any

from app.models.asset import WorkspaceAsset
from app.schemas.asset import resolve_asset_role
from app.services.asset_render_metadata_service import AssetRenderMetadataService


def build_asset_manifest_metadata(asset: WorkspaceAsset) -> dict[str, Any]:
    """把资源模型转换为 Runtime manifest 可消费的轻量元数据。"""

    metadata: dict[str, Any] = {
        "file_hash": str(asset.file_hash or "").strip(),
        "original_name": str(asset.original_name or "").strip(),
        "asset_role": resolve_asset_role(asset.asset_type).value,
        "render_type": str(asset.asset_type or "").strip(),
        "content_type": str(asset.content_type or "").strip(),
    }
    ratio_summary = AssetRenderMetadataService.summarize_metadata(asset.render_metadata)
    for key in ("approx_aspect_ratio", "approx_aspect_ratio_value", "aspect_ratio_source"):
        value = ratio_summary.get(key)
        if value is not None:
            metadata[key] = value
    return metadata
