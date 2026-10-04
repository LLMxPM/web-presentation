"""文件功能：经独立 MCP SDK/TCP 执行真实创作与 PNG，验证 Runtime/Renderer 而非合成截图。"""

import asyncio
import base64
import hashlib
import io
import json
from time import monotonic

import pytest

from tests.api.test_oauth_preview_expiry import media_client as media_client
from tests.fixtures.mcp_gateway import nginx_gateway
from tests.fixtures.mcp_render import real_render_backend as real_render_backend
from tests.integration.test_mcp_consumer import consumer_backend as consumer_backend
from tests.integration.test_mcp_consumer import loopback_server, make_runtime

PAGE_SOURCE = '<template><main style="width:1920px;height:1080px;position:relative;overflow:hidden;background:#f5f7fc;display:flex;align-items:center;justify-content:center;"><h1 style="font-size:72px;color:#183b65;">MCP 真实渲染</h1></main></template>'


async def invoke(session, name, arguments):
    """所有业务由真实 SDK tools/call，工具失败不能被当作空数据继续。"""
    result = await session.call_tool(name, arguments)
    assert not result.is_error, result.structured_content
    return result.structured_content["data"]


async def completed(session, job):
    """显式短等待到终态，失败保持完整诊断，不直接修改 Job 或伪造成功。"""
    async with asyncio.timeout(180):
        while True:
            current = await invoke(session, "wp_get_mutation_job", {"workspace_id": 1, "job_id": job["job_id"], "wait_seconds": 5})
            if current["status"] in {"succeeded", "failed", "canceled"}:
                assert current["status"] == "succeeded", json.dumps(current.get("error"), ensure_ascii=False)
                return current
            await asyncio.sleep(.1)


async def published_component(session):
    """真实创建、编辑并发布组件，复核草稿指纹和返回的版本化导入路径。"""
    content = '<script setup>const props = defineProps({height:{type:Number,default:96}})</script><template><section :style="{height:props.height+\'px\'}" style="font-size:48px;color:#183b65;">组件初稿</section></template>'
    created = await invoke(session, "wp_create_entity", {"workspace_id": 1, "resource_type": "component", "mode": "new",
        "idempotency_key": "render-component-create", "payload": {"workspace_id": 1, "import_name": "McpCard",
        "name": "MCP 真组件", "component_type": "content", "source_code": content,
        "preview_schema": {"props": {"height": {"type": "number", "default": 96}}}}})
    created = await completed(session, created)
    component_id = created["target_id"]
    locator = {"workspace_id": 1, "resource_type": "component", "target_id": component_id}
    draft = await invoke(session, "wp_get_entity", {**locator, "view": "draft"})
    assert draft["content"] == content
    edited = await invoke(session, "wp_update_entity", {**locator, "action": "content", "idempotency_key": "render-component-edit",
        "payload": {"component_id": component_id, "base_version_no": draft["current_version_no"], "base_draft_hash": draft["draft_hash"],
        "edits": [{"type": "replace_exact", "old_text": "组件初稿", "new_text": "MCP 组件发布成功"}]}})
    edited = await completed(session, edited)
    newest = await invoke(session, "wp_get_entity", {**locator, "view": "draft"})
    assert newest["draft_hash"] != draft["draft_hash"] and "MCP 组件发布成功" in newest["content"]
    published = await invoke(session, "wp_execute_action", {**locator, "action": "publish", "idempotency_key": "render-component-publish",
        "payload": {"release_name": "MCP 本地联测"}})
    assert published["current_version_no"] == 1 and not published["has_unpublished_changes"]
    assert published["import_path"] == f'@workspace-components/{published["code"]}/v/1'
    return published, {"component_id": component_id, "component_version": 1,
                       "component_create_job": created["job_id"], "component_edit_job": edited["job_id"]}


