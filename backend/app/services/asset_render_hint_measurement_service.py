"""文件功能：统一测量资源近似比例，封装静态解析与 Runtime 渲染测量分支。"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType
from app.services.asset_render_metadata_service import AssetRenderMetadataService
from app.services.runtime_asset_render_hint_client import RuntimeAssetRenderHintClient


class AssetRenderHintMeasurementService:
    """生成资源渲染提示元数据，供回填任务和 CLI 复用。"""

    def __init__(self, runtime_client: RuntimeAssetRenderHintClient | None = None) -> None:
        self.runtime_client = runtime_client or RuntimeAssetRenderHintClient()

    async def measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any] | None:
        """按资源类型测量近似比例；无法推断时返回 None。"""

        asset_type = AssetType(asset.asset_type)
        if asset_type in {AssetType.FORMULA, AssetType.MERMAID}:
            text = self._decode_text_content(content)
            result = await self.runtime_client.measure_asset_render_hint(asset_type=asset_type, content=text)
            return AssetRenderMetadataService.build_metadata_from_ratio(result.aspect_ratio_value, source="auto")
        return AssetRenderMetadataService.build_auto_metadata(
            asset_type,
            asset.original_name,
            asset.content_type,
            content,
        )

    @staticmethod
    def _decode_text_content(content: bytes) -> str:
        """把文本资源内容解码为 UTF-8 字符串。"""

        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppException(status_code=400, code="ASSET_CONTENT_NOT_UTF8", detail="资源内容不是合法 UTF-8 文本。") from exc
