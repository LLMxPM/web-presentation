"""文件功能：验证提交后 OAuth 审计日志的 ORM 过期边界和服务运维幂等事件。"""

import json
import logging
from uuid import uuid4

from app.core.logging_config import JsonLineFormatter, bind_request_id, reset_request_id
from app.core.time_utils import utc_now
from app.models.oauth_audit import OAuthAuditEvent
from app.services.oauth.audit_logging import commit_audit_events
from app.services.oauth.service_registry import OAuthServiceRegistry
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.fixtures.oauth import POLICY


async def test_committed_snapshot_survives_expire_on_commit(oauth_database, caplog):
    """真实 Session 提交后所有 ORM 属性过期，日志仍从提交前公共快照产生，不能隐式读库。"""
    caplog.set_level(logging.INFO)
    factory = async_sessionmaker(oauth_database.kw["bind"], expire_on_commit=True)
    audit_id = uuid4().hex
    context = bind_request_id("expire-request")
    try:
        async with factory() as session:
            row = OAuthAuditEvent(
                event_id=audit_id,
                event="service_created",
                service_id="snapshot-mcp",
                created_at=utc_now(),
            )
            session.add(row)
            await commit_audit_events(session, [row])
            assert "event_id" not in row.__dict__
    finally:
        reset_request_id(context)
    record = next(
        row
        for row in caplog.records
        if getattr(row, "event", None) == "oauth.audit.committed"
    )
    payload = json.loads(JsonLineFormatter(service="backend").format(record))
    assert (
        payload["request_id"] == "expire-request"
        and payload["audit_event_id"] == audit_id
    )
    assert payload["service_id"] == "snapshot-mcp"
    async with oauth_database() as session:
        stored = await session.get(OAuthAuditEvent, audit_id)
        assert stored is not None and stored.event == payload["audit_event"]


async def test_service_changes_only_log_committed_new_events(oauth_database, caplog):
    """服务创建/停用/轮换启用逐一映射数据库审计；重复停用无新事件且日志无密钥。"""
    caplog.set_level(logging.INFO)
    registry = OAuthServiceRegistry(oauth_database, POLICY)
    secret = "sensitive-registry-secret-" * 3
    context = bind_request_id("operator-request")
    try:
        await registry.create("logging-mcp", "日志关联测试", secret)
        await registry.disable("logging-mcp")
        await registry.disable("logging-mcp")
        await registry.rotate("logging-mcp", secret, enable=True)
    finally:
        reset_request_id(context)
    formatter = JsonLineFormatter(service="backend")
    payloads = [
        json.loads(formatter.format(row))
        for row in caplog.records
        if getattr(row, "event", None) == "oauth.audit.committed"
    ]
    assert [row["audit_event"] for row in payloads] == [
        "service_created",
        "service_disabled",
        "service_secret_rotated",
        "service_enabled",
    ]
    assert {row["request_id"] for row in payloads} == {"operator-request"}
    assert {row["service_id"] for row in payloads} == {"logging-mcp"}
    assert secret not in json.dumps(payloads)
    async with oauth_database() as session:
        for payload in payloads:
            row = await session.get(OAuthAuditEvent, payload["audit_event_id"])
            assert row is not None and row.event == payload["audit_event"]
