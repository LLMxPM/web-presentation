"""文件功能：编排页面预览、截图和文件落库流程，对外提供页面截图保存能力。"""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import normalize_utc, utc_now
from app.models.enums import PageFileType
from app.models.page import Page
from app.schemas.page import (
    PageItem,
    PageScreenshotBatchFailure,
    PageScreenshotBatchRefreshResponse,
)
from app.services.auth_service import AuthContext
from app.services.browser_capture_service import BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewport, CaptureViewportResolver
from app.services.object_storage_service import ObjectStorageService
from app.services.page_preview_service import PagePreviewResult, PagePreviewService
from app.services.page_service import PageService
from app.services.project_config_service import ProjectConfigService
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService
from app.services.token_service import TokenService

RUNTIME_SERVICE_TOKEN_HEADER = "x-runtime-service-token"
RUNTIME_PREVIEW_CONTEXT_HEADER = "x-runtime-preview-context"
RUNTIME_PUBLIC_BASE_URL_HEADER = "x-runtime-public-base-url"
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PageScreenshotResult:
    """页面截图查询结果，包含最新对象内容和本次是否刷新。"""

    page: Page
    page_item: PageItem
    storage_key: str
    content: bytes
    refreshed: bool
    public_url: str


@dataclass(slots=True, frozen=True)
class PageScreenshotCaptureTarget:
    """截图浏览器实际访问的地址和额外请求头。"""

    preview_url: str
    extra_http_headers: dict[str, str] | None = None


@dataclass(slots=True, frozen=True)
class PageScreenshotCaptureArtifact:
    """一次截图捕获产物，使用任务快照生成不可变对象键，尚未发布到页面元数据。"""

    storage_key: str
    page_version_no: int
    config_hash: str
    viewport_width: int
    viewport_height: int


