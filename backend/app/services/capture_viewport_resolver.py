"""文件功能：统一解析页面截图视口配置，封装默认值与项目级结构化画布配置入口。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.page import Page
from app.schemas.project_app_config import ProjectAppPageConfig, DEFAULT_PAGE_HEIGHT, DEFAULT_PAGE_WIDTH


@dataclass(slots=True, frozen=True)
class CaptureViewport:
    """页面截图视口配置。"""

    width: int
    height: int


class CaptureViewportResolver:
    """截图视口解析器，统一处理显式参数、项目配置与系统默认值。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def resolve(
        self,
        page: Page,
        project_page_config: ProjectAppPageConfig | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> CaptureViewport:
        """解析本次截图应使用的视口尺寸。"""

        project_viewport = self._resolve_project_viewport(page, project_page_config)
        resolved_width = viewport_width or project_viewport.width or self.settings.page_screenshot_default_viewport_width
        resolved_height = viewport_height or project_viewport.height or self.settings.page_screenshot_default_viewport_height
        self._validate_dimension("viewport_width", resolved_width, self.settings.page_screenshot_max_viewport_width)
        self._validate_dimension("viewport_height", resolved_height, self.settings.page_screenshot_max_viewport_height)
        return CaptureViewport(width=resolved_width, height=resolved_height)

    def _resolve_project_viewport(self, page: Page, project_page_config: ProjectAppPageConfig | None = None) -> CaptureViewport:
        """从项目结构化配置读取页面尺寸，供截图链路复用。"""

        _ = page
        page_config = project_page_config or ProjectAppPageConfig(
            width=DEFAULT_PAGE_WIDTH,
            height=DEFAULT_PAGE_HEIGHT,
        )
        return CaptureViewport(width=page_config.width, height=page_config.height)

    @staticmethod
    def _validate_dimension(field_name: str, value: int, upper_bound: int) -> None:
        """校验单个维度为合理正整数，避免异常大图拖垮服务。"""

        if value <= 0:
            raise AppException(status_code=400, code="PAGE_SCREENSHOT_VIEWPORT_INVALID", detail=f"{field_name} 必须大于 0。")
        if value > upper_bound:
            raise AppException(
                status_code=400,
                code="PAGE_SCREENSHOT_VIEWPORT_INVALID",
                detail=f"{field_name} 不能超过 {upper_bound}。",
            )
