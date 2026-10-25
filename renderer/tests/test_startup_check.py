"""文件功能：验证 Renderer 启动自检的事件循环判定与 readyz 失败语义。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

os.environ.setdefault("RENDER_SERVICE_CREDENTIAL", "renderer-test-secret")
os.environ.setdefault("RENDER_WORKER_ID", "renderer-local")
os.environ.setdefault("RENDER_WORKER_EPOCH", "epoch-1")

from wp_renderer.api import routes  # noqa: E402
from wp_renderer.control.slot import SlotController  # noqa: E402
from wp_renderer.startup_check import (  # noqa: E402
    RENDERER_BROWSER_UNAVAILABLE,
    RENDERER_EVENT_LOOP_UNSUPPORTED,
    RendererSelfCheck,
    _detect_subprocess_support,
    _verify_browser,
    run_renderer_self_check,
)

pytestmark = pytest.mark.unit


class SelectorEventLoop:
    """模拟 Windows SelectorEventLoop 的类型名。"""


class ProactorEventLoop:
    """模拟 Windows ProactorEventLoop 的类型名。"""


def test_windows_selector_loop_is_reported_unsupported() -> None:
    """Windows 上 Selector 循环无法创建子进程，必须显式判定为不支持。"""

    assert _detect_subprocess_support(SelectorEventLoop(), "win32") is False
    assert _detect_subprocess_support(ProactorEventLoop(), "win32") is True
    assert _detect_subprocess_support(SelectorEventLoop(), "linux") is True


@pytest.mark.asyncio
async def test_self_check_records_loop_type_when_browser_check_is_skipped() -> None:
    """跳过浏览器验证时仍记录实际事件循环与子进程条件。"""

    result = await run_renderer_self_check(verify_browser=False, timeout_seconds=1.0)

    assert result.loop_type
    assert result.platform == sys.platform
    assert result.browser_available is False
    if sys.platform == "win32" and result.loop_type == "SelectorEventLoop":
        assert result.ok is False
        assert result.reason == RENDERER_EVENT_LOOP_UNSUPPORTED
    else:
        assert result.ok is True


@pytest.mark.asyncio
async def test_headless_shell_succeeds_without_full_chromium_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """仅安装 headless shell 时，完整 Chromium 路径缺失不应阻断真实启动自检。"""

    page = SimpleNamespace(set_content=AsyncMock(), close=AsyncMock())
    browser = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    chromium = SimpleNamespace(
        executable_path=str(tmp_path / "missing-chrome"),
        launch=AsyncMock(return_value=browser),
    )
    playwright = SimpleNamespace(chromium=chromium, stop=AsyncMock())
    manager = SimpleNamespace(start=AsyncMock(return_value=playwright))
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: manager)

    ok, executable, detail = await _verify_browser(1.0)

    assert (ok, executable, detail) == (True, None, "")
    chromium.launch.assert_awaited_once_with(headless=True)
    page.set_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_readyz_returns_503_with_stable_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """自检失败时 readyz 必须返回非 200，并保留槽位状态便于排障。"""

    monkeypatch.setattr(
        routes,
        "_slot",
        SlotController(worker_id="renderer-local", worker_epoch="epoch-1"),
    )
    monkeypatch.setattr(
        routes,
        "_self_check",
        RendererSelfCheck(
            ok=False,
            reason=RENDERER_BROWSER_UNAVAILABLE,
            detail="Chromium 启动验证失败",
            platform=sys.platform,
            python_version="3.13.0",
            loop_type="ProactorEventLoop",
            subprocess_supported=True,
            browser_executable=None,
            browser_available=False,
        ),
    )
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["self_check"]["reason"] == RENDERER_BROWSER_UNAVAILABLE
    assert body["slot_state"] == "idle"


@pytest.mark.asyncio
async def test_readyz_returns_200_when_self_check_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    """自检通过且槽位空闲时 readyz 返回 200；busy 不改变健康语义。"""

    monkeypatch.setattr(
        routes,
        "_slot",
        SlotController(worker_id="renderer-local", worker_epoch="epoch-1"),
    )
    monkeypatch.setattr(
        routes,
        "_self_check",
        RendererSelfCheck(
            ok=True,
            reason=None,
            detail="",
            platform=sys.platform,
            python_version="3.13.0",
            loop_type="ProactorEventLoop",
            subprocess_supported=True,
            browser_executable="C:/ms-playwright/chromium/chrome.exe",
            browser_available=True,
        ),
    )
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["self_check"]["browser_available"] is True
