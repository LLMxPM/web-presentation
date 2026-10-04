"""文件功能：主仓消费独立 MCP wheel，联测真实 OAuth/业务路由与 SDK TCP，使用专属隔离数据库。"""

import asyncio
import importlib.util
import os
import socket
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.ai.tool_specs import AGENT_COORDINATOR_AGENT_ID
from app.api.routes.external import projects, v1_router
from app.models.ai_agent_config import AiAgentCodeStandardUserConfig
from tests.fixtures.oauth import POLICY
from tests.fixtures.oauth_mutations import SOURCE, other_user_access, refresh_access

if importlib.util.find_spec("wp_mcp") is None:
    if os.getenv("WP_MCP_CONSUMER_REQUIRED") == "1":
        raise RuntimeError("MCP 消费者门禁必须用 --with 安装独立 MCP wheel")
    pytest.skip("独立 MCP wheel 未安装；显式消费者联测入口才计入跨仓证据", allow_module_level=True)

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2026-07-28"}


@pytest.fixture
async def consumer_backend(oauth_mutation_client):
    """扩充真实项目路由/用户规范；公开 OpenAPI 由当前生产 v1_router 生成，业务不替换。"""
    client, factory, access, _ = oauth_mutation_client
    app = client._transport.app
    app.include_router(projects.router, prefix="/api/v1/projects")
    schema_app = FastAPI()
    schema_app.include_router(v1_router, prefix="/api")
    app.openapi = schema_app.openapi
    second = await other_user_access(client, factory)
    async with factory() as session:
        session.add_all([AiAgentCodeStandardUserConfig(user_id=user, agent_id=AGENT_COORDINATOR_AGENT_ID,
            standard_type="page", content_override="用户" + str(user) + "专属规范") for user in (1, 2)])
        await session.commit()
    return client, app, access, second


def make_runtime(app, *, backend=POLICY.issuer, hosts=(), api_transport=None):
    """MCP 只通过 HTTP Transport 消费主仓，没有内部业务导入或身份绕过。"""
    from wp_mcp.remote import RemoteRuntime
    from wp_mcp.remote_settings import RemoteSettings
    settings = RemoteSettings(backend, POLICY.issuer, POLICY.mcp_resource, POLICY.api_audience,
                              "mcp-service", "service-secret", allowed_hosts=hosts)
    if app is None:
        return RemoteRuntime(settings)
    return RemoteRuntime(settings, oauth_transport=httpx.ASGITransport(app=app),
                         api_transport=api_transport or httpx.ASGITransport(app=app))


