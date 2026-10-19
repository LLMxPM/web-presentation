"""文件功能：页面渲染诊断业务入口，通过远程渲染请求返回布局事实与 warning。"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.rendering.domain_facade import RenderDomainFacade
from app.services.rendering.target_resolver import RenderTargetResolver
from app.services.runtime_target_router import RUNTIME_SERVICE_TOKEN_HEADER
from app.services.token_service import TokenService
from render_contracts.errors import (
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_SERVICE_UNAVAILABLE,
)

PAGE_RENDER_WARNING_SOURCE = "runtime-render"
PAGE_RENDER_BOTTOM_OVERFLOW_CODE = "PAGE_RENDER_BOTTOM_OVERFLOW"
PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE = "RENDER_SERVICE_UNAVAILABLE"
PAGE_RENDER_PREVIEW_TOKEN_INVALID_CODE = "PAGE_RENDER_PREVIEW_TOKEN_INVALID"
LAYOUT_ANALYSIS_SCHEMA_VERSION = 3

# 与截图链路一致的 Runtime 直连请求头；Renderer 只向初始预览文档附加这些头。
RUNTIME_PREVIEW_CONTEXT_HEADER = "x-runtime-preview-context"
RUNTIME_PUBLIC_BASE_URL_HEADER = "x-runtime-public-base-url"

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PageRenderDiagnosticsTarget:
    """页面渲染诊断浏览器实际访问的地址与额外请求头。"""

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
        source_override: str | None = None,
        capture_screenshot: bool = False,
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
            # 公开预览地址（Backend 桥接宿主页）不能作为无头浏览器导航目标：
            # 宿主页顶层没有 render-ready 协议，Renderer 会等到硬期限。必须还原为
            # Runtime 直连目标，与截图链路共用「初始文档请求头 + 查询串身份」约定。
            target = self._build_browser_target(preview_url)
            return await facade.diagnose_page_preview(
                preview_url=target.preview_url,
                viewport={"width": viewport.width, "height": viewport.height, "device_scale_factor": 1},
                logical_owner_key=owner_key,
                workspace_id=int(workspace_id),
                project_id=project_id,
                page_id=page_id,
                artifact_id=artifact_id,
                preview_token=preview_token,
                source_override=source_override,
                **({"capture_screenshot": True} if capture_screenshot else {}),
                timeout_seconds=float(self.settings.render_request_timeout_seconds),
                extra_http_headers=target.extra_http_headers,
            )
        except AppException as exc:
            if exc.code in {
                ERROR_CODE_SERVICE_UNAVAILABLE,
                ERROR_CODE_INTERNAL_ERROR,
                "RENDER_BROWSER_LOST",
                "RENDER_QUEUE_FULL",
                ERROR_CODE_DEADLINE_EXCEEDED,
                "RENDER_RESULT_LOST",
                PAGE_RENDER_PREVIEW_TOKEN_INVALID_CODE,
            }:
                return self._build_unavailable_result(
                    exc.detail,
                    defer_artifact_cleanup=exc.code == ERROR_CODE_DEADLINE_EXCEEDED,
                )
            raise

    def _build_browser_target(self, preview_url: str) -> PageRenderDiagnosticsTarget:
        """把公开预览地址转换为 Runtime 直连诊断目标；无票据时原样透传。"""

        preview_token = self._extract_preview_token(preview_url)
        if not preview_token:
            return PageRenderDiagnosticsTarget(preview_url=preview_url)
        try:
            preview_claims = TokenService.verify_preview_context_token(preview_token)
        except Exception as exc:  # noqa: BLE001
            raise AppException(
                status_code=502,
                code=PAGE_RENDER_PREVIEW_TOKEN_INVALID_CODE,
                detail="渲染诊断预览上下文令牌非法或已过期。",
            ) from exc
        artifact_id = str(preview_claims.get("artifact_id") or "").strip()
        if not artifact_id:
            raise AppException(
                status_code=502,
                code=PAGE_RENDER_PREVIEW_TOKEN_INVALID_CODE,
                detail="渲染诊断预览上下文缺少 artifact_id。",
            )
        runtime_service_token = TokenService.generate_runtime_service_access_token(
            artifact_id=artifact_id,
            expires_in_seconds=TokenService.resolve_preview_service_token_ttl(preview_claims),
        )
        targets = RenderTargetResolver(self.settings)
        return PageRenderDiagnosticsTarget(
            preview_url=f"{targets.navigation_base_url()}/__preview",
            extra_http_headers={
                RUNTIME_PREVIEW_CONTEXT_HEADER: preview_token,
                RUNTIME_SERVICE_TOKEN_HEADER: runtime_service_token,
                RUNTIME_PUBLIC_BASE_URL_HEADER: self._resolve_browser_runtime_public_base_url(targets),
            },
        )

    @staticmethod
    def _resolve_browser_runtime_public_base_url(targets: RenderTargetResolver) -> str:
        """返回诊断浏览器可访问的 Runtime 资源基址，与截图链路保持同一解析规则。"""

        configured = str(get_settings().page_screenshot_runtime_public_base_url or "").strip().rstrip("/")
        return configured or targets.asset_base_url()

    @staticmethod
    def _extract_preview_token(preview_url: str) -> str:
        """从公开预览 URL 读取 token 查询参数；测试替身 URL 允许为空。"""

        query = parse_qs(urlsplit(preview_url).query)
        return str((query.get("token") or [""])[0]).strip()

    @staticmethod
    def _build_unavailable_result(
        message: str,
        *,
        defer_artifact_cleanup: bool = False,
    ) -> dict[str, object]:
        """执行不可用：明确标注基础设施故障，并保持布局契约完整。

        severity 使用 warning 而非 error，避免下游把基础设施故障汇总成内容错误。
        """

        from app.services.rendering.layout_contract import empty_layout_analysis
        from app.services.rendering.sanitize import sanitize_error_message

        result: dict[str, object] = {
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
        if defer_artifact_cleanup:
            result["_render_artifact_cleanup_deferred"] = True
        return result

    @staticmethod
    def _sanitize_error_message(error: object) -> str:
        """脱敏错误摘要。"""

        text = str(error) if error else "未知错误"
        return text[:300]
