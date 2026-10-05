"""文件功能：主仓消费独立 MCP wheel，回归两空间写入边界与委托交换后的真实撤销竞态。"""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.api.routes.external import v1_router
from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page
from tests.integration.test_mcp_consumer import call, data, make_runtime


@pytest.fixture
async def review_backend(multi_workspace_client):
    """业务使用真实路由和双空间授权；契约从生产 v1_router 生成。"""
    backend, factory, access, _ = multi_workspace_client
    app = backend._transport.app
    schema = FastAPI()
    schema.include_router(v1_router, prefix="/api")
    app.openapi = schema.openapi
    return backend, factory, app, access


async def test_mcp_selected_workspace_rejects_foreign_object_and_job(review_backend):
    """MCP 包络选择空间一时不能读写空间二；失败不修改标题或入队，正确空间可操作。"""
    _, factory, app, access = review_backend
    runtime = make_runtime(app)
    async with (
        runtime.sdk_app.router.lifespan_context(runtime.sdk_app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client,
    ):
        read = {"workspace_id": 1, "resource_type": "page", "target_id": 2, "view": "source"}
        write = {"workspace_id": 1, "resource_type": "page", "target_id": 2, "action": "metadata",
                 "idempotency_key": "original-key", "payload": {"title": "不得跨空间修改"}}
        for name, args in (("wp_get_entity", read), ("wp_update_entity", write)):
            result = (await call(client, name, args, access["access_token"])).json()["result"]
            assert result["isError"] and result["structuredContent"]["error"]["code"] == "WORKSPACE_CONTEXT_MISMATCH"
            assert result["structuredContent"]["workspace_id"] == 1
        async with factory() as session:
            assert (await session.get(Page, 2)).title == "空间二页面"
            assert await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 0
        assert data(await call(client, "wp_update_entity", {**write, "workspace_id": 2}, access["access_token"]))["title"] == write["payload"]["title"]
        job = data(await call(client, "wp_create_entity", {"workspace_id": 2, "resource_type": "page", "mode": "new",
            "idempotency_key": "create", "payload": {"project_id": 2, "name": "测试任务", "source_code": "<template><div>测试</div></template>"}}, access["access_token"]))
        for name in ("wp_get_mutation_job", "wp_cancel_mutation_job", "wp_retry_mutation_job"):
            args = {"workspace_id": 1, "job_id": job["job_id"]}
            if name != "wp_get_mutation_job":
                args["idempotency_key"] = "wrong-job"
            result = (await call(client, name, args, access["access_token"])).json()["result"]
            assert result["isError"] and result["structuredContent"]["error"]["code"] == "WORKSPACE_CONTEXT_MISMATCH"
        async with factory() as session:
            jobs = (await session.scalars(select(ApiMutationJob))).all()
            assert len(jobs) == 1 and jobs[0].status == "pending" and jobs[0].cancel_requested_at is None


@pytest.mark.parametrize("write", [False, True])
async def test_real_grant_revocation_after_exchange_returns_challenge(review_backend, write):
    """自省、委托及能力查询完成后真实撤销 Grant；业务 401 仍生成标准重新授权结果。"""
    backend, factory, app, access = review_backend
    path = "/api/v1/pages/1" + ("" if write else "/source")
    requests = []

    class RevokeBeforeBusiness(httpx.AsyncBaseTransport):
        """仅改变真实撤销时序，不替换 Backend 的认证或业务响应。"""

        async def handle_async_request(self, request):
            """收到目标请求时先经账户 HTTP 撤销，再进入生产 External API。"""
            if request.url.path == path:
                requests.append(request)
                revoked = await backend.post("/api/v1/account/oauth/grants/grant-1/revoke")
                assert revoked.status_code == 200, revoked.text
            return await httpx.ASGITransport(app=app).handle_async_request(request)

    runtime = make_runtime(app, api_transport=RevokeBeforeBusiness())
    name = "wp_update_entity" if write else "wp_get_entity"
    arguments = {"workspace_id": 1, "resource_type": "page", "target_id": 1}
    arguments.update({"action": "metadata", "idempotency_key": "original-key", "payload": {"title": "不得写入"}} if write else {"view": "source"})
    async with (
        runtime.sdk_app.router.lifespan_context(runtime.sdk_app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client,
    ):
        result = (await call(client, name, arguments, access["access_token"])).json()["result"]
    envelope = result["structuredContent"]
    assert result["isError"] and envelope["error"]["code"] == "AUTHORIZATION_REQUIRED"
    assert len(requests) == 1
    assert result["_meta"]["mcp/www_authenticate"] == [
        'Bearer resource_metadata="https://mcp.example.test/.well-known/oauth-protected-resource/mcp", error="invalid_token"']
    if write:
        assert envelope["meta"]["idempotency_key"] == "original-key"
        assert envelope["meta"]["replay"]["reuse_original_payload"]
        assert "payload" not in envelope["meta"]["replay"]["arguments"]
        assert requests[0].headers["Idempotency-Key"] == "original-key"
    async with factory() as session:
        assert (await session.get(Page, 1)).title == "测试页面"


async def test_real_backend_accepts_published_key_boundary(review_backend):
    """独立 wheel 的 129 字符请求在本地失败，128 字符原键可完成真实 Backend 更新。"""
    _, factory, app, access = review_backend
    runtime = make_runtime(app)
    arguments = {"workspace_id": 1, "resource_type": "page", "target_id": 1, "action": "metadata", "payload": {"title": "边界更新"}}
    async with (
        runtime.sdk_app.router.lifespan_context(runtime.sdk_app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client,
    ):
        invalid = (await call(client, "wp_update_entity", {**arguments, "idempotency_key": "k" * 129}, access["access_token"])).json()["result"]
        assert invalid["isError"] and invalid["structuredContent"]["error"]["code"] == "INVALID_ARGUMENTS"
        async with factory() as session:
            assert (await session.get(Page, 1)).title == "测试页面"
        updated = data(await call(client, "wp_update_entity", {**arguments, "idempotency_key": "k" * 128}, access["access_token"]))
        assert updated["title"] == "边界更新"
