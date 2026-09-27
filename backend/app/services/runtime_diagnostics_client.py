"""文件功能：封装 Backend 调用 Runtime 内部代码诊断接口的 HTTP 客户端。"""

from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.logging_config import get_current_request_id
from app.services.runtime_target_router import RUNTIME_SERVICE_TOKEN_HEADER, request_runtime_role_json
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
        """通过选址器调用 Runtime 诊断入口，满载自动换副本。"""

        return await request_runtime_role_json(
            role="check",
            method=method,
            path=path,
            settings=self.settings,
            headers=headers or {},
            timeout_seconds=self.settings.runtime_diagnostics_request_timeout_seconds,
            default_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            timeout_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            unavailable_error_code="RUNTIME_DIAGNOSTICS_FAILED",
            json_payload=payload,
        )
