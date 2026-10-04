"""文件功能：在 OAuth 审计事务提交后输出固定公共身份字段，关联 HTTP 请求且不读取原始凭证。"""

import logging
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_current_request_id
from app.models.oauth_audit import OAuthAuditEvent

logger = logging.getLogger("app.oauth.audit")


def _log_event(message: str, fields: dict) -> None:
    """日志字段由本模块构造；Handler 故障不得把已提交凭证变成发行失败。"""
    try:
        logger.info(message, extra=fields)
    except Exception:  # noqa: BLE001 — 日志故障不能触发发行重试。
        return


def log_protocol_result(
    endpoint: str, status_code: int, error_code: str | None
) -> None:
    """仅记录固定协议入口、HTTP 状态与库生成的错误码，不记录表单、Header 或错误描述。"""
    _log_event(
        "OAuth 协议请求完成。",
        {
            "event": "oauth.request.completed",
            "request_id": get_current_request_id(),
            "endpoint": endpoint,
            "status_code": status_code,
            "error_code": error_code,
        },
    )


async def commit_audit_events(
    session: AsyncSession, events: Iterable[OAuthAuditEvent]
) -> None:
    """提交原有事务后记录审计快照；提交失败不输出成功事件，日志故障不改变已提交结果。"""
    request_id = get_current_request_id()
    snapshots = [
        {
            "event": "oauth.audit.committed",
            "audit_event": row.event,
            "audit_event_id": row.event_id,
            "request_id": request_id,
            "user_id": row.user_id,
            "client_id": row.client_id,
            "service_id": row.service_id,
            "grant_id": row.grant_id,
            "credential_id": row.token_id,
        }
        for row in events
    ]
    await session.commit()
    for snapshot in snapshots:
        _log_event("OAuth 审计事务已提交。", snapshot)
