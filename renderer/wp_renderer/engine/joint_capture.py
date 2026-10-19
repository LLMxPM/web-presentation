"""文件功能：在已完成的布局诊断后有界捕获 PNG，隔离图片失败且不重启浏览器。"""

import asyncio
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from render_contracts.errors import RenderExecutionError, ERROR_CODE_CANCELLED
from render_contracts.screenshot import ScreenshotPhaseResult

logger = logging.getLogger(__name__)
MAX_IMAGE_PHASE_SECONDS = 10.0


async def append_screenshot(executor: Any, result: Any, *, ready: dict, artifact_dir: Path):
    """只在布局成功后捕获，预算不超过原硬期限；取消始终向上传播。"""
    started = time.perf_counter()
    if not executor.execution.request.operation_options.get("capture_screenshot", False):
        return result
    executor._check_cancel(stage="capture")
    remaining = executor._deadline.remaining_seconds()
    if remaining < 0.25:
        return replace(result, screenshot=ScreenshotPhaseResult("skipped", "SCREENSHOT_BUDGET_EXHAUSTED", True))

    async def capture():
        """固定静态画面后捕获；不再次导航或启动 Chromium。"""
        await executor._prepare_static_capture(executor.execution.request, ready, capture=True)
        return await executor._capture_page(artifact_dir)

    try:
        image = await executor._await_without_cancelling(capture(), timeout=min(MAX_IMAGE_PHASE_SECONDS, remaining - 0.1))
        executor._check_cancel(stage="capture")
        return replace(result, artifacts=image.artifacts, screenshot=ScreenshotPhaseResult("available"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        executor._check_cancel(stage="capture")
        if isinstance(exc, RenderExecutionError) and exc.error.code == ERROR_CODE_CANCELLED:
            raise
        code = exc.error.code if isinstance(exc, RenderExecutionError) else "SCREENSHOT_CAPTURE_FAILED"
        if isinstance(exc, TimeoutError):
            code = "SCREENSHOT_DEADLINE_EXCEEDED"
        logger.warning("诊断已完成，附带截图失败。", extra={"event": "render.screenshot.failed", "reason_code": code})
        return replace(result, artifacts=[], screenshot=ScreenshotPhaseResult("failed", code, True))
    finally:
        logger.info("附带截图阶段结束。", extra={"event": "render.screenshot.finished", "attempt_id": executor.execution.request.attempt_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
