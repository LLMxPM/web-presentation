"""文件功能：封装 Backend 调用 Runtime 内部资源比例测量接口的 HTTP 客户端。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import get_current_request_id
from app.models.enums import AssetType
from app.services.runtime_target_router import RUNTIME_SERVICE_TOKEN_HEADER, request_runtime_role_json
from app.services.token_service import TokenService


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeAssetRenderHintMeasureResult:
    """Runtime 资源比例测量结果。"""

    aspect_ratio: str
    aspect_ratio_value: float
    source: str


class RuntimeAssetRenderHintClient:
    """Runtime 资源比例测量内部客户端。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def measure_asset_render_hint(
        self,
        *,
        asset_type: AssetType,
        content: str,
    ) -> RuntimeAssetRenderHintMeasureResult:
        """向 Runtime 请求测量 Formula/Mermaid 内容的近似比例。"""

        if asset_type not in {AssetType.FORMULA, AssetType.MERMAID}:
            raise AppException(status_code=400, code="ASSET_RENDER_HINT_TYPE_UNSUPPORTED", detail="该资源类型不支持 Runtime 比例测量。")

        start_time = time.perf_counter()
        payload: dict[str, object] = {
            "asset_type": asset_type.value,
            "content": content,
        }
        result = await self._request_json(
            "POST",
            "/__runtime_internal/v1/assets/render-hints/measure",
            payload,
            headers={
                "X-Request-ID": get_current_request_id(),
                RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_internal_tool_token(
                    expires_in_seconds=900,
                ),
            },
        )
        if result.get("ok") is not True:
            raise AppException(
                status_code=502,
                code=str(result.get("code") or "RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED"),
                detail=str(result.get("message") or "Runtime 资源比例测量失败。"),
            )
        try:
            aspect_ratio_value = float(result.get("aspect_ratio_value"))
        except (TypeError, ValueError) as exc:
            raise AppException(status_code=502, code="RUNTIME_RESPONSE_INVALID", detail="Runtime 返回的比例值不合法。") from exc
        logger.info(
            "Runtime 资源比例测量完成。",
            extra={
                "event": "runtime.asset_render_hint.measure.done",
                "asset_type": asset_type.value,
                "aspect_ratio_value": aspect_ratio_value,
                "duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
            },
        )
        return RuntimeAssetRenderHintMeasureResult(
            aspect_ratio=str(result.get("aspect_ratio") or "").strip(),
            aspect_ratio_value=aspect_ratio_value,
            source=str(result.get("source") or "runtime-svg"),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """通过选址器调用 Runtime 轻量测量入口，满载自动换副本。"""

        return await request_runtime_role_json(
            role="light",
            method=method,
            path=path,
            settings=self.settings,
            headers=headers or {},
            timeout_seconds=self.settings.runtime_request_timeout_seconds * 4,
            default_error_code="RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED",
            timeout_error_code="RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED",
            unavailable_error_code="RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED",
            json_payload=payload,
        )
