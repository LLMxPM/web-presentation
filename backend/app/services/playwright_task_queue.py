"""文件功能：兼容旧导入路径并导出新的共享 Playwright 浏览器池。"""

from app.services.playwright_browser_pool import (
    PlaywrightBrowserPool,
    get_playwright_browser_pool,
)


# 旧类名和 getter 保留，避免现有服务、扩展与测试发生不必要的接口中断。
PlaywrightTaskQueue = PlaywrightBrowserPool


def get_playwright_task_queue() -> PlaywrightBrowserPool:
    """返回共享浏览器池；函数名仅用于兼容旧调用。"""

    return get_playwright_browser_pool()


__all__ = [
    "PlaywrightBrowserPool",
    "PlaywrightTaskQueue",
    "get_playwright_browser_pool",
    "get_playwright_task_queue",
]
