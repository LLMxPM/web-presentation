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
from app.services.runtime_target_router import RUNTIME_SERVICE_TOKEN_HEADER, request_runtime_role_json
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
        """发送 Runtime 内部请求，经选址器做多副本重试，并把错误归一化为 AppException。"""

        headers = {
            "X-Request-ID": get_current_request_id(),
            RUNTIME_SERVICE_TOKEN_HEADER: TokenService.generate_runtime_internal_tool_token(
                expires_in_seconds=900,
            ),
        }
        return await request_runtime_role_json(
            role="light",
            method="POST",
            path=path,
            settings=self.settings,
            headers=headers,
            timeout_seconds=self.settings.runtime_request_timeout_seconds,
            default_error_code="RUNTIME_VISUAL_EDIT_FAILED",
            timeout_error_code="RUNTIME_VISUAL_EDIT_TIMEOUT",
            unavailable_error_code="RUNTIME_VISUAL_EDIT_UNAVAILABLE",
            invalid_response_code="RUNTIME_VISUAL_EDIT_RESPONSE_INVALID",
            json_payload=payload,
            transport=self.transport,
        )

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
