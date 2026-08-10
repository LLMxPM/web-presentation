"""文件功能：通过共享 Playwright 池检查组件预览默认态与 presets 的真实渲染、运行时错误和布局事实。"""

from __future__ import annotations

import logging
import uuid
from app.core.config import get_settings
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.component_render_layout_script import build_component_render_layout_script
from app.services.component_render_result import (
    COMPONENT_RENDER_SOURCE,
    build_component_diagnostic,
    build_component_layout_diagnostics,
    has_component_errors,
)
from app.services.component_render_scenarios import (
    COMPONENT_SCENARIO_LIMIT,
    ComponentRenderScenario,
    build_component_render_scenarios,
)
from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService, PageRenderDiagnosticsTarget
from app.services.playwright_task_queue import PlaywrightTaskQueue, get_playwright_task_queue

COMPONENT_VALIDATION_PROFILE_VERSION = "component-profiles.v1"

logger = logging.getLogger(__name__)


class ComponentCandidateRenderError(RuntimeError):
    """候选组件自身导致的确定性预览失败，不应归类为基础设施不可用。"""

    def __init__(self, message: str, *, scenario_key: str = "default") -> None:
        super().__init__(message)
        self.scenario_key = scenario_key


class ComponentRenderDiagnosticsService:
    """组件真实渲染诊断服务，布局启发式 warning 与确定性运行错误分开返回。"""

    def __init__(self, playwright_task_queue: PlaywrightTaskQueue | None = None) -> None:
        self.settings = get_settings()
        self.playwright_task_queue = playwright_task_queue or get_playwright_task_queue()
        self.preview_support = PageRenderDiagnosticsService(self.playwright_task_queue)

    async def diagnose_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        profile_key: str,
    ) -> dict[str, object]:
        """打开组件预览并返回 default/presets 的运行和布局诊断。"""

        try:
            target = self.preview_support._build_browser_target(preview_url)  # noqa: SLF001
            return await self.playwright_task_queue.run_with_browser(
                "component-render-diagnostics",
                self._diagnose_with_browser,
                target,
                viewport,
                profile_key,
                timeout_ms=int(self.settings.page_screenshot_timeout_seconds * 1000),
                visual_ready_timeout_ms=int(self.settings.page_screenshot_visual_ready_timeout_seconds * 1000),
                priority="interactive",
            )
        except ComponentCandidateRenderError as error:
            return {
                "status": "failed",
                "retryable": False,
                "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
                "diagnostics": [build_component_diagnostic(
                    severity="error",
                    source=COMPONENT_RENDER_SOURCE,
                    code="COMPONENT_PREVIEW_BOOTSTRAP_FAILED",
                    message=str(error),
                    scenario_key=error.scenario_key,
                    profile_key=profile_key,
                    suggestion="检查组件初始化、默认 props、preset 状态和运行时依赖。",
                )],
                "scenarios": [{
                    "key": error.scenario_key,
                    "profile_key": profile_key,
                    "status": "failed",
                    "diagnostic_count": 1,
                }],
            }
        except Exception as error:  # noqa: BLE001
            logger.warning("组件真实渲染诊断不可用。", exc_info=True)
            return {
                "status": "unavailable",
                "retryable": True,
                "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
                "diagnostics": [{
                    "severity": "error",
                    "stage": "render",
                    "source": "infrastructure",
                    "code": "COMPONENT_CHECK_UNAVAILABLE",
                    "message": f"组件真实渲染诊断不可用：{self.preview_support._sanitize_error_message(error)}",  # noqa: SLF001
                    "profile_key": profile_key,
                }],
                "scenarios": [],
            }

    def _diagnose_with_browser(
        self,
        browser: object,
        target: PageRenderDiagnosticsTarget,
        viewport: CaptureViewport,
        profile_key: str,
        *,
        timeout_ms: int,
        visual_ready_timeout_ms: int,
    ) -> dict[str, object]:
        """在池内浏览器线程中执行组件多场景诊断。"""

        context = browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        try:
            context.add_init_script(
                """
                window.__COMPONENT_CHECK_MESSAGES__ = [];
                window.addEventListener('message', (event) => {
                  const data = event && event.data;
                  if (data && typeof data === 'object' && typeof data.type === 'string'
                      && data.type.startsWith('component-preview:')) {
                    window.__COMPONENT_CHECK_MESSAGES__.push(data);
                  }
                });
                """
            )
            page = context.new_page()
            runtime_errors: list[str] = []
            console_errors: list[str] = []
            page.on("pageerror", lambda error: runtime_errors.append(str(error)))
            page.on("console", lambda message: self._collect_console_error(message, console_errors))
            self.preview_support._install_initial_preview_header_route(  # noqa: SLF001
                page,
                target.preview_url,
                target.extra_http_headers,
            )
            page.goto(target.preview_url, wait_until="domcontentloaded", timeout=timeout_ms)
            ready_payload = self._wait_for_bootstrap(page, timeout_ms)
            self._wait_for_default_settled(page, timeout_ms)
            self._wait_for_fonts(page)

            scenarios, truncated_count = build_component_render_scenarios(ready_payload)
            diagnostics: list[dict[str, object]] = []
            scenario_results: list[dict[str, object]] = []
            if truncated_count:
                diagnostics.append(build_component_diagnostic(
                    severity="warning",
                    source="component-check",
                    code="COMPONENT_CHECK_SCENARIOS_TRUNCATED",
                    message=f"preset 数量超过检查上限，另有 {truncated_count} 个场景未执行。",
                    profile_key=profile_key,
                    facts={"skipped_count": truncated_count, "limit": COMPONENT_SCENARIO_LIMIT},
                ))

            for index, scenario in enumerate(scenarios):
                runtime_errors.clear()
                console_errors.clear()
                if index > 0:
                    self._apply_scenario(page, scenario, timeout_ms)
                scenario_diagnostics = self._diagnose_scenario(
                    page,
                    scenario=scenario,
                    profile_key=profile_key,
                    runtime_errors=runtime_errors,
                    console_errors=console_errors,
                    visual_ready_timeout_ms=visual_ready_timeout_ms,
                )
                diagnostics.extend(scenario_diagnostics)
                scenario_results.append({
                    "key": scenario.key,
                    "profile_key": profile_key,
                    "status": "failed" if has_component_errors(scenario_diagnostics) else (
                        "passed_with_warnings" if scenario_diagnostics else "passed"
                    ),
                    "diagnostic_count": len(scenario_diagnostics),
                })

            status = "failed" if has_component_errors(diagnostics) else (
                "passed_with_warnings" if diagnostics else "passed"
            )
            return {
                "status": status,
                "retryable": False,
                "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
                "diagnostics": diagnostics,
                "scenarios": scenario_results,
            }
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                logger.warning("组件渲染诊断 BrowserContext 关闭失败。", exc_info=True)

    @staticmethod
    def _wait_for_bootstrap(page: object, timeout_ms: int) -> dict[str, object]:
        """等待组件预览 ready/error 握手并返回 ready payload。"""

        page.wait_for_function(
            """
            () => window.__COMPONENT_CHECK_MESSAGES__.some((item) =>
              item.type === 'component-preview:ready' || item.type === 'component-preview:error')
            """,
            timeout=timeout_ms,
        )
        message = page.evaluate(
            """
            () => window.__COMPONENT_CHECK_MESSAGES__.find((item) =>
              item.type === 'component-preview:error' || item.type === 'component-preview:ready')
            """
        )
        if isinstance(message, dict) and message.get("type") == "component-preview:error":
            payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
            raise ComponentCandidateRenderError(str(payload.get("message") or "组件预览启动失败。"))
        payload = message.get("payload") if isinstance(message, dict) else None
        if not isinstance(payload, dict):
            raise ComponentCandidateRenderError("组件预览 ready 消息缺少有效 payload。")
        return payload

    @staticmethod
    def _wait_for_default_settled(page: object, timeout_ms: int) -> None:
        """等待默认场景完成 Vue 更新和浏览器绘制。"""

        page.wait_for_function(
            """
            () => window.__COMPONENT_CHECK_MESSAGES__.some((item) =>
              item.type === 'component-preview:render-settled' && !item.payload?.requestId)
            """,
            timeout=timeout_ms,
        )

    @staticmethod
    def _wait_for_fonts(page: object) -> None:
        """等待字体加载，避免字体切换造成测量抖动。"""

        page.evaluate(
            """
            async () => {
              if (document.fonts && document.fonts.ready) await document.fonts.ready;
            }
            """
        )

    @staticmethod
    def _apply_scenario(page: object, scenario: ComponentRenderScenario, timeout_ms: int) -> None:
        """切换一个 preset，并等待带请求标识的 settled/error 消息。"""

        request_id = uuid.uuid4().hex
        page.evaluate(
            """
            ({ requestId, state }) => window.postMessage({
              type: 'component-preview:update-state',
              payload: {
                version: 1,
                artifactId: window.__RUNTIME_PREVIEW_CONTEXT__?.artifactId,
                requestId,
                state,
              },
            }, '*')
            """,
            {"requestId": request_id, "state": scenario.state},
        )
        page.wait_for_function(
            """
            (requestId) => window.__COMPONENT_CHECK_MESSAGES__.some((item) =>
              (item.type === 'component-preview:render-settled' && item.payload?.requestId === requestId)
              || item.type === 'component-preview:error')
            """,
            request_id,
            timeout=timeout_ms,
        )
        error_message = page.evaluate(
            """
            () => [...window.__COMPONENT_CHECK_MESSAGES__].reverse().find((item) =>
              item.type === 'component-preview:error')
            """
        )
        if isinstance(error_message, dict):
            payload = error_message.get("payload") if isinstance(error_message.get("payload"), dict) else {}
            raise ComponentCandidateRenderError(
                str(payload.get("message") or f"{scenario.key} 渲染失败。"),
                scenario_key=scenario.key,
            )

    def _diagnose_scenario(
        self,
        page: object,
        *,
        scenario: ComponentRenderScenario,
        profile_key: str,
        runtime_errors: list[str],
        console_errors: list[str],
        visual_ready_timeout_ms: int,
    ) -> list[dict[str, object]]:
        """收集单场景的运行时、资源和布局诊断。"""

        diagnostics: list[dict[str, object]] = []
        for message in dict.fromkeys([*runtime_errors, *console_errors]):
            diagnostics.append(build_component_diagnostic(
                severity="error",
                source=COMPONENT_RENDER_SOURCE,
                code="COMPONENT_RENDER_RUNTIME_ERROR",
                message=message,
                scenario_key=scenario.key,
                profile_key=profile_key,
            ))

        visual_result = page.evaluate(
            """
            async (timeoutMs) => {
              const waitForVisualAssets = window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__;
              if (typeof waitForVisualAssets !== 'function') return { ok: true, skipped: true };
              return await waitForVisualAssets({ timeoutMs });
            }
            """,
            visual_ready_timeout_ms,
        )
        if not isinstance(visual_result, dict) or not visual_result.get("ok", False):
            diagnostics.append(build_component_diagnostic(
                severity="warning",
                source=COMPONENT_RENDER_SOURCE,
                code="COMPONENT_RENDER_ASSET_NOT_READY",
                message=f"{scenario.key} 的视觉资源未在限定时间内就绪。",
                scenario_key=scenario.key,
                profile_key=profile_key,
            ))

        layout = page.evaluate(build_component_render_layout_script())
        diagnostics.extend(build_component_layout_diagnostics(layout, scenario.key, profile_key))
        return diagnostics

    @staticmethod
    def _collect_console_error(message: object, target: list[str]) -> None:
        """只收集浏览器 console error，忽略普通 warning 和日志。"""

        if str(getattr(message, "type", "")) == "error":
            text = str(getattr(message, "text", "") or "").strip()
            if text:
                target.append(text)
