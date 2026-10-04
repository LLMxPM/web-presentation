"""文件功能：独立 MCP wheel 经真实 TLS Nginx 联测主仓 OAuth/Job 与 SDK 两种协议。"""

from pathlib import Path

import httpx
import pytest

from tests.fixtures.mcp_gateway import nginx_gateway
from tests.fixtures.oauth import POLICY
from tests.fixtures.oauth_mutations import SOURCE
from tests.integration.test_mcp_consumer import (
    consumer_backend as consumer_backend,
)
from tests.integration.test_mcp_consumer import (
    loopback_server,
    make_runtime,
)


@pytest.mark.parametrize("negotiation", ["discover", "initialize"])
async def test_real_tls_gateway_oauth_job_and_health(consumer_backend, negotiation):
    """真实 TLS 验证、认证挑战/来源、Job 短等待/取消，不把代理直连当网关成功。"""
    from httpx2 import AsyncClient
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    _, app, access, _ = consumer_backend
    async with loopback_server(app, lifespan="off") as backend_port:
        runtime = make_runtime(None, backend=f"http://127.0.0.1:{backend_port}")
        async with loopback_server(runtime.app, lifespan="on", shutdown_seconds=35) as mcp_port:
            async with nginx_gateway(mcp_port) as (endpoint, context, directory):
                async with httpx.AsyncClient(base_url=endpoint, verify=context, trust_env=False,
                                             headers={"Host": "mcp.example.test"}) as probe:
                    assert (await probe.get("/health/ready")).status_code == 200
                    challenge = await probe.post("/mcp", json={})
                    assert challenge.status_code == 401 and "oauth-protected-resource/mcp" in challenge.headers["WWW-Authenticate"]
                    assert challenge.headers["X-Request-ID"]
                    metadata = (await probe.get("/.well-known/oauth-protected-resource/mcp")).json()
                    assert metadata["resource"] == POLICY.mcp_resource
                    assert (await probe.post("/mcp", headers={"Origin": "https://other.test"}, json={})).status_code == 403
                    assert (await probe.get("/other")).status_code == 404
                    stream = await probe.get("/mcp", headers={"Accept": "text/event-stream",
                        "MCP-Protocol-Version": "2026-07-28", "Authorization": "Bearer " + access["access_token"]})
                    assert stream.status_code == 405  # 当前 SDK stateless + JSON 不启用独立 SSE。
                headers = {"Host": "mcp.example.test", "Authorization": "Bearer " + access["access_token"]}
                async with AsyncClient(headers=headers, verify=context, trust_env=False, timeout=45) as transport:
                    async with streamable_http_client(endpoint + "/mcp", http_client=transport) as (read, write):
                        async with ClientSession(read, write) as session:
                            await (session.discover() if negotiation == "discover" else session.initialize())
                            tools = await session.list_tools()
                            assert len(tools.tools) == 15
                            created = await session.call_tool("wp_create_entity", {"workspace_id": 1, "resource_type": "page", "mode": "new",
                                "idempotency_key": "gateway-create", "payload": {"project_id": 1, "name": "网关联测", "source_code": SOURCE}})
                            assert not created.is_error, created
                            job = created.structured_content["data"]
                            assert job["status"] == "pending"
                            # 2026 场景实际用满最大 20 秒短等待；旧协议用短预算覆盖兼容路径。
                            waited = await session.call_tool("wp_get_mutation_job", {"workspace_id": 1, "job_id": job["job_id"],
                                                                                   "wait_seconds": 20 if negotiation == "discover" else .2})
                            assert not waited.is_error and waited.structured_content["meta"]["wait_exhausted"]
                            assert waited.structured_content["data"]["status"] == "pending"
                            canceled = await session.call_tool("wp_cancel_mutation_job", {"workspace_id": 1, "job_id": job["job_id"],
                                                                                         "idempotency_key": "gateway-cancel"})
                            assert not canceled.is_error and canceled.structured_content["data"]["status"] == "canceled"
                log = (Path(directory) / "logs" / "access.log").read_text(encoding="utf-8")
                assert "wp_oat_" not in log and "gateway-create" not in log and "Bearer" not in log
        assert runtime.api._http.is_closed and runtime.oauth._transport.http.is_closed
