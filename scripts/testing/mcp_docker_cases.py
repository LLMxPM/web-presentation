"""文件功能：通过真实 SDK/TLS 消费容器 MCP，验证授权隔离、创作 PNG 与跨 Backend 恢复。"""

import asyncio
import base64
import hashlib
import io
from contextlib import asynccontextmanager
from time import monotonic

import httpx
from httpx2 import AsyncClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image

SOURCE = '<template><main style="width:1920px;height:1080px;background:#f5f7fc;display:flex;align-items:center;justify-content:center"><h1 style="font-size:72px;color:#183b65">MCP 容器创作</h1></main></template>'


@asynccontextmanager
async def sdk(endpoint, access, tls, *, negotiation="discover"):
    """显式传入逐用户 Bearer、Host 和私有 CA，不读取环境 PAT 或代理。"""
    async with AsyncClient(headers={"Host": "mcp.example.test", "Authorization": "Bearer " + access},
                           verify=tls, trust_env=False, timeout=45) as client:
        async with streamable_http_client(endpoint + "/mcp", http_client=client) as (read, write):
            async with ClientSession(read, write) as session:
                if negotiation == "discover":
                    await session.discover()
                else:
                    await session.initialize()
                assert len((await session.list_tools()).tools) == 15
                yield session


async def invoke(session, name, arguments):
    """工具失败保持非零，不把空数据或合成占位结果计为成功。"""
    result = await session.call_tool(name, arguments)
    assert not result.is_error, result.structured_content
    return result.structured_content["data"]


async def completed(session, workspace, job):
    """重复显式短等待，不透明重试写入；真实 Job 终态必须成功。"""
    async with asyncio.timeout(180):
        while True:
            current = await invoke(session, "wp_get_mutation_job", {"workspace_id": workspace,
                "job_id": job["job_id"], "wait_seconds": 5})
            if current["status"] in {"succeeded", "failed", "canceled"}:
                assert current["status"] == "succeeded", current.get("error")
                return current
            await asyncio.sleep(.2)


async def access_tokens(drill, credentials):
    """两个 HTTP Backend 并发兑换同码只允许一个成功；第二用户独立兑换。"""
    async with httpx.AsyncClient(trust_env=False, headers={"Host": "platform.example.test"}, timeout=15) as client:
        def payload(item):
            """授权码原值只留在内存与专属私有文件，不出现在报告。"""
            return {"grant_type": "authorization_code", "client_id": item["client_id"], "code": item["code"],
                "redirect_uri": item["redirect_uri"], "code_verifier": item["verifier"], "resource": "https://mcp.example.test/mcp"}
        raced = await asyncio.gather(*[client.post(drill.url(service, 8000) + "/oauth/token", data=payload(credentials[0]))
                                      for service in ("backend_a", "backend_b")])
        assert sorted(response.status_code for response in raced) == [200, 400]
        first = next(response.json() for response in raced if response.status_code == 200)
        other = await client.post(drill.url("backend_b", 8000) + "/oauth/token", data=payload(credentials[1]))
        assert other.status_code == 200
        return first, other.json()


