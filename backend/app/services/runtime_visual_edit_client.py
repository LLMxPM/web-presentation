"""文件功能：封装 Backend 调用 Runtime 页面可视化编辑 AST 分析与改写端点的内部客户端。"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from pydantic.alias_generators import to_camel

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import get_current_request_id
from app.schemas.page_visual_edit_manifest import PAGE_VISUAL_EDIT_PROTOCOL_VERSION
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditAnalyzeResponse,
    RuntimePageVisualEditApplyRequest,
    RuntimePageVisualEditApplyResponse,
)
from app.services.runtime_build_client import RUNTIME_SERVICE_TOKEN_HEADER
from app.services.token_service import TokenService


logger = logging.getLogger(__name__)

RUNTIME_VISUAL_EDIT_ANALYZE_PATH = "/__runtime_internal/v1/visual-edit/analyze"
RUNTIME_VISUAL_EDIT_APPLY_PATH = "/__runtime_internal/v1/visual-edit/apply"
RuntimeVisualEditResponseModel = TypeVar(
    "RuntimeVisualEditResponseModel", bound=BaseModel
)


def serialize_runtime_visual_edit_payload(model: BaseModel) -> dict[str, object]:
    """把 Backend 的 snake_case 协议模型递归转换为 Runtime camelCase 请求载荷。"""

    def convert(value: object) -> object:
        """递归转换协议字段名，字面量值本身保持不变。"""

        if isinstance(value, dict):
            return {to_camel(str(key)): convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    payload = convert(model.model_dump(mode="python"))
    if not isinstance(
        payload, dict
    ):  # pragma: no cover - BaseModel dump 的显式类型防线
        raise TypeError("Runtime 可视化编辑请求必须序列化为对象。")
    return payload


class RuntimeVisualEditClient:
    """Runtime 页面可视化编辑内部客户端，负责协议序列化和错误归一化。"""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = get_settings()
        self.transport = transport

    async def analyze(
        self,
        request: RuntimePageVisualEditAnalyzeRequest,
    ) -> RuntimePageVisualEditAnalyzeResponse:
        """请求 Runtime 分析规范 Vue SFC，并校验返回清单仍绑定请求源码。"""

        started_at = time.perf_counter()
        payload = await self._request_json(
            RUNTIME_VISUAL_EDIT_ANALYZE_PATH,
            serialize_runtime_visual_edit_payload(request),
        )
        response = self._validate_response(
            payload, RuntimePageVisualEditAnalyzeResponse
        )
        if (
            response.manifest.source_hash != request.source_hash
            or response.manifest.module_path != request.module_path
        ):
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_SOURCE_MISMATCH",
                detail="Runtime 可视化编辑分析结果与请求源码不匹配。",
            )
        logger.info(
            "Runtime 页面可视化编辑分析完成。",
            extra={
                "event": "runtime.visual_edit.analyze.done",
                "module_path": request.module_path,
                "duration_ms": round((time.perf_counter() - started_at) * 1_000, 2),
            },
        )
        return response

    async def apply(
        self,
        request: RuntimePageVisualEditApplyRequest,
    ) -> RuntimePageVisualEditApplyResponse:
        """请求 Runtime 应用受控 AST 操作，并拒绝部分应用或基线漂移。"""

        started_at = time.perf_counter()
        payload = await self._request_json(
            RUNTIME_VISUAL_EDIT_APPLY_PATH,
            serialize_runtime_visual_edit_payload(request),
        )
        response = self._validate_response(payload, RuntimePageVisualEditApplyResponse)
        if response.base_source_hash != request.source_hash:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_SOURCE_MISMATCH",
                detail="Runtime 可视化编辑改写结果与请求源码不匹配。",
            )
        if response.operations_applied != len(request.operations):
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_PARTIAL_APPLY",
                detail="Runtime 未完整应用页面可视化编辑操作。",
            )
        logger.info(
            "Runtime 页面可视化编辑改写完成。",
            extra={
                "event": "runtime.visual_edit.apply.done",
                "module_path": request.module_path,
                "operations_applied": response.operations_applied,
                "duration_ms": round((time.perf_counter() - started_at) * 1_000, 2),
            },
        )
        return response

    async def _request_json(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, object]:
        """发送 Runtime 内部请求，并把网络、HTTP 与 JSON 错误归一化为 AppException。"""

        headers = {
            "X-Request-ID": get_current_request_id(),
            RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_service_access_token(
                expires_in_seconds=900,
            ),
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.runtime_base_url.rstrip("/"),
                timeout=httpx.Timeout(self.settings.runtime_request_timeout_seconds),
                transport=self.transport,
            ) as client:
                response = await client.post(path, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AppException(
                status_code=504,
                code="RUNTIME_VISUAL_EDIT_TIMEOUT",
                detail="Runtime 页面可视化编辑请求超时。",
            ) from exc
        except httpx.RequestError as exc:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_UNAVAILABLE",
                detail="Runtime 页面可视化编辑服务不可访问。",
            ) from exc

        if response.status_code >= 500:
            logger.error(
                "Runtime 页面可视化编辑请求返回服务端错误。",
                extra={
                    "event": "runtime.visual_edit.request.failed",
                    "path": path,
                    "status_code": response.status_code,
                },
            )
            raise self._build_http_exception(response, force_status_code=502)
        if response.status_code >= 400:
            logger.warning(
                "Runtime 页面可视化编辑请求被拒绝。",
                extra={
                    "event": "runtime.visual_edit.request.rejected",
                    "path": path,
                    "status_code": response.status_code,
                },
            )
            raise self._build_http_exception(response)

        try:
            result = response.json()
        except ValueError as exc:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_RESPONSE_INVALID",
                detail="Runtime 页面可视化编辑返回了非法 JSON。",
            ) from exc
        if not isinstance(result, dict):
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_RESPONSE_INVALID",
                detail="Runtime 页面可视化编辑响应必须是 JSON 对象。",
            )
        return dict(result)

    @staticmethod
    def _validate_response(
        payload: dict[str, object],
        model_type: type[RuntimeVisualEditResponseModel],
    ) -> RuntimeVisualEditResponseModel:
        """校验 Runtime 响应结构与协议版本，避免错误结果进入页面保存链路。"""

        raw_protocol_version = payload.get(
            "protocol_version", payload.get("protocolVersion")
        )
        if raw_protocol_version != PAGE_VISUAL_EDIT_PROTOCOL_VERSION:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_PROTOCOL_MISMATCH",
                detail="Runtime 页面可视化编辑协议版本不兼容。",
            )
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_RESPONSE_INVALID",
                detail="Runtime 页面可视化编辑响应结构不合法。",
            ) from exc

    @staticmethod
    def _build_http_exception(
        response: httpx.Response, force_status_code: int | None = None
    ) -> AppException:
        """将 Runtime HTTP 错误转换为稳定的 Backend 业务错误。"""

        code = "RUNTIME_VISUAL_EDIT_FAILED"
        detail = response.text or "Runtime 页面可视化编辑请求失败。"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                code = str(payload.get("code") or code)
                detail = str(payload.get("message") or payload.get("detail") or detail)
        except ValueError:
            pass
        return AppException(
            status_code=force_status_code or response.status_code,
            code=code,
            detail=detail,
        )
