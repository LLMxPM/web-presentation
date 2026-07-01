"""文件功能：封装 Backend 调用 Runtime 内部资源比例测量接口的 HTTP 客户端。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import get_current_request_id
from app.models.enums import AssetType
from app.services.runtime_build_client import RUNTIME_SERVICE_TOKEN_HEADER
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
                RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_service_access_token(
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
        """发送 JSON 请求到 Runtime，并统一映射错误。"""

        runtime_base_url = self.settings.runtime_base_url.rstrip("/")
        timeout = httpx.Timeout(self.settings.runtime_request_timeout_seconds * 4)

        async with httpx.AsyncClient(base_url=runtime_base_url, timeout=timeout) as client:
            response = await client.request(method, path, json=payload, headers=headers or {})

        if response.status_code >= 500:
            logger.error(
                "Runtime 资源比例测量返回服务端错误。",
                extra={"event": "runtime.asset_render_hint.measure.failed", "path": path, "status_code": response.status_code},
            )
            raise self._build_app_exception(response, force_status_code=502)
        if response.status_code >= 400:
            logger.warning(
                "Runtime 资源比例测量返回业务错误。",
                extra={"event": "runtime.asset_render_hint.measure.rejected", "path": path, "status_code": response.status_code},
            )
            raise self._build_app_exception(response)

        try:
            return dict(response.json())
        except ValueError as exc:
            raise AppException(status_code=502, code="RUNTIME_RESPONSE_INVALID", detail="Runtime 返回了非法 JSON。") from exc

    @staticmethod
    def _build_app_exception(response: httpx.Response, force_status_code: int | None = None) -> AppException:
        """将 Runtime 错误响应转换为统一应用错误。"""

        code = "RUNTIME_ASSET_RENDER_HINT_MEASURE_FAILED"
        detail = response.text or "Runtime 资源比例测量请求失败。"
        try:
            payload = response.json()
            code = str(payload.get("code") or code)
            detail = str(payload.get("message") or detail)
        except ValueError:
            pass
        return AppException(
            status_code=force_status_code or response.status_code,
            code=code,
            detail=detail,
        )
