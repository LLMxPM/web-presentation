"""文件功能：联测独立 MCP 的真实预览 artifact/签名/期限与授权；PNG 测试只覆盖 API/SDK 适配。"""

import base64
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.models.page import Page
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService
from tests.api.test_oauth_preview_expiry import media_client as media_client
from tests.integration.test_mcp_consumer import (
    call,
    data,
    loopback_server,
    make_runtime,
)
from tests.integration.test_mcp_consumer import consumer_backend as consumer_backend
from tests.integration.test_mcp_write_consumer import limited_access


@pytest.mark.parametrize("kind", ["page", "project"])
async def test_mcp_preview_real_artifact_expiry_and_permission(consumer_backend, media_client, kind):
    """真实 PreviewService 构建与独立 memory artifact，验证原签名地址/期限，未启动 Runtime 浏览器。"""
    backend, app, access, other = consumer_backend
    _, factory, _, _, _, storage = media_client
    runtime = make_runtime(app)
    args = {"workspace_id": 1, "resource_type": kind, "target_id": 1}
    if kind == "project":
        args["payload"] = {}
    read_only = await limited_access(backend, factory, ["page:read", "project:read"])
    async with runtime.sdk_app.router.lifespan_context(runtime.sdk_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=runtime.app), base_url="https://mcp.example.test") as client:
            denied = await call(client, "wp_create_preview", args, read_only)
            assert denied.json()["result"]["structuredContent"]["error"]["code"] == "INSUFFICIENT_SCOPE"
            foreign = await call(client, "wp_create_preview", {**args, "workspace_id": 2}, other["access_token"])
            assert foreign.json()["result"]["isError"]
            result = data(await call(client, "wp_create_preview", args, access["access_token"]))
            expiry = datetime.fromisoformat(result["expires_at"])
            url = urlsplit(result["preview_url"])
            claims = TokenService.verify_preview_context_token(parse_qs(url.query)["token"][0])
            assert result["preview_kind"] == kind and result["workspace_id"] == result["project_id"] == 1
            assert url.path == "/preview/artifacts/" + result["artifact_id"]
            assert int(expiry.timestamp()) == claims["exp"] and claims["tenant_id"] == "tenant_1"
            assert expiry <= await RuntimeArtifactStore(storage).get_expires_at(result["artifact_id"])


@pytest.mark.parametrize("negotiation", ["discover", "initialize"])
async def test_mcp_png_real_sdk_tcp_and_auth_boundary(consumer_backend, media_client, monkeypatch, negotiation):
    """真实 SDK/TCP/OAuth/对象路由；仅截图队列结果用合成 PNG，不作为 Renderer 成功证据。"""
    from httpx2 import AsyncClient
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from PIL import Image

    from app.services.page_screenshot_job_service import PageScreenshotJobService

    _, app, access, other = consumer_backend
    _, _, _, _, _, _ = media_client
    buffer = BytesIO()
    with Image.new("RGB", (16, 16), "white") as image:
        image.save(buffer, format="PNG")
    content = buffer.getvalue()
    requested = []

    async def screenshot(self, *, page_id, user_id, workspace_id, project_id):
        """合成媒体仅用于版本 Header/ImageContent 适配，权限仍由真实路由在调用前检查。"""
        requested.append((page_id, user_id, workspace_id, project_id))
        return SimpleNamespace(page=await self.session.get(Page, page_id), content=content)

    monkeypatch.setattr(PageScreenshotJobService, "ensure_latest_page_screenshot_via_queue", screenshot)
    async with loopback_server(app, lifespan="off") as backend_port:
        runtime = make_runtime(None, backend=f"http://127.0.0.1:{backend_port}", hosts=("127.0.0.1",))
        async with loopback_server(runtime.app, lifespan="on") as port:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers={"Host": "127.0.0.1"}, trust_env=False) as probe:
                denied = await call(probe, "wp_get_page_screenshot", {"workspace_id": 2, "target_id": 1}, other["access_token"])
                assert denied.json()["result"]["isError"] and not requested
            async with AsyncClient(headers={"Authorization": "Bearer " + access["access_token"], "Host": "127.0.0.1"}, trust_env=False) as http:
                async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.discover() if negotiation == "discover" else await session.initialize()
                        result = await session.call_tool("wp_get_page_screenshot", {"workspace_id": 1, "target_id": 1})
                        assert not result.is_error and result.structured_content["data"]["page_id"] == 1
                        assert result.structured_content["data"]["version_no"] == 1
                        assert result.content[1].type == "image" and result.content[1].mime_type == "image/png"
                        assert base64.b64decode(result.content[1].data, validate=True) == content
                        assert requested == [(1, 1, 1, 1)]
