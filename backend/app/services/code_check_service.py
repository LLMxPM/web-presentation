"""文件功能：提供页面与组件源码的只读代码检查服务，统一生成临时预览 artifact 并调用 Runtime 诊断。"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.shared import SourceEditPayload, apply_source_edits
from app.core.component_preview_schema import (
    validate_component_preview_schema_text,
    validate_content_component_size_controls,
)
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.models.page import Page
from app.schemas.release import PreviewEntryDescriptor
from app.services.asset_binding_service import (
    OWNER_KIND_PREVIEW_ARTIFACT,
    AssetBindingService,
)
from app.services.audio_capability_gate import AUDIO_CAPABILITY_UNAVAILABLE
from app.services.audio_options_gate import (
    AUDIO_ERROR_OPTIONS_INVALID,
    collect_asset_audio_errors,
    collect_audio_capability_errors,
)
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.code_check_fingerprint import CodeCheckFingerprintBuilder
from app.services.code_check_result_cache import (
    CodeCheckResultCache,
    get_code_check_result_cache,
)
from app.services.component_preview_service import ComponentPreviewService
from app.services.component_validation_profile import (
    build_component_validation_profile,
)
from app.services.component_validation_service import ComponentValidationService
from app.services.page_render_diagnostics_service import (
    PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE,
    PageRenderDiagnosticsService,
)
from app.services.page_service import PageService
from app.services.preview_service import PreviewService
from app.services.project_artifact_builder import ProjectPageModuleOverride
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_diagnostics_client import RuntimeDiagnosticsClient
from app.services.token_service import TokenService
from app.services.validation_result import is_validation_passed
from app.services.workspace_component_service import WorkspaceComponentService

logger = logging.getLogger(__name__)


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
    retryable: bool = False,
) -> dict[str, object]:
    """构造统一代码检查失败响应，供只读检查和 apply 内置校验复用。

    `retryable=True` 表示瞬态基础设施失败（Redis 抖动、Runtime 满载、超时等），
    检查结果缓存不得把它当成稳定「代码检查失败」长期沉淀。
    """

    return {
        "success": False,
        "status": "failed",
        "artifact_id": None,
        "summary": message,
        "message": message,
        "patch_repaired": False,
        "canonical_diff": canonical_diff,
        "retryable": retryable,
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

    def __init__(
        self,
        session: AsyncSession,
        runtime_client: RuntimeDiagnosticsClient | None = None,
        render_diagnostics_service: PageRenderDiagnosticsService | None = None,
        result_cache: CodeCheckResultCache | None = None,
    ) -> None:
        self.session = session
        self.runtime_client = runtime_client or RuntimeDiagnosticsClient()
        self.render_diagnostics_service = render_diagnostics_service or PageRenderDiagnosticsService()
        self.component_validation_service = ComponentValidationService(self.runtime_client, session)
        self.result_cache = result_cache if result_cache is not None else get_code_check_result_cache()
        self.fingerprint_builder = CodeCheckFingerprintBuilder(session)

    async def check_page_code(
        self,
        *,
        page_id: int | None = None,
        user_id: int | str,
        project_id: int | None = None,
        workspace_id: int | None = None,
        content: str | None = None,
        edits: list[SourceEditPayload] | None = None,
        capture_screenshot: bool = False,
        candidate_code: str | None = None,
        candidate_title: str | None = None,
        candidate_speaker_notes: str | None = None,
        candidate_route_options: dict | None = None,
    ) -> dict[str, object]:
        """检查页面当前源码、完整候选源码或 edits 应用后的候选源码。

        鉴权与候选解析始终先于缓存查找；缓存只复用检查计算结果，不替代权限校验。
        """

        if page_id is None:
            return await self._check_transient_page_code(
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
                content=content,
                edits=edits,
                capture_screenshot=capture_screenshot,
                candidate_code=candidate_code,
                candidate_title=candidate_title,
                candidate_speaker_notes=candidate_speaker_notes,
                candidate_route_options=candidate_route_options,
            )

        page = await PageService(self.session)._get_page_or_raise(page_id)
        await PageService(self.session)._ensure_page_access(page, user_id=user_id)
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
        audio_failure = self._audio_option_failure(candidate.content)
        if audio_failure is not None:
            return audio_failure

        module_path = f"src/views/{page.code}.{page.file_type}"

        async def execute_check() -> dict[str, object]:
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
                    snapshot_profile="page_diagnostics",
                )
            except AppException as exc:
                return self._failed_result_from_exception(exc)
            await self._release_session_before_diagnostics()
            return await self._dispatch_diagnostics(
                artifact_id=preview.artifact_id,
                workspace_id=preview.workspace_id or page.workspace_id,
                project_id=page.project_id,
                label=f"page:{page.id}",
                patch_repaired=candidate.patch_repaired,
                canonical_diff=candidate.canonical_diff,
                render_preview_url=preview.preview_url,
                render_viewport=CaptureViewport(width=preview.viewport_width, height=preview.viewport_height),
                page_id=page.id,
                source_override=candidate.content,
                capture_screenshot=capture_screenshot,
            )

        return await self._run_with_cache(
            kind="page",
            workspace_id=page.workspace_id,
            project_id=page.project_id,
            source=candidate.content,
            importer_module_path=module_path,
            candidate=candidate,
            execute_check=execute_check,
            capture_screenshot=capture_screenshot,
            page_metadata={"code": page.code, "title": page.title, "speaker_notes": page.speaker_notes},
        )

    async def _check_transient_page_code(
        self,
        *,
        project_id: int | None,
        workspace_id: int | None,
        user_id: int | str,
        content: str | None,
        edits: list[SourceEditPayload] | None,
        capture_screenshot: bool = False,
        candidate_code: str | None = None,
        candidate_title: str | None = None,
        candidate_speaker_notes: str | None = None,
        candidate_route_options: dict | None = None,
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
        audio_failure = self._audio_option_failure(candidate.content)
        if audio_failure is not None:
            return audio_failure

        preview_service = PreviewService(self.session)
        project = await preview_service.artifact_builder.get_project_or_raise(project_id)
        from app.services.workspace_service import WorkspaceService
        await WorkspaceService(self.session).ensure_access(project.workspace_id, user_id=user_id)
        if workspace_id is not None and project.workspace_id != workspace_id:
            raise AppException(status_code=403, code="AI_PAGE_SCOPE_DENIED", detail="项目不属于当前工作空间，拒绝检查。")

        draft_page = Page(
            code=candidate_code or "__ai_page_draft__",
            page_content=candidate.content,
            current_version_no=1,
            file_type=PageFileType.VUE.value,
            title=candidate_title or "未保存页面草稿",
            speaker_notes=candidate_speaker_notes,
            status=RecordStatus.ACTIVE.value,
            workspace_id=project.workspace_id,
            project_id=project.id,
        )
        module_path = f"src/views/{draft_page.code}.{draft_page.file_type}"
        from app.services.page_candidate_routes import candidate_runtime_routes
        runtime_routes_override = await candidate_runtime_routes(self.session, page=draft_page, options=candidate_route_options)

        async def execute_check() -> dict[str, object]:
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
                    **({"runtime_routes_override": runtime_routes_override} if runtime_routes_override is not None else {}),
                    snapshot_profile="page_diagnostics",
                )
            except AppException as exc:
                return self._failed_result_from_exception(exc)
            await self._release_session_before_diagnostics()
            return await self._dispatch_diagnostics(
                artifact_id=preview.artifact_id,
                workspace_id=preview.workspace_id or project.workspace_id,
                project_id=project.id,
                label=f"page:draft:{project.id}",
                patch_repaired=candidate.patch_repaired,
                canonical_diff=candidate.canonical_diff,
                render_preview_url=preview.preview_url,
                render_viewport=CaptureViewport(width=preview.viewport_width, height=preview.viewport_height),
                capture_screenshot=capture_screenshot,
            )

        return await self._run_with_cache(
            kind="page",
            workspace_id=project.workspace_id,
            project_id=project.id,
            source=candidate.content,
            importer_module_path=module_path,
            candidate=candidate,
            execute_check=execute_check,
            capture_screenshot=capture_screenshot,
            page_metadata={"code": draft_page.code, "title": draft_page.title, "speaker_notes": draft_page.speaker_notes},
            runtime_routes_override=runtime_routes_override,
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
        component_type: WorkspaceComponentType | None = None,
    ) -> dict[str, object]:
        """检查组件当前草稿、完整候选源码或 edits 应用后的候选源码。

        组件归属校验始终先于缓存查找；缓存只复用检查计算结果。
        """

        component = None
        current_content = ""
        component_name = "未保存组件草稿"
        resolved_preview_schema = preview_schema
        resolved_component_type = component_type or WorkspaceComponentType.CONTENT_COMPONENT
        if component_id is not None:
            component = await WorkspaceComponentService(self.session).get(component_id)
            if component.workspace_id != workspace_id:
                raise AppException(status_code=403, code="AI_COMPONENT_SCOPE_DENIED", detail="组件不属于当前工作空间，拒绝检查。")
            current_content = component.content
            component_name = component.name
            if preview_schema is None:
                resolved_preview_schema = component.preview_schema
            if component_type is None:
                resolved_component_type = component.component_type
        elif content is None:
            return ComponentValidationService.contract_failed_result(
                code="COMPONENT_TARGET_REQUIRED",
                message="未指定组件时，必须传入 content 才能检查未保存组件源码。",
            )

        candidate = self._resolve_candidate_source(
            current_content=current_content,
            content=content,
            edits=edits,
        )
        if isinstance(candidate, dict):
            return ComponentValidationService.enrich_contract_failure(candidate)
        audio_failure = self._audio_option_failure(candidate.content)
        if audio_failure is not None:
            return ComponentValidationService.enrich_contract_failure(audio_failure)

        try:
            resolved_preview_schema = validate_component_preview_schema_text(resolved_preview_schema)
            if resolved_component_type == WorkspaceComponentType.CONTENT_COMPONENT:
                validate_content_component_size_controls(resolved_preview_schema)
        except AppException as exc:
            return ComponentValidationService.contract_failed_result(
                code=exc.code,
                message=exc.detail,
                canonical_diff=candidate.canonical_diff,
            )

        profile_key, preview_options = build_component_validation_profile(resolved_component_type)
        candidate_hash = ComponentValidationService.build_candidate_hash(
            content=candidate.content,
            preview_schema=resolved_preview_schema,
            component_type=resolved_component_type,
        )

        async def execute_check() -> dict[str, object]:
            try:
                preview = await ComponentPreviewService(self.session).create_source_preview_artifact(
                    workspace_id=workspace_id,
                    component_id=component_id,
                    component_name=component_name,
                    content=candidate.content,
                    preview_schema=resolved_preview_schema,
                    preview_options=preview_options,
                    tenant_id=f"tenant_{user_id}",
                    file_type=PageFileType.VUE,
                )
            except AppException as exc:
                return ComponentValidationService.contract_failed_result(
                    code=exc.code,
                    message=exc.detail,
                    canonical_diff=candidate.canonical_diff,
                )
            await self._release_session_before_diagnostics()
            return await self.component_validation_service.dispatch(
                artifact_id=preview.artifact_id,
                workspace_id=workspace_id,
                project_id=preview.project_id,
                label=f"component:{component_id or 'draft'}",
                patch_repaired=candidate.patch_repaired,
                canonical_diff=candidate.canonical_diff,
                profile_key=profile_key,
                candidate_hash=candidate_hash,
            )

        return await self._run_with_cache(
            kind="component",
            workspace_id=workspace_id,
            project_id=None,
            source=candidate.content,
            importer_module_path=None,
            candidate=candidate,
            execute_check=execute_check,
            component_preview_schema=resolved_preview_schema,
            component_type_value=resolved_component_type.value,
            profile_key=profile_key,
        )

    async def _run_with_cache(
        self,
        *,
        kind: str,
        workspace_id: int,
        project_id: int | None,
        source: str,
        importer_module_path: str | None,
        candidate: CandidateSource,
        execute_check: Callable[[], Awaitable[dict[str, object]]],
        component_preview_schema: str | None = None,
        component_type_value: str = "",
        profile_key: str = "",
        page_metadata: dict[str, object] | None = None,
        runtime_routes_override: dict[str, object] | None = None,
        capture_screenshot: bool = False,
    ) -> dict[str, object]:
        """鉴权之后按完整输入指纹复用检查结果，并对并发相同检查做 in-flight 合并。"""

        try:
            if capture_screenshot:
                from app.services.runtime_release_identity import (
                    refresh_runtime_release_identity,
                )
                await self._release_session_before_diagnostics()
                await refresh_runtime_release_identity()
            if kind == "component":
                fingerprint = await self.fingerprint_builder.build_component_fingerprint(
                    workspace_id=workspace_id,
                    source=source,
                    preview_schema=component_preview_schema,
                    component_type_value=component_type_value,
                    profile_key=profile_key,
                )
            else:
                fingerprint = await self.fingerprint_builder.build_page_fingerprint(
                    workspace_id=workspace_id,
                    project_id=int(project_id or 0),
                    source=source,
                    importer_module_path=importer_module_path or "",
                    **({"page_metadata": page_metadata} if capture_screenshot else {}),
                    **({"runtime_routes_override": runtime_routes_override} if runtime_routes_override is not None else {}),
                )
        except AppException as exc:
            if kind == "component":
                return ComponentValidationService.contract_failed_result(
                    code=exc.code,
                    message=exc.detail,
                    canonical_diff=candidate.canonical_diff,
                )
            return self._failed_result(code=exc.code, message=exc.detail)

        if kind == "page" and capture_screenshot:
            from app.services.code_check_fingerprint import capture_check_fingerprint
            fingerprint = capture_check_fingerprint(fingerprint)
        result, cache_source = await self.result_cache.get_or_execute(fingerprint, execute_check)
        logger.info("代码检查结果已解析。", extra={"event": "code_check.result", "fingerprint": fingerprint,
                    "cache_source": cache_source, "capture_screenshot": capture_screenshot,
                    "screenshot_status": (result.get("_screenshot_phase") or {}).get("status")})
        # 命中/合并结果复用检查结论，但回填本次候选的 edits 元数据，避免复用别的编辑路径 diff。
        return {
            **result,
            "patch_repaired": candidate.patch_repaired,
            "canonical_diff": candidate.canonical_diff,
            "_code_check_cache": cache_source,
            **({"_capture_identity": fingerprint, "_capture_metadata": page_metadata} if capture_screenshot else {}),
        }

    async def _dispatch_diagnostics(
        self,
        *,
        artifact_id: str,
        workspace_id: int,
        project_id: int | None,
        label: str,
        patch_repaired: bool,
        canonical_diff: str | None,
        render_preview_url: str | None = None,
        render_viewport: CaptureViewport | None = None,
        page_id: int | None = None,
        source_override: str | None = None,
        capture_screenshot: bool = False,
    ) -> dict[str, object]:
        """调用 Runtime 诊断接口，并补齐候选源码变更元数据。"""

        defer_artifact_cleanup = False
        try:
            diagnostics_token = TokenService.generate_runtime_diagnostics_command_token(
                artifact_id=artifact_id,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            compile_started_at = time.perf_counter()
            result = await self.runtime_client.dispatch_artifact_diagnostics(
                artifact_id=artifact_id,
                diagnostics_token=diagnostics_token,
                label=label,
            )
            logger.info(
                "Runtime 编译诊断阶段完成。",
                extra={
                    "event": "runtime.diagnostics.compile.finished",
                    "artifact_id": artifact_id,
                    "label": label,
                    "duration_ms": round((time.perf_counter() - compile_started_at) * 1000, 2),
                },
            )
            enriched_result = {
                **result,
                "patch_repaired": patch_repaired,
                "canonical_diff": canonical_diff,
            }
            if render_preview_url and render_viewport and is_validation_passed(
                enriched_result, require_render=False
            ):
                # 从调用远程渲染开始，异常路径必须保留 artifact，避免后台 attempt
                # 仍在使用时读到 404；已知终态返回后再立即清理。
                defer_artifact_cleanup = True
                render_result = await self._append_page_render_diagnostics(
                    enriched_result,
                    preview_url=render_preview_url,
                    viewport=render_viewport,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    page_id=page_id,
                    artifact_id=artifact_id,
                    source_override=source_override,
                    capture_screenshot=capture_screenshot,
                )
                if isinstance(render_result, dict) and not render_result.get("_render_artifact_cleanup_deferred"):
                    defer_artifact_cleanup = False
                if isinstance(render_result, dict):
                    render_result.pop("_render_artifact_cleanup_deferred", None)
                return render_result
            return {
                **enriched_result,
                "stages": {
                    "compile": _compile_stage_status(enriched_result),
                    "render": "skipped",
                },
            }
        finally:
            if not defer_artifact_cleanup:
                try:
                    await RuntimeArtifactStore().delete_artifact(artifact_id)
                except Exception:
                    logger.warning(
                        "Runtime 诊断 artifact 主动清理失败，将由 TTL 清扫兜底。",
                        extra={"event": "runtime.artifact.cleanup.failed", "artifact_id": artifact_id},
                        exc_info=True,
                    )
                # artifact 主动清理后同步释放资源持有；延迟清理（在途渲染仍在使用）走 TTL 对账。
                await self._release_preview_artifact_bindings(artifact_id)

    async def _release_preview_artifact_bindings(self, artifact_id: str) -> None:
        """释放检查 artifact 的三维资源持有；释放失败由 TTL 对账兜底，不打断检查结果。"""

        try:
            await AssetBindingService(self.session).release_owner(OWNER_KIND_PREVIEW_ARTIFACT, artifact_id)
            await self.session.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "检查 artifact 资源持有释放失败，将由 TTL 对账兜底。",
                extra={"event": "code_check.binding.release.failed", "artifact_id": artifact_id},
                exc_info=True,
            )

    async def _release_session_before_diagnostics(self) -> None:
        """结束 artifact 准备阶段的只读事务后再进入慢诊断。"""

        from app.db.tx import commit_end_read

        await commit_end_read(self.session)

    async def _append_page_render_diagnostics(
        self,
        result: dict[str, object],
        *,
        preview_url: str,
        viewport: CaptureViewport,
        workspace_id: int,
        project_id: int | None = None,
        page_id: int | None = None,
        artifact_id: str | None = None,
        source_override: str | None = None,
        capture_screenshot: bool = False,
    ) -> dict[str, object]:
        """在页面 Runtime 检查通过后追加真实渲染诊断和布局事实。"""

        from urllib.parse import parse_qs, urlsplit

        from app.services.rendering.layout_contract import normalize_layout_analysis

        query = parse_qs(urlsplit(preview_url).query)
        preview_token = (query.get("token") or [""])[0]
        render_started_at = time.perf_counter()
        render_result = await self.render_diagnostics_service.diagnose_preview(
            preview_url,
            viewport,
            logical_owner_key=(
                f"page-diagnose:{artifact_id or 'draft'}:"
                f"{viewport.width}x{viewport.height}"
            )[:128],
            workspace_id=workspace_id,
            project_id=project_id,
            page_id=page_id,
            artifact_id=artifact_id,
            preview_token=preview_token or None,
            source_override=source_override,
            **({"capture_screenshot": True} if capture_screenshot else {}),
        )
        logger.info(
            "页面远程渲染诊断阶段完成。",
            extra={
                "event": "runtime.diagnostics.render.finished",
                "duration_ms": round((time.perf_counter() - render_started_at) * 1000, 2),
            },
        )
        raw_diagnostics = render_result.get("diagnostics")
        render_diagnostics: list[object] = list(raw_diagnostics) if isinstance(raw_diagnostics, list) else []
        layout_analysis = normalize_layout_analysis(render_result.get("layout_analysis"))

        diagnostics = list(result.get("diagnostics") if isinstance(result.get("diagnostics"), list) else [])
        diagnostics.extend(render_diagnostics)
        render_stage = _render_stage_status(render_result, render_diagnostics)
        stages = {"compile": _compile_stage_status(result), "render": render_stage}
        if render_stage == "unavailable":
            # 执行不可用 ≠ 检查通过：不得继承编译的 success/status。
            enriched_result: dict[str, object] = {
                **result,
                "success": False,
                "valid": False,
                "status": "unavailable",
                "retryable": True,
                "diagnostics": diagnostics,
                "layout_analysis": layout_analysis,
                "summary": (
                    "页面渲染诊断执行不可用，未完成视觉校验；"
                    "请确认 Renderer 可用后重试，或显式跳过视觉校验。"
                ),
                "stages": stages,
            }
        elif render_stage == "failed":
            enriched_result = {
                **result,
                "success": False,
                "valid": False,
                "status": "failed",
                "retryable": False,
                "diagnostics": diagnostics,
                "layout_analysis": layout_analysis,
                "summary": "页面渲染诊断发现内容错误，代码检查未通过。",
                "stages": stages,
            }
        else:
            enriched_result = {
                **result,
                "diagnostics": diagnostics,
                "layout_analysis": layout_analysis,
                "stages": stages,
            }
            if render_diagnostics:
                enriched_result["summary"] = f"代码检查通过，发现 {len(render_diagnostics)} 个布局警告。"
        if isinstance(render_result, dict) and render_result.get("_render_artifact_cleanup_deferred"):
            enriched_result["_render_artifact_cleanup_deferred"] = True
        if capture_screenshot:
            enriched_result["_candidate_screenshot"] = render_result.get("_candidate_screenshot")
            enriched_result["_screenshot_phase"] = render_result.get("screenshot")
        return enriched_result

    @staticmethod
    def _audio_option_failure(source: str) -> dict[str, object] | None:
        """静态校验候选源码的音频能力与播放参数；无错误时返回 None。"""

        capability_errors = collect_audio_capability_errors(source)
        if capability_errors:
            return CodeCheckService._failed_result(
                code=AUDIO_CAPABILITY_UNAVAILABLE,
                message="候选源码依赖尚未开放的音频能力：" + "；".join(capability_errors),
            )
        errors = collect_asset_audio_errors(source)
        if not errors:
            return None
        return CodeCheckService._failed_result(
            code=AUDIO_ERROR_OPTIONS_INVALID,
            message="候选源码存在非法的音频组件参数：" + "；".join(errors),
        )

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
    def _failed_result(
        *,
        code: str,
        message: str,
        source: str = "backend",
        retryable: bool = False,
    ) -> dict[str, object]:
        """构造统一失败响应。"""

        return build_code_check_failed_result(
            code=code,
            message=message,
            source=source,
            retryable=retryable,
        )

    @staticmethod
    def _failed_result_from_exception(exc: AppException) -> dict[str, object]:
        """把 AppException 归一为检查失败结果；瞬态基础设施错误必须标记 retryable。"""

        from app.services.code_check_result_cache import (
            is_transient_infrastructure_error,
        )

        return CodeCheckService._failed_result(
            code=exc.code,
            message=exc.detail,
            retryable=is_transient_infrastructure_error(exc),
        )


def _compile_stage_status(result: Mapping[str, object]) -> str:
    """归一化编译阶段状态。"""

    status = result.get("status")
    if status == "unavailable":
        return "unavailable"
    diagnostics = result.get("diagnostics")
    has_error = isinstance(diagnostics, list) and any(
        isinstance(item, dict) and item.get("severity") == "error" for item in diagnostics
    )
    has_warning = isinstance(diagnostics, list) and any(
        isinstance(item, dict) and item.get("severity") == "warning" for item in diagnostics
    )
    if result.get("success") is False or status == "failed" or has_error:
        return "failed"
    if has_warning or status in {"passed_with_warnings", "warning"}:
        return "passed_with_warnings"
    return "passed"


def _render_stage_status(render_result: Mapping[str, object], render_diagnostics: list[object]) -> str:
    """归一化渲染阶段状态：unavailable 表示基础设施故障，不得映射为通过。"""

    render_status = render_result.get("status")
    if render_status == "unavailable":
        return "unavailable"
    if any(
        isinstance(item, dict) and item.get("code") == PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE
        for item in render_diagnostics
    ):
        return "unavailable"
    if render_status == "failed":
        return "failed"
    has_error = any(
        isinstance(item, dict) and item.get("severity") == "error" for item in render_diagnostics
    )
    has_warning = any(
        isinstance(item, dict) and item.get("severity") == "warning" for item in render_diagnostics
    )
    if has_error:
        return "failed"
    if has_warning:
        return "warning"
    return "passed"
