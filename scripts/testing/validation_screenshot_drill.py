"""文件功能：在独立 E2E 库中验收真实 CLI/AI 页面写入附图，记录物理 attempt 和 PNG 证据。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import time
import uuid
import zlib
from pathlib import Path

import httpx
from app.ai.external_task_control import seal_external_batch_for_requirement
from app.ai.page_mutation_enqueue import enqueue_page_mutation
from app.api.business_origin import trusted_business_origins
from app.core.config import get_settings
from app.core.testing_environment import require_e2e_database
from app.db.session import get_session_factory, reset_database_state
from app.models.ai_agent_runtime import (
    AiAgentRequirement,
    AiAgentRun,
    AiAgentSession,
    AiAgentToolCall,
)
from app.models.ai_page_mutation import AiPageMutationJob
from app.models.render_attempt import RenderAttempt
from app.models.render_execution import RenderResult
from app.models.render_request import RenderRequest
from app.services.rendering.client import RendererClient
from app.services.rendering.target_resolver import RenderTargetResolver
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "test-results/validation-screenshots"


async def json_request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
    """通过真实 HTTP API 操作测试对象，错误不输出凭证。"""
    response = await client.request(method, path, **kwargs)
    assert response.is_success, f"{path}: {response.status_code}: {response.text[:1500]}"
    return response.json()


def page_source(label: str) -> str:
    """包含当前标题、页码和真实模块路由，捕获编码漂移会直接改变可见内容。"""
    return f'''<!-- 文件功能：真实渲染验收的固定画布与页面上下文。 -->
<script setup lang="ts">
import {{ useCurrentPage }} from '@runtime-kit/public/composables/page/useCurrentPage.v1'
const {{ title, route, currentPage, totalPages }} = useCurrentPage()
</script>
<template><main class="h-full w-full bg-white p-16 text-slate-900">
<h1 class="text-5xl">{label}</h1><p class="mt-8 text-3xl">{{{{ title }}}}</p>
<p class="mt-8 text-2xl">{{{{ route.path }}}}</p><p>{{{{ currentPage }}}} / {{{{ totalPages }}}}</p>
</main></template>'''


def verify_png(content: bytes) -> tuple[int, int]:
    """核对 PNG chunk CRC 并解压像素，拒绝仅有图片头的伪产物。"""
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", content[16:24])
    offset, data, color = 8, bytearray(), content[25]
    while offset < len(content):
        length = struct.unpack(">I", content[offset:offset + 4])[0]
        kind = content[offset + 4:offset + 8]
        payload = content[offset + 8:offset + 8 + length]
        expected = struct.unpack(">I", content[offset + 8 + length:offset + 12 + length])[0]
        assert zlib.crc32(kind + payload) & 0xFFFFFFFF == expected
        if kind == b"IDAT":
            data.extend(payload)
        offset += length + 12
    channels = {2: 3, 6: 4}[color]
    assert len(zlib.decompress(data)) == height * (width * channels + 1)
    return width, height


async def render_metrics(project_id: int) -> dict:
    """读取专属项目的物理执行证据，不修改任何 Renderer 状态。"""
    async with get_session_factory()() as session:
        requests = list(await session.scalars(select(RenderRequest).where(RenderRequest.project_id == project_id)))
        ids = [row.id for row in requests]
        attempts = list(await session.scalars(select(RenderAttempt).where(RenderAttempt.request_id.in_(ids)))) if ids else []
        results = list(await session.scalars(select(RenderResult).where(RenderResult.request_id.in_(ids)))) if ids else []
        metrics = {"attempts": len(attempts), "successful_attempts": len(results), "request_ids": ids,
                "attempt_details": [{"attempt": row.attempt_uid, "error": row.error_code or row.dispatch_error_code} for row in attempts],
                "launches": sum(int(row.environment_summary.get("browser_launch_count", 0)) for row in results),
                "navigations": sum(int(row.environment_summary.get("navigation_count", 0)) for row in results),
                "png_bytes": sum(sum(int(ref.get("byte_length", 0)) for ref in (row.object_refs or {}).values()) for row in results),
                "diagnose_ms": sum(float(row.environment_summary.get("diagnose_ms", 0)) for row in results),
                "screenshot_ms": sum(float(row.environment_summary.get("screenshot_ms", 0)) for row in results)}
    capabilities = await RendererClient().fetch_capabilities(RenderTargetResolver().worker_endpoints()[0])
    metrics["physical_launches"] = capabilities.environment_summary["browser_launches_total"]
    metrics["physical_navigations"] = capabilities.environment_summary["navigations_total"]
    return metrics


async def cli_call(token: str, workspace_id: int, *args: str) -> dict:
    """调用相邻仓的真实 CLI 命令树与 HTTP Client，只用内存 Profile 注入测试凭证。"""
    executable = ROOT.parent / "web-presentation-cli/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert executable.exists(), "需要明确的相邻 CLI 版本，缺仓不能记为通过"
    profile = {"current_profile": "drill", "profiles": {"drill": {"endpoint": get_settings().backend_public_base_url,
                "token": token, "default_workspace_id": workspace_id}}}
    env = {**os.environ, "WP_DRILL_PROFILE": json.dumps(profile)}
    process = await asyncio.create_subprocess_exec(str(executable), str(ROOT / "scripts/testing/validation_screenshot_cli.py"),
                "--json", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, (stdout.decode(errors="replace") + stderr.decode(errors="replace"))[-2500:]
    return json.loads(stdout)


async def ai_write(*, user_id: int, workspace_id: int, project_id: int, content: str, page_id: int | None = None) -> dict:
    """经过真实持久队列与 Backend Worker 执行，不替换 CodeCheck 或 Renderer。"""
    identity = f"validation-drill-{uuid.uuid4().hex}"
    create = page_id is None
    payload = {"project_id": project_id, "title": "AI 正式标题", "content": content, "route_placement": "root"} if create else {
        "base_version_no": 1, "edits": [{"type": "rewrite_file", "content": content}]}
    arguments = {"resource_type": "page", "payload": payload, **({"mode": "new"} if create else {"target_id": page_id, "action": "content"})}
    async with get_session_factory()() as session:
        session.add(AiAgentSession(session_id=identity, agent_id="agent-coordinator", user_id=user_id, workspace_id=workspace_id))
        await session.flush()
        session.add(AiAgentRun(run_id=identity, session_id=identity, agent_id="agent-coordinator", user_id=user_id,
            status="running", scope_type="project", workspace_id=workspace_id, project_id=project_id, source="e2e-drill"))
        await session.flush()
        session.add(AiAgentToolCall(run_id=identity, session_id=identity, tool_call_id=identity,
                tool_name="create_entity" if create else "update_entity", status="running", input_payload_json=arguments))
        await session.commit()
    queued = await enqueue_page_mutation(get_session_factory(), run_id=identity, session_id=identity, run_step=0,
                tool_call_id=identity, operation="create_page" if create else "apply_page_edits", workspace_id=workspace_id,
                project_id=project_id, page_id=page_id, base_version_no=None if create else 1)
    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, identity)
        requirement = AiAgentRequirement(requirement_id=identity, run_id=identity, session_id=identity,
                    kind="external_job", status="pending", payload_json={"id": identity, "kind": "external_job"})
        session.add(requirement)
        await session.flush()
        await seal_external_batch_for_requirement(session, run=run, requirement=requirement)
        run.status, run.pending_requirement_json = "waiting_external", {"id": identity, "kind": "external_job"}
        await session.commit()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        async with get_session_factory()() as session:
            job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == queued.job_id))
            if job.status == "succeeded":
                result = job.result_json
                assert result.get("success") is not False, result
                return result.get("data") or result
            assert job.status not in {"failed", "cancelled"}, (job.error_code, job.error_message)
        await asyncio.sleep(0.5)
    raise AssertionError("AI 页面队列超时")


async def main() -> None:
    """四条写入路径随后取图不得增加 attempt，产物与当前版本/配置必须吻合。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--actor", choices=("cli", "ai", "all"), default="all")
    parser.add_argument("--benchmark-only", action="store_true")
    options = parser.parse_args()
    require_e2e_database()
    OUT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    report = {"paths": [], "output_dir": str(OUT)}
    if (options.benchmark_only or options.actor != "all") and (OUT / "report.json").exists():
        report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    async with httpx.AsyncClient(base_url=settings.backend_public_base_url, timeout=180,
                                 headers={"Origin": min(trusted_business_origins())}) as client:
        readiness = await json_request(client, "GET", "/api/testing/e2e-readiness")
        assert readiness["database_profile"] == "e2e" and readiness["test_mode"] == "mock"
        login = await json_request(client, "POST", "/api/auth/login", json={"username": settings.default_admin_username, "password": settings.default_admin_password})
        user_id = login["user"]["id"]
        workspace = await json_request(client, "POST", "/api/workspaces", json={"name": f"截图复用验收 {uuid.uuid4().hex[:8]}"})
        ws = workspace["id"]
        project = await json_request(client, "POST", "/api/projects", json={"workspace_id": ws, "name": "截图复用四路径"})
        project_id = project["id"]
        pat = await json_request(client, "POST", "/api/access-tokens", json={"name": "截图验收临时令牌", "workspace_ids": [ws],
                                "scopes": ["page:read", "page:write", "preview:run", "project:read", "asset:read", "workspace:read"], "expires_in_days": 1})
        token = pat["token"]
        try:
            for actor in ("cli", "ai"):
                if options.benchmark_only:
                    continue
                if options.actor != "all" and actor != options.actor:
                    continue
                page_id = None
                for operation in ("create", "edit"):
                    label = f"{actor}-{operation}"
                    content = page_source(label)
                    source = OUT / f"{label}.vue"
                    source.write_text(content, encoding="utf-8")
                    before = await render_metrics(project_id)
                    started = time.perf_counter()
                    if actor == "cli":
                        if operation == "create":
                            job = await cli_call(token, ws, "page", "create", "--project-id", str(project_id), "--name", "CLI 正式标题", "--file", str(source))
                        else:
                            edits = OUT / "edits.json"
                            edits.write_text(json.dumps([{"type": "rewrite_file", "content": content}]), encoding="utf-8")
                            job = await cli_call(token, ws, "page", "edit", str(page_id), "--base-version-no", "1", "--edits-file", str(edits), "--timeout", "180")
                        result = job["result"]
                    else:
                        result = await ai_write(user_id=user_id, workspace_id=ws, project_id=project_id, content=content, page_id=page_id)
                    page_id = result["page_id"]
                    shot = result["screenshot"]
                    assert shot["status"] == "ready", {"path": label, "result": result}
                    after_write = await render_metrics(project_id)
                    filename = OUT / f"{label}.png"
                    await cli_call(token, ws, "page", "screenshot", str(page_id), "--screenshot-id", shot["screenshot_id"], "--output", str(filename))
                    size = verify_png(filename.read_bytes())
                    assert size == (shot["width"], shot["height"])
                    response = await client.get(f"/api/v1/pages/{page_id}/screenshot", headers={"Authorization": f"Bearer {token}"})
                    assert response.is_success, response.text[:300] if not response.is_success else ""
                    assert response.content == filename.read_bytes()
                    after_read = await render_metrics(project_id)
                    delta = {key: after_read[key] - before[key] for key in ("attempts", "successful_attempts", "launches", "navigations", "physical_launches", "physical_navigations", "png_bytes", "screenshot_ms", "diagnose_ms")}
                    assert delta["successful_attempts"] == delta["launches"] == delta["navigations"] == 1, {**delta, "details": after_read["attempt_details"]}
                    assert delta["physical_launches"] == delta["physical_navigations"] == 1, delta
                    assert after_write["attempts"] == after_read["attempts"], "下载或视觉读取触发了重复渲染"
                    report["paths"] = [row for row in report["paths"] if row["path"] != label]
                    report["paths"].append({"path": label, "page_id": page_id, "screenshot": shot, "duration_ms": round((time.perf_counter()-started)*1000,2), **delta})
                    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(report["paths"][-1], ensure_ascii=False), flush=True)
            if not options.quick:
                from validation_screenshot_benchmark import run_benchmark
                await run_benchmark(client, ws=ws, project_id=project_id, user_id=user_id, token=token, root=ROOT, out=OUT,
                                    report=report, request_json=json_request, metrics=render_metrics, verify_png=verify_png,
                                    cli_call=cli_call, context_source=page_source("上下文对拍"))
            report["renderer_ready"] = (await client.get("http://127.0.0.1:7400/readyz")).json()
            (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            await client.post(f"/api/access-tokens/{pat['id']}/revoke")
    await reset_database_state()


if __name__ == "__main__":
    asyncio.run(main())
