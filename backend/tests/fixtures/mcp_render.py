"""文件功能：为 MCP 创作联测启动专属 Runtime/Renderer 和真实队列，所有数据使用隔离夹具。"""

import asyncio
import os
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.api.routes import internal_runtime, preview, well_known
from app.core.config import AppSettings
from app.services import (
    mutation_job_service,
    page_screenshot_queue_worker,
    redis_runtime_client,
)
from app.services.rendering import coordinator
from cryptography.fernet import Fernet
from fastapi import Request

from tests.integration.test_mcp_consumer import loopback_server


def free_port():
    """只选择新的 loopback 端口，不停止或复用开发服务。"""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def wait_ready(url, process):
    """依赖真实健康响应；启动错误与超时明确失败，不以固定等待当作成功。"""
    async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
        async with asyncio.timeout(60):
            while True:
                if process.poll() is not None:
                    raise RuntimeError("专属 Runtime/Renderer 提前退出，请检查本轮服务日志")
                try:
                    if (await client.get(url)).status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.1)


@asynccontextmanager
async def processes(root, directory, environment, runtime_port, renderer_port):
    """运行已安装的 Node/Python 包；子进程日志和 Renderer 产物限定本次目录。"""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    logs, children = [], []
    commands = [
        (["node", str(root / "runtime/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(runtime_port)], root / "runtime", "runtime"),
        ([sys.executable, "-c", "import asyncio,uvicorn; asyncio.run(uvicorn.Server(uvicorn.Config('wp_renderer.main:app',host='127.0.0.1',port=" + str(renderer_port) + ",log_level='warning',timeout_graceful_shutdown=10)).serve())"], root, "renderer"),
    ]
    try:
        for command, cwd, label in commands:
            log = (directory / (label + ".log")).open("wb")
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=log, creationflags=flags))
        await wait_ready(f"http://127.0.0.1:{runtime_port}/__runtime_readyz", children[0])
        await wait_ready(f"http://127.0.0.1:{renderer_port}/readyz", children[1])
        yield
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
            await asyncio.to_thread(process.wait, 15)
        for log in logs:
            log.close()


@pytest.fixture
async def real_render_backend(media_client, consumer_backend, monkeypatch):
    """仅替换受信配置/独立存储，不替换鉴权、规划器、队列、锁、渲染或最终提交。"""
    if os.getenv("WP_MCP_RENDER_REQUIRED") != "1":
        pytest.skip("真实 MCP 渲染门禁需显式 WP_MCP_RENDER_REQUIRED=1 和已安装 Runtime/Renderer/Chromium")
    client, factory, access, _, _, memory = media_client
    _, app, _, _ = consumer_backend
    root = Path(__file__).resolve().parents[3]
    directory = root / ".tmp" / "mcp-render" / uuid4().hex
    directory.mkdir(parents=True)
    runtime_port, renderer_port = free_port(), free_port()
    runtime_url, renderer_url = f"http://127.0.0.1:{runtime_port}", f"http://127.0.0.1:{renderer_port}"
    app.include_router(internal_runtime.router)
    app.include_router(preview.router_public)
    app.include_router(well_known.router)

    @app.post("/api/client-logs/errors")
    async def client_error(request: Request):
        """仅记录已脱敏的测试浏览器错误栈，便于诊断真实 Runtime 初始化失败。"""
        import json
        body = await request.json()
        (directory / "client-error.json").write_text(json.dumps({key: body.get(key) for key in ("message", "error_name", "stack")},
                                                               ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    async with loopback_server(app, lifespan="off", shutdown_seconds=10) as backend_port:
        backend_url = f"http://127.0.0.1:{backend_port}"
        from tests.fixtures.oauth import POLICY
        settings = AppSettings(_env_file=(), database_url=str(factory.kw["bind"].url), redis_url="memory://mcp-render",
            ai_secret_encryption_key=Fernet.generate_key().decode(),
            backend_public_base_url=backend_url, runtime_base_url=runtime_url, runtime_public_base_url=runtime_url,
            oauth_enabled=True, oauth_issuer=POLICY.issuer, oauth_mcp_resource=POLICY.mcp_resource,
            oauth_api_audience=POLICY.api_audience, oauth_editor_origin=POLICY.issuer, session_secure=True,
            default_admin_password="StrongTestAdminPass#2026!", runtime_build_worker_credential="mcp-render-test-build",
            render_service_credential="mcp-render-test-service", render_workers_config=[{"worker_id": "mcp-render-test", "base_url": renderer_url}],
            render_runtime_navigation_base_url=runtime_url, render_runtime_asset_base_url=runtime_url,
            render_platform_asset_base_url=backend_url, page_screenshot_local_root=str(directory / "objects"),
            mutation_job_max_attempts=1, mutation_job_idle_poll_interval_seconds=.1, page_screenshot_queue_poll_interval_seconds=.1)
        # 新导入模块也从 core 取得本次配置；已导入模块的别名指向同一独立工厂。
        for name, module in list(sys.modules.items()):
            if name == "app" or name.startswith("app."):
                if hasattr(module, "get_settings"):
                    monkeypatch.setattr(module, "get_settings", lambda: settings)
                if hasattr(module, "get_session_factory"):
                    monkeypatch.setattr(module, "get_session_factory", lambda: factory)
                if hasattr(module, "get_redis_runtime_client"):
                    monkeypatch.setattr(module, "get_redis_runtime_client", lambda: memory)
        redis_runtime_client.validate_runtime_state_deployment(settings)
        instance = coordinator.RenderCoordinator(factory)
        monkeypatch.setattr(coordinator, "_DEFAULT_COORDINATOR", instance)
        monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
        environment = dict(os.environ)
        environment.update({"RENDER_SERVICE_CREDENTIAL": "mcp-render-test-service", "RENDER_SERVICE_CREDENTIAL_FILE": "",
            "RENDER_WORKER_ID": "mcp-render-test", "RENDER_PROFILE_DIGEST": "profile.v1", "RENDER_PROFILE_MANIFEST": "",
            "RENDER_RUNTIME_NAVIGATION_BASE_URL": runtime_url, "RENDER_RUNTIME_ASSET_BASE_URL": runtime_url,
            "RENDER_PLATFORM_ASSET_BASE_URL": backend_url, "RENDER_WORKSPACE_DIR": str(directory / "worker"),
            "RUNTIME_ROLE": "all", "RUNTIME_BUILD_ID": "mcp-test-" + directory.name,
            "RUNTIME_BUILD_WORKER_CREDENTIAL": "mcp-render-test-build", "RUNTIME_BUILD_WORKER_CREDENTIAL_FILE": "",
            "RUNTIME_SERVER_HOST": "127.0.0.1", "RUNTIME_SERVER_PORT": str(runtime_port), "RUNTIME_SERVER_BASE_PATH": "/",
            "RUNTIME_PUBLIC_BASE_URL": runtime_url, "RUNTIME_BACKEND_API_BASE_URL": backend_url,
            "RUNTIME_PREVIEW_JWKS_URL": backend_url + "/.well-known/jwks.json", "VITE_CONFIG_NATIVE_IGNORE_WARNING": "true"})
        async with processes(root, directory, environment, runtime_port, renderer_port):
            tasks = [asyncio.create_task(mutation_job_service.run_api_mutation_worker_loop(factory)),
                     asyncio.create_task(page_screenshot_queue_worker.run_page_screenshot_queue_loop(factory))]
            try:
                yield app, backend_url, access, directory, settings
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
