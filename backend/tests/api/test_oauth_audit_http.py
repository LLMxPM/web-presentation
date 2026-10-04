"""文件功能：用真实 OAuth HTTP 验证授权/交换日志关联、提交失败与协议错误脱敏。"""

import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from app.models.oauth_audit import OAuthAuditEvent
from app.services.oauth.chatgpt_client import CHATGPT_REDIRECT_URI
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.oauth import POLICY, VERIFIER
from tests.fixtures.oauth_consent import consent_query
from tests.fixtures.oauth_logging import call, events
from tests.fixtures.oauth_resource import exchange_data, service_request


@pytest.mark.parametrize("approved", [True, False])
async def test_consent_to_exchange_has_committed_audit_ids(
    oauth_http_client, mcp_access, caplog, approved
):
    """批准/拒绝关联审计行；批准后真实代码兑换和服务交换沿用同一 Grant，日志无原始凭证。"""
    caplog.set_level(logging.INFO)
    client, factory, _ = oauth_http_client
    base = "/api/v1/account/oauth/consents"
    view = (
        await client.post(base, json={"authorization_query": consent_query()})
    ).json()
    result = await call(
        client,
        "consent-request",
        "POST",
        f"{base}/{view['request_id']}/decision",
        json={
            "approved": approved,
            "csrf_token": view["csrf_token"],
            "workspace_ids": [1] if approved else [],
            "scopes": ["page:read"] if approved else [],
        },
    )
    assert result.status_code == 200, result.text
    audits = events(caplog, "oauth.audit.committed")
    first = audits[0]
    assert first["audit_event"] == (
        "consent_approved" if approved else "consent_denied"
    )
    assert first["request_id"] == "consent-request" and first["user_id"] == 1
    async with factory() as session:
        row = await session.get(OAuthAuditEvent, first["audit_event_id"])
        assert row is not None and row.event == first["audit_event"]
    if not approved:
        assert first["grant_id"] is None
        return
    code = parse_qs(urlsplit(result.json()["redirect_uri"]).query)["code"][0]
    issued = await call(
        client,
        "code-request",
        "POST",
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": VERIFIER,
            "client_id": first["client_id"],
            "redirect_uri": CHATGPT_REDIRECT_URI,
            "resource": POLICY.mcp_resource,
        },
    )
    assert issued.status_code == 200, issued.text
    access = issued.json()["access_token"]
    exchanged = await call(
        client,
        "exchange-request",
        "POST",
        "/oauth/token",
        data=exchange_data(access, scope="page:read"),
        headers=dict(service_request({}).headers),
    )
    assert exchanged.status_code == 200, exchanged.text
    delegated = exchanged.json()["access_token"]
    identity = await call(
        client,
        "business-request",
        "GET",
        "/api/v1/auth/whoami",
        headers={"Authorization": "Bearer " + delegated},
    )
    assert identity.status_code == 200, identity.text
    audits = events(caplog, "oauth.audit.committed")
    assert [row["audit_event"] for row in audits] == [
        "consent_approved",
        "code_consumed",
        "token_exchanged",
    ]
    assert {row["grant_id"] for row in audits} == {first["grant_id"]}
    assert [row["request_id"] for row in audits] == [
        "consent-request",
        "code-request",
        "exchange-request",
    ]
    business = events(caplog, "external.request.completed")[0]
    assert (
        business["grant_id"] == first["grant_id"]
        and business["client_id"] == first["client_id"]
    )
    assert (
        business["service_id"] == "mcp-service"
        and business["credential_source"] == "delegated"
    )
    assert business["request_id"] == "business-request"
    assert business["credential_id"] == audits[-1]["credential_id"]
    serialized = json.dumps(audits + [business])
    assert all(
        secret not in serialized
        for secret in (code, access, delegated, view["csrf_token"])
    )


async def test_failed_commit_does_not_emit_success_audit(
    oauth_http_client, mcp_access, monkeypatch, caplog
):
    """真正提交故障不能产生 token_exchanged 成功日志，协议也不交付暂存 Token。"""
    caplog.set_level(logging.INFO)
    client, _, _ = oauth_http_client

    async def fail_commit(self):
        """只在本例注入提交失败，Session 关闭仍走原有回滚。"""
        raise RuntimeError("commit-fault")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    caplog.clear()
    with pytest.raises(RuntimeError, match="commit-fault"):
        await call(
            client,
            "failed-commit",
            "POST",
            "/oauth/token",
            data=exchange_data(mcp_access["access_token"]),
            headers=dict(service_request({}).headers),
        )
    assert not events(caplog, "oauth.audit.committed")


async def test_protocol_error_has_request_id_and_no_form(oauth_http_client, caplog):
    """协议入口拒绝查询凭证时只记录库错误码，不能记录表单或错误描述。"""
    caplog.set_level(logging.INFO)
    client, _, _ = oauth_http_client
    result = await call(
        client,
        "protocol-denied",
        "POST",
        "/oauth/token?code=query-secret",
        data={
            "grant_type": "authorization_code",
            "code": "form-secret",
        },
    )
    assert result.status_code == 400
    row = events(caplog, "oauth.request.completed")[0]
    assert row["endpoint"] == "token" and row["request_id"] == "protocol-denied"
    assert row["error_code"] == "invalid_request" and row["status_code"] == 400
    assert not events(caplog, "oauth.audit.committed")
    assert "query-secret" not in json.dumps(row) and "form-secret" not in json.dumps(
        row
    )