async def creation(drill, endpoint, tls, credentials, tokens):
    """真实双 Backend/PG/Redis/Runtime/Renderer：身份隔离、创建编辑、重启恢复及 PNG。"""
    first, second = credentials
    workspace = first["workspace_id"]
    async with sdk(endpoint, tokens[0]["access_token"], tls) as one, sdk(
        endpoint, tokens[1]["access_token"], tls, negotiation="initialize") as two:
        identities = await asyncio.gather(invoke(one, "wp_get_context", {}), invoke(two, "wp_get_context", {}))
        assert [identity["user"]["id"] for identity in identities] == [first["user_id"], second["user_id"]]
        assert [[w["id"] for w in identity["workspaces"]] for identity in identities] == [[workspace], [second["workspace_id"]]]
        # 暂停真实 Runtime，使 Job 稳定处于非终态；不替换规划器、队列或最终提交。
        drill.compose("pause", "runtime")
        try:
            created = await invoke(one, "wp_create_entity", {"workspace_id": workspace, "resource_type": "page", "mode": "new",
                "idempotency_key": "docker-page-create", "payload": {"project_id": first["project_id"], "name": "容器页面", "source_code": SOURCE}})
            replay = await invoke(one, "wp_create_entity", {"workspace_id": workspace, "resource_type": "page", "mode": "new",
                "idempotency_key": "docker-page-create", "payload": {"project_id": first["project_id"], "name": "容器页面", "source_code": SOURCE}})
            assert replay["job_id"] == created["job_id"]
            pending = await invoke(one, "wp_get_mutation_job", {"workspace_id": workspace, "job_id": created["job_id"]})
            assert pending["status"] in {"pending", "running"}
            drill.compose("restart", "mcp")
            drill.wait("gateway", 443, "/health/ready", tls=tls)
        finally:
            drill.compose("unpause", "runtime")
        final = await completed(one, workspace, created)
        locator = {"workspace_id": workspace, "resource_type": "page", "target_id": final["target_id"]}
        source = await invoke(one, "wp_get_entity", {**locator, "view": "source"})
        assert source["source_code"] == SOURCE and source["version_no"] == 1
        forbidden = await two.call_tool("wp_get_entity", {**locator, "view": "source"})
        assert forbidden.is_error and forbidden.structured_content["error"]["code"] == "WORKSPACE_FORBIDDEN"
        edited = await invoke(one, "wp_update_entity", {**locator, "action": "content", "idempotency_key": "docker-page-edit",
            "payload": {"page_id": final["target_id"], "base_version_no": 1,
                        "edits": [{"type": "replace_exact", "old_text": "MCP 容器创作", "new_text": "MCP 容器编辑成功"}]}})
        edited = await completed(one, workspace, edited)
        # 重启 MCP 与 A，B/PG/Redis 保留业务结果；新 MCP 必须按原 Job ID 继续查询。
    drill.compose("restart", "mcp", "backend_a")
    drill.wait("backend_a", 8000, "/healthz")
    drill.wait("gateway", 443, "/health/ready", tls=tls)
    async with sdk(endpoint, tokens[0]["access_token"], tls) as session:
        recovered = await invoke(session, "wp_get_mutation_job", {"workspace_id": workspace, "job_id": edited["job_id"]})
        assert recovered["status"] == "succeeded" and recovered["target_id"] == final["target_id"]
        newest = await invoke(session, "wp_get_entity", {**locator, "view": "source"})
        assert newest["version_no"] == 2 and "MCP 容器编辑成功" in newest["source_code"]
        timings = []
        for kind in ("cold", "hot"):
            started = monotonic()
            image = await session.call_tool("wp_get_page_screenshot", {"workspace_id": workspace, "target_id": final["target_id"]})
            assert not image.is_error, image.structured_content
            png = base64.b64decode(next(block.data for block in image.content if block.type == "image"), validate=True)
            with Image.open(io.BytesIO(png)) as decoded:
                decoded.load()
                assert decoded.size == (1920, 1080)
            assert image.structured_content["data"]["version_no"] == 2
            timings.append({"kind": kind, "seconds": round(monotonic()-started, 3), "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest()})
        assert timings[0]["sha256"] == timings[1]["sha256"]
        (drill.output / "page.png").write_bytes(png)
        return {"create_job": created["job_id"], "edit_job": edited["job_id"], "page_id": final["target_id"], "page_version": 2,
                "two_users_isolated": True, "idempotent_replay": True, "restart_job_recovery": True,
                "accepted_job_survived_mcp_restart": True, "job_before_mcp_restart": pending["status"], "screenshots": timings}


async def revoked(drill, endpoint, tls, credentials, tokens):
    """两 HTTP Backend 的 refresh 重放整链撤销；另一用户仍有效，最后公开撤销其 Grant。"""
    headers = {"Host": "platform.example.test"}
    async with httpx.AsyncClient(trust_env=False, headers=headers, timeout=15) as client:
        body = {"grant_type": "refresh_token", "client_id": credentials[0]["client_id"], "refresh_token": tokens[0]["refresh_token"],
                "resource": "https://mcp.example.test/mcp"}
        raced = await asyncio.gather(*[client.post(drill.url(service, 8000) + "/oauth/token", data=body) for service in ("backend_a", "backend_b")])
        assert sorted(response.status_code for response in raced) == [200, 400]
        winner = next(response.json() for response in raced if response.status_code == 200)
        retry = await client.post(drill.url("backend_b", 8000) + "/oauth/token", data={**body, "refresh_token": winner["refresh_token"]})
        assert retry.status_code == 400 and retry.json()["error"] == "invalid_grant"
    async with sdk(endpoint, tokens[1]["access_token"], tls) as session:
        assert (await invoke(session, "wp_get_context", {}))["user"]["id"] == credentials[1]["user_id"]
    async with httpx.AsyncClient(verify=tls, trust_env=False, timeout=15) as client:
        for access in (tokens[0]["access_token"], winner["access_token"]):
            response = await client.post(endpoint + "/mcp", headers={"Host": "mcp.example.test", "Authorization": "Bearer " + access}, json={})
            assert response.status_code == 401
        response = await client.post(drill.url("platform_tls", 443) + "/oauth/revoke", headers=headers,
            data={"client_id": credentials[1]["client_id"], "token": tokens[1]["access_token"]})
        assert response.status_code == 200
        response = await client.post(endpoint + "/mcp", headers={"Host": "mcp.example.test", "Authorization": "Bearer " + tokens[1]["access_token"]}, json={})
        assert response.status_code == 401
    return {"code_single_consumer": True, "refresh_replay_chain_revoked": True, "other_grant_isolated": True, "public_revoke_observed": True}