@pytest.mark.parametrize("negotiation", ["discover", "initialize"])
async def test_sdk_real_page_creation_edit_and_renderer_png(real_render_backend, negotiation):
    """真实规划器/租约/提交、Runtime 编译、Renderer Chromium 和图片/版本形成闭环。"""
    from httpx2 import AsyncClient
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from PIL import Image

    app, backend, access, directory, _ = real_render_backend
    runtime = make_runtime(None, backend=backend, hosts=("mcp.example.test",))
    evidence = {"schema": "mcp-render-evidence.v1", "backend": "source-working-tree", "transport": "tls-nginx",
                "protocol": "2026-07-28" if negotiation == "discover" else "2025-11-25"}
    async with loopback_server(runtime.app, lifespan="on", shutdown_seconds=35) as port:
        async with nginx_gateway(port) as (endpoint, tls, _), AsyncClient(
            headers={"Host": "mcp.example.test", "Authorization": "Bearer " + access["access_token"]},
            verify=tls, trust_env=False, timeout=45) as client:
            async with streamable_http_client(endpoint + "/mcp", http_client=client) as (read, write):
                async with ClientSession(read, write) as session:
                    if negotiation == "discover":
                        await session.discover()
                    else:
                        await session.initialize()
                    created = await invoke(session, "wp_create_entity", {"workspace_id": 1, "resource_type": "page", "mode": "new",
                        "idempotency_key": "render-create", "payload": {"project_id": 1, "name": "MCP 真实渲染", "source_code": PAGE_SOURCE}})
                    final = await completed(session, created)
                    page_id = final["target_id"]
                    source = await invoke(session, "wp_get_entity", {"workspace_id": 1, "resource_type": "page", "target_id": page_id, "view": "source"})
                    assert source["source_code"] == PAGE_SOURCE and source["version_no"] >= 1
                    edited = await invoke(session, "wp_update_entity", {"workspace_id": 1, "resource_type": "page", "target_id": page_id,
                        "action": "content", "idempotency_key": "render-edit", "payload": {"page_id": page_id,
                        "base_version_no": source["version_no"], "edits": [{"type": "replace_exact", "old_text": "MCP 真实渲染", "new_text": "MCP 编辑成功"}]}})
                    edited = await completed(session, edited)
                    newest = await invoke(session, "wp_get_entity", {"workspace_id": 1, "resource_type": "page", "target_id": page_id, "view": "source"})
                    assert "MCP 编辑成功" in newest["source_code"] and newest["version_no"] > source["version_no"]
                    component, component_evidence = await published_component(session)
                    # 使用发布响应给出的公共 import path，页面渲染必须加载真实不可变组件版本。
                    component_page = '<script setup>import McpCard from "' + component["import_path"] + '"</script>' + newest["source_code"].replace('</h1>', '</h1><McpCard/>')
                    referenced = await invoke(session, "wp_update_entity", {"workspace_id": 1, "resource_type": "page", "target_id": page_id,
                        "action": "content", "idempotency_key": "render-component-reference", "payload": {"page_id": page_id,
                        "base_version_no": newest["version_no"], "edits": [{"type": "rewrite_file", "content": component_page}]}})
                    referenced = await completed(session, referenced)
                    newest = await invoke(session, "wp_get_entity", {"workspace_id": 1, "resource_type": "page", "target_id": page_id, "view": "source"})
                    assert newest["source_code"] == component_page
                    timings = []
                    for kind in ("cold", "hot"):
                        start = monotonic()
                        image = await session.call_tool("wp_get_page_screenshot", {"workspace_id": 1, "target_id": page_id})
                        assert not image.is_error, image.structured_content
                        png = base64.b64decode(next(block.data for block in image.content if block.type == "image"), validate=True)
                        with Image.open(io.BytesIO(png)) as decoded:
                            decoded.load()
                            assert decoded.size == (1920, 1080)
                        assert image.structured_content["data"]["version_no"] == newest["version_no"]
                        timings.append({"kind": kind, "seconds": round(monotonic() - start, 3), "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest()})
                    (directory / "page.png").write_bytes(png)
                    evidence.update(page_id=page_id, page_version=newest["version_no"], create_job=final["job_id"], edit_job=edited["job_id"],
                                    component_reference_job=referenced["job_id"], screenshots=timings, **component_evidence)
    (directory / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