async def call(client, name, arguments, token):
    """真正 MCP 2026 工具调用，返回 HTTP 响应供认证状态与统一结果分别断言。"""
    return await client.post("/mcp", headers={**HEADERS, "Authorization": "Bearer " + token,
        "Mcp-Method": "tools/call", "Mcp-Name": name}, json={"jsonrpc": "2.0", "id": "consumer", "method": "tools/call",
        "params": {"name": name, "arguments": arguments, "_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}}})


def data(response):
    """成功必须是结构化包络；工具错误不能作为正常空列表通过。"""
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert not result["isError"], result
    assert result["structuredContent"]["ok"]
    return result["structuredContent"]["data"]


async def test_mcp_real_oauth_read_chain_two_users_refresh_and_revoke(consumer_backend):
    """真实自省/交换/成员/对象/用户规范；两用户交错、刷新轮换与主仓撤销后立即拒绝。"""
    backend, app, first, second = consumer_backend
    runtime = make_runtime(app)
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            identity = data(await call(client, "wp_get_context", {}, first["access_token"]))
            assert identity["user"]["id"] == 1 and [w["id"] for w in identity["workspaces"]] == [1]
            assert identity["token"] is None and identity["credential"]["type"] == "delegated"
            guide = data(await call(client, "wp_get_operation_guide", {"workspace_id": 1}, first["access_token"]))
            assert any(item["binding_id"] == "page.get.source" for item in guide["operations"])
            manuals = await asyncio.gather(*[call(client, "wp_get_code_standards", {"workspace_id": user, "resource_type": "page"},
                access["access_token"]) for user, access in ((1, first), (2, second))])
            assert [data(item)["markdown"] for item in manuals] == ["用户1专属规范", "用户2专属规范"]
            lists = await asyncio.gather(*[call(client, "wp_list_entities", {"workspace_id": user, "resource_type": "project"},
                access["access_token"]) for user, access in ((1, first), (2, second))])
            assert [[item["id"] for item in data(r)["items"]] for r in lists] == [[1], [2]]
            oversized = await call(client, "wp_list_entities", {"workspace_id": 1, "resource_type": "project",
                "filters": {"page_size": 101}}, first["access_token"])
            assert oversized.json()["result"]["structuredContent"]["error"]["code"] == "INVALID_ARGUMENTS"
            read = {"workspace_id": 1, "resource_type": "page", "view": "source", "target_id": 1}
            source = data(await call(client, "wp_get_entity", read, first["access_token"]))
            assert source["source_code"] == SOURCE and source["version_no"] == 1
            wrong_space = await call(client, "wp_get_entity", read, second["access_token"])
            assert wrong_space.json()["result"]["structuredContent"]["error"]["code"] == "WORKSPACE_FORBIDDEN"
            wrong_object = await call(client, "wp_get_entity", {**read, "workspace_id": 2}, second["access_token"])
            assert wrong_object.json()["result"]["isError"]
            rotated = await refresh_access(backend, first["refresh_token"])
            # 刷新轮换消费旧 refresh；旧 access 按平台策略仍在自身期限内有效，撤销 Grant 则全部失效。
            assert data(await call(client, "wp_get_context", {}, first["access_token"]))["user"]["id"] == 1
            assert data(await call(client, "wp_get_context", {}, rotated["access_token"]))["user"]["id"] == 1
            revoked = await backend.post("/api/v1/account/oauth/grants/grant-1/revoke")
            assert revoked.status_code == 200, revoked.text
            assert (await call(client, "wp_get_entity", read, rotated["access_token"])).status_code == 401
            assert (await call(client, "wp_get_context", {}, first["access_token"])).status_code == 401
            assert data(await call(client, "wp_get_context", {}, second["access_token"]))["user"]["id"] == 2
    assert runtime.api._http.is_closed


@asynccontextmanager
async def loopback_server(app, *, lifespan):
    """仅测试专属 loopback 随机端口；退出关闭服务与 socket，不启动或重启开发平台实例。"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan=lifespan, proxy_headers=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("测试 HTTP 服务没有启动")
                await asyncio.sleep(0.01)
        yield port
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            listener.close()


@pytest.mark.parametrize("negotiation", ["discover", "initialize"])
async def test_sdk_client_real_tcp_backend_and_mcp(consumer_backend, negotiation):
    """真实 SDK→TCP MCP→TCP Backend→隔离 ORM，覆盖现代发现、tools/list/call 和真实只读链路。"""
    from httpx2 import AsyncClient
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared.exceptions import MCPError
    _, app, access, _ = consumer_backend
    async with loopback_server(app, lifespan="off") as backend_port:
        runtime = make_runtime(None, backend=f"http://127.0.0.1:{backend_port}", hosts=("127.0.0.1",))
        # Host 固定允许值，不信任代理 Header；随机端口通过客户端显式 Host 对齐。
        async with loopback_server(runtime.app, lifespan="on") as mcp_port:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{mcp_port}", headers={"Host": "127.0.0.1"}, trust_env=False) as probe:
                metadata = await probe.get("/.well-known/oauth-protected-resource/mcp")
                assert metadata.status_code == 200, metadata.text
                assert (await probe.get("/.well-known/oauth-protected-resource/mcp", headers={"Host": "evil.test"})).status_code == 421
                assert (await probe.get("/.well-known/oauth-protected-resource/mcp", headers={"Origin": "https://evil.test"})).status_code == 403
            async with AsyncClient(headers={"Authorization": "Bearer " + access["access_token"], "Host": "127.0.0.1"}, trust_env=False) as http:
                async with streamable_http_client(f"http://127.0.0.1:{mcp_port}/mcp", http_client=http) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        try:
                            if negotiation == "discover":
                                discovery = await session.discover()
                                assert "2026-07-28" in discovery.supported_versions
                            else:
                                initialized = await session.initialize()
                                assert initialized.protocol_version == "2025-11-25"
                        except MCPError as error:
                            pytest.fail(f"SDK 协议协商失败：{error.code} {error.message} {error.data}")
                        tools = await session.list_tools()
                        assert {tool.name for tool in tools.tools} == {"wp_get_context", "wp_get_operation_guide", "wp_get_code_standards",
                            "wp_list_entities", "wp_get_entity", "wp_create_entity", "wp_update_entity", "wp_archive_entity",
                            "wp_validate_entity", "wp_execute_action", "wp_get_mutation_job", "wp_cancel_mutation_job", "wp_retry_mutation_job"}
                        result = await session.call_tool("wp_get_context", {})
                        assert not result.is_error and result.structured_content["data"]["user"]["id"] == 1
                        source = await session.call_tool("wp_get_entity", {"workspace_id": 1, "resource_type": "page", "view": "source", "target_id": 1})
                        assert not source.is_error and source.structured_content["data"]["source_code"] == SOURCE
                        created = await session.call_tool("wp_create_entity", {"workspace_id": 1, "resource_type": "page", "mode": "new",
                            "idempotency_key": "tcp-create", "payload": {"project_id": 1, "name": "TCP 创建", "source_code": SOURCE}})
                        assert not created.is_error and created.structured_content["data"]["status"] == "pending"
                        locator = {"workspace_id": 1, "job_id": created.structured_content["data"]["job_id"]}
                        status = await session.call_tool("wp_get_mutation_job", locator)
                        assert not status.is_error and status.structured_content["data"]["job_id"] == locator["job_id"]
                        canceled = await session.call_tool("wp_cancel_mutation_job", {**locator, "idempotency_key": "tcp-cancel"})
                        assert not canceled.is_error and canceled.structured_content["meta"]["canceled"]
