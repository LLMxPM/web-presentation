"""文件功能：提供页面与组件源码的只读代码检查服务，统一生成临时预览 artifact 并调用 Runtime 诊断。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.shared import SourceEditPayload, apply_source_edits
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import PageFileType, RecordStatus
from app.models.page import Page
from app.schemas.release import PreviewEntryDescriptor
from app.services.component_preview_service import ComponentPreviewService
from app.services.page_service import PageService
from app.services.preview_service import PreviewService
from app.services.project_artifact_builder import ProjectPageModuleOverride
from app.services.runtime_diagnostics_client import RuntimeDiagnosticsClient
from app.services.token_service import TokenService
from app.services.workspace_component_service import WorkspaceComponentService


@dataclass(frozen=True)
class CandidateSource:
    """代码检查候选源码及其结构化编辑应用信息。"""

    content: str
    patch_repaired: bool = False
    canonical_diff: str | None = None


def build_code_check_failed_result(
    *,
    code: str,
    message: str,
    source: str = "backend",
    canonical_diff: str | None = None,
) -> dict[str, object]:
    """构造统一代码检查失败响应，供只读检查和 apply 内置校验复用。"""

    return {
        "success": False,
        "status": "failed",
        "artifact_id": None,
        "summary": message,
        "message": message,
        "patch_repaired": False,
        "canonical_diff": canonical_diff,
        "diagnostics": [
            {
                "severity": "error",
                "source": source,
                "code": code,
                "message": message,
            }
        ],
    }


class CodeCheckService:
    """页面/组件代码检查服务。"""

    def __init__(self, session: AsyncSession, runtime_client: RuntimeDiagnosticsClient | None = None) -> None:
        self.session = session
        self.runtime_client = runtime_client or RuntimeDiagnosticsClient()

    async def check_page_code(
        self,
        *,
        page_id: int | None = None,
        user_id: int | str,
        project_id: int | None = None,
        workspace_id: int | None = None,
        content: str | None = None,
        edits: list[SourceEditPayload] | None = None,
    ) -> dict[str, object]:
        """检查页面当前源码、完整候选源码或 edits 应用后的候选源码。"""

        if page_id is None:
            return await self._check_transient_page_code(
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
                content=content,
                edits=edits,
            )

        page = await PageService(self.session)._get_page_or_raise(page_id)
        if workspace_id is not None and page.workspace_id != workspace_id:
            raise AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="页面不属于当前工作空间，拒绝检查。")
        if page.project_id is None:
            return self._failed_result(
                code="PAGE_PROJECT_REQUIRED",
                message="页面未关联项目，无法生成 Runtime 代码检查 artifact。",
            )
        if page.file_type != PageFileType.VUE.value:
            return self._failed_result(code="PAGE_FILE_TYPE_UNSUPPORTED", message="当前阶段仅支持 Vue 页面代码检查。")

        candidate = self._resolve_candidate_source(
            current_content=page.page_content,
            content=content,
            edits=edits,
        )
        if isinstance(candidate, dict):
            return candidate

        module_path = f"src/views/{page.code}.{page.file_type}"
        try:
            preview = await PreviewService(self.session).create_preview_artifact(
                project_id=page.project_id,
                entry_descriptor=PreviewEntryDescriptor(entry_type="module", module_path=module_path),
                tenant_id=f"tenant_{user_id}",
                page_module_overrides={
                    module_path: ProjectPageModuleOverride(
                        content=candidate.content,
                        page_version_id=None,
                    )
                },
            )
        except AppException as exc:
            return self._failed_result(code=exc.code, message=exc.detail)
        return await self._dispatch_diagnostics(
            artifact_id=preview.artifact_id,
            workspace_id=preview.workspace_id or page.workspace_id,
            project_id=page.project_id,
            label=f"page:{page.id}",
            patch_repaired=candidate.patch_repaired,
            canonical_diff=candidate.canonical_diff,
        )

    async def _check_transient_page_code(
        self,
        *,
        project_id: int | None,
        workspace_id: int | None,
        user_id: int | str,
        content: str | None,
        edits: list[SourceEditPayload] | None,
    ) -> dict[str, object]:
        """检查新增页面写入前的未落库完整候选源码。"""

        if project_id is None:
            return self._failed_result(
                code="PAGE_PROJECT_REQUIRED",
                message="未指定 page_id 时，必须在项目上下文中提供 project_id 才能检查新增页面源码。",
            )
        if edits is not None:
            return self._failed_result(
                code="PAGE_TARGET_REQUIRED",
                message="未指定 page_id 时不能检查 edits，请传入完整 content 检查新增页面源码。",
            )
        if content is None:
            return self._failed_result(
                code="PAGE_TARGET_REQUIRED",
                message="未指定 page_id 时，必须传入 content 才能检查新增页面源码。",
            )

        candidate = self._resolve_candidate_source(
            current_content="",
            content=content,
            edits=None,
        )
        if isinstance(candidate, dict):
            return candidate

        preview_service = PreviewService(self.session)
        project = await preview_service.artifact_builder.get_project_or_raise(project_id)
        if workspace_id is not None and project.workspace_id != workspace_id:
            raise AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="项目不属于当前工作空间，拒绝检查。")

        draft_page = Page(
            code="__ai_page_draft__",
            page_content=candidate.content,
            current_version_no=1,
            file_type=PageFileType.VUE.value,
            title="未保存页面草稿",
            status=RecordStatus.ACTIVE.value,
            workspace_id=project.workspace_id,
            project_id=project.id,
        )
        module_path = f"src/views/{draft_page.code}.{draft_page.file_type}"
        try:
            preview = await preview_service.create_preview_artifact(
                project_id=project.id,
                entry_descriptor=PreviewEntryDescriptor(entry_type="module", module_path=module_path),
                tenant_id=f"tenant_{user_id}",
                page_module_overrides={
                    module_path: ProjectPageModuleOverride(
                        content=candidate.content,
                        page_version_id=None,
                    )
                },
                transient_pages=[draft_page],
            )
        except AppException as exc:
            return self._failed_result(code=exc.code, message=exc.detail)
        return await self._dispatch_diagnostics(
            artifact_id=preview.artifact_id,
            workspace_id=preview.workspace_id or project.workspace_id,
            project_id=project.id,
            label=f"page:draft:{project.id}",
            patch_repaired=candidate.patch_repaired,
            canonical_diff=candidate.canonical_diff,
        )

    async def check_component_code(
        self,
        *,
        workspace_id: int,
        user_id: int | str,
        component_id: int | None = None,
        content: str | None = None,
        edits: list[SourceEditPayload] | None = None,
        preview_schema: str | None = None,
    ) -> dict[str, object]:
        """检查组件当前草稿、完整候选源码或 edits 应用后的候选源码。"""

        component = None
        current_content = ""
        component_name = "未保存组件草稿"
        resolved_preview_schema = preview_schema
        if component_id is not None:
            component = await WorkspaceComponentService(self.session).get(component_id)
            if component.workspace_id != workspace_id:
                raise AppException(status_code=403, code="AI_COMPONENT_SCOPE_DENIED", detail="组件不属于当前工作空间，拒绝检查。")
            current_content = component.content
            component_name = component.name
            if preview_schema is None:
                resolved_preview_schema = component.preview_schema
        elif content is None:
            return self._failed_result(
                code="COMPONENT_TARGET_REQUIRED",
                message="未指定组件时，必须传入 content 才能检查未保存组件源码。",
            )

        candidate = self._resolve_candidate_source(
            current_content=current_content,
            content=content,
            edits=edits,
        )
        if isinstance(candidate, dict):
            return candidate

        try:
            preview = await ComponentPreviewService(self.session).create_source_preview_artifact(
                workspace_id=workspace_id,
                component_id=component_id,
                component_name=component_name,
                content=candidate.content,
                preview_schema=resolved_preview_schema,
                preview_options=None,
                tenant_id=f"tenant_{user_id}",
                file_type=PageFileType.VUE,
            )
        except AppException as exc:
            return self._failed_result(code=exc.code, message=exc.detail)
        return await self._dispatch_diagnostics(
            artifact_id=preview.artifact_id,
            workspace_id=workspace_id,
            project_id=preview.project_id,
            label=f"component:{component_id or 'draft'}",
            patch_repaired=candidate.patch_repaired,
            canonical_diff=candidate.canonical_diff,
        )

    async def _dispatch_diagnostics(
        self,
        *,
        artifact_id: str,
        workspace_id: int,
        project_id: int | None,
        label: str,
        patch_repaired: bool,
        canonical_diff: str | None,
    ) -> dict[str, object]:
        """调用 Runtime 诊断接口，并补齐候选源码变更元数据。"""

        diagnostics_token = TokenService.generate_runtime_diagnostics_command_token(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        result = await self.runtime_client.dispatch_artifact_diagnostics(
            artifact_id=artifact_id,
            diagnostics_token=diagnostics_token,
            label=label,
        )
        return {
            **result,
            "patch_repaired": patch_repaired,
            "canonical_diff": canonical_diff,
        }

    def _resolve_candidate_source(
        self,
        *,
        current_content: str,
        content: str | None,
        edits: list[SourceEditPayload] | None,
    ) -> CandidateSource | dict[str, object]:
        """根据 content 或 edits 生成候选源码；输入非法时直接返回失败结果。"""

        has_content = content is not None
        has_edits = edits is not None
        if has_content and has_edits:
            return self._failed_result(code="CODE_CHECK_INPUT_CONFLICT", message="content 和 edits 只能二选一。")
        if has_content:
            normalized_content = normalize_text_to_lf(content or "")
            if not normalized_content.strip():
                return self._failed_result(code="CODE_CHECK_CONTENT_EMPTY", message="候选源码不能为空。")
            return CandidateSource(content=normalized_content)
        if not has_edits:
            return CandidateSource(content=normalize_text_to_lf(current_content))

        try:
            edit_result = apply_source_edits(current_content, edits or [])
        except AppException as exc:
            return self._failed_result(code=exc.code, message=exc.detail, source="edits")
        return CandidateSource(
            content=edit_result.next_content,
            patch_repaired=False,
            canonical_diff=edit_result.canonical_diff,
        )

    @staticmethod
    def _failed_result(*, code: str, message: str, source: str = "backend") -> dict[str, object]:
        """构造统一失败响应。"""

        return build_code_check_failed_result(code=code, message=message, source=source)
