"""文件功能：Renderer 执行引擎，使用异步 Playwright 在子进程语义中完成三类操作。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from render_contracts.constants import (
    OPERATION_COMPONENT_DIAGNOSE,
    OPERATION_PAGE_CAPTURE,
    OPERATION_PAGE_DIAGNOSE,
    RESULT_SCHEMA_VERSION,
)
from render_contracts.errors import (
    ERROR_CODE_ASSET_NOT_READY,
    ERROR_CODE_CANCELLED,
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INPUT_EXPIRED,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_OUTPUT_LIMIT_EXCEEDED,
    ERROR_CODE_PROFILE_MISMATCH,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import ArtifactDescriptor, DiagnosticItem, ExecutionResult
from render_contracts.tokens import sha256_hex

from wp_renderer.engine.layout_scripts import (
    build_component_render_layout_script,
    build_page_render_layout_script,
)
from wp_renderer.engine.render_ready import wait_for_render_ready

logger = logging.getLogger(__name__)

# 与 Runtime 侧 runtime-saas-preview / page_screenshot 约定一致。
RUNTIME_PREVIEW_CONTEXT_HEADER = "x-runtime-preview-context"

# 导航目标仅允许 http/https，并拦截云元数据与链路本地地址。
_BLOCKED_NAVIGATION_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "fd00:ec2::254",
        "instance-data",
    }
)
_ALLOWED_NAVIGATION_SCHEMES = frozenset({"http", "https"})
# 浏览器不得访问控制 API：拦截控制面路径与本机控制端口（端口跟随配置）。
_CONTROL_API_PATH_PREFIXES = ("/internal/render/",)

# 每个 Playwright closer 的关闭超时秒数，避免关停卡死。
_CLOSER_TIMEOUT_SECONDS = 5.0

# 组件 ready/settled 与 runtime/console 错误必须从文档初始化阶段开始收集。
_COMPONENT_MESSAGE_CAPTURE_SCRIPT = """
(() => {
  window.__COMPONENT_CHECK_MESSAGES__ = [];
  window.__COMPONENT_CHECK_RUNTIME_ERRORS__ = [];
  window.__COMPONENT_CHECK_CONSOLE_ERRORS__ = [];
  window.addEventListener('message', (event) => {
    const data = event && event.data;
    if (data && typeof data === 'object' && typeof data.type === 'string'
        && data.type.startsWith('component-preview:')) {
      window.__COMPONENT_CHECK_MESSAGES__.push(data);
    }
  });
  window.addEventListener('error', (event) => {
    const message = event && event.message ? String(event.message) : '未捕获运行时异常';
    window.__COMPONENT_CHECK_RUNTIME_ERRORS__.push(message);
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event && event.reason;
    const message = reason && reason.message ? String(reason.message) : String(reason || '未处理的 Promise 拒绝');
    window.__COMPONENT_CHECK_RUNTIME_ERRORS__.push(message);
  });
})();
"""


class DeadlineClock:
    """以 monotonic 时钟执行硬期限约束，综合 remaining_budget_ms 与 stop_by/deadline_at。"""

    def __init__(self, *, deadline_monotonic: float) -> None:
        self._deadline_monotonic = deadline_monotonic

    @classmethod
    def from_request(cls, request: Any) -> "DeadlineClock":
        """从请求预算与票据期限计算更紧的硬期限。"""

        now_mono = time.monotonic()
        now_wall = datetime.now(UTC)
        candidates: list[float] = []
        budget_s = float(getattr(request, "remaining_budget_ms", 0) or 0) / 1000.0
        candidates.append(max(0.0, budget_s))
        raw_values = [getattr(request, "deadline_at", None)]
        ticket = getattr(request, "admission_ticket", None)
        raw_values.append(getattr(ticket, "stop_by", None) if ticket is not None else None)
        for raw in raw_values:
            if not raw:
                continue
            parsed = _parse_utc(raw)
            if parsed is None:
                continue
            candidates.append(max(0.0, (parsed - now_wall).total_seconds()))
        return cls(deadline_monotonic=now_mono + max(0.0, min(candidates)))

    def remaining_seconds(self) -> float:
        """返回距硬期限的剩余秒数。"""

        return max(0.0, self._deadline_monotonic - time.monotonic())

    def remaining_ms(self) -> int:
        """返回距硬期限的剩余毫秒数。"""

        return max(0, int(self.remaining_seconds() * 1000))

    def check(self, *, stage: str) -> None:
        """已超时则抛出 RENDER_DEADLINE_EXCEEDED。"""

        if self.remaining_seconds() <= 0:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_DEADLINE_EXCEEDED,
                    message="执行超过硬期限（remaining_budget_ms / stop_by）。",
                    stage=stage,
                )
            )


class RenderExecutor:
    """每次 attempt 新建 Playwright/Chromium/Context，不跨请求复用。"""

    def __init__(self, *, settings: Any, slot: Any, execution: Any) -> None:
        self.settings = settings
        self.slot = slot
        self.execution = execution
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_started = False
        self._deadline: DeadlineClock | None = None
        self._unsettled_tasks: set[asyncio.Future[Any]] = set()

    async def execute(self, *, artifact_dir: Path) -> ExecutionResult:
        """按 operation 执行页面截图、页面诊断或组件诊断；全程受硬期限与取消约束。"""

        request = self.execution.request
        self._deadline = DeadlineClock.from_request(request)
        self._check_cancel(stage="admission")
        self._deadline.check(stage="admission")
        if request.preview_access.is_expired():
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_INPUT_EXPIRED, message="预览访问授权已过期。", stage="admission")
            )
        if self.slot.settings.render_profile_digest and request.render_profile_digest:
            if request.render_profile_digest != self.slot.settings.render_profile_digest:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_PROFILE_MISMATCH,
                        message="执行环境 profile 与请求不一致。",
                        stage="admission",
                    )
                )
        navigation_url = str(request.preview_access.navigation_base_url or "")
        assert_safe_navigation_url(navigation_url)
        await self._launch_browser(request)
        try:
            self._check_cancel(stage="navigate")
            await self._await_bounded(
                self._page.goto(navigation_url, wait_until="domcontentloaded"),
                stage="navigate",
            )
            self._check_cancel(stage="ready")
            ready_timeout_ms = max(1, min(self._deadline.remaining_ms() - 500, self._deadline.remaining_ms()))
            ready = await self._await_bounded(
                wait_for_render_ready(
                    self._page,
                    timeout_ms=ready_timeout_ms,
                    expected_artifact_id=request.snapshot_ref.artifact_id,
                    expected_input_digest=request.input_digest,
                ),
                stage="ready",
            )
            if not ready.get("ok"):
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_ASSET_NOT_READY,
                        message=str(ready.get("message") or "Runtime 渲染协议未就绪。"),
                        stage="ready",
                    )
                )
            self._check_cancel(stage="ready")
            await self._wait_visual_assets(request)
            self._check_cancel(stage="capture")
            if request.operation == OPERATION_PAGE_CAPTURE:
                return await self._await_bounded(self._capture_page(artifact_dir), stage="capture")
            if request.operation == OPERATION_PAGE_DIAGNOSE:
                return await self._await_bounded(self._diagnose_page(), stage="diagnose")
            if request.operation == OPERATION_COMPONENT_DIAGNOSE:
                return await self._await_bounded(self._diagnose_component(), stage="diagnose")
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_CONTRACT_MISMATCH, message="未知操作。")
            )
        finally:
            await self.shutdown()

    def _check_cancel(self, *, stage: str) -> None:
        """阶段边界检查取消标记，保证 cancel 能中断执行。"""

        if bool(getattr(self.execution, "cancel_requested", False)):
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_CANCELLED, message="执行已取消。", stage=stage)
            )

    async def _await_bounded(self, awaitable: Any, *, stage: str) -> Any:
        """用剩余硬期限包住异步调用；超时映射为 RENDER_DEADLINE_EXCEEDED。"""

        deadline = self._deadline or DeadlineClock.from_request(self.execution.request)
        self._deadline = deadline
        timeout = deadline.remaining_seconds()
        if timeout <= 0:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_DEADLINE_EXCEEDED,
                    message="执行超过硬期限（remaining_budget_ms / stop_by）。",
                    stage=stage,
                )
            )
        try:
            return await self._await_without_cancelling(awaitable, timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_DEADLINE_EXCEEDED,
                    message=f"阶段 {stage} 超过硬期限。",
                    stage=stage,
                )
            ) from exc

    async def _await_without_cancelling(self, awaitable: Any, *, timeout: float) -> Any:
        """限时等待 Playwright 调用但不取消底层任务，交由关闭阶段解除阻塞。"""

        task = asyncio.ensure_future(awaitable)
        try:
            done, _pending = await asyncio.wait({task}, timeout=max(0.0, timeout))
        except asyncio.CancelledError:
            self._track_unsettled_task(task)
            raise
        if not done:
            self._track_unsettled_task(task)
            raise TimeoutError
        return task.result()

    def _track_unsettled_task(self, task: asyncio.Future[Any]) -> None:
        """保留超时后的 Playwright 任务，并消费其后续异常，避免任务泄漏告警。"""

        if task.done():
            try:
                task.result()
            except BaseException:  # noqa: BLE001
                pass
            return
        self._unsettled_tasks.add(task)

        def _consume(completed: asyncio.Future[Any]) -> None:
            """任务最终完成时移除引用并消费异常。"""

            self._unsettled_tasks.discard(completed)
            try:
                completed.result()
            except BaseException:  # noqa: BLE001
                pass

        task.add_done_callback(_consume)

    async def _launch_browser(self, request: Any) -> None:
        """启动独立 Chromium 与 Context，应用固定视口与降动效策略。"""

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_INTERNAL_ERROR, message="Renderer 未安装 Playwright。")
            ) from exc
        self._playwright = await self._await_bounded(async_playwright().start(), stage="launch")
        self._browser = await self._await_bounded(
            self._playwright.chromium.launch(headless=True),
            stage="launch",
        )
        viewport = request.viewport
        self._context = await self._await_bounded(
            self._browser.new_context(
                viewport={"width": int(viewport.width), "height": int(viewport.height)},
                device_scale_factor=float(viewport.device_scale_factor or 1),
                reduced_motion="reduce",
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                color_scheme="light",
            ),
            stage="launch",
        )
        if request.operation == OPERATION_COMPONENT_DIAGNOSE:
            await self._await_bounded(
                self._context.add_init_script(script=_COMPONENT_MESSAGE_CAPTURE_SCRIPT),
                stage="launch",
            )
        self._page = await self._await_bounded(self._context.new_page(), stage="launch")
        # 仅初始预览文档请求附带鉴权头，避免污染跨源资源请求。
        preview_access = request.preview_access

        async def _handle_route(route: Any) -> None:
            """拦截控制 API，并按请求目标决定是否附加 Runtime 预览头。"""

            request_url = str(getattr(route.request, "url", "") or "")
            if is_control_api_target(request_url):
                await route.abort("blockedbyclient")
                return
            await _route_preview_headers(route, preview_access)

        await self._page.route("**/*", _handle_route)

    async def _wait_visual_assets(self, request: Any) -> None:
        """等待图片/背景图等视觉资源就绪；等待上限不得超过剩余硬期限。"""

        if self._deadline is not None:
            self._deadline.check(stage="ready")
        default_timeout = max(500, int(getattr(self.settings, "visual_ready_timeout_ms", 25000)))
        remaining_ms = (self._deadline.remaining_ms() if self._deadline else default_timeout) - 200
        timeout_ms = max(1, min(default_timeout, remaining_ms))
        visual_ready_result = await self._await_bounded(
            self._page.evaluate(
                """
                async (timeoutMs) => {
                  const waitForVisualAssets = window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__;
                  if (typeof waitForVisualAssets !== 'function') {
                    return { ok: true, skipped: true, total: 0, failed: [], pending: [] };
                  }
                  return await waitForVisualAssets({ timeoutMs });
                }
                """,
                timeout_ms,
            ),
            stage="ready",
        )
        if not isinstance(visual_ready_result, dict) or not visual_ready_result.get("ok", False):
            failed = visual_ready_result.get("failed") if isinstance(visual_ready_result, dict) else []
            pending = visual_ready_result.get("pending") if isinstance(visual_ready_result, dict) else []
            samples: list[str] = []
            for item in [*failed, *pending][:3]:
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("message") or "").strip()
                    if url:
                        samples.append(url)
            sample_text = f"；示例资源：{'，'.join(samples)}" if samples else ""
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_ASSET_NOT_READY,
                    message=f"页面视觉资源未在限定时间内加载完成{sample_text}。",
                    stage="ready",
                )
            )

    async def _capture_page(self, artifact_dir: Path) -> ExecutionResult:
        """捕获静态 PNG；字体/资源未就绪不能输出成功图片。"""

        await self._page.wait_for_timeout(150)
        png_bytes = await self._page.screenshot(type="png", animations="disabled", full_page=False)
        if len(png_bytes) > self.settings.max_png_bytes:
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_OUTPUT_LIMIT_EXCEEDED, message="PNG 超过 32MiB 上限。")
            )
        name = "page.png"
        path = artifact_dir / name
        path.write_bytes(png_bytes)
        self.execution.artifacts[name] = path
        digest = sha256_hex(png_bytes)
        viewport = self.execution.request.viewport
        result = self._base_result()
        result.artifacts.append(
            ArtifactDescriptor(
                name=name,
                content_type="image/png",
                byte_length=len(png_bytes),
                sha256=digest,
                width=int(viewport.width),
                height=int(viewport.height),
            )
        )
        return result

    async def _diagnose_page(self) -> ExecutionResult:
        """运行布局分析脚本，返回诊断与布局事实。"""

        raw = await self._page.evaluate(build_page_render_layout_script())
        layout = raw if isinstance(raw, dict) else {}
        diagnostics = _diagnostics_from_layout(layout)
        result = self._base_result()
        result.layout = layout
        result.diagnostics.extend(diagnostics)
        return result

    async def _diagnose_component(self) -> ExecutionResult:
        """在宿主中执行 default 与指定 presets。"""

        options = self.execution.request.operation_options or {}
        profile_key = str(options.get("profile_key") or "default")
        scenarios = list(options.get("scenarios") or [{"key": "default"}])
        if len(scenarios) > self.settings.max_component_scenarios:
            raise RenderExecutionError(
                RenderError.from_code(ERROR_CODE_OUTPUT_LIMIT_EXCEEDED, message="组件场景超过上限。")
            )
        script = build_component_render_layout_script()
        raw = await self._page.evaluate(script, {"profileKey": profile_key, "scenarios": scenarios})
        payload = raw if isinstance(raw, dict) else {}
        diagnostics = []
        for item in payload.get("diagnostics") or []:
            if not isinstance(item, dict):
                continue
            diagnostics.append(
                DiagnosticItem(
                    severity=str(item.get("severity") or "warning"),
                    code=str(item.get("code") or "COMPONENT_LAYOUT_WARNING"),
                    message=str(item.get("message") or ""),
                    scenario=(str(item["scenario_key"]) if item.get("scenario_key") else None),
                    evidence={"profile_key": item.get("profile_key") or profile_key},
                    truncated=bool(item.get("truncated", False)),
                )
            )
        result = self._base_result()
        result.layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else payload
        result.scenarios = list(payload.get("scenarios") or [])
        result.diagnostics.extend(diagnostics)
        return result

    def _base_result(self) -> ExecutionResult:
        """构造结果骨架；成功产物在清理前保持 retained，不得虚报 cleaned_at。"""

        request = self.execution.request
        slot_generation = int(
            getattr(self.execution, "slot_generation", None)
            if getattr(self.execution, "slot_generation", None) is not None
            else self.slot.slot_generation
        )
        return ExecutionResult(
            request_id=request.request_id,
            attempt_id=request.attempt_id,
            worker_id=self.slot.worker_id,
            worker_epoch=self.slot.worker_epoch,
            slot_generation=slot_generation,
            operation=request.operation,
            input_digest=request.input_digest,
            render_profile_digest=self.slot.settings.render_profile_digest,
            request_digest=request.request_digest,
            result_schema_version=RESULT_SCHEMA_VERSION,
            environment_summary={
                "render_profile_digest": self.slot.settings.render_profile_digest,
                "runtime_protocol_version": self.slot.settings.runtime_protocol_version,
                "worker_id": self.slot.worker_id,
                "worker_epoch": self.slot.worker_epoch,
            },
            finished_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            # 产物尚在 retained 状态，cleaned_at 留空，resource_state 与真实状态一致。
            cleaned_at="",
            resource_state="retained",
        )

    async def shutdown(self) -> None:
        """关闭 Context、浏览器与 Playwright；每个 closer 限时，幂等且可被取消路径复用。"""

        async with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
            closers = (
                self._context.close if self._context is not None else None,
                self._browser.close if self._browser is not None else None,
                self._playwright.stop if self._playwright is not None else None,
            )
            for closer in closers:
                if closer is None:
                    continue
                try:
                    await self._await_without_cancelling(closer(), timeout=_CLOSER_TIMEOUT_SECONDS)
                except (TimeoutError, asyncio.TimeoutError):
                    logger.warning("Renderer 浏览器资源关闭超时。")
                except Exception:  # noqa: BLE001
                    logger.warning("Renderer 浏览器资源关闭失败。", exc_info=True)
            if self._unsettled_tasks:
                _done, pending = await asyncio.wait(
                    set(self._unsettled_tasks),
                    timeout=_CLOSER_TIMEOUT_SECONDS,
                )
                if pending:
                    logger.warning("Renderer 仍有 %s 个底层 Playwright 任务未结束。", len(pending))
            self._context = None
            self._browser = None
            self._playwright = None
            self._page = None


def is_control_api_target(url: str) -> bool:
    """判断浏览器请求是否指向 Renderer 控制 API；浏览器网络不得访问控制面。"""

    try:
        parts = urlsplit(url)
    except Exception:  # noqa: BLE001
        return False
    path = parts.path or ""
    for prefix in _CONTROL_API_PATH_PREFIXES:
        if path.startswith(prefix) or path.startswith("/internal/render/v1"):
            return True
    try:
        from wp_renderer.config import get_renderer_settings

        control_ports = {int(get_renderer_settings().render_port)}
    except Exception:  # noqa: BLE001
        control_ports = {7400}
    host = (parts.hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"} and parts.port in control_ports:
        return True
    if host in {"127.0.0.1", "localhost", "::1"} and path.startswith("/internal/"):
        return True
    return False


def assert_safe_navigation_url(url: str) -> None:
    """导航 URL 白名单：仅 http/https，拦截云元数据与链路本地主机。"""

    raw = (url or "").strip()
    if not raw:
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_CONTRACT_MISMATCH,
                message="导航 URL 为空。",
                stage="admission",
            )
        )
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_CONTRACT_MISMATCH,
                message="导航 URL 无法解析。",
                stage="admission",
            )
        ) from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_NAVIGATION_SCHEMES:
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_CONTRACT_MISMATCH,
                message="导航 URL 仅允许 http/https。",
                stage="admission",
            )
        )
    host = (parts.hostname or "").lower().strip("[]")
    if not host:
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_CONTRACT_MISMATCH,
                message="导航 URL 缺少主机名。",
                stage="admission",
            )
        )
    if host in _BLOCKED_NAVIGATION_HOSTS or host.startswith("169.254."):
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_CONTRACT_MISMATCH,
                message="导航 URL 命中元数据/链路本地地址黑名单。",
                stage="admission",
            )
        )


def _parse_utc(raw: Any) -> datetime | None:
    """解析 ISO-8601 时间；非法值忽略以免拖垮预算计算。"""

    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def _route_preview_headers(route: Any, preview_access: Any) -> None:
    """仅初始预览文档请求附加 Runtime 预览鉴权头，不污染跨源资源。"""

    route_request = route.request
    url = route_request.url
    extra_headers = dict(getattr(preview_access, "extra_http_headers", None) or {})
    preview_token = getattr(preview_access, "preview_token", "") or ""

    should_attach = _should_attach_initial_preview_headers(
        request_url=url,
        preview_url=preview_access.navigation_base_url,
        is_navigation_request=_request_is_navigation(route_request),
        resource_type=str(route_request.resource_type or ""),
    )
    if should_attach:
        headers = {**route_request.headers}
        headers.update(extra_headers)
        if preview_token:
            headers.setdefault(RUNTIME_PREVIEW_CONTEXT_HEADER, preview_token)
        await route.continue_(headers=headers)
        return
    await route.continue_()


def _request_is_navigation(request: Any) -> bool:
    """读取 Playwright Request 导航判断方法，兼容测试替身的布尔属性。"""

    checker = getattr(request, "is_navigation_request", False)
    return bool(checker() if callable(checker) else checker)


def _should_attach_initial_preview_headers(
    *,
    request_url: str,
    preview_url: str,
    is_navigation_request: bool,
    resource_type: str,
) -> bool:
    """判断是否为需要 Runtime 预览鉴权头的首个文档请求。"""

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


def _diagnostics_from_layout(layout: dict[str, Any]) -> list[DiagnosticItem]:
    """把布局分析结果转换为内容诊断条目。"""

    items: list[DiagnosticItem] = []
    for overflow in layout.get("overflows") or []:
        if not isinstance(overflow, dict):
            continue
        items.append(
            DiagnosticItem(
                severity=str(overflow.get("severity") or "warning"),
                code=str(overflow.get("code") or "PAGE_RENDER_BOTTOM_OVERFLOW"),
                message=str(overflow.get("message") or "检测到布局溢出。"),
                evidence={"overflow": overflow},
                truncated=bool(layout.get("truncated", False)),
            )
        )
    summary = layout.get("summary") if isinstance(layout.get("summary"), dict) else {}
    if str(summary.get("attention") or "") in {"error", "likely_issue"}:
        items.append(
            DiagnosticItem(
                severity="error" if str(summary.get("attention")) == "error" else "warning",
                code=str(summary.get("code") or "PAGE_RENDER_LAYOUT_ERROR"),
                message=str(summary.get("message") or "页面布局分析需要关注。"),
                evidence={"summary": summary},
            )
        )
    return items
