"""文件功能：在固定专属线程中维护可复用的 Playwright 与 Chromium 实例。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


class PlaywrightBrowserMissingError(RuntimeError):
    """表示部署环境缺少 Playwright Python 包或 Chromium 浏览器。"""


class PlaywrightBrowserWorker:
    """绑定单个线程的浏览器执行器；所有公开方法都必须在所属线程调用。"""

    def __init__(
        self,
        *,
        slot_id: int,
        executable_path: str | None,
        reuse_enabled: bool,
        recycle_task_count: int,
        recycle_age_seconds: float,
    ) -> None:
        self.slot_id = slot_id
        self.executable_path = executable_path
        self.reuse_enabled = reuse_enabled
        self.recycle_task_count = max(1, int(recycle_task_count))
        self.recycle_age_seconds = max(1.0, float(recycle_age_seconds))
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._browser_started_at = 0.0
        self._browser_task_count = 0

    def run_plain(self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """在专属线程执行不需要浏览器实例的兼容任务。"""

        return func(*args, **kwargs)

    def run_with_browser(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """使用当前槽位浏览器执行任务；浏览器断开时只重建并重试一次。"""

        self._recycle_if_needed()
        browser = self._ensure_browser()
        try:
            result = func(browser, *args, **kwargs)
        except Exception:
            if self._is_browser_connected(browser):
                raise
            logger.warning(
                "Playwright 浏览器连接中断，重建后重试当前任务。",
                extra={"event": "playwright.browser.reconnect", "slot_id": self.slot_id},
                exc_info=True,
            )
            self._close_browser()
            browser = self._ensure_browser()
            result = func(browser, *args, **kwargs)
        finally:
            self._browser_task_count += 1
            if not self.reuse_enabled:
                self._close_browser()
        return result

    def close(self) -> None:
        """关闭浏览器和 Playwright 驱动；应用退出时由所属专属线程调用。"""

        self._close_browser()
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                logger.warning("Playwright 驱动关闭失败。", exc_info=True)
            finally:
                self._playwright = None

    def _ensure_browser(self) -> Any:
        """懒加载 Playwright 与 Chromium，并记录轮换基线。"""

        if self._browser is not None and self._is_browser_connected(self._browser):
            return self._browser

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - 部署依赖问题
            raise PlaywrightBrowserMissingError("未安装 Playwright Python 包。") from error

        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                executable_path=self.executable_path or None,
            )
        except Exception as error:  # noqa: BLE001
            self.close()
            raise PlaywrightBrowserMissingError(f"Chromium 启动失败：{error}") from error

        self._browser_started_at = time.monotonic()
        self._browser_task_count = 0
        logger.info(
            "Playwright 浏览器槽位已启动。",
            extra={"event": "playwright.browser.started", "slot_id": self.slot_id},
        )
        return self._browser

    def _recycle_if_needed(self) -> None:
        """达到任务数、存活时间或断线阈值时回收浏览器。"""

        if self._browser is None:
            return
        expired = self._browser_started_at > 0 and (
            time.monotonic() - self._browser_started_at >= self.recycle_age_seconds
        )
        if (
            self._browser_task_count >= self.recycle_task_count
            or expired
            or not self._is_browser_connected(self._browser)
        ):
            self._close_browser()

    def _close_browser(self) -> None:
        """尽力关闭当前 Chromium，不因清理失败阻断后续重建。"""

        browser = self._browser
        self._browser = None
        self._browser_started_at = 0.0
        self._browser_task_count = 0
        if browser is None:
            return
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            logger.warning("Playwright 浏览器关闭失败。", exc_info=True)

    @staticmethod
    def _is_browser_connected(browser: Any) -> bool:
        """兼容真实与测试浏览器对象地判断连接状态。"""

        checker = getattr(browser, "is_connected", None)
        if checker is None:
            return True
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            return False
