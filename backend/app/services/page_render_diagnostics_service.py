"""文件功能：页面渲染诊断业务入口，通过远程渲染请求返回布局事实与 warning。"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.rendering.domain_facade import RenderDomainFacade
from render_contracts.errors import ERROR_CODE_INTERNAL_ERROR, ERROR_CODE_SERVICE_UNAVAILABLE

PAGE_RENDER_WARNING_SOURCE = "runtime-render"
PAGE_RENDER_BOTTOM_OVERFLOW_CODE = "PAGE_RENDER_BOTTOM_OVERFLOW"
PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE = "RENDER_SERVICE_UNAVAILABLE"
LAYOUT_ANALYSIS_SCHEMA_VERSION = 3

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PageRenderDiagnosticsTarget:
    """页面渲染诊断目标描述，兼容既有调用方字段。"""

    preview_url: str
    extra_http_headers: Mapping[str, str] | None = None


class PageRenderDiagnosticsService:
    """页面渲染诊断服务，执行不可用时返回基础设施结论，不把内容 warning 当失败。"""

    def __init__(self, session: AsyncSession | None = None, facade: RenderDomainFacade | None = None) -> None:
        self.settings = get_settings()
        self.facade = facade or RenderDomainFacade(session)

    async def diagnose_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        logical_owner_key: str | None = None,
        workspace_id: int | None = None,
        project_id: int | None = None,
        page_id: int | None = None,
        artifact_id: str | None = None,
        preview_token: str | None = None,
        session: AsyncSession | None = None,
    ) -> dict[str, object]:
        """打开页面预览并返回固定画布诊断与文本布局分析。"""

        if workspace_id is None or int(workspace_id) <= 0:
            raise AppException(
                status_code=500,
                code="RENDER_INTERNAL_ERROR",
                detail="页面渲染诊断必须提供合法 workspace_id，拒绝写入非法渲染请求。",
            )
        facade = self.facade if session is None else RenderDomainFacade(session)
        from app.services.rendering.domain_facade import sanitize_owner_key

        safe_url = sanitize_owner_key(preview_url)
        owner_key = (logical_owner_key or f"page-diagnose:{safe_url}:{viewport.width}x{viewport.height}")[:128]
        try:
            return await facade.diagnose_page_preview(
                preview_url=preview_url,
                viewport={"width": viewport.width, "height": viewport.height, "device_scale_factor": 1},
                logical_owner_key=owner_key,
                workspace_id=int(workspace_id),
                project_id=project_id,
                page_id=page_id,
                artifact_id=artifact_id,
                preview_token=preview_token,
                timeout_seconds=float(self.settings.render_request_timeout_seconds),
            )
        except AppException as exc:
            if exc.code in {
                ERROR_CODE_SERVICE_UNAVAILABLE,
                ERROR_CODE_INTERNAL_ERROR,
                "RENDER_BROWSER_LOST",
                "RENDER_QUEUE_FULL",
                "RENDER_DEADLINE_EXCEEDED",
                "RENDER_RESULT_LOST",
            }:
                return self._build_unavailable_result(exc.detail)
            raise

    @staticmethod
    def _build_unavailable_result(message: str) -> dict[str, object]:
        """执行不可用：明确标注基础设施故障，并保持布局契约完整。

        severity 使用 warning 而非 error，避免下游把基础设施故障汇总成内容错误。
        """

        from app.services.rendering.layout_contract import empty_layout_analysis
        from app.services.rendering.sanitize import sanitize_error_message

        return {
            "status": "unavailable",
            "retryable": True,
            "diagnostics": [
                {
                    "severity": "warning",
                    "stage": "render",
                    "source": "infrastructure",
                    "code": PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE,
                    "message": f"页面渲染布局诊断执行不可用：{sanitize_error_message(message)}",
                }
            ],
            "layout_analysis": empty_layout_analysis(
                message="渲染执行不可用，未产出布局分析。",
                truncated=True,
            ),
        }

    @staticmethod
    def _sanitize_error_message(error: object) -> str:
        """脱敏错误摘要。"""

        text = str(error) if error else "未知错误"
        return text[:300]
