"""文件功能：从受信部署配置解析渲染目标地址，不从 loopback 推断远端浏览器地址。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AppSettings, get_settings
from render_contracts.errors import ERROR_CODE_SERVICE_UNAVAILABLE, RenderError, RenderExecutionError


@dataclass(slots=True, frozen=True)
class WorkerEndpoint:
    """受信 Renderer Worker 地址与身份。"""

    worker_id: str
    base_url: str


class RenderTargetResolver:
    """唯一解析 Runtime 预览与资源基址的组件。"""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def navigation_base_url(self) -> str:
        """返回浏览器访问预览文档的基址。"""

        configured = (
            self.settings.render_runtime_navigation_base_url
            or self.settings.page_screenshot_runtime_public_base_url
            or self.settings.runtime_public_base_url
            or self.settings.runtime_base_url
        )
        return str(configured).rstrip("/")

    def asset_base_url(self) -> str:
        """返回浏览器访问 Runtime 静态资源的基址。"""

        configured = self.settings.render_runtime_asset_base_url or self.navigation_base_url()
        return str(configured).rstrip("/")

    def platform_asset_base_url(self) -> str:
        """返回浏览器访问平台资源的基址。"""

        configured = self.settings.render_platform_asset_base_url or self.settings.backend_public_base_url
        return str(configured).rstrip("/")

    def worker_endpoints(self) -> list[WorkerEndpoint]:
        """解析受信 Worker 地址列表；地址仅来自部署配置。"""

        endpoints: list[WorkerEndpoint] = []
        for item in self.settings.render_workers_config:
            worker_id = str(item.get("worker_id") or "").strip()
            base_url = str(item.get("base_url") or "").strip().rstrip("/")
            if not worker_id or not base_url:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_SERVICE_UNAVAILABLE,
                        message="RENDER_WORKERS_CONFIG 存在非法条目，必须同时提供 worker_id 与 base_url。",
                        stage="configuration",
                    )
                )
            endpoints.append(WorkerEndpoint(worker_id=worker_id, base_url=base_url))
        return endpoints
