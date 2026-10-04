"""文件功能：用真实 External HTTP 验证 Job 日志关联、并发隔离和日志故障边界。"""

import asyncio
import json
import logging

import pytest
from app.models.api_mutation_job import ApiMutationJob
from app.services.oauth import audit_logging
from sqlalchemy import select

from tests.fixtures.oauth_logging import call, events
from tests.fixtures.oauth_mutations import SOURCE, delegate_headers, other_user_access


async def test_mutation_replay_and_dynamic_job_have_safe_context(
    oauth_mutation_client, caplog
):
    """队列受理/幂等重放/动态状态共享 Job；PAT 对等且未采信幂等键、查询参数或正文。"""
    caplog.set_level(logging.INFO)
    client, _, access, pat = oauth_mutation_client
    headers = await delegate_headers(
        client, access["access_token"], key="sensitive-idempotency-value"
    )
    caplog.clear()
    kwargs = {
        "json": {"project_id": 1, "name": "页面", "source_code": SOURCE},
        "headers": headers,
    }
    created = await call(
        client, "create-request", "POST", "/api/v1/jobs/mutations/pages", **kwargs
    )
    replay = await call(
        client, "replay-request", "POST", "/api/v1/jobs/mutations/pages", **kwargs
    )
    job_id = created.json()["job_id"]
    assert (
        created.status_code == replay.status_code == 202
        and replay.json()["job_id"] == job_id
    )
    status = await call(
        client,
        "status-request",
        "GET",
        "/api/v1/jobs/mutations/" + job_id,
        headers={"Authorization": "Bearer " + pat, "X-Workspace-ID": "999"},
        params={"resource_type": "component", "ctx": "signed-url-secret"},
    )
    assert status.status_code == 200
    rows = events(caplog, "external.request.completed")
    assert len(rows) == 3 and {row["job_id"] for row in rows} == {job_id}
    assert {row["workspace_id"] for row in rows} == {1}
    assert [row["operation"] for row in rows] == [
        "jobs.mutation.page.create",
        "jobs.mutation.page.create",
        "jobs.mutation.page.status",
    ]
    assert rows[-1]["credential_source"] == "pat" and "grant_id" not in rows[-1]
    serialized = json.dumps(rows)
    assert all(
        secret not in serialized
        for secret in (
            SOURCE,
            access["access_token"],
            pat,
            "sensitive-idempotency-value",
            "signed-url-secret",
        )
    )


async def test_concurrent_requests_do_not_mix_users(oauth_mutation_client, caplog):
    """两用户并发请求的公共身份/请求 ID 逐一对应，第三个伪造凭证没有认证主体。"""
    caplog.set_level(logging.INFO)
    client, factory, access, _ = oauth_mutation_client
    other = await other_user_access(client, factory)
    first_headers = await delegate_headers(client, access["access_token"])
    second_headers = await delegate_headers(client, other["access_token"])
    caplog.clear()
    results = await asyncio.gather(
        call(client, "user-one", "GET", "/api/v1/auth/whoami", headers=first_headers),
        call(client, "user-two", "GET", "/api/v1/auth/whoami", headers=second_headers),
        call(
            client,
            "invalid-user",
            "GET",
            "/api/v1/auth/whoami",
            headers={
                "Authorization": "Bearer wp_dlg_invalid-secret",
                "X-Workspace-ID": "2",
            },
        ),
    )
    assert [row.status_code for row in results] == [200, 200, 401]
    rows = {
        row["request_id"]: row for row in events(caplog, "external.request.completed")
    }
    assert (
        rows["user-one"]["user_id"] == 1 and rows["user-one"]["grant_id"] == "grant-1"
    )
    assert (
        rows["user-two"]["user_id"] == 2 and rows["user-two"]["grant_id"] == "grant-2"
    )
    assert (
        "user_id" not in rows["invalid-user"]
        and "workspace_id" not in rows["invalid-user"]
    )
    assert rows["invalid-user"]["error_code"] == "UNAUTHENTICATED"
    assert "invalid-secret" not in json.dumps(rows)
    assert events(caplog, "external.request.completed")[0]["duration_ms"] >= 0


@pytest.mark.parametrize("kind", ["scope", "body", "space"])
async def test_denied_request_logs_status_without_payload(
    oauth_mutation_client, caplog, kind
):
    """权限、结构与空间失败保留 HTTP 状态，不输出错误文本或未验证的空间。"""
    caplog.set_level(logging.INFO)
    client, _, access, _ = oauth_mutation_client
    scopes = ["page:read"] if kind == "scope" else ["page:read", "page:write"]
    headers = await delegate_headers(client, access["access_token"], scopes=scopes)
    if kind == "space":
        headers["X-Workspace-ID"] = "999"
    caplog.clear()
    body = {"project_id": 1, "source_code": SOURCE, "name": "页面"}
    if kind == "body":
        body["project_id"] = "invalid-payload-secret"
    result = await call(
        client,
        "denied-request",
        "POST",
        "/api/v1/jobs/mutations/pages",
        json=body,
        headers=headers,
    )
    assert result.status_code == (422 if kind == "body" else 403)
    row = events(caplog, "external.request.completed")[0]
    assert row["status_code"] == result.status_code and row["user_id"] == 1
    assert "job_id" not in row
    if kind != "body":
        assert "workspace_id" not in row
    assert "invalid-payload-secret" not in json.dumps(row) and SOURCE not in json.dumps(
        row
    )


async def test_logger_failure_does_not_repeat_committed_writes(
    oauth_mutation_client, monkeypatch
):
    """日志 Handler 抛错后发行/受理仍成功，同键恢复只有一个 Job。"""
    from app.api import external_request_logging

    client, factory, access, _ = oauth_mutation_client

    def fail_log(*args, **kwargs):
        """模拟日志设施故障，不能成为业务重试理由。"""
        raise RuntimeError("log-fault")

    monkeypatch.setattr(audit_logging.logger, "info", fail_log)
    monkeypatch.setattr(external_request_logging.logger, "info", fail_log)
    headers = await delegate_headers(client, access["access_token"])
    kwargs = {
        "json": {"project_id": 1, "name": "页面", "source_code": SOURCE},
        "headers": headers,
    }
    created = await client.post("/api/v1/jobs/mutations/pages", **kwargs)
    replay = await client.post("/api/v1/jobs/mutations/pages", **kwargs)
    assert created.status_code == replay.status_code == 202
    assert created.json()["job_id"] == replay.json()["job_id"]
    async with factory() as session:
        rows = (await session.scalars(select(ApiMutationJob))).all()
        assert len(rows) == 1
