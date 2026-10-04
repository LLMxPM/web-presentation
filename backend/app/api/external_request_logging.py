"""文件功能：为 External 真实鉴权结果与业务响应记录固定公共标识，不记录请求或响应正文。"""

import json
import logging

from fastapi import Request, Response

from app.core.logging_config import get_current_request_id
from app.services.external_principal import DelegatedCredential, ExternalPrincipal

logger = logging.getLogger("app.external.access")
MAX_JOB_RESPONSE_BYTES = 64 * 1024
_IDENTITY_FIELDS = frozenset(
    {
        "credential_source",
        "credential_id",
        "user_id",
        "grant_id",
        "client_id",
        "service_id",
        "operation",
        "workspace_id",
        "workspace_context_id",
        "job_id",
    }
)


def bind_external_identity(request: Request, principal: ExternalPrincipal) -> None:
    """认证完成后立即保存公共标量，避免幂等回滚后读取已过期 ORM 或采信 Header 声明。"""
    credential = principal.credential
    fields = {
        "credential_source": credential.source,
        "credential_id": credential.public_id,
        "user_id": principal.user.id,
    }
    if isinstance(credential, DelegatedCredential):
        fields.update(
            grant_id=credential.grant_id,
            client_id=credential.client_id,
            service_id=credential.service_id,
        )
    request.state.external_log_fields = fields


def bind_external_operation(
    request: Request,
    operation: str,
    *,
    workspace_id: int | None = None,
    workspace_context_id: int | None = None,
    job_id: str | None = None,
) -> None:
    """区分已验证的 Header 空间上下文与真实目标空间；操作/Job 来自真实依赖，不猜测载荷。"""
    fields = getattr(request.state, "external_log_fields", {})
    fields["operation"] = operation
    if workspace_id is not None:
        fields["workspace_id"] = workspace_id
    if workspace_context_id is not None:
        fields["workspace_context_id"] = workspace_context_id
    if job_id is not None:
        fields["job_id"] = job_id
    request.state.external_log_fields = fields


def bind_mutation_response(request: Request, response: Response) -> None:
    """只从已序列化的 Mutation DTO 提取 Job/空间标量；大响应跳过，不展开领域结果或错误正文。"""
    body = getattr(response, "body", b"")
    if len(body) > MAX_JOB_RESPONSE_BYTES or not 200 <= response.status_code < 300:
        return
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    fields = getattr(request.state, "external_log_fields", {})
    if isinstance(payload.get("job_id"), str):
        fields["job_id"] = payload["job_id"]
    if type(payload.get("workspace_id")) is int:
        fields["workspace_id"] = payload["workspace_id"]
    request.state.external_log_fields = fields


def log_external_result(
    request: Request,
    *,
    route: str,
    operation: str | None,
    status_code: int,
    duration_ms: float,
    error_code: str | None = None,
) -> None:
    """输出一次完成结果；仅允许本模块绑定的固定字段，日志故障不得改变业务响应。"""
    fields = getattr(request.state, "external_log_fields", {})
    extra = {
        "event": "external.request.completed",
        "request_id": get_current_request_id(),
        "method": request.method,
        "route": route,
        "operation": operation,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "error_code": error_code,
        **{key: value for key, value in fields.items() if key in _IDENTITY_FIELDS},
    }
    try:
        logger.info("External API 请求完成。", extra=extra)
    except Exception:  # noqa: BLE001 — 日志故障不能改变已提交业务结果。
        # 尤其不能把已提交 Mutation 的成功响应变成重试诱因。
        return
