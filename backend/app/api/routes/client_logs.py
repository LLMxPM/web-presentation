"""文件功能：接收浏览器端错误日志，并写入 Backend 标准输出。"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.logging_config import sanitize_log_value
from app.schemas.client_log import ClientErrorLogRequest
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthContext


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/errors", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def report_client_error(
    payload: ClientErrorLogRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> MessageResponse:
    """记录已登录用户浏览器端运行错误；日志只进入 stdout，不做持久化。"""

    settings = get_settings()
    if not settings.client_error_log_enabled:
        return MessageResponse(message="客户端错误日志上报已关闭。")

    safe_payload = _build_safe_client_error_payload(
        payload,
        user_id=current.user.id,
        max_bytes=settings.client_error_log_max_bytes,
    )
    safe_extra = {
        ("client_message" if key == "message" else key): value
        for key, value in safe_payload.items()
    }
    logger.error(
        "浏览器端运行错误。",
        extra={
            "event": "client.error",
            **safe_extra,
        },
    )
    return MessageResponse(message="已接收客户端错误日志。")


def _build_safe_client_error_payload(
    payload: ClientErrorLogRequest,
    *,
    user_id: int,
    max_bytes: int,
) -> dict[str, object]:
    """对浏览器错误载荷做二次脱敏与大小裁剪，避免大对象进入标准日志。"""

    safe_payload = sanitize_log_value(
        {
            "source": payload.source,
            "user_id": user_id,
            "message": payload.message,
            "error_name": payload.error_name,
            "stack": payload.stack,
            "route": payload.route,
            "url": payload.url,
            "component": payload.component,
            "trace_id": payload.trace_id,
            "artifact_id": payload.artifact_id,
            "context": payload.context,
        },
        max_string_length=4096,
    )
    if _payload_size(safe_payload) <= max_bytes:
        return safe_payload

    safe_payload["stack"] = "[truncated]"
    safe_payload["context"] = {"truncated": True}
    if _payload_size(safe_payload) <= max_bytes:
        return safe_payload

    safe_payload["message"] = str(safe_payload.get("message") or "")[:512]
    return safe_payload


def _payload_size(payload: dict[str, object]) -> int:
    """计算日志 payload JSON 编码后的字节数。"""

    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