class PageScreenshotService:
    """页面截图服务，统一处理截图参数解析、内容生成与覆盖保存。"""

    def __init__(
        self,
        session: AsyncSession,
        page_service: PageService | None = None,
        preview_service: PagePreviewService | None = None,
        viewport_resolver: CaptureViewportResolver | None = None,
        browser_capture_service: BrowserCaptureService | None = None,
        object_storage_service: ObjectStorageService | None = None,
        project_config_service: ProjectConfigService | None = None,
        screenshot_fingerprint_service: PageScreenshotFingerprintService | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.page_service = page_service or PageService(session)
        self.preview_service = preview_service or PagePreviewService(session)
        self.viewport_resolver = viewport_resolver or CaptureViewportResolver()
        self.browser_capture_service = browser_capture_service or BrowserCaptureService()
        self.object_storage_service = object_storage_service or ObjectStorageService()
        self.project_config_service = project_config_service or ProjectConfigService(session)
        self.screenshot_fingerprint_service = screenshot_fingerprint_service or PageScreenshotFingerprintService(
            session,
            project_config_service=self.project_config_service,
        )

    async def save_page_screenshot(
        self,
        page_id: int,
        current: AuthContext,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> PageItem:
        """兼容旧同步接口：提交截图 Job 并等待终态，不直接绕过持久化队列。"""

        # 延迟导入避免截图 Job 服务与本服务在模块加载阶段互相引用。
        from app.services.page_screenshot_job_service import PageScreenshotJobService

        user_id = current.user.id
        job = await PageScreenshotJobService(self.session).create_page_screenshot_job(
            page_id=page_id,
            current=current,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        terminal = await PageScreenshotJobService.wait_for_job_terminal_detached(
            job.id,
            timeout_seconds=self.settings.page_screenshot_ai_wait_timeout_seconds,
        )
        PageScreenshotJobService._raise_if_job_stale(terminal)
        if terminal.status == "cancelled":
            raise AppException(status_code=409, code="PAGE_SCREENSHOT_JOB_CANCELLED", detail="页面截图任务已取消。")
        if terminal.status == "failed":
            raise AppException(
                status_code=502,
                code=terminal.error_code or "PAGE_SCREENSHOT_JOB_FAILED",
                detail=terminal.error_message or "页面截图任务执行失败。",
        )
        self.session.expire_all()
        return await self.page_service.get(page_id, user_id=user_id)

    async def batch_refresh_project_screenshots(
        self,
        *,
        project_id: int,
        current: AuthContext,
        source: str = "batch_refresh",
    ) -> PageScreenshotBatchRefreshResponse:
        """兼容旧批量接口：创建任务组并等待终态，避免直接并发启动 Chromium。"""

        # 延迟导入避免本服务和任务服务形成模块循环。
        from app.services.page_screenshot_job_service import PageScreenshotJobService

        job_service = PageScreenshotJobService(self.session)
        group = await job_service.create_batch_refresh_screenshot_jobs(
            project_id=project_id,
            current=current,
            source=source,
        )
        job_ids = [job.id for job in group.jobs]
        if not job_ids:
            return PageScreenshotBatchRefreshResponse(
                requested_count=0,
                succeeded_count=0,
                failed_count=0,
            )

        terminal_jobs = await PageScreenshotJobService.wait_for_jobs_terminal_detached(
            job_ids,
            timeout_seconds=self.settings.page_screenshot_ai_wait_timeout_seconds,
        )
        stale_code = "PAGE_SCREENSHOT_JOB_STALE"
        succeeded_ids = [
            job.page_id
            for job in terminal_jobs
            if job.status in {"succeeded", "skipped"} and job.error_code != stale_code
        ]
        failures = [
            PageScreenshotBatchFailure(
                page_id=job.page_id,
                code=job.error_code or "PAGE_SCREENSHOT_JOB_CANCELLED",
                detail=job.error_message or "页面截图任务已取消。",
            )
            for job in terminal_jobs
            if job.status in {"failed", "cancelled"} or job.error_code == stale_code
        ]
        return PageScreenshotBatchRefreshResponse(
            requested_count=len(terminal_jobs),
            succeeded_count=len(succeeded_ids),
            failed_count=len(failures),
            page_ids=succeeded_ids,
            failures=failures,
        )

    async def build_screenshot_zip_archive(
        self,
        *,
        page_ids: list[int],
        current: AuthContext,
    ) -> tuple[bytes, str]:
        """读取指定页面的最新截图并打包为 ZIP；截图未就绪时拒绝下载。"""

        unique_page_ids = list(dict.fromkeys(page_ids))
        if not unique_page_ids:
            raise AppException(status_code=400, code="PAGE_SCREENSHOT_BATCH_EMPTY", detail="请选择需要下载截图的页面。")

        screenshots: list[tuple[Page, bytes]] = []
        for page_id in unique_page_ids:
            page = await self.page_service._get_page_or_raise(page_id)
            await self.page_service._ensure_page_access(page, user_id=current.user.id)
            self._validate_page_screenshot_supported(page)

            if not await self._is_page_screenshot_current(page):
                raise AppException(
                    status_code=409,
                    code="PAGE_SCREENSHOT_NOT_READY",
                    detail=f"「{page.title}」截图尚未生成或不是最新版本，请先刷新截图。",
                )

            if not page.screenshot_storage_key:
                raise AppException(status_code=404, code="PAGE_SCREENSHOT_NOT_FOUND", detail=f"「{page.title}」截图不存在。")

            content = await self.object_storage_service.read_object(str(page.screenshot_storage_key))
            screenshots.append((page, content))

        return self._build_zip_archive(screenshots), "page-screenshots.zip"

    async def ensure_latest_page_screenshot(
        self,
        *,
        page_id: int,
        user_id: int,
        workspace_id: int,
        project_id: int | None = None,
    ) -> PageScreenshotResult:
        """返回最新截图；缺失时只提交持久化任务，绝不在调用方直接启动 Chromium。"""

        # 保留旧服务入口，避免 AI 工具或扩展绕开截图持久化队列。延迟导入也可避免
        # Job 服务与本服务在模块初始化阶段形成循环依赖。
        from app.services.page_screenshot_job_service import PageScreenshotJobService

        return await PageScreenshotJobService(self.session).ensure_latest_page_screenshot_via_queue(
            page_id=page_id,
            user_id=user_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )

    async def _capture_and_store_page_screenshot(
        self,
        page: Page,
        *,
        operator_id: int,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        commit: bool = True,
    ) -> Page:
        """生成并写回截图；队列可延迟提交以便与任务终态保持同一事务。"""

        config_snapshot = await self.screenshot_fingerprint_service.build_page_snapshot(page)
        viewport = self.viewport_resolver.resolve(
            page,
            project_page_config=config_snapshot.page_config,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        artifact = await self.capture_page_screenshot_artifact(
            page=page,
            operator_id=operator_id,
            target_page_version_no=page.current_version_no,
            config_hash=config_snapshot.config_hash,
            viewport=viewport,
        )
        await self.persist_page_screenshot_artifact(
            page=page,
            artifact=artifact,
            operator_id=operator_id,
            commit=commit,
        )
        return page

    async def capture_page_screenshot_artifact(
        self,
        *,
        page: Page,
        operator_id: int,
        target_page_version_no: int,
        config_hash: str,
        viewport: CaptureViewport,
    ) -> PageScreenshotCaptureArtifact:
        """捕获并写入不可变对象，但不修改页面元数据或任务状态。"""

        try:
            logger.info(
                "页面截图开始生成。",
                extra={
                    "event": "page.screenshot.capture.start",
                    "page_id": page.id,
                    "project_id": page.project_id,
                    "workspace_id": page.workspace_id,
                    "viewport": f"{viewport.width}x{viewport.height}",
                },
            )
            preview = await self.preview_service.create_page_preview(
                page,
                operator_id,
                asset_delivery_mode="backend_cache",
                asset_base_url_override=self._resolve_browser_backend_base_url(),
            )
            capture_target = self._build_browser_capture_target(preview)
            await self._release_session_before_browser_capture()
            screenshot_content = await self.browser_capture_service.capture_preview(
                capture_target.preview_url,
                viewport,
                extra_http_headers=capture_target.extra_http_headers,
            )
            storage_key = await self.object_storage_service.put_object(
                self.build_page_screenshot_storage_key(
                    page_id=page.id,
                    page_version_no=target_page_version_no,
                    config_hash=config_hash,
                    viewport=viewport,
                ),
                content=screenshot_content,
                content_type="image/png",
            )
            logger.info(
                "页面截图对象已保存，等待任务终态提交。",
                extra={
                    "event": "page.screenshot.capture.artifact_saved",
                    "page_id": page.id,
                    "project_id": page.project_id,
                    "workspace_id": page.workspace_id,
                    "size_bytes": len(screenshot_content),
                },
            )
            return PageScreenshotCaptureArtifact(
                storage_key=storage_key,
                page_version_no=target_page_version_no,
                config_hash=config_hash,
                viewport_width=viewport.width,
                viewport_height=viewport.height,
            )
        except Exception:
            logger.exception(
                "页面截图生成失败。",
                extra={
                    "event": "page.screenshot.capture.failed",
                    "page_id": page.id,
                    "project_id": page.project_id,
                    "workspace_id": page.workspace_id,
                },
            )
            raise

    async def persist_page_screenshot_artifact(
        self,
        *,
        page: Page,
        artifact: PageScreenshotCaptureArtifact,
        operator_id: int,
        commit: bool = True,
    ) -> None:
        """把已捕获对象发布为页面截图；调用方负责先确认页面版本仍匹配。"""

        page.screenshot_storage_key = artifact.storage_key
        page.screenshot_version_no = artifact.page_version_no
        page.screenshot_config_hash = artifact.config_hash
        page.screenshot_viewport_width = artifact.viewport_width
        page.screenshot_viewport_height = artifact.viewport_height
        page.screenshot_updated_at = utc_now()
        page.updated_by = operator_id
        if commit:
            await self.session.commit()
            await self.session.refresh(page)
        else:
            await self.session.flush()

    async def _release_session_before_browser_capture(self) -> None:
        """截图前结束当前空闲事务，避免回环请求等待同一进程内的数据库连接。"""

        if self.session.in_transaction():
            await self.session.commit()

    def _build_browser_capture_target(self, preview: PagePreviewResult) -> PageScreenshotCaptureTarget:
        """把公开预览地址转换为截图专用 Runtime 直连目标。"""

        preview_token = self._extract_preview_token(preview.preview_url)
        if not preview_token:
            return PageScreenshotCaptureTarget(preview_url=preview.preview_url)

        try:
            preview_claims = TokenService.verify_preview_context_token(preview_token)
        except Exception as exc:  # noqa: BLE001
            raise AppException(
                status_code=502,
                code="PAGE_SCREENSHOT_PREVIEW_TOKEN_INVALID",
                detail="截图预览上下文令牌非法或已过期。",
            ) from exc

        artifact_id = str(preview_claims.get("artifact_id") or "").strip()
        if not artifact_id:
            raise AppException(
                status_code=502,
                code="PAGE_SCREENSHOT_PREVIEW_TOKEN_INVALID",
                detail="截图预览上下文缺少 artifact_id。",
            )

        settings = get_settings()
        runtime_service_token = TokenService.generate_runtime_service_access_token(
            artifact_id=artifact_id,
            expires_in_seconds=self._resolve_runtime_service_token_ttl(preview_claims),
        )
        runtime_public_base_url = self._resolve_browser_runtime_public_base_url()
        return PageScreenshotCaptureTarget(
            preview_url=f"{settings.runtime_base_url.rstrip('/')}/__preview",
            extra_http_headers={
                RUNTIME_PREVIEW_CONTEXT_HEADER: preview_token,
                RUNTIME_SERVICE_TOKEN_HEADER: runtime_service_token,
                RUNTIME_PUBLIC_BASE_URL_HEADER: runtime_public_base_url,
            },
        )

    @staticmethod
    def _resolve_browser_backend_base_url() -> str:
        """返回截图浏览器可访问的 Backend 基址，用于 artifact 中资源 URL。"""

        settings = get_settings()
        configured = str(settings.page_screenshot_backend_base_url or "").strip().rstrip("/")
        if configured:
            return configured
        return f"http://127.0.0.1:{settings.app_port}"

    @staticmethod
    def _resolve_browser_runtime_public_base_url() -> str:
        """返回截图浏览器可访问的 Runtime 基址，用于 Runtime HTML 中脚本和样式 URL。"""

        settings = get_settings()
        configured = str(settings.page_screenshot_runtime_public_base_url or "").strip().rstrip("/")
        if configured:
            return configured

        runtime_base_url = settings.runtime_base_url.rstrip("/")
        public_path = urlsplit(str(settings.runtime_public_base_url or "")).path.strip("/")
        if public_path:
            return f"{runtime_base_url}/{public_path}"
        return runtime_base_url

    @staticmethod
    def _extract_preview_token(preview_url: str) -> str:
        """从公开预览 URL 中读取 token 查询参数；测试替身 URL 允许为空。"""

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

    @staticmethod
    def build_page_screenshot_storage_key(
        *,
        page_id: int,
        page_version_no: int,
        config_hash: str,
        viewport: CaptureViewport,
    ) -> str:
        """根据页面版本、展示配置和视口构造可安全重试的不可变对象键。"""

        return (
            f"page-screenshots/{int(page_id)}/v{int(page_version_no)}/"
            f"{str(config_hash).strip()}/{int(viewport.width)}x{int(viewport.height)}.png"
        )

    @staticmethod
    def _validate_page_screenshot_supported(page: Page) -> None:
        """校验页面类型是否支持截图缓存。"""

        if PageFileType(page.file_type) != PageFileType.VUE:
            raise AppException(
                status_code=400,
                code="PAGE_SCREENSHOT_FILE_TYPE_UNSUPPORTED",
                detail="当前仅支持为 Vue 页面生成截图。",
            )

    @staticmethod
    def _ensure_page_within_scope(page: Page, *, workspace_id: int, project_id: int | None) -> None:
        """校验截图查询目标页面属于当前 workspace/project 边界。"""

        if page.workspace_id != workspace_id:
            raise AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="当前页面不属于当前工作空间。")
        if project_id is not None and page.project_id != project_id:
            raise AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="当前页面不属于当前项目。")

    async def _is_page_screenshot_current(self, page: Page) -> bool:
        """判断页面截图缓存是否指向当前页面版本。"""

        config_snapshot = await self.screenshot_fingerprint_service.build_page_snapshot(page)
        viewport = self.viewport_resolver.resolve(page, project_page_config=config_snapshot.page_config)
        return self._is_page_screenshot_current_for_hash(
            page,
            config_snapshot.config_hash,
            viewport=viewport,
        )

    @staticmethod
    def _is_page_screenshot_current_for_hash(
        page: Page,
        config_hash: str,
        *,
        viewport: CaptureViewport | None = None,
    ) -> bool:
        """按已解析配置和可选视口判断截图是否仍然最新。"""

        base_current = bool(
            page.screenshot_storage_key
            and page.screenshot_version_no is not None
            and int(page.screenshot_version_no) == int(page.current_version_no)
            and page.screenshot_config_hash
            and str(page.screenshot_config_hash) == config_hash
        )
        if not base_current or viewport is None:
            return base_current
        return (
            int(page.screenshot_viewport_width or 0) == int(viewport.width)
            and int(page.screenshot_viewport_height or 0) == int(viewport.height)
        )

    async def _build_result(self, *, page: Page, content: bytes, refreshed: bool) -> PageScreenshotResult:
        """构造页面截图查询结果。"""

        storage_key = str(page.screenshot_storage_key or "")
        settings = get_settings()
        version = page.screenshot_version_no or page.current_version_no
        if page.screenshot_updated_at is not None:
            version = int(normalize_utc(page.screenshot_updated_at).timestamp() * 1000)
        public_url = f"{settings.backend_public_base_url.rstrip('/')}/public/page-screenshots/{page.id}?v={version}"
        return PageScreenshotResult(
            page=page,
            page_item=await self.page_service._to_item(page),
            storage_key=storage_key,
            content=content,
            refreshed=refreshed,
            public_url=public_url,
        )

    @classmethod
    def _build_zip_archive(cls, screenshots: list[tuple[Page, bytes]]) -> bytes:
        """把页面截图内容写入 ZIP，文件名按选择顺序编号避免重名。"""

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, (page, content) in enumerate(screenshots, start=1):
                archive.writestr(cls._build_zip_entry_name(page, index), content)
        return buffer.getvalue()

    @staticmethod
    def _build_zip_entry_name(page: Page, index: int) -> str:
        """生成 ZIP 内部截图文件名，保留页面标题并补充版本号。"""

        raw_name = str(page.title or page.code or f"page-{page.id}").strip()
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "-", raw_name).strip("-")[:64] or f"page-{page.id}"
        version_suffix = f"-v{page.screenshot_version_no}" if page.screenshot_version_no else ""
        return f"{index:02d}-{safe_name}{version_suffix}.png"
