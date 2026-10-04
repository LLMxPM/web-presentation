"""文件功能：通过独立 MCP wheel 联测真实写入幂等、动态 Job 权限、取消/重试及基线冲突。"""

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.api_mutation_job import ApiMutationJob
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.services.oauth.protocol import credential_digest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from sqlalchemy import func, select, update

from tests.fixtures.oauth import POLICY, REDIRECT, VERIFIER, request_data
from tests.fixtures.oauth_mutations import SOURCE, delegate_headers
from tests.integration.test_mcp_consumer import call, data, make_runtime
from tests.integration.test_mcp_consumer import consumer_backend as consumer_backend
from tests.integration.test_oauth_mutation_commit import claim, prepared


class LostWriteResponse(httpx.AsyncBaseTransport):
    """仅测试在真实入队已提交后丢失首个响应，验证客户端不能透明重发写入。"""

    def __init__(self, app):
        """保留真实 ASGI 业务路由与数据库，故障只发生在响应传输边界。"""
        self.inner = httpx.ASGITransport(app=app)
        self.writes = 0

    async def handle_async_request(self, request):
        """等待真实页面创建完成后一次性模拟网络断开，不复制幂等或入队实现。"""
        response = await self.inner.handle_async_request(request)
        if request.method == "POST" and request.url.path == "/api/v1/pages":
            self.writes += 1
            if self.writes == 1:
                await response.aclose()
                raise httpx.ReadError("已提交响应在链路中丢失", request=request)
        return response

    async def aclose(self):
        """关闭测试 HTTP transport。"""
        await self.inner.aclose()


async def limited_access(client, factory, scopes):
    """用已有批准 Grant 的 Scope 子集签发真实授权码，不改动原访问凭证或认证依赖。"""
    code = "consumer-limited-" + uuid4().hex
    async with factory() as session:
        session.add(OAuthAuthorizationCode(code_hash=credential_digest(code), grant_id="grant-1", redirect_uri=REDIRECT,
            scopes=scopes, code_challenge=create_s256_code_challenge(VERIFIER), code_challenge_method="S256",
            created_at=utc_now(), expires_at=utc_now() + timedelta(seconds=POLICY.code_ttl_seconds)))
        await session.commit()
    response = await client.post("/oauth/token", data=request_data(code=code))
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def edit_arguments(kind):
    """构造测试已有实体的明确编辑基线；这是测试数据，不是 MCP 业务 DTO 镜像。"""
    return {"workspace_id": 1, "resource_type": kind, "action": "content", "target_id": 1,
        "idempotency_key": "edit-" + kind, "payload": {kind + "_id": 1, "base_version_no": 1 if kind == "page" else 0,
        "edits": [{"type": "replace_exact", "old_text": "原始", "new_text": "修改"}]}}


@pytest.mark.parametrize("kind", ["page", "component"])
async def test_invalid_edits_rejected_by_mcp_and_producer_before_enqueue(consumer_backend, oauth_mutation_client, kind):
    """真实 OpenAPI 的联合编辑 Schema 被两端执行，错误 type/字段不创建异步任务。"""
    backend, app, access, _ = consumer_backend
    _, factory, _, _ = oauth_mutation_client
    runtime = make_runtime(app)
    headers = await delegate_headers(backend, access["access_token"])
    args = edit_arguments(kind)
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            guide = data(await call(client, "wp_get_operation_guide", {"workspace_id": 1, "binding_id": kind + ".update.content"}, access["access_token"]))
            assert "replace_exact" in str(guide["request_body"]) and "rewrite_file" in str(guide["request_body"])
            for edits in ([{"type": "replace", "old_text": "原始", "new_text": "修改"}],
                          [{"type": "replace_exact", "new_text": "修改"}],
                          [{"type": "rewrite_file", "content": "<template/>", "unexpected": True}]):
                invalid = {**args, "payload": {**args["payload"], "edits": edits}}
                result = (await call(client, "wp_update_entity", invalid, access["access_token"])).json()["result"]
                assert result["isError"] and result["structuredContent"]["error"]["code"] == "INVALID_ARGUMENTS"
                response = await backend.post(f"/api/v1/{'pages' if kind == 'page' else 'components'}/1/edits",
                    json=invalid["payload"], headers={**headers, "Idempotency-Key": "invalid-edits"})
                assert response.status_code == 422
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 0


