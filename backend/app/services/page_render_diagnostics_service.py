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
from app.services.page_render_layout_script import build_page_render_layout_script
from app.services.playwright_task_queue import PlaywrightTaskQueue, get_playwright_task_queue
from app.services.runtime_build_client import RUNTIME_SERVICE_TOKEN_HEADER
from app.services.token_service import TokenService

RUNTIME_PREVIEW_CONTEXT_HEADER = "x-runtime-preview-context"
RUNTIME_PUBLIC_BASE_URL_HEADER = "x-runtime-public-base-url"

PAGE_RENDER_WARNING_SOURCE = "runtime-render"
PAGE_RENDER_BOTTOM_OVERFLOW_CODE = "PAGE_RENDER_BOTTOM_OVERFLOW"
PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE = "PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE"
LAYOUT_ANALYSIS_SCHEMA_VERSION = 2
LAYOUT_ANALYSIS_RESULT_KEYS = (
    "text_layouts",
    "item_groups",
    "overflows",
    "spatial_relations",
)

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
    ) -> dict[str, object]:
        """打开页面预览并返回固定画布诊断与文本布局分析。"""

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
            return self._build_unavailable_result(
                f"页面渲染布局诊断不可用：{self._sanitize_error_message(error)}",
            )

    def _diagnose_preview_with_browser(
        self,
        browser: object,
        target: PageRenderDiagnosticsTarget,
        viewport: CaptureViewport,
        *,
        timeout_ms: int,
        visual_ready_timeout_ms: int,
    ) -> dict[str, object]:
        """使用池内长期浏览器和任务独立 Context 执行页面布局测量。"""

        context = browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=1,
            # 模拟 prefers-reduced-motion，避免入场动画位移干扰布局测量结果。
            reduced_motion="reduce",
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
            result = page.evaluate(build_page_render_layout_script())
            return self._normalize_render_result(result)
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

    def _normalize_render_result(self, result: object) -> dict[str, object]:
        """规范化浏览器端布局分析结果，隔离非法诊断和文本明细。"""

        if not isinstance(result, dict):
            return self._build_unavailable_result("页面渲染布局诊断返回了非法结果。")

        diagnostics: list[dict[str, object]] = []
        raw_diagnostics = result.get("diagnostics")
        for item in raw_diagnostics if isinstance(raw_diagnostics, list) else []:
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
        return {
            "diagnostics": diagnostics,
            "layout_analysis": self._normalize_layout_analysis(result.get("layout_analysis")),
        }

    @staticmethod
    def _normalize_layout_analysis(value: object) -> dict[str, object]:
        """规范化 v2 文本、分排、越界和空间关系统一契约。"""

        if not isinstance(value, dict):
            return PageRenderDiagnosticsService._empty_layout_analysis()
        result_lists = {
            key: _normalize_dict_list(value.get(key))
            for key in LAYOUT_ANALYSIS_RESULT_KEYS
        }
        raw_summary = value.get("summary")
        summary = _normalize_layout_summary(
            raw_summary if isinstance(raw_summary, dict) else {},
            result_lists,
        )
        return {
            "schema_version": LAYOUT_ANALYSIS_SCHEMA_VERSION,
            "summary": summary,
            **result_lists,
        }

    @classmethod
    def _build_unavailable_result(cls, message: str) -> dict[str, object]:
        """构造渲染诊断不可用结果并保留稳定分析结构。"""

        return {
            "diagnostics": [cls._build_unavailable_warning(message)],
            "layout_analysis": cls._empty_layout_analysis(),
        }

    @staticmethod
    def _empty_layout_analysis() -> dict[str, object]:
        """返回没有可报告布局事实时的稳定分析结构。"""

        return {
            "schema_version": LAYOUT_ANALYSIS_SCHEMA_VERSION,
            "summary": {
                "attention": "none",
                "message": "未发现需要关注的视觉检测结果。",
                "totals": {key: 0 for key in LAYOUT_ANALYSIS_RESULT_KEYS},
                "returned": {key: 0 for key in LAYOUT_ANALYSIS_RESULT_KEYS},
                "truncated": False,
            },
            **{key: [] for key in LAYOUT_ANALYSIS_RESULT_KEYS},
        }

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


def _coerce_non_negative_int(value: object, fallback: int) -> int:
    """把浏览器返回的计数转换为非负整数。"""

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _normalize_dict_list(value: object) -> list[dict[str, object]]:
    """仅保留浏览器布局清单中的对象项，避免异常数据破坏返回契约。"""

    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_layout_summary(
    value: dict[str, object],
    result_lists: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    """按实际返回清单修正 summary 计数，并保留浏览器端截断前总数。"""

    raw_totals = value.get("totals")
    totals_source = raw_totals if isinstance(raw_totals, dict) else {}
    totals = {
        key: _coerce_non_negative_int(totals_source.get(key), len(result_lists[key]))
        for key in LAYOUT_ANALYSIS_RESULT_KEYS
    }
    returned = {key: len(result_lists[key]) for key in LAYOUT_ANALYSIS_RESULT_KEYS}
    valid_attentions = {"none", "review", "likely_issue"}
    attention = str(value.get("attention") or "none")
    if attention not in valid_attentions:
        attention = "none"
    message = str(value.get("message") or "").strip()
    if not message:
        message = (
            "未发现需要关注的视觉检测结果。"
            if attention == "none"
            else "发现需要关注的视觉检测结果。"
        )
    return {
        "attention": attention,
        "message": message,
        "totals": totals,
        "returned": returned,
        "truncated": bool(value.get("truncated"))
        or any(totals[key] > returned[key] for key in LAYOUT_ANALYSIS_RESULT_KEYS),
    }
