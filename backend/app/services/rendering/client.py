"""文件功能：Backend 调用 Renderer 内部 HTTP API 的客户端。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.rendering.credentials import RenderCredentialService
from app.services.rendering.target_resolver import WorkerEndpoint
from render_contracts.constants import (
    ENDPOINT_CAPABILITIES,
    ENDPOINT_EXECUTIONS,
    PROTOCOL_VERSION,
    RESULT_SCHEMA_VERSION,
    RUNTIME_RENDER_PROTOCOL_VERSION,
)
from render_contracts.errors import (
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_PROFILE_MISMATCH,
    ERROR_CODE_RESULT_LOST,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    ERROR_CODE_WORKER_BUSY,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import ExecutionReceipt, ExecutionRequest, WorkerCapabilities

logger = logging.getLogger(__name__)

SERVICE_AUTH_HEADER = "x-render-service-token"


class RendererClient:
    """按指定 Worker/epoch 发送执行请求，不把状态查询随机发到任意副本。"""

    def __init__(
        self,
        *,
        credential_service: RenderCredentialService | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.settings = get_settings()
        self.credentials = credential_service or RenderCredentialService(self.settings)
        self.timeout_seconds = float(timeout_seconds or self.settings.render_request_timeout_seconds)

    async def fetch_capabilities(self, endpoint: WorkerEndpoint) -> WorkerCapabilities:
        """查询 Worker 能力、协议版本与槽位状态。"""

        url = f"{endpoint.base_url}{ENDPOINT_CAPABILITIES}"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message=f"Renderer 能力查询失败：{endpoint.worker_id}",
                    stage="capabilities",
                )
            ) from exc
        if response.status_code >= 400:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message=f"Renderer 能力接口返回 {response.status_code}。",
                    stage="capabilities",
                )
            )
        capabilities = WorkerCapabilities.from_dict(response.json())
        if capabilities.protocol_version and capabilities.protocol_version != PROTOCOL_VERSION:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_CONTRACT_MISMATCH,
                    message="Renderer 控制协议版本不匹配。",
                    stage="capabilities",
                )
            )
        if capabilities.result_schema_version and capabilities.result_schema_version != RESULT_SCHEMA_VERSION:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_CONTRACT_MISMATCH,
                    message="Renderer 结果 Schema 版本不匹配。",
                    stage="capabilities",
                )
            )
        return capabilities

    async def dispatch_execution(self, endpoint: WorkerEndpoint, request: ExecutionRequest) -> ExecutionReceipt:
        """派发 attempt；429 表示明确未接管。"""

        url = f"{endpoint.base_url}{ENDPOINT_EXECUTIONS}"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=request.to_dict())
        except httpx.HTTPError as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message=f"Renderer 派发请求网络失败：{endpoint.worker_id}",
                    stage="dispatch",
                )
            ) from exc
        if response.status_code == 429:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_WORKER_BUSY,
                    message="Renderer 槽位繁忙，明确未接管。",
                    stage="dispatch",
                )
            )
        if response.status_code >= 400:
            payload: dict[str, Any] = {}
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = {"message": f"Renderer 派发失败 HTTP {response.status_code}"}
            error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else payload
            error = RenderError.from_dict(
                {
                    **error_payload,
                    "stage": error_payload.get("stage") or "dispatch",
                }
            )
            wrapped = RenderExecutionError(error)
            # 4xx 表示 Worker 明确未接管；保留 HTTP 状态供调度侧安全释放占用。
            wrapped.http_status = response.status_code  # type: ignore[attr-defined]
            raise wrapped
        receipt = ExecutionReceipt.from_dict(response.json())
        if receipt.attempt_id != request.attempt_id:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_CONTRACT_MISMATCH,
                    message="Renderer 回执 attempt_id 与请求不一致。",
                    stage="dispatch",
                )
            )
        return receipt

    async def fetch_execution(self, endpoint: WorkerEndpoint, attempt_id: str) -> ExecutionReceipt:
        """查询 attempt 状态；HTTP 200 仍须读取执行状态。"""

        url = f"{endpoint.base_url}{ENDPOINT_EXECUTIONS}/{attempt_id}"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message="Renderer 执行状态查询失败。",
                    stage="query",
                )
            ) from exc
        if response.status_code == 404:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_RESULT_LOST,
                    message="Renderer 不认识该 attempt（可能已重启）。",
                    stage="query",
                )
            )
        if response.status_code == 410:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_RESULT_LOST,
                    message="Renderer 结果已回收。",
                    stage="query",
                )
            )
        if response.status_code >= 400:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message=f"Renderer 状态查询 HTTP {response.status_code}。",
                    stage="query",
                )
            )
        return ExecutionReceipt.from_dict(response.json())

    async def fetch_artifact(self, endpoint: WorkerEndpoint, attempt_id: str, name: str) -> bytes:
        """流式读取有界产物，超过上限直接失败。"""

        url = f"{endpoint.base_url}{ENDPOINT_EXECUTIONS}/{attempt_id}/artifacts/{name}"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        max_bytes = int(getattr(self.settings, "render_artifact_max_bytes", 32 * 1024 * 1024))
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise RenderExecutionError(
                            RenderError.from_code(
                                ERROR_CODE_SERVICE_UNAVAILABLE,
                                message=f"Renderer 产物 HTTP {response.status_code}。",
                                stage="fetch",
                            )
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise RenderExecutionError(
                                RenderError.from_code(
                                    "RENDER_OUTPUT_LIMIT_EXCEEDED",
                                    message="产物超过大小上限。",
                                    stage="fetch",
                                )
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
        except RenderExecutionError:
            raise
        except httpx.HTTPError as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    message="Renderer 产物读取失败。",
                    stage="fetch",
                )
            ) from exc

    async def confirm_result_consumption(self, endpoint: WorkerEndpoint, attempt_id: str) -> None:
        """通知 Worker 结果已持久化，可提前释放临时产物。"""

        url = f"{endpoint.base_url}{ENDPOINT_EXECUTIONS}/{attempt_id}/result-consumption"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(url, headers=headers, json={"consumed": True})
        except httpx.HTTPError:
            # 消费确认丢失可幂等补发，不重新执行渲染。
            logger.warning(
                "Renderer 结果消费确认发送失败，将由后续重试补发。",
                extra={"event": "render.client.consume_confirm.failed", "attempt_id": attempt_id},
            )

    async def cancel_execution(self, endpoint: WorkerEndpoint, attempt_id: str) -> None:
        """向 Worker 发送幂等取消。"""

        url = f"{endpoint.base_url}{ENDPOINT_EXECUTIONS}/{attempt_id}/cancellation"
        headers = {SERVICE_AUTH_HEADER: self.credentials.issue_service_token(worker_id=endpoint.worker_id)}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(url, headers=headers, json={"cancel_requested": True})
        except httpx.HTTPError:
            logger.warning(
                "Renderer 取消请求发送失败。",
                extra={"event": "render.client.cancel.failed", "attempt_id": attempt_id},
            )

    @staticmethod
    def validate_profile(capabilities: WorkerCapabilities, expected_digest: str) -> None:
        """核对 Worker 实际 profile 与发布清单一致。"""

        if not expected_digest:
            return
        if capabilities.render_profile_digest and capabilities.render_profile_digest != expected_digest:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_PROFILE_MISMATCH,
                    message="Renderer 环境 profile 与当前发布清单不一致。",
                    stage="capabilities",
                )
            )
        runtime_version = capabilities.runtime_render_protocol_version
        if runtime_version and runtime_version != RUNTIME_RENDER_PROTOCOL_VERSION:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_CONTRACT_MISMATCH,
                    message="Runtime 渲染协议版本不匹配。",
                    stage="capabilities",
                )
            )
