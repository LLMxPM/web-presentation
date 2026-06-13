"""文件功能：编排页面预览、截图和文件落库流程，对外提供页面截图保存能力。"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import normalize_utc, utc_now
from app.models.enums import PageFileType, RecordStatus
from app.models.page import Page
from app.schemas.page import (
    PageItem,
    PageScreenshotBatchFailure,
    PageScreenshotBatchRefreshResponse,
)
from app.services.auth_service import AuthContext
from app.services.browser_capture_service import BrowserCaptureJob, BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewportResolver
from app.services.object_storage_service import ObjectStorageService
from app.services.page_preview_service import PagePreviewResult, PagePreviewService
from app.services.page_service import PageService
from app.services.project_config_service import ProjectConfigService
from app.services.project_service import ProjectService
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService
from app.services.redis_runtime_client import get_redis_runtime_client
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
        """为指定页面生成并保存截图，成功后返回最新页面详情。"""

        page = await self.page_service._get_page_or_raise(page_id)
        await self.page_service._ensure_page_access(page, user_id=current.user.id)
        self._validate_page_screenshot_supported(page)
        page = await self._capture_and_store_page_screenshot(
            page,
            operator_id=current.user.id,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        return await self.page_service._to_item(page)

    async def batch_refresh_project_screenshots(
        self,
        *,
        project_id: int,
        current: AuthContext,
    ) -> PageScreenshotBatchRefreshResponse:
        """批量刷新项目中缺失或已过期的页面截图。"""

        project = await self.project_config_service.get_active_project_or_raise(project_id)
        await ProjectService(self.session).get(project_id, user_id=current.user.id)
        config_snapshot = await self.screenshot_fingerprint_service.build_project_snapshot(project)
        pages = await self._list_project_pages_for_batch_screenshot_refresh(project_id)
        outdated_pages = [
            page for page in pages
            if not self._is_page_screenshot_current_for_hash(page, config_snapshot.config_hash)
        ]
        failures: list[PageScreenshotBatchFailure] = []
        capture_jobs: list[BrowserCaptureJob] = []
        page_by_id: dict[int, Page] = {}
        lock_key_by_page_id: dict[int, str] = {}

        for page in outdated_pages:
            try:
                viewport = self.viewport_resolver.resolve(page, project_page_config=config_snapshot.page_config)
                lock_key = self._build_screenshot_lock_key(
                    page_id=page.id,
                    config_hash=config_snapshot.config_hash,
                    viewport_hash=f"{viewport.width}x{viewport.height}",
                )
                if not await self._acquire_screenshot_lock(lock_key):
                    raise AppException(status_code=409, code="PAGE_SCREENSHOT_IN_PROGRESS", detail="页面截图正在生成中，请稍后重试。")
                lock_key_by_page_id[page.id] = lock_key
                preview = await self.preview_service.create_page_preview(
                    page,
                    current.user.id,
                    asset_delivery_mode="backend_cache",
                    asset_base_url_override=self._resolve_browser_backend_base_url(),
                )
                capture_target = self._build_browser_capture_target(preview)
                capture_jobs.append(
                    BrowserCaptureJob(
                        key=page.id,
                        preview_url=capture_target.preview_url,
                        viewport=viewport,
                        extra_http_headers=capture_target.extra_http_headers,
                    )
                )
                page_by_id[page.id] = page
            except Exception as error:  # noqa: BLE001
                lock_key = lock_key_by_page_id.pop(page.id, None)
                if lock_key is not None:
                    await self._release_screenshot_lock(lock_key)
                failures.append(self._build_batch_failure(page, error))

        if capture_jobs:
            await self._release_session_before_browser_capture()
        succeeded_ids: list[int] = []
        handled_capture_keys: set[int] = set()
        try:
            capture_results = await self.browser_capture_service.capture_preview_batch(
                capture_jobs,
                max_concurrency=get_settings().page_screenshot_batch_concurrency,
            )
            for result in capture_results:
                handled_capture_keys.add(result.key)
                page = page_by_id.get(result.key)
                if page is None:
                    continue
                if result.error is not None or result.content is None:
                    failures.append(self._build_batch_failure(page, result.error or RuntimeError("页面截图内容为空。")))
                    continue

                try:
                    await self._store_page_screenshot_content(
                        page=page,
                        content=result.content,
                        operator_id=current.user.id,
                        config_hash=config_snapshot.config_hash,
                    )
                    succeeded_ids.append(page.id)
                except Exception as error:  # noqa: BLE001
                    await self.session.rollback()
                    failures.append(self._build_batch_failure(page, error))

            for job in capture_jobs:
                if job.key not in handled_capture_keys:
                    failures.append(self._build_batch_failure(page_by_id[job.key], RuntimeError("页面截图任务未返回结果。")))
        finally:
            for lock_key in lock_key_by_page_id.values():
                await self._release_screenshot_lock(lock_key)

        return PageScreenshotBatchRefreshResponse(
            requested_count=len(outdated_pages),
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
        """返回指定页面当前版本最新截图，缺失、过期或对象丢失时自动重截。"""

        page = await self.page_service._get_page_or_raise(page_id)
        self._validate_page_screenshot_supported(page)
        self._ensure_page_within_scope(page, workspace_id=workspace_id, project_id=project_id)

        if await self._is_page_screenshot_current(page):
            try:
                content = await self.object_storage_service.read_object(str(page.screenshot_storage_key))
                return await self._build_result(page=page, content=content, refreshed=False)
            except AppException as exc:
                if exc.status_code != 404:
                    raise

        page = await self._capture_and_store_page_screenshot(page, operator_id=user_id)
        content = await self.object_storage_service.read_object(str(page.screenshot_storage_key))
        return await self._build_result(page=page, content=content, refreshed=True)

    async def _capture_and_store_page_screenshot(
        self,
        page: Page,
        *,
        operator_id: int,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> Page:
        """生成页面预览截图并写回页面截图缓存字段。"""

        config_snapshot = await self.screenshot_fingerprint_service.build_page_snapshot(page)
        viewport = self.viewport_resolver.resolve(
            page,
            project_page_config=config_snapshot.page_config,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        lock_key = self._build_screenshot_lock_key(
            page_id=page.id,
            config_hash=config_snapshot.config_hash,
            viewport_hash=f"{viewport.width}x{viewport.height}",
        )
        if not await self._acquire_screenshot_lock(lock_key):
            return await self._wait_for_concurrent_screenshot(page=page, config_hash=config_snapshot.config_hash)

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
            await self._store_page_screenshot_content(
                page=page,
                content=screenshot_content,
                operator_id=operator_id,
                config_hash=config_snapshot.config_hash,
            )
            logger.info(
                "页面截图保存完成。",
                extra={
                    "event": "page.screenshot.capture.done",
                    "page_id": page.id,
                    "project_id": page.project_id,
                    "workspace_id": page.workspace_id,
                    "size_bytes": len(screenshot_content),
                },
            )
            return page
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
        finally:
            await self._release_screenshot_lock(lock_key)

    async def _release_session_before_browser_capture(self) -> None:
        """截图前结束当前空闲事务，避免回环请求等待同一进程内的数据库连接。"""

        if self.session.in_transaction():
            await self.session.commit()

    async def _acquire_screenshot_lock(self, lock_key: str) -> bool:
        """抢占 Redis 截图锁，避免同一页面同一配置重复生成。"""

        runtime = get_redis_runtime_client()
        acquired = await asyncio.to_thread(runtime.client.set, lock_key, "1", ex=120, nx=True)
        return bool(acquired)

    async def _release_screenshot_lock(self, lock_key: str) -> None:
        """释放 Redis 截图锁；TTL 仍是异常兜底。"""

        runtime = get_redis_runtime_client()
        await asyncio.to_thread(runtime.client.delete, lock_key)

    async def _wait_for_concurrent_screenshot(self, *, page: Page, config_hash: str) -> Page:
        """短轮询等待并发截图落库，超时后返回明确的运行态错误。"""

        for _ in range(10):
            await asyncio.sleep(0.5)
            await self.session.refresh(page)
            if self._is_page_screenshot_current_for_hash(page, config_hash):
                return page
        raise AppException(status_code=409, code="PAGE_SCREENSHOT_IN_PROGRESS", detail="页面截图正在生成中，请稍后重试。")

    @staticmethod
    def _build_screenshot_lock_key(*, page_id: int, config_hash: str, viewport_hash: str) -> str:
        """构造截图去重锁 key。"""

        return get_redis_runtime_client().key(f"runtime:screenshot-lock:{page_id}:{config_hash}:{viewport_hash}")

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

    async def _store_page_screenshot_content(
        self,
        *,
        page: Page,
        content: bytes,
        operator_id: int,
        config_hash: str,
    ) -> None:
        """保存截图对象并更新页面截图缓存元数据。"""

        storage_key = await self.object_storage_service.put_object(
            f"page-screenshots/{page.code}.png",
            content,
            "image/png",
        )

        page.screenshot_storage_key = storage_key
        page.screenshot_version_no = page.current_version_no
        page.screenshot_config_hash = config_hash
        page.screenshot_updated_at = utc_now()
        page.updated_by = operator_id
        await self.session.commit()
        await self.session.refresh(page)

    async def _list_project_pages_for_batch_screenshot_refresh(self, project_id: int) -> list[Page]:
        """读取项目中可批量刷新截图的启用 Vue 页面。"""

        result = await self.session.scalars(
            select(Page)
            .where(Page.project_id == project_id)
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.file_type == PageFileType.VUE.value)
            .where(Page.deleted_at.is_(None))
            .order_by(Page.updated_at.desc(), Page.id.desc())
        )
        return list(result.all())

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
        return self._is_page_screenshot_current_for_hash(page, config_snapshot.config_hash)

    @staticmethod
    def _is_page_screenshot_current_for_hash(page: Page, config_hash: str) -> bool:
        """按已解析配置指纹判断截图是否仍然最新。"""

        return bool(
            page.screenshot_storage_key
            and page.screenshot_version_no is not None
            and int(page.screenshot_version_no) == int(page.current_version_no)
            and page.screenshot_config_hash
            and str(page.screenshot_config_hash) == config_hash
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

    @staticmethod
    def _build_batch_failure(page: Page, error: Exception) -> PageScreenshotBatchFailure:
        """把单页异常转换为批量刷新失败明细。"""

        if isinstance(error, AppException):
            detail = error.detail
        else:
            detail = str(error) or "截图刷新失败。"
        return PageScreenshotBatchFailure(page_id=page.id, code=page.code, detail=detail)

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
