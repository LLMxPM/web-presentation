"""文件功能：封装 Backend 调用 Runtime 内部代码诊断接口的 HTTP 客户端。"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import get_current_request_id
from app.services.runtime_build_client import RUNTIME_SERVICE_TOKEN_HEADER
from app.services.token_service import TokenService


logger = logging.getLogger(__name__)


class RuntimeDiagnosticsClient:
    """Runtime 代码诊断内部客户端。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def dispatch_artifact_diagnostics(
        self,
        *,
        artifact_id: str,
        diagnostics_token: str,
        label: str | None = None,
    ) -> dict[str, object]:
        """向 Runtime 派发 artifact 代码检查任务。"""

        if self.settings.ai_test_mode == "mock":
            return {
                "success": True,
                "status": "passed",
                "artifact_id": artifact_id,
                "summary": "代码检查通过。",
                "diagnostics": [],
            }

        start_time = time.perf_counter()
        logger.info(
            "开始派发 Runtime 代码诊断。",
            extra={"event": "runtime.diagnostics.dispatch.start", "artifact_id": artifact_id, "label": label},
        )
        payload = {
            "artifact_id": artifact_id,
            "label": label,
        }
        result = await self._request_json(
            "POST",
            "/__runtime_internal/v1/diagnostics/artifact",
            payload,
            headers={
                "Authorization": f"Bearer {diagnostics_token}",
                "X-Request-ID": get_current_request_id(),
                RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_service_access_token(
                    artifact_id=artifact_id,
                    expires_in_seconds=900,
                ),
            },
        )
        logger.info(
            "Runtime 代码诊断派发完成。",
            extra={
                "event": "runtime.diagnostics.dispatch.done",
                "artifact_id": artifact_id,
                "status": result.get("status"),
                "duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
            },
        )
        return result

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
                "Runtime 代码诊断请求返回服务端错误。",
                extra={"event": "runtime.diagnostics.request.failed", "path": path, "status_code": response.status_code},
            )
            raise self._build_app_exception(response, force_status_code=502)
        if response.status_code >= 400:
            logger.warning(
                "Runtime 代码诊断请求返回业务错误。",
                extra={"event": "runtime.diagnostics.request.rejected", "path": path, "status_code": response.status_code},
            )
            raise self._build_app_exception(response)

        try:
            return dict(response.json())
        except ValueError as exc:
            raise AppException(status_code=502, code="RUNTIME_RESPONSE_INVALID", detail="Runtime 返回了非法 JSON。") from exc

    @staticmethod
    def _build_app_exception(response: httpx.Response, force_status_code: int | None = None) -> AppException:
        """将 Runtime 错误响应转换为统一应用错误。"""

        code = "RUNTIME_DIAGNOSTICS_FAILED"
        detail = response.text or "Runtime 代码检查请求失败。"
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
