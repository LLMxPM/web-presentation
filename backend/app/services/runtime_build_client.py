"""文件功能：封装 Backend 调用 Runtime 内部整包构建接口的 HTTP 客户端。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.project_build import RuntimeBuildDispatchRequest
from app.services.token_service import TokenService


RUNTIME_SERVICE_TOKEN_HEADER = "x-runtime-service-token"


@dataclass(slots=True)
class RuntimeBuildDispatchResult:
    """Runtime 整包构建派发结果。"""

    artifact_id: str
    base_url: str
    artifact_entry_file: str | None
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    message: str


class RuntimeBuildClient:
    """Runtime 整包构建内部客户端。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def dispatch_project_build(
        self,
        *,
        artifact_id: str,
        base_url: str,
        build_token: str,
    ) -> RuntimeBuildDispatchResult:
        """向 Runtime 派发整项目构建任务。"""

        payload = RuntimeBuildDispatchRequest(artifact_id=artifact_id, base_url=base_url)
        response = await self._request_json(
            "POST",
            "/__runtime_internal/v1/builds/project",
            payload.model_dump_json().encode("utf-8"),
            headers={
                "Authorization": f"Bearer {build_token}",
                "Content-Type": "application/json",
                RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_service_access_token(
                    artifact_id=artifact_id,
                    expires_in_seconds=3600,
                ),
            },
        )
        return RuntimeBuildDispatchResult(
            artifact_id=str(response.get("artifact_id") or artifact_id),
            base_url=str(response.get("base_url") or base_url),
            artifact_entry_file=str(response.get("artifact_entry_file") or "").strip() or None,
            artifact_sha256=str(response.get("artifact_sha256") or "").strip() or None,
            artifact_size_bytes=_coerce_int(response.get("artifact_size_bytes")),
            message=str(response.get("message") or "构建完成。"),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        content: bytes,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """发送 JSON 请求到 Runtime，并统一映射错误。"""

        runtime_base_url = self.settings.runtime_base_url.rstrip("/")
        timeout = httpx.Timeout(self.settings.runtime_request_timeout_seconds * 12)

        async with httpx.AsyncClient(base_url=runtime_base_url, timeout=timeout) as client:
            response = await client.request(method, path, content=content, headers=headers or {})

        if response.status_code >= 500:
            raise self._build_app_exception(response, force_status_code=502)
        if response.status_code >= 400:
            raise self._build_app_exception(response)

        try:
            return response.json()
        except ValueError as exc:
            raise AppException(status_code=502, code="RUNTIME_RESPONSE_INVALID", detail="Runtime 返回了非法 JSON。") from exc

    @staticmethod
    def _build_app_exception(response: httpx.Response, force_status_code: int | None = None) -> AppException:
        """将 Runtime 错误响应转换为统一应用错误。"""

        code = "RUNTIME_REQUEST_FAILED"
        detail = response.text or "Runtime 请求失败。"
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


def _coerce_int(raw_value: object) -> int | None:
    """把 Runtime 返回的数值字段安全转换为 int。"""

    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None