async def test_mcp_lost_write_dedup_dynamic_permission_and_cancel(consumer_backend, oauth_mutation_client):
    """真实 OAuth/MCP/入队/幂等：响应丢失后同键返回原 Job，只读与跨空间/任务类型权限不能绕过。"""
    backend, app, first, second = consumer_backend
    _, factory, _, _ = oauth_mutation_client
    page_only = await limited_access(backend, factory, ["page:read"])
    transport = LostWriteResponse(app)
    runtime = make_runtime(app, api_transport=transport)
    args = {"workspace_id": 1, "resource_type": "page", "mode": "new", "idempotency_key": "create-original",
            "payload": {"project_id": 1, "name": "MCP 创建", "source_code": SOURCE}}
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            readonly = await call(client, "wp_create_entity", args, page_only)
            assert readonly.json()["result"]["structuredContent"]["error"]["code"] == "INSUFFICIENT_SCOPE" and transport.writes == 0
            lost = (await call(client, "wp_create_entity", args, first["access_token"])).json()["result"]["structuredContent"]
            assert lost["error"]["outcome_unknown"] and lost["error"]["idempotency_key"] == "create-original"
            recovered = data(await call(client, "wp_create_entity", args, first["access_token"]))
            repeated = data(await call(client, "wp_create_entity", args, first["access_token"]))
            assert recovered["job_id"] == repeated["job_id"] and recovered["status"] == "pending" and transport.writes == 3
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1
            conflict = await call(client, "wp_create_entity", {**args, "payload": {**args["payload"], "name": "不同载荷"}}, first["access_token"])
            assert conflict.json()["result"]["structuredContent"]["error"]["status_code"] == 409
            component = data(await call(client, "wp_update_entity", edit_arguments("component"), first["access_token"]))
            locator = {"workspace_id": 1, "job_id": component["job_id"]}
            denied = await call(client, "wp_get_mutation_job", locator, page_only)
            assert denied.json()["result"]["structuredContent"]["error"]["status_code"] == 403
            cross_space = await call(client, "wp_get_mutation_job", {**locator, "workspace_id": 2}, second["access_token"])
            assert cross_space.json()["result"]["isError"]
            waiting = (await call(client, "wp_get_mutation_job", {**locator, "wait_seconds": 0.2}, first["access_token"])).json()["result"]
            assert not waiting["isError"] and waiting["structuredContent"]["meta"]["wait_exhausted"]
            canceled = data(await call(client, "wp_cancel_mutation_job", {**locator, "idempotency_key": "cancel-component"}, first["access_token"]))
            assert canceled["status"] == "canceled"
            retry = await call(client, "wp_retry_mutation_job", {**locator, "idempotency_key": "retry-canceled"}, first["access_token"])
            assert retry.json()["result"]["structuredContent"]["error"]["code"] == "MUTATION_JOB_NOT_RETRYABLE"


@pytest.mark.parametrize("kind", ["page", "component"])
async def test_mcp_failed_job_conflict_reload_without_baseline_upgrade(consumer_backend, oauth_mutation_client, monkeypatch, kind):
    """受控规划结果仅验证真实领域提交围栏；MCP 查询 failed 为成功，并给出源码重读入口。"""
    _, app, access, _ = consumer_backend
    _, factory, _, _ = oauth_mutation_client
    runtime = make_runtime(app)
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            accepted = data(await call(client, "wp_update_entity", edit_arguments(kind), access["access_token"]))
            worker, stored = await claim(factory, monkeypatch)
            model = Page if kind == "page" else WorkspaceComponent
            async with factory() as session:
                await session.execute(update(model).where(model.id == 1).values(current_version_no=2))
                await session.commit()
            with pytest.raises(AppException) as caught:
                await worker._finalize_success(stored.id, stored.lease_generation, prepared())
            await worker._handle_job_failure(stored.id, stored.lease_generation, caught.value)
            locator = {"workspace_id": 1, "job_id": accepted["job_id"]}
            response = (await call(client, "wp_get_mutation_job", locator, access["access_token"])).json()["result"]
            assert not response["isError"] and response["structuredContent"]["data"]["status"] == "failed"
            assert response["structuredContent"]["meta"]["reload"]["arguments"]["view"] == ("source" if kind == "page" else "draft")
            retry = await call(client, "wp_retry_mutation_job", {**locator, "idempotency_key": "retry-conflict"}, access["access_token"])
            assert retry.json()["result"]["structuredContent"]["error"]["code"] == "MUTATION_JOB_NOT_RETRYABLE"
            async with factory() as session:
                original = await session.get(ApiMutationJob, stored.id)
                assert original.base_version_no == (1 if kind == "page" else 0)
                assert await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1


async def test_mcp_retry_new_job_preserves_original_payload(consumer_backend, oauth_mutation_client):
    """预置失败状态仅覆盖 retry 协议，实际重试路由与幂等事务保留原 payload/hash/版本。"""
    _, app, access, _ = consumer_backend
    _, factory, _, _ = oauth_mutation_client
    runtime = make_runtime(app)
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            original = data(await call(client, "wp_update_entity", edit_arguments("component"), access["access_token"]))
            async with factory() as session:
                stored = await session.scalar(select(ApiMutationJob).where(ApiMutationJob.job_id == original["job_id"]))
                stored.status, stored.finished_at = "failed", utc_now()
                stored.error_json = {"code": "RUNTIME_UNAVAILABLE", "message": "测试失败状态", "retryable": True}
                original_payload, baseline, source_hash = dict(stored.payload_json), stored.base_version_no, stored.source_hash
                await session.commit()
            args = {"workspace_id": 1, "job_id": original["job_id"], "idempotency_key": "retry-original"}
            retried = data(await call(client, "wp_retry_mutation_job", args, access["access_token"]))
            same = data(await call(client, "wp_retry_mutation_job", args, access["access_token"]))
            assert retried["job_id"] == same["job_id"] != original["job_id"] and retried["retry_of_job_id"] == original["job_id"]
            async with factory() as session:
                stored = await session.scalar(select(ApiMutationJob).where(ApiMutationJob.job_id == retried["job_id"]))
                assert stored.payload_json == original_payload and stored.base_version_no == baseline and stored.source_hash == source_hash
