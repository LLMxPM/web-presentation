"""文件功能：远程截图业务入口，通过统一渲染请求链路产出 PNG，不再持有浏览器。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.rendering.domain_facade import RenderDomainFacade
from app.services.rendering.errors import render_error_to_app_exception
from render_contracts.errors import RenderError, RenderExecutionError

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class BrowserCaptureJob:
    """批量截图中的单个渲染任务。"""

    key: int
    preview_url: str
    viewport: CaptureViewport
    extra_http_headers: Mapping[str, str] | None = None
    logical_owner_key: str | None = None
    workspace_id: int | None = None
    project_id: int | None = None
    page_id: int | None = None
    artifact_id: str | None = None
    preview_token: str | None = None


@dataclass(slots=True, frozen=True)
class BrowserCaptureJobResult:
    """批量截图中单个任务的结果。"""

    key: int
    content: bytes | None = None
    error: Exception | None = None


class BrowserCaptureService:
    """页面截图业务入口，创建渲染请求并消费远端执行结果。"""

    def __init__(self, session: AsyncSession | None = None, facade: RenderDomainFacade | None = None) -> None:
        self.settings = get_settings()
        self.facade = facade or RenderDomainFacade(session)

    async def capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers: Mapping[str, str] | None = None,
        logical_owner_key: str | None = None,
        workspace_id: int | None = None,
        project_id: int | None = None,
        page_id: int | None = None,
        artifact_id: str | None = None,
        preview_token: str | None = None,
        session: AsyncSession | None = None,
        facade: RenderDomainFacade | None = None,
    ) -> bytes:
        """打开预览地址并按给定视口生成截图内容。"""

        if workspace_id is None or int(workspace_id) <= 0:
            raise AppException(
                status_code=500,
                code="RENDER_INTERNAL_ERROR",
                detail="页面截图必须提供合法 workspace_id，拒绝写入非法渲染请求。",
            )
        if facade is not None:
            target_facade = facade
        elif session is not None:
            target_facade = RenderDomainFacade(session)
        else:
            target_facade = self.facade
        from app.services.rendering.domain_facade import sanitize_owner_key

        safe_url = sanitize_owner_key(preview_url)
        owner_key = (logical_owner_key or f"page-screenshot:{safe_url}:{viewport.width}x{viewport.height}")[:128]
        timeout = float(self.settings.render_request_timeout_seconds)
        try:
            return await target_facade.capture_page_preview(
                preview_url=preview_url,
                viewport={"width": viewport.width, "height": viewport.height, "device_scale_factor": 1},
                logical_owner_key=owner_key,
                workspace_id=int(workspace_id),
                project_id=project_id,
                page_id=page_id,
                artifact_id=artifact_id,
                preview_token=preview_token,
                extra_http_headers=extra_http_headers,
                timeout_seconds=timeout,
            )
        except AppException:
            raise
        except RenderExecutionError as error:
            raise render_error_to_app_exception(error.error) from error
        except Exception as error:  # noqa: BLE001
            from app.services.rendering.errors import render_error_from_exception
            from app.services.rendering.sanitize import sanitize_error_message, sanitize_url

            logger.exception(
                "页面截图失败：preview_url=%s viewport=%sx%s",
                sanitize_url(preview_url),
                viewport.width,
                viewport.height,
            )
            mapped = render_error_from_exception(error, stage="capture")
            raise render_error_to_app_exception(
                RenderError.from_code(
                    mapped.code,
                    message=sanitize_error_message(mapped.message),
                    stage=mapped.stage,
                    retryable=mapped.retryable,
                )
            ) from error

    async def capture_preview_batch(
        self,
        jobs: list[BrowserCaptureJob],
        *,
        max_concurrency: int | None = None,
        session: AsyncSession | None = None,
    ) -> list[BrowserCaptureJobResult]:
        """按并发上限独立执行截图任务，并保留逐项失败结果。

        AsyncSession 不可跨 asyncio.gather 并发共用；批量路径为每个任务
        创建独立 RenderDomainFacade，不复用 self.facade 或外部 session。
        """

        if not jobs:
            return []
        batch_concurrency = max(1, int(max_concurrency or self.settings.page_screenshot_batch_concurrency))
        semaphore = asyncio.Semaphore(batch_concurrency)

        async def run_job(job: BrowserCaptureJob) -> BrowserCaptureJobResult:
            """在批量截图中独立执行单页任务，强制使用独立领域门面。"""

            async with semaphore:
                try:
                    job_facade = RenderDomainFacade(None)
                    content = await self.capture_preview(
                        job.preview_url,
                        job.viewport,
                        extra_http_headers=job.extra_http_headers,
                        logical_owner_key=job.logical_owner_key,
                        workspace_id=job.workspace_id,
                        project_id=job.project_id,
                        page_id=job.page_id,
                        artifact_id=job.artifact_id,
                        preview_token=job.preview_token,
                        session=None,
                        facade=job_facade,
                    )
                    return BrowserCaptureJobResult(key=job.key, content=content)
                except AppException as error:
                    return BrowserCaptureJobResult(key=job.key, error=error)
                except Exception as error:  # noqa: BLE001
                    from app.services.rendering.errors import render_error_from_exception
                    from app.services.rendering.sanitize import sanitize_error_message, sanitize_url

                    logger.exception(
                        "页面批量截图出现未预期异常：preview_url=%s",
                        sanitize_url(job.preview_url),
                    )
                    mapped = render_error_from_exception(error, stage="capture")
                    return BrowserCaptureJobResult(
                        key=job.key,
                        error=render_error_to_app_exception(
                            RenderError.from_code(
                                mapped.code,
                                message=sanitize_error_message(mapped.message),
                                stage=mapped.stage,
                                retryable=mapped.retryable,
                            )
                        ),
                    )

        return await asyncio.gather(*[run_job(job) for job in jobs])
