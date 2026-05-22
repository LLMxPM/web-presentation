"""文件功能：复用 Runtime 预览上传链路，为页面截图与其他能力生成可访问预览地址。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.repositories.page_version_repository import PageVersionRepository
from app.schemas.release import PreviewArtifactResponse
from app.models.page import Page
from app.schemas.release import PreviewEntryDescriptor
from app.services.page_version_service import PageVersionService
from app.services.preview_service import PreviewService
from app.services.project_artifact_builder import AssetDeliveryMode, ProjectPageModuleOverride


@dataclass(slots=True, frozen=True)
class PagePreviewResult:
    """页面预览结果，包含 Runtime 文件路径与签名地址。"""

    file_path: str
    preview_url: str


class PagePreviewService:
    """页面预览服务，复用 Runtime 文件上传和签名预览能力。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.preview_service = PreviewService(session)
        self.page_version_repository = PageVersionRepository(session)
        self.page_version_service = PageVersionService(session)

    async def create_page_preview(
        self,
        page: Page,
        user_id: int | str,
        *,
        asset_delivery_mode: AssetDeliveryMode = "public",
    ) -> PagePreviewResult:
        """为当前页面生成草稿临时发布快照，然后返回截图/预览链路需要的地址。"""

        preview_response = await self.create_page_preview_artifact(page, user_id, asset_delivery_mode=asset_delivery_mode)
        module_path = self._build_page_module_path(page)
        return PagePreviewResult(file_path=module_path, preview_url=preview_response.preview_url)

    async def create_page_preview_artifact(
        self,
        page: Page,
        user_id: int | str,
        *,
        asset_delivery_mode: AssetDeliveryMode = "public",
    ) -> PreviewArtifactResponse:
        """基于当前页面最新内容生成单页预览 artifact。"""

        if page.project_id is None:
            raise AppException(status_code=409, code="PAGE_PROJECT_REQUIRED", detail="页面未关联项目，无法生成项目级配置预览。")

        tenant_id = f"tenant_{user_id}"
        module_path = self._build_page_module_path(page)

        return await self.preview_service.create_preview_artifact(
            project_id=page.project_id,
            entry_descriptor=PreviewEntryDescriptor(entry_type="module", module_path=module_path),
            tenant_id=tenant_id,
            asset_delivery_mode=asset_delivery_mode,
        )

    async def create_page_version_preview_artifact(
        self,
        *,
        page: Page,
        version_no: int,
        user_id: int | str,
    ) -> PreviewArtifactResponse:
        """基于指定历史版本的物化源码生成单页临时预览 artifact。"""

        if page.project_id is None:
            raise AppException(status_code=409, code="PAGE_PROJECT_REQUIRED", detail="页面未关联项目，无法生成项目级配置预览。")

        target_version = await self.page_version_repository.get_by_page_and_version(page.id, version_no)
        if target_version is None:
            raise AppException(status_code=404, code="PAGE_VERSION_NOT_FOUND", detail="页面版本不存在。")

        version_content = await self.page_version_service.get_version_content(page, version_no)
        module_path = self._build_page_module_path(page)
        tenant_id = f"tenant_{user_id}"

        return await self.preview_service.create_preview_artifact(
            project_id=page.project_id,
            entry_descriptor=PreviewEntryDescriptor(entry_type="module", module_path=module_path),
            tenant_id=tenant_id,
            asset_delivery_mode="public",
            page_module_overrides={
                module_path: ProjectPageModuleOverride(
                    content=version_content.resolved_content,
                    page_version_id=target_version.id,
                )
            },
        )

    @staticmethod
    def _build_page_module_path(page: Page) -> str:
        """统一拼接页面在 Runtime 侧使用的逻辑模块路径。"""

        return f"src/views/{page.code}.{page.file_type}"
