"""文件功能：编排页面可视化编辑分析、版本绑定 artifact 与受控批量保存。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import PageFileType
from app.models.page import Page
from app.models.page_version import PageVersion
from app.repositories.page_version_repository import PageVersionRepository
from app.schemas.page_visual_edit import (
    PageVisualEditApplyDiagnostic,
    PageVisualEditApplyRequest,
    PageVisualEditApplyResponse,
    PageVisualEditPreviewArtifactCreateRequest,
    PageVisualEditPreviewArtifactResponse,
    PageVisualEditPreviewContext,
)
from app.schemas.page_visual_edit_manifest import build_page_visual_edit_source_hash
from app.schemas.page import PageUpdateRequest
from app.schemas.release import PreviewEntryDescriptor
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditApplyRequest,
    RuntimePageVisualEditApplyResponse,
)
from app.services.page_visual_edit_artifact_validator import (
    PageVisualEditArtifactExpectation,
    PageVisualEditArtifactValidator,
)
from app.services.page_visual_edit_component_schema_service import (
    PageVisualEditComponentSchemaService,
)
from app.services.page_service import PageService
from app.services.preview_service import PreviewService
from app.services.project_artifact_builder import ProjectPageModuleOverride
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_visual_edit_client import (
    RuntimeVisualEditClient,
    serialize_runtime_visual_edit_payload,
)


class PageVisualEditService:
    """页面可视化编辑服务，负责分析 artifact 创建与受控源码批量保存。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        page_service: PageService | None = None,
        page_version_repository: PageVersionRepository | None = None,
        runtime_client: RuntimeVisualEditClient | None = None,
        preview_service: PreviewService | None = None,
        artifact_store: RuntimeArtifactStore | None = None,
        component_schema_service: PageVisualEditComponentSchemaService | None = None,
    ) -> None:
        self.session = session
        self.page_service = page_service or PageService(session)
        self.page_version_repository = page_version_repository or PageVersionRepository(
            session
        )
        self.runtime_client = runtime_client or RuntimeVisualEditClient()
        self.preview_service = preview_service or PreviewService(session)
        self.artifact_store = artifact_store or RuntimeArtifactStore()
        self.component_schema_service = (
            component_schema_service or PageVisualEditComponentSchemaService(session)
        )

    async def create_preview_artifact(
        self,
        *,
        page_id: int,
        payload: PageVisualEditPreviewArtifactCreateRequest,
        user_id: int,
    ) -> PageVisualEditPreviewArtifactResponse:
        """校验页面基线、请求 Runtime 分析，并创建不修改规范源码的编辑态 artifact。"""

        page = await self.page_service._get_page_or_raise(page_id)
        await self.page_service._ensure_page_access(page, user_id=user_id)
        self._validate_page_target(page, payload.base_version_no)

        page_version = await self.page_version_repository.get_by_page_and_version(
            page.id,
            page.current_version_no,
        )
        if page_version is None:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_VERSION_NOT_FOUND",
                detail="页面当前版本记录不存在，无法创建可视化编辑预览。",
            )

        module_path = f"src/views/{page.code}.{page.file_type}"
        source_hash = build_page_visual_edit_source_hash(page.page_content)
        component_schemas = await self.component_schema_service.build_for_page(
            page=page
        )
        analysis = await self.runtime_client.analyze(
            RuntimePageVisualEditAnalyzeRequest(
                protocol_version=payload.protocol_version,
                source_hash=source_hash,
                module_path=module_path,
                source=page.page_content,
            )
        )
        warning_diagnostics = [
            item for item in analysis.manifest.diagnostics if item.severity == "warning"
        ]
        visual_edit_metadata = {
            "protocol_version": payload.protocol_version,
            "page_id": page.id,
            "page_version_id": page_version.id,
            "base_version_no": page.current_version_no,
            "source_hash": source_hash,
            "module_path": module_path,
            "manifest": serialize_runtime_visual_edit_payload(analysis.manifest),
            "component_schemas": {
                local_name: schema.model_dump(mode="python")
                for local_name, schema in component_schemas.items()
            },
            "warnings": [
                serialize_runtime_visual_edit_payload(item)
                for item in warning_diagnostics
            ],
        }
        preview = await self.preview_service.create_preview_artifact(
            project_id=page.project_id,
            entry_descriptor=PreviewEntryDescriptor(
                entry_type="module", module_path=module_path
            ),
            tenant_id=f"tenant_{user_id}",
            page_module_overrides={
                module_path: ProjectPageModuleOverride(
                    content=analysis.instrumented_source,
                    page_version_id=page_version.id,
                )
            },
            artifact_kind="page_visual_edit_preview",
            manifest_extensions={"visual_edit": visual_edit_metadata},
        )
        self._validate_preview_scope(
            preview_kind=preview.preview_kind,
            preview_project_id=preview.project_id,
            preview_workspace_id=preview.workspace_id,
            page_project_id=page.project_id,
            page_workspace_id=page.workspace_id,
        )
        return PageVisualEditPreviewArtifactResponse(
            preview_url=preview.preview_url,
            artifact_id=preview.artifact_id,
            preview_kind=preview.preview_kind,
            entry_descriptor=preview.entry_descriptor.model_dump(mode="python"),
            viewport_width=preview.viewport_width,
            viewport_height=preview.viewport_height,
            project_id=preview.project_id,
            workspace_id=preview.workspace_id,
            visual_edit=PageVisualEditPreviewContext(
                protocol_version=payload.protocol_version,
                page_id=page.id,
                base_version_no=page.current_version_no,
                source_hash=source_hash,
                module_path=module_path,
                manifest=analysis.manifest,
                component_schemas=component_schemas,
                warnings=warning_diagnostics,
            ),
        )

    async def apply(
        self,
        *,
        page_id: int,
        payload: PageVisualEditApplyRequest,
        user_id: int,
    ) -> PageVisualEditApplyResponse:
        """校验 artifact 与双重乐观锁，应用完整 AST 批次并原子保存一个页面版本。"""

        page = await self.page_service._get_page_or_raise(page_id)
        await self.page_service._ensure_page_access(page, user_id=user_id)
        self._validate_page_target(page, payload.base_version_no)
        source_hash = self._validate_source_hash(page.page_content, payload.source_hash)
        page_version = await self._get_current_page_version(page)
        module_path = f"src/views/{page.code}.{page.file_type}"
        artifact_manifest = await self.artifact_store.get_manifest(payload.artifact_id)
        artifact_binding = PageVisualEditArtifactValidator.validate(
            artifact_manifest,
            PageVisualEditArtifactExpectation(
                artifact_id=payload.artifact_id,
                user_id=user_id,
                page_id=page.id,
                page_version_id=page_version.id,
                base_version_no=page.current_version_no,
                source_hash=source_hash,
                module_path=module_path,
                project_id=page.project_id,
                workspace_id=page.workspace_id,
                protocol_version=payload.protocol_version,
            ),
        )
        PageVisualEditArtifactValidator.validate_tailwind_operations(
            artifact_binding,
            payload.operations,
        )
        PageVisualEditArtifactValidator.validate_structural_operations(
            artifact_binding,
            payload.operations,
        )
        canonical_source = page.page_content
        page_version_id = page_version.id
        await self.session.rollback()

        runtime_result = await self.runtime_client.apply(
            RuntimePageVisualEditApplyRequest(
                protocol_version=payload.protocol_version,
                source_hash=source_hash,
                module_path=module_path,
                source=canonical_source,
                operations=payload.operations,
            )
        )
        self._validate_runtime_apply_result(
            runtime_result, payload, source_hash, canonical_source
        )
        return await self._save_candidate(
            page_id=page_id,
            payload=payload,
            user_id=user_id,
            expected_source_hash=source_hash,
            expected_page_version_id=page_version_id,
            runtime_result=runtime_result,
        )

    async def _save_candidate(
        self,
        *,
        page_id: int,
        payload: PageVisualEditApplyRequest,
        user_id: int,
        expected_source_hash: str,
        expected_page_version_id: int,
        runtime_result: RuntimePageVisualEditApplyResponse,
    ) -> PageVisualEditApplyResponse:
        """在最终短事务中锁定并复核页面，然后通过 PageService 写入新版本。"""

        candidate_source = normalize_text_to_lf(runtime_result.next_source)
        try:
            page = await self.session.scalar(
                select(Page)
                .where(Page.id == page_id)
                .where(Page.deleted_at.is_(None))
                .with_for_update()
            )
            if page is None:
                raise AppException(
                    status_code=404, code="PAGE_NOT_FOUND", detail="页面不存在。"
                )
            await self.page_service._ensure_page_access(page, user_id=user_id)
            self._validate_page_target(page, payload.base_version_no)
            self._validate_source_hash(page.page_content, expected_source_hash)
            current_version = await self._get_current_page_version(page)
            if current_version.id != expected_page_version_id:
                raise AppException(
                    status_code=409,
                    code="PAGE_VISUAL_EDIT_BASE_VERSION_STALE",
                    detail="页面版本基线已变化，请刷新预览后重试。",
                )
            updated_page = await self.page_service.update(
                page_id,
                PageUpdateRequest(
                    page_content=candidate_source,
                    change_note=payload.change_note or "可视化编辑",
                ),
                user_id,
                commit=False,
            )
            if updated_page.current_version_no != payload.base_version_no + 1:
                raise AppException(
                    status_code=409,
                    code="PAGE_VISUAL_EDIT_VERSION_WRITE_CONFLICT",
                    detail="页面版本未按预期推进，已取消本次可视化编辑。",
                )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_BASE_VERSION_STALE",
                detail="页面版本已被其他请求更新，请刷新预览后重试。",
            ) from exc
        except Exception:
            await self.session.rollback()
            raise

        return PageVisualEditApplyResponse(
            protocol_version=payload.protocol_version,
            page_id=page_id,
            previous_version_no=payload.base_version_no,
            current_version_no=updated_page.current_version_no,
            source_hash=build_page_visual_edit_source_hash(candidate_source),
            operations_applied=runtime_result.operations_applied,
            canonical_diff=runtime_result.canonical_diff,
            diagnostics=[
                PageVisualEditApplyDiagnostic(
                    severity=item.severity,
                    source="runtime-visual-edit",
                    code=item.code,
                    message=item.message,
                )
                for item in runtime_result.diagnostics
            ],
            refresh_required=True,
        )

    async def _get_current_page_version(self, page: Page) -> PageVersion:
        """读取并校验页面当前版本记录，避免 artifact 绑定不可审计版本。"""

        page_version = await self.page_version_repository.get_by_page_and_version(
            page.id,
            page.current_version_no,
        )
        if page_version is None:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_VERSION_NOT_FOUND",
                detail="页面当前版本记录不存在，无法执行可视化编辑。",
            )
        return page_version

    @staticmethod
    def _validate_source_hash(source: str, expected_source_hash: str) -> str:
        """复算 Backend 规范源码 hash，防止仅凭版本号覆盖同号漂移内容。"""

        current_source_hash = build_page_visual_edit_source_hash(source)
        if current_source_hash != expected_source_hash:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_SOURCE_HASH_STALE",
                detail="页面源码基线已变化，请刷新预览后重试。",
            )
        return current_source_hash

    @staticmethod
    def _validate_runtime_apply_result(
        result: RuntimePageVisualEditApplyResponse,
        payload: PageVisualEditApplyRequest,
        source_hash: str,
        canonical_source: str,
    ) -> None:
        """防御性校验 Runtime 必须基于规范源码完整应用整个操作批次。"""

        if result.base_source_hash != source_hash:
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_SOURCE_MISMATCH",
                detail="Runtime 可视化编辑结果与 Backend 规范源码不匹配。",
            )
        if result.operations_applied != len(payload.operations):
            raise AppException(
                status_code=502,
                code="RUNTIME_VISUAL_EDIT_PARTIAL_APPLY",
                detail="Runtime 未完整应用页面可视化编辑操作。",
            )
        if (
            normalize_text_to_lf(result.next_source) == canonical_source
            or result.next_source_hash == source_hash
        ):
            raise AppException(
                status_code=422,
                code="PAGE_VISUAL_EDIT_NO_CHANGES",
                detail="本次可视化编辑没有产生可保存的源码变化。",
            )

    @staticmethod
    def _validate_page_target(page, base_version_no: int) -> None:
        """校验页面具备项目、Vue 文件类型和未漂移的编辑基线。"""

        if page.project_id is None:
            raise AppException(
                status_code=409,
                code="PAGE_PROJECT_REQUIRED",
                detail="页面未关联项目，无法生成项目级可视化编辑预览。",
            )
        if page.file_type != PageFileType.VUE.value:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_FILE_TYPE_UNSUPPORTED",
                detail="当前阶段仅支持 Vue 页面可视化编辑。",
            )
        if page.current_version_no != base_version_no:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_BASE_VERSION_STALE",
                detail="页面版本已变化，请刷新页面后重新进入可视化编辑。",
            )

    @staticmethod
    def _validate_preview_scope(
        *,
        preview_kind: str,
        preview_project_id: int | None,
        preview_workspace_id: int | None,
        page_project_id: int | None,
        page_workspace_id: int | None,
    ) -> None:
        """确认 PreviewService 返回的 artifact 未偏离目标页面作用域。"""

        if (
            preview_kind != "page"
            or preview_project_id is None
            or preview_workspace_id is None
            or preview_project_id != page_project_id
            or preview_workspace_id != page_workspace_id
        ):
            raise AppException(
                status_code=502,
                code="PAGE_VISUAL_EDIT_PREVIEW_SCOPE_INVALID",
                detail="可视化编辑预览返回了不匹配的页面作用域。",
            )
