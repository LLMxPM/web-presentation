"""文件功能：验证页面可视化编辑服务的基线校验、Runtime 分析与 artifact 编排。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.schemas.page_visual_edit import (
    PageVisualEditComponentSchema,
    PageVisualEditPreviewArtifactCreateRequest,
)
from app.schemas.page_visual_edit_manifest import (
    PageVisualEditDiagnostic,
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
    build_page_visual_edit_source_hash,
)
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.schemas.runtime_page_visual_edit import RuntimePageVisualEditAnalyzeResponse
from app.services.page_visual_edit_service import PageVisualEditService


SOURCE = "<template><main>页面</main></template>"
INSTRUMENTED_SOURCE = f"{SOURCE}\n<!-- visual-edit -->"
MODULE_PATH = "src/views/PGdemo.vue"


def _build_manifest() -> PageVisualEditManifest:
    """构造包含 warning 和 error 的 Runtime canonical Manifest。"""

    return PageVisualEditManifest(
        protocol_version=1,
        module_path=MODULE_PATH,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        root=PageVisualEditNode(
            node_id="node_root",
            kind="root",
            tag="#document",
            source_range=PageVisualEditSourceRange(start=0, end=len(SOURCE)),
        ),
        diagnostics=[
            PageVisualEditDiagnostic(
                severity="warning",
                code="DYNAMIC_EXPRESSION",
                message="动态表达式只读。",
            ),
            PageVisualEditDiagnostic(
                severity="error",
                code="SFC_PARSE_ERROR",
                message="示例错误。",
            ),
        ],
        tailwind_catalog={"version": 1, "groups": []},
    )


def _build_dependencies(*, instrumented_source: str | None = INSTRUMENTED_SOURCE):
    """构造服务单元测试所需的页面、仓储和外部服务替身。"""

    page = SimpleNamespace(
        id=12,
        code="PGdemo",
        page_content=SOURCE,
        current_version_no=3,
        file_type="vue",
        workspace_id=5,
        project_id=7,
    )
    page_service = SimpleNamespace(
        _get_page_or_raise=AsyncMock(return_value=page),
        _ensure_page_access=AsyncMock(return_value=None),
    )
    page_version_repository = SimpleNamespace(
        get_by_page_and_version=AsyncMock(return_value=SimpleNamespace(id=31)),
    )
    runtime_client = SimpleNamespace(
        analyze=AsyncMock(
            return_value=RuntimePageVisualEditAnalyzeResponse(
                protocol_version=1,
                manifest=_build_manifest(),
                instrumented_source=instrumented_source,
            )
        )
    )
    preview_service = SimpleNamespace(
        create_preview_artifact=AsyncMock(
            return_value=PreviewArtifactResponse(
                preview_url="http://backend/preview/artifacts/rt_demo?token=test",
                artifact_id="rt_demo",
                preview_kind="page",
                entry_descriptor=PreviewEntryDescriptor(
                    entry_type="module", module_path=MODULE_PATH
                ),
                viewport_width=1920,
                viewport_height=1080,
                project_id=7,
                workspace_id=5,
            )
        )
    )
    component_schema_service = SimpleNamespace(
        build_for_page=AsyncMock(
            return_value={
                "LocalCard": PageVisualEditComponentSchema(
                    source="workspace_component",
                    import_path="@workspace-components/CMP001/v/1",
                    component_code="CMP001",
                    version_no=1,
                    props=None,
                )
            }
        )
    )
    return (
        page,
        page_service,
        page_version_repository,
        runtime_client,
        preview_service,
        component_schema_service,
    )


def _build_service(*, instrumented_source: str | None = INSTRUMENTED_SOURCE):
    """使用替身依赖构造待测服务。"""

    dependencies = _build_dependencies(instrumented_source=instrumented_source)
    (
        _,
        page_service,
        repository,
        runtime_client,
        preview_service,
        component_schema_service,
    ) = dependencies
    service = PageVisualEditService(
        SimpleNamespace(),
        page_service=page_service,
        page_version_repository=repository,
        runtime_client=runtime_client,
        preview_service=preview_service,
        component_schema_service=component_schema_service,
    )
    return service, dependencies


@pytest.mark.asyncio
async def test_create_preview_artifact_should_bind_current_page_version() -> None:
    """成功链路应把当前版本、源码 hash 和 canonical Manifest 绑定到专用 artifact。"""

    service, dependencies = _build_service()
    (
        page,
        page_service,
        repository,
        runtime_client,
        preview_service,
        component_schema_service,
    ) = dependencies

    response = await service.create_preview_artifact(
        page_id=page.id,
        payload=PageVisualEditPreviewArtifactCreateRequest(
            protocol_version=1, base_version_no=3
        ),
        user_id=9,
    )

    page_service._ensure_page_access.assert_awaited_once_with(page, user_id=9)
    repository.get_by_page_and_version.assert_awaited_once_with(12, 3)
    analyze_request = runtime_client.analyze.await_args.args[0]
    assert analyze_request.source == SOURCE
    assert analyze_request.source_hash == build_page_visual_edit_source_hash(SOURCE)
    preview_kwargs = preview_service.create_preview_artifact.await_args.kwargs
    assert preview_kwargs["artifact_kind"] == "page_visual_edit_preview"
    assert preview_kwargs["tenant_id"] == "tenant_9"
    assert (
        preview_kwargs["page_module_overrides"][MODULE_PATH].content
        == INSTRUMENTED_SOURCE
    )
    assert preview_kwargs["page_module_overrides"][MODULE_PATH].page_version_id == 31
    visual_edit = preview_kwargs["manifest_extensions"]["visual_edit"]
    assert visual_edit["page_id"] == 12
    assert visual_edit["page_version_id"] == 31
    assert visual_edit["base_version_no"] == 3
    assert visual_edit["manifest"]["protocolVersion"] == 1
    assert visual_edit["component_schemas"] == {
        "LocalCard": {
            "source": "workspace_component",
            "import_path": "@workspace-components/CMP001/v/1",
            "component_code": "CMP001",
            "version_no": 1,
            "props": None,
        }
    }
    assert visual_edit["warnings"] == [
        {
            "severity": "warning",
            "code": "DYNAMIC_EXPRESSION",
            "message": "动态表达式只读。",
            "sourceRange": None,
        }
    ]
    assert response.visual_edit.warnings == [_build_manifest().diagnostics[0]]
    assert response.visual_edit.component_schemas["LocalCard"].version_no == 1
    component_schema_service.build_for_page.assert_awaited_once_with(page=page)
    assert response.visual_edit.source_hash == build_page_visual_edit_source_hash(
        SOURCE
    )


def test_runtime_analysis_should_require_instrumented_source() -> None:
    """Runtime analyze 缺少插桩源码时应在响应协议层拒绝，不能静默回退 canonical。"""

    with pytest.raises(ValidationError):
        _build_service(instrumented_source=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "base_version_no", "error_code"),
    [
        ("project_id", None, 3, "PAGE_PROJECT_REQUIRED"),
        ("file_type", "ts", 3, "PAGE_VISUAL_EDIT_FILE_TYPE_UNSUPPORTED"),
        ("current_version_no", 4, 3, "PAGE_VISUAL_EDIT_BASE_VERSION_STALE"),
    ],
)
async def test_create_preview_artifact_should_reject_invalid_page_target(
    field_name: str,
    field_value: object,
    base_version_no: int,
    error_code: str,
) -> None:
    """页面缺少项目、不是 Vue 或版本漂移时不得调用 Runtime。"""

    service, dependencies = _build_service()
    page, _, _, runtime_client, _, _ = dependencies
    setattr(page, field_name, field_value)

    with pytest.raises(AppException) as exc_info:
        await service.create_preview_artifact(
            page_id=page.id,
            payload=PageVisualEditPreviewArtifactCreateRequest(
                protocol_version=1,
                base_version_no=base_version_no,
            ),
            user_id=9,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == error_code
    runtime_client.analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_preview_artifact_should_require_current_version_row() -> None:
    """页面版本链缺少当前节点时应失败，不能生成无法审计的 artifact。"""

    service, dependencies = _build_service()
    page, _, repository, runtime_client, _, _ = dependencies
    repository.get_by_page_and_version.return_value = None

    with pytest.raises(AppException) as exc_info:
        await service.create_preview_artifact(
            page_id=page.id,
            payload=PageVisualEditPreviewArtifactCreateRequest(
                protocol_version=1, base_version_no=3
            ),
            user_id=9,
        )

    assert exc_info.value.code == "PAGE_VISUAL_EDIT_VERSION_NOT_FOUND"
    runtime_client.analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_preview_artifact_should_validate_component_scope_before_runtime() -> (
    None
):
    """组件错版本或错域时应沿用依赖边界，并在 Runtime 分析前失败。"""

    service, dependencies = _build_service()
    page, _, _, runtime_client, preview_service, component_schema_service = dependencies
    component_schema_service.build_for_page.side_effect = AppException(
        status_code=400,
        code="REMOTE_COMPONENT_NOT_FOUND",
        detail="页面引用了其他工作空间组件。",
    )

    with pytest.raises(AppException) as exc_info:
        await service.create_preview_artifact(
            page_id=page.id,
            payload=PageVisualEditPreviewArtifactCreateRequest(
                protocol_version=1,
                base_version_no=3,
            ),
            user_id=9,
        )

    assert exc_info.value.code == "REMOTE_COMPONENT_NOT_FOUND"
    runtime_client.analyze.assert_not_awaited()
    preview_service.create_preview_artifact.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_preview_artifact_should_reject_preview_scope_drift() -> None:
    """PreviewService 返回其他项目作用域时不得向 Editor 暴露 artifact。"""

    service, dependencies = _build_service()
    page, _, _, _, preview_service, _ = dependencies
    preview_service.create_preview_artifact.return_value.project_id = 99

    with pytest.raises(AppException) as exc_info:
        await service.create_preview_artifact(
            page_id=page.id,
            payload=PageVisualEditPreviewArtifactCreateRequest(
                protocol_version=1, base_version_no=3
            ),
            user_id=9,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_PREVIEW_SCOPE_INVALID"
