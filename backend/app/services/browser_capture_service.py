"""文件功能：基于 Playwright 打开预览页并生成截图字节内容。"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.playwright_browser_worker import PlaywrightBrowserMissingError
from app.services.playwright_task_queue import PlaywrightTaskQueue, get_playwright_task_queue

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class BrowserCaptureJob:
    """批量截图中的单个浏览器截图任务。"""

    key: int
    preview_url: str
    viewport: CaptureViewport
    extra_http_headers: Mapping[str, str] | None = None


@dataclass(slots=True, frozen=True)
class BrowserCaptureJobResult:
    """批量截图中单个任务的结果。"""

    key: int
    content: bytes | None = None
    error: Exception | None = None


class BrowserCaptureService:
    """无头浏览器截图服务，负责等待预览就绪后产出 PNG。"""

    def __init__(self, playwright_task_queue: PlaywrightTaskQueue | None = None) -> None:
        self.settings = get_settings()
        self.playwright_task_queue = playwright_task_queue or get_playwright_task_queue()

    async def capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers: Mapping[str, str] | None = None,
    ) -> bytes:
        """打开预览地址并按给定视口生成截图内容。"""

        timeout_ms = int(self.settings.page_screenshot_timeout_seconds * 1000)
        visual_ready_timeout_ms = int(self.settings.page_screenshot_visual_ready_timeout_seconds * 1000)
        try:
            return await self.playwright_task_queue.run_with_browser(
                "page-screenshot",
                self._capture_preview_with_browser,
                preview_url,
                viewport,
                extra_http_headers=extra_http_headers,
                timeout_ms=timeout_ms,
                visual_ready_timeout_ms=visual_ready_timeout_ms,
                priority="background",
            )
        except AppException:
            raise
        except PlaywrightBrowserMissingError as error:
            raise AppException(
                status_code=500,
                code="PAGE_SCREENSHOT_BROWSER_MISSING",
                detail="未安装 Playwright 或 Chromium，请先完成浏览器依赖安装。",
            ) from error
        except Exception as error:
            logger.exception(
                "页面截图失败：preview_url=%s viewport=%sx%s",
                self._sanitize_url(preview_url),
                viewport.width,
                viewport.height,
            )
            raise self._build_capture_failed_exception(error) from error

    async def capture_preview_batch(
        self,
        jobs: list[BrowserCaptureJob],
        *,
        max_concurrency: int | None = None,
    ) -> list[BrowserCaptureJobResult]:
        """按并发上限独立执行截图任务，并保留逐项失败结果。"""

        if not jobs:
            return []
        batch_concurrency = max(1, int(max_concurrency or self.settings.page_screenshot_batch_concurrency))
        semaphore = asyncio.Semaphore(batch_concurrency)

        async def run_job(job: BrowserCaptureJob) -> BrowserCaptureJobResult:
            """在批量截图中独立执行单页任务，避免浏览器实例互相污染。"""

            async with semaphore:
                try:
                    content = await self.capture_preview(
                        job.preview_url,
                        job.viewport,
                        extra_http_headers=job.extra_http_headers,
                    )
                    return BrowserCaptureJobResult(key=job.key, content=content)
                except AppException as error:
                    return BrowserCaptureJobResult(key=job.key, error=error)
                except Exception as error:  # noqa: BLE001
                    logger.exception(
                        "页面批量截图出现未预期异常：preview_url=%s viewport=%sx%s",
                        self._sanitize_url(job.preview_url),
                        job.viewport.width,
                        job.viewport.height,
                    )
                    return BrowserCaptureJobResult(key=job.key, error=self._build_capture_failed_exception(error))

        return await asyncio.gather(*[run_job(job) for job in jobs])

    def _capture_preview_with_browser(
        self,
        browser: object,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers: Mapping[str, str] | None = None,
        timeout_ms: int,
        visual_ready_timeout_ms: int,
    ) -> bytes:
        """使用已启动的浏览器实例打开独立页面并截图。"""

        context_options = {
            "viewport": {"width": viewport.width, "height": viewport.height},
            "device_scale_factor": 1,
        }
        context = browser.new_context(**context_options)
        try:
            # new_page 本身也可能因浏览器断连失败；必须纳入 finally，避免长期池
            # 留下无法自动回收的 BrowserContext。
            page = context.new_page()
            self._install_initial_preview_header_route(page, preview_url, extra_http_headers)
            page.on(
                "pageerror",
                lambda error: logger.error("页面截图运行时异常：%s", error),
            )
            page.goto(preview_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function(
                """
                () => {
                  if (window.__EDITOR_RUNTIME_PREVIEW_READY__ === true) {
                    return true;
                  }

                  const appRoot = document.querySelector('#app');
                  const hasMountedContent = Boolean(appRoot && appRoot.childElementCount > 0);
                  const hasInitError = Boolean(document.body?.innerText?.includes('Runtime 初始化失败'));
                  return document.readyState === 'complete' && hasMountedContent && !hasInitError;
                }
                """,
                timeout=timeout_ms,
            )
            page.evaluate(
                """
                async () => {
                  if (document.fonts && document.fonts.ready) {
                    await document.fonts.ready;
                  }
                }
                """
            )
            visual_ready_result = page.evaluate(
                """
                async (timeoutMs) => {
                  const waitForVisualAssets = window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__;
                  if (typeof waitForVisualAssets !== 'function') {
                    return { ok: true, skipped: true, total: 0, failed: [], pending: [] };
                  }
                  return await waitForVisualAssets({ timeoutMs });
                }
                """,
                visual_ready_timeout_ms,
            )
            if not isinstance(visual_ready_result, dict) or not visual_ready_result.get("ok", False):
                raise AppException(
                    status_code=502,
                    code="PAGE_SCREENSHOT_ASSET_NOT_READY",
                    detail=self._build_visual_ready_error_detail(visual_ready_result),
                )
            page.wait_for_timeout(300)
            return page.screenshot(type="png")
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                logger.warning("页面截图 BrowserContext 关闭失败。", exc_info=True)

    def _install_initial_preview_header_route(
        self,
        page: object,
        preview_url: str,
        extra_http_headers: Mapping[str, str] | None,
    ) -> None:
        """仅为初始 Runtime 预览文档请求附加鉴权头，避免污染跨源资源请求。"""

        if not extra_http_headers:
            return

        def handle_route(route: object) -> None:
            """按请求目标决定是否附加 Runtime 预览头。"""

            request = route.request
            if self._should_attach_initial_preview_headers(
                request_url=request.url,
                preview_url=preview_url,
                is_navigation_request=bool(request.is_navigation_request()),
                resource_type=str(request.resource_type or ""),
            ):
                headers = dict(request.headers)
                headers.update(extra_http_headers)
                route.continue_(headers=headers)
                return

            route.continue_()

        page.route("**/*", handle_route)

    @staticmethod
    def _should_attach_initial_preview_headers(
        *,
        request_url: str,
        preview_url: str,
        is_navigation_request: bool,
        resource_type: str,
    ) -> bool:
        """判断当前请求是否为需要 Runtime 预览鉴权头的首个文档请求。"""

        if not is_navigation_request or resource_type != "document":
            return False

        try:
            request_parts = urlsplit(request_url)
            preview_parts = urlsplit(preview_url)
        except Exception:  # noqa: BLE001
            return False

        return (
            request_parts.scheme == preview_parts.scheme
            and request_parts.netloc == preview_parts.netloc
            and request_parts.path == preview_parts.path
        )

    @classmethod
    def _build_capture_failed_exception(cls, error: Exception) -> AppException:
        """把 Playwright 或未知异常包装为统一截图错误。"""

        return AppException(
            status_code=502,
            code="PAGE_SCREENSHOT_CAPTURE_FAILED",
            detail=f"页面截图失败：{cls._sanitize_error_message(error)}",
        )

    @classmethod
    def _sanitize_error_message(cls, error: Exception) -> str:
        """脱敏异常文本中的预览 Token，避免日志或接口详情泄漏签名 URL。"""

        return cls._sanitize_token_text(str(error))

    @classmethod
    def _sanitize_url(cls, url: str) -> str:
        """脱敏 URL 查询参数中的 token 值。"""

        try:
            parts = urlsplit(url)
            query = urlencode([
                (key, "[redacted]") if "token" in key.lower() else (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
            ])
            return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        except Exception:  # noqa: BLE001
            return cls._sanitize_token_text(url)

    @staticmethod
    def _sanitize_token_text(value: str) -> str:
        """脱敏任意文本中常见的 token 查询参数。"""

        return re.sub(r"([?&]token=)[A-Za-z0-9_.-]+", r"\1[redacted]", value)

    @staticmethod
    def _build_visual_ready_error_detail(result: object) -> str:
        """把浏览器端视觉资源等待结果压缩成接口错误详情。"""

        if not isinstance(result, dict):
            return "页面视觉资源未在限定时间内加载完成。"

        failed = result.get("failed") if isinstance(result.get("failed"), list) else []
        pending = result.get("pending") if isinstance(result.get("pending"), list) else []
        timed_out = bool(result.get("timedOut"))
        samples: list[str] = []
        for item in [*failed, *pending][:3]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("message") or "").strip()
            if url:
                samples.append(url)

        reason = "加载超时" if timed_out else "加载失败"
        sample_text = f"；示例资源：{'，'.join(samples)}" if samples else ""
        return f"页面视觉资源{reason}，失败 {len(failed)} 个，未完成 {len(pending)} 个{sample_text}。"
