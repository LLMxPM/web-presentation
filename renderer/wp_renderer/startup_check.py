"""文件功能：Renderer 启动自检，记录事件循环、子进程与 Chromium 实际可执行条件。"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

RENDERER_EVENT_LOOP_UNSUPPORTED = "RENDERER_EVENT_LOOP_UNSUPPORTED"
RENDERER_BROWSER_UNAVAILABLE = "RENDERER_BROWSER_UNAVAILABLE"
RENDERER_SELF_CHECK_FAILED = "RENDERER_SELF_CHECK_FAILED"


@dataclass(frozen=True)
class RendererSelfCheck:
    """一次有界启动自检的稳定结果，供 readyz 与日志复用。"""

    ok: bool
    reason: str | None
    detail: str
    platform: str
    python_version: str
    loop_type: str
    subprocess_supported: bool
    browser_executable: str | None
    browser_available: bool

    def to_dict(self) -> dict[str, Any]:
        """转换为可直接写入 JSON 响应的字典。"""

        return asdict(self)


def _detect_loop_type(loop: asyncio.AbstractEventLoop) -> str:
    """返回实际运行的事件循环类型名，不根据配置推测。"""

    return type(loop).__name__


def _detect_subprocess_support(loop: asyncio.AbstractEventLoop, platform: str) -> bool:
    """Windows 的 SelectorEventLoop 不支持子进程，Playwright 无法启动浏览器。"""

    if platform != "win32":
        return True
    return _detect_loop_type(loop) == "ProactorEventLoop"


async def _verify_browser(timeout_seconds: float) -> tuple[bool, str | None, str]:
    """有界启动一次 Chromium 并打开空白页，验证可执行而不只是路径存在。"""

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001 - 缺少依赖必须转成稳定自检原因
        return False, None, f"Playwright 不可用：{exc}"

    playwright = None
    browser = None
    try:
        playwright = await asyncio.wait_for(async_playwright().start(), timeout=timeout_seconds)
        executable = playwright.chromium.executable_path
        # --only-shell 镜像没有完整 Chromium 路径；实际启动才是可用性的判据。
        browser = await asyncio.wait_for(
            playwright.chromium.launch(headless=True),
            timeout=timeout_seconds,
        )
        page = await asyncio.wait_for(browser.new_page(), timeout=timeout_seconds)
        await asyncio.wait_for(page.set_content("<html><body>renderer-self-check</body></html>"), timeout=timeout_seconds)
        await page.close()
        reported_executable = (
            executable if executable and Path(executable).is_file() else None
        )
        return True, reported_executable, ""
    except Exception as exc:  # noqa: BLE001 - 启动失败必须返回非 200 原因
        return False, None, f"Chromium 启动验证失败：{exc}"
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001 - 清理失败不覆盖原始自检结论
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:  # noqa: BLE001
                pass


async def run_renderer_self_check(*, verify_browser: bool, timeout_seconds: float) -> RendererSelfCheck:
    """执行有界启动自检；任何失败都给出稳定原因而不是静默降级。"""

    loop = asyncio.get_running_loop()
    loop_type = _detect_loop_type(loop)
    subprocess_supported = _detect_subprocess_support(loop, sys.platform)
    base = {
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "loop_type": loop_type,
        "subprocess_supported": subprocess_supported,
    }
    if not subprocess_supported:
        return RendererSelfCheck(
            ok=False,
            reason=RENDERER_EVENT_LOOP_UNSUPPORTED,
            detail=(
                f"Windows 下 Renderer 运行在 {loop_type}，无法创建子进程启动 Chromium；"
                "请关闭 uvicorn --reload 或改用 Proactor 事件循环。"
            ),
            browser_executable=None,
            browser_available=False,
            **base,
        )
    if not verify_browser:
        return RendererSelfCheck(
            ok=True,
            reason=None,
            detail="已跳过 Chromium 启动验证（RENDER_SELF_CHECK_BROWSER=false）。",
            browser_executable=None,
            browser_available=False,
            **base,
        )

    try:
        browser_available, executable, detail = await asyncio.wait_for(
            _verify_browser(timeout_seconds),
            timeout=timeout_seconds * 3,
        )
    except asyncio.TimeoutError:
        browser_available, executable, detail = False, None, "Chromium 启动验证超时。"
    if browser_available:
        return RendererSelfCheck(
            ok=True,
            reason=None,
            detail="",
            browser_executable=executable,
            browser_available=True,
            **base,
        )
    return RendererSelfCheck(
        ok=False,
        reason=RENDERER_BROWSER_UNAVAILABLE,
        detail=detail,
        browser_executable=executable,
        browser_available=False,
        **base,
    )


__all__ = [
    "RENDERER_BROWSER_UNAVAILABLE",
    "RENDERER_EVENT_LOOP_UNSUPPORTED",
    "RENDERER_SELF_CHECK_FAILED",
    "RendererSelfCheck",
    "run_renderer_self_check",
]
