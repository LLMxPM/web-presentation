"""文件功能：使用无头浏览器检查页面预览真实渲染后的固定画布布局警告。"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.playwright_task_queue import PlaywrightTaskQueue, get_playwright_task_queue
from app.services.runtime_build_client import RUNTIME_SERVICE_TOKEN_HEADER
from app.services.token_service import TokenService

RUNTIME_PREVIEW_CONTEXT_HEADER = "x-runtime-preview-context"
RUNTIME_PUBLIC_BASE_URL_HEADER = "x-runtime-public-base-url"

PAGE_RENDER_WARNING_SOURCE = "runtime-render"
PAGE_RENDER_BOTTOM_OVERFLOW_CODE = "PAGE_RENDER_BOTTOM_OVERFLOW"
PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE = "PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE"

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PageRenderDiagnosticsTarget:
    """页面渲染诊断浏览器实际访问的地址与额外请求头。"""

    preview_url: str
    extra_http_headers: Mapping[str, str] | None = None


class PageRenderDiagnosticsService:
    """页面渲染诊断服务，负责返回不会阻塞写入的布局 warning。"""

    def __init__(self, playwright_task_queue: PlaywrightTaskQueue | None = None) -> None:
        self.settings = get_settings()
        self.playwright_task_queue = playwright_task_queue or get_playwright_task_queue()

    async def diagnose_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
    ) -> list[dict[str, object]]:
        """打开页面预览并检查固定画布底部是否存在可见内容溢出。"""

        try:
            target = self._build_browser_target(preview_url)
            return await self.playwright_task_queue.run_with_browser(
                "page-render-diagnostics",
                self._diagnose_preview_with_browser,
                target,
                viewport,
                timeout_ms=int(self.settings.page_screenshot_timeout_seconds * 1000),
                visual_ready_timeout_ms=int(self.settings.page_screenshot_visual_ready_timeout_seconds * 1000),
                priority="interactive",
            )
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "页面渲染布局诊断不可用：preview_url=%s viewport=%sx%s",
                self._sanitize_url(preview_url),
                viewport.width,
                viewport.height,
                exc_info=True,
            )
            return [
                self._build_unavailable_warning(
                    f"页面渲染布局诊断不可用：{self._sanitize_error_message(error)}",
                )
            ]

    def _diagnose_preview_with_browser(
        self,
        browser: object,
        target: PageRenderDiagnosticsTarget,
        viewport: CaptureViewport,
        *,
        timeout_ms: int,
        visual_ready_timeout_ms: int,
    ) -> list[dict[str, object]]:
        """使用池内长期浏览器和任务独立 Context 执行页面布局测量。"""

        context = browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=1,
        )
        try:
            # BrowserContext 创建成功后，即使 new_page 失败也要在本槽位线程中关闭它。
            page = context.new_page()
            self._install_initial_preview_header_route(
                page,
                target.preview_url,
                target.extra_http_headers,
            )
            self._wait_for_preview_ready(page, target.preview_url, timeout_ms, visual_ready_timeout_ms)
            result = page.evaluate(self._build_bottom_overflow_script())
            return self._normalize_diagnostics_result(result)
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                logger.warning("页面渲染诊断 BrowserContext 关闭失败。", exc_info=True)

    def _build_browser_target(self, preview_url: str) -> PageRenderDiagnosticsTarget:
        """把公开预览地址转换为 Runtime 直连诊断目标。"""

        preview_token = self._extract_preview_token(preview_url)
        if not preview_token:
            return PageRenderDiagnosticsTarget(preview_url=preview_url)

        preview_claims = TokenService.verify_preview_context_token(preview_token)
        artifact_id = str(preview_claims.get("artifact_id") or "").strip()
        if not artifact_id:
            raise AppException(
                status_code=502,
                code="PAGE_RENDER_PREVIEW_TOKEN_INVALID",
                detail="渲染诊断预览上下文缺少 artifact_id。",
            )

        runtime_service_token = TokenService.generate_runtime_service_access_token(
            artifact_id=artifact_id,
            expires_in_seconds=self._resolve_runtime_service_token_ttl(preview_claims),
        )
        return PageRenderDiagnosticsTarget(
            preview_url=f"{self.settings.runtime_base_url.rstrip('/')}/__preview",
            extra_http_headers={
                RUNTIME_PREVIEW_CONTEXT_HEADER: preview_token,
                RUNTIME_SERVICE_TOKEN_HEADER: runtime_service_token,
                RUNTIME_PUBLIC_BASE_URL_HEADER: self._resolve_browser_runtime_public_base_url(),
            },
        )

    def _wait_for_preview_ready(
        self,
        page: object,
        preview_url: str,
        timeout_ms: int,
        visual_ready_timeout_ms: int,
    ) -> None:
        """等待 Runtime 挂载、字体和视觉资源完成后再测量布局。"""

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
                code="PAGE_RENDER_VISUAL_ASSET_NOT_READY",
                detail="页面视觉资源未在限定时间内加载完成，无法可靠执行布局诊断。",
            )
        page.wait_for_timeout(300)

    def _install_initial_preview_header_route(
        self,
        page: object,
        preview_url: str,
        extra_http_headers: Mapping[str, str] | None,
    ) -> None:
        """仅为 Runtime 预览文档请求附加鉴权头。"""

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
        """判断请求是否为需要 Runtime 预览鉴权头的首个文档请求。"""

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

    @staticmethod
    def _build_bottom_overflow_script() -> str:
        """构造浏览器端页面底部溢出检测脚本。"""

        return """
        () => {
          const tolerancePx = 2;
          const root = document.querySelector('.runtime-page-print-source, .runtime-view-preview-source');
          if (!root) {
            return [{
              severity: 'warning',
              source: 'runtime-render',
              code: 'PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE',
              message: '未找到页面渲染根节点 .runtime-page-print-source 或 .runtime-view-preview-source，无法检查底部溢出。'
            }];
          }

          const rootRect = root.getBoundingClientRect();
          const rootScrollOverflow = Math.max(0, Math.ceil(root.scrollHeight - root.clientHeight - tolerancePx));
          let maxVisualOverflow = 0;
          const offenders = [];

          const describeElement = (element, overflowPx) => {
            const tagName = String(element.tagName || '').toLowerCase();
            const id = element.id ? `#${element.id}` : '';
            const className = typeof element.className === 'string'
              ? element.className.trim().split(/\\s+/).filter(Boolean).slice(0, 4).join('.')
              : '';
            const classLabel = className ? `.${className}` : '';
            const text = String(element.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
            return `${tagName}${id}${classLabel} 超出 ${overflowPx}px${text ? `，文本：${text}` : ''}`;
          };

          for (const element of root.querySelectorAll('*')) {
            const style = window.getComputedStyle(element);
            if (
              style.display === 'none'
              || style.visibility === 'hidden'
              || Number(style.opacity) === 0
            ) {
              continue;
            }

            const rect = element.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) {
              continue;
            }

            const overflowPx = Math.ceil(rect.bottom - rootRect.bottom - tolerancePx);
            if (overflowPx <= 0) {
              continue;
            }

            maxVisualOverflow = Math.max(maxVisualOverflow, overflowPx);
            offenders.push({ element, overflowPx });
          }

          const overflowPx = Math.max(rootScrollOverflow, maxVisualOverflow);
          if (overflowPx <= 0) {
            return [];
          }

          const samples = offenders
            .sort((left, right) => right.overflowPx - left.overflowPx)
            .slice(0, 3)
            .map(item => describeElement(item.element, item.overflowPx));
          const sampleText = samples.length ? ` 疑似元素：${samples.join('；')}` : '';
          return [{
            severity: 'warning',
            source: 'runtime-render',
            code: 'PAGE_RENDER_BOTTOM_OVERFLOW',
            message: `页面内容底部超出画布 ${overflowPx}px，预览或导出时可能被裁切。${sampleText}`
          }];
        }
        """

    def _normalize_diagnostics_result(self, result: object) -> list[dict[str, object]]:
        """规范化浏览器端返回值，过滤非 warning 结构。"""

        if not isinstance(result, list):
            return [self._build_unavailable_warning("页面渲染布局诊断返回了非法结果。")]

        diagnostics: list[dict[str, object]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            message = str(item.get("message") or "").strip()
            if not code or not message:
                continue
            diagnostics.append(
                {
                    "severity": "warning",
                    "source": PAGE_RENDER_WARNING_SOURCE,
                    "code": code,
                    "message": message,
                }
            )
        return diagnostics

    @staticmethod
    def _build_unavailable_warning(message: str) -> dict[str, object]:
        """构造渲染诊断不可用 warning。"""

        return {
            "severity": "warning",
            "source": PAGE_RENDER_WARNING_SOURCE,
            "code": PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE,
            "message": message,
        }

    @staticmethod
    def _extract_preview_token(preview_url: str) -> str:
        """从公开预览 URL 中读取 token 查询参数。"""

        query = parse_qs(urlsplit(preview_url).query)
        return str((query.get("token") or [""])[0]).strip()

    @staticmethod
    def _resolve_runtime_service_token_ttl(preview_claims: dict[str, object]) -> int:
        """按预览上下文令牌剩余有效期生成 Runtime 服务令牌 TTL。"""

        now = int(time.time())
        try:
            preview_exp = int(preview_claims.get("exp") or now)
        except (TypeError, ValueError):
            preview_exp = now
        return max(60, preview_exp - now)

    def _resolve_browser_runtime_public_base_url(self) -> str:
        """返回浏览器可访问的 Runtime 基址，用于 Runtime HTML 中脚本和样式 URL。"""

        configured = str(self.settings.page_screenshot_runtime_public_base_url or "").strip().rstrip("/")
        if configured:
            return configured

        runtime_base_url = self.settings.runtime_base_url.rstrip("/")
        public_path = urlsplit(str(self.settings.runtime_public_base_url or "")).path.strip("/")
        if public_path:
            return f"{runtime_base_url}/{public_path}"
        return runtime_base_url

    @classmethod
    def _sanitize_error_message(cls, error: Exception) -> str:
        """脱敏异常文本中的预览 Token。"""

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
