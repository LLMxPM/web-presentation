"""文件功能：验证页面可视化编辑预览 artifact API 的鉴权、版本基线与 artifact 元数据。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.schemas.page_visual_edit_manifest import (
    PageVisualEditDiagnostic,
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
)
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditAnalyzeResponse,
)
from app.services.runtime_visual_edit_client import RuntimeVisualEditClient


PAGE_SOURCE = '<template><main class="p-4">页面标题</main></template>'


async def _create_workspace_and_project(
    authenticated_client: AsyncClient,
    *,
    suffix: str,
) -> tuple[int, int]:
    """创建组件 schema API 场景所需的工作空间和项目。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": f"可视化组件空间-{suffix}", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": f"可视化组件项目-{suffix}",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    return workspace_id, project_response.json()["id"]


async def _create_and_publish_component(
    authenticated_client: AsyncClient,
    *,
    workspace_id: int,
    name: str,
    import_name: str,
    preview_schema: str | None,
) -> dict[str, Any]:
    """创建并发布一个原子组件，允许覆盖有 schema 和无 schema 场景。"""

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "import_name": import_name,
            "component_type": "原子组件",
            "content": "<template><section /></template>",
            "preview_schema": preview_schema,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    publish_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"change_note": "发布 visual edit 测试版本"},
    )
    assert publish_response.status_code == 200
    return publish_response.json()


async def _create_page(authenticated_client: AsyncClient) -> dict[str, Any]:
    """创建带项目归属的 Vue 页面并返回页面响应。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "可视化编辑空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "可视化编辑项目",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": PAGE_SOURCE,
            "file_type": "vue",
            "title": "可视化编辑页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    return page_response.json()


def _build_analysis(
    request: RuntimePageVisualEditAnalyzeRequest,
) -> RuntimePageVisualEditAnalyzeResponse:
    """根据 Backend 请求构造可验证来源身份的 Runtime 分析结果。"""

    manifest = PageVisualEditManifest(
        protocol_version=1,
        module_path=request.module_path,
        source_hash=request.source_hash,
        root=PageVisualEditNode(
            node_id="node_root",
            kind="root",
            tag="#document",
            source_range=PageVisualEditSourceRange(start=0, end=len(request.source)),
            template_actions={
                "can_duplicate": False,
                "can_delete": False,
                "readonly_reason": "STRUCTURE_ROOT_UNSUPPORTED",
            },
        ),
        diagnostics=[
            PageVisualEditDiagnostic(
                severity="warning",
                code="DYNAMIC_EXPRESSION",
                message="动态表达式保持只读。",
            )
        ],
        json_sources=[],
        tailwind_catalog={"version": 1, "groups": []},
    )
    return RuntimePageVisualEditAnalyzeResponse(
        protocol_version=1,
        manifest=manifest,
        instrumented_source=f"{request.source}\n<!-- instrumented -->",
    )


def _patch_analyze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """让组件 schema API 场景使用与请求源码严格绑定的 Runtime 分析结果。"""

    async def analyze(
        _self: RuntimeVisualEditClient,
        request: RuntimePageVisualEditAnalyzeRequest,
    ) -> RuntimePageVisualEditAnalyzeResponse:
        """返回包含最小节点树的 canonical Manifest。"""

        return _build_analysis(request)

    monkeypatch.setattr(RuntimeVisualEditClient, "analyze", analyze)


@pytest.mark.asyncio
async def test_create_visual_edit_preview_artifact_should_persist_bound_metadata(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API 应生成绑定当前版本的专用 artifact，并保存 Runtime canonical Manifest。"""

    page = await _create_page(authenticated_client)
    captured_requests: list[RuntimePageVisualEditAnalyzeRequest] = []

    async def analyze(
        _self: RuntimeVisualEditClient,
        request: RuntimePageVisualEditAnalyzeRequest,
    ) -> RuntimePageVisualEditAnalyzeResponse:
        """记录 Runtime 分析请求并返回带插桩源码的结果。"""

        captured_requests.append(request)
        return _build_analysis(request)

    monkeypatch.setattr(RuntimeVisualEditClient, "analyze", analyze)
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/preview-artifacts",
        json={"protocol_version": 1, "base_version_no": page["current_version_no"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preview_kind"] == "page"
    assert payload["visual_edit"]["protocol_version"] == 1
    assert payload["visual_edit"]["base_version_no"] == 1
    assert len(payload["visual_edit"]["source_hash"]) == 64
    assert payload["visual_edit"]["component_schemas"] == {}
    assert payload["visual_edit"]["warnings"][0]["severity"] == "warning"
    assert captured_requests[0].source == PAGE_SOURCE

    artifact_id = payload["artifact_id"]
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    artifact_manifest = manifest_response.json()
    assert artifact_manifest["artifact_kind"] == "page_visual_edit_preview"
    visual_edit = artifact_manifest["visual_edit"]
    assert visual_edit["page_id"] == page["id"]
    assert visual_edit["page_version_id"] > 0
    assert visual_edit["base_version_no"] == 1
    assert visual_edit["source_hash"] == payload["visual_edit"]["source_hash"]
    assert visual_edit["module_path"] == f"src/views/{page['code']}.vue"
    assert visual_edit["manifest"]["protocolVersion"] == 1
    assert visual_edit["manifest"]["tailwindCatalog"] == {"version": 1, "groups": []}
    assert visual_edit["manifest"]["diagnostics"][0]["code"] == "DYNAMIC_EXPRESSION"
    assert visual_edit["component_schemas"] == {}

    module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": visual_edit["module_path"]},
        headers=runtime_service_headers,
    )
    assert module_response.status_code == 200
    assert module_response.text == f"{PAGE_SOURCE}\n<!-- instrumented -->"


@pytest.mark.asyncio
async def test_create_visual_edit_artifact_should_expose_pinned_component_props_only(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组件映射应使用页面 v1 import 本地名和 v1 schema，不受组件最新草稿漂移。"""

    workspace_id, project_id = await _create_workspace_and_project(
        authenticated_client,
        suffix="pinned",
    )
    published_schema = json.dumps(
        {
            "props": {
                "height": {"type": "number", "label": "高度", "default": 320},
                "variant": {
                    "type": "select",
                    "label": "样式",
                    "default": "primary",
                    "options": [
                        {"label": "主要", "value": "primary"},
                        {"label": "次要", "value": "secondary"},
                    ],
                },
                "enabled": {"type": "boolean", "label": "启用", "default": True},
            },
            "slots": {"default": {"default": []}},
            "presets": [],
        },
        ensure_ascii=False,
    )
    pinned_component = await _create_and_publish_component(
        authenticated_client,
        workspace_id=workspace_id,
        name="钉住版本组件",
        import_name="PinnedVisualCard",
        preview_schema=published_schema,
    )
    no_schema_component = await _create_and_publish_component(
        authenticated_client,
        workspace_id=workspace_id,
        name="无 Schema 组件",
        import_name="BareVisualCard",
        preview_schema=None,
    )
    draft_schema = json.dumps(
        {
            "props": {
                "height": {"type": "number", "default": 999},
                "draftOnly": {"type": "string", "default": "不能下发"},
            }
        },
        ensure_ascii=False,
    )
    update_response = await authenticated_client.patch(
        f"/api/components/{pinned_component['id']}",
        json={"preview_schema": draft_schema},
    )
    assert update_response.status_code == 200
    assert update_response.json()["has_unpublished_changes"] is True

    page_source = f"""<script setup lang="ts">
import LocalPinnedCard from '@workspace-components/{pinned_component["code"]}/v/1'
import LocalBareCard from '@workspace-components/{no_schema_component["code"]}/v/1'
</script>
<template><LocalPinnedCard /><LocalBareCard /></template>"""
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": page_source,
            "file_type": "vue",
            "title": "组件属性页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()
    _patch_analyze(monkeypatch)

    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/preview-artifacts",
        json={"protocol_version": 1, "base_version_no": 1},
    )

    assert response.status_code == 200
    component_schemas = response.json()["visual_edit"]["component_schemas"]
    assert set(component_schemas) == {"LocalPinnedCard", "LocalBareCard"}
    pinned_schema = component_schemas["LocalPinnedCard"]
    assert pinned_schema["source"] == "workspace_component"
    assert pinned_schema["component_code"] == pinned_component["code"]
    assert pinned_schema["version_no"] == 1
    assert pinned_schema["import_path"].endswith(f"{pinned_component['code']}/v/1")
    assert pinned_schema["props"]["height"]["default"] == 320
    assert pinned_schema["props"]["variant"]["type"] == "select"
    assert pinned_schema["props"]["variant"]["options"][1] == {
        "label": "次要",
        "value": "secondary",
    }
    assert pinned_schema["props"]["enabled"]["type"] == "boolean"
    assert "draftOnly" not in pinned_schema["props"]
    assert "slots" not in pinned_schema
    assert "presets" not in pinned_schema
    assert component_schemas["LocalBareCard"]["props"] is None

    artifact_id = response.json()["artifact_id"]
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    assert (
        manifest_response.json()["visual_edit"]["component_schemas"]
        == component_schemas
    )


@pytest.mark.asyncio
async def test_component_schema_dependency_errors_should_reuse_page_boundary(
    authenticated_client: AsyncClient,
) -> None:
    """错版本和跨工作空间组件在页面写入边界即失败，visual edit 不得另行猜测。"""

    source_workspace_id, _ = await _create_workspace_and_project(
        authenticated_client,
        suffix="source",
    )
    component = await _create_and_publish_component(
        authenticated_client,
        workspace_id=source_workspace_id,
        name="边界组件",
        import_name="BoundaryVisualCard",
        preview_schema=None,
    )
    target_workspace_id, target_project_id = await _create_workspace_and_project(
        authenticated_client,
        suffix="target",
    )

    cross_workspace_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": (
                f"<script setup>import CrossCard from '@workspace-components/{component['code']}/v/1'"
                "</script><template><CrossCard /></template>"
            ),
            "file_type": "vue",
            "title": "跨空间非法页面",
            "status": "active",
            "workspace_id": target_workspace_id,
            "project_id": target_project_id,
        },
    )
    assert cross_workspace_response.status_code == 400
    assert cross_workspace_response.json()["code"] == "REMOTE_COMPONENT_NOT_FOUND"

    source_project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": source_workspace_id,
            "name": "错版本项目",
            "status": "active",
        },
    )
    assert source_project_response.status_code == 200
    wrong_version_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": (
                f"<script setup>import WrongCard from '@workspace-components/{component['code']}/v/99'"
                "</script><template><WrongCard /></template>"
            ),
            "file_type": "vue",
            "title": "错版本非法页面",
            "status": "active",
            "workspace_id": source_workspace_id,
            "project_id": source_project_response.json()["id"],
        },
    )
    assert wrong_version_response.status_code == 400
    assert wrong_version_response.json()["code"] == "REMOTE_COMPONENT_VERSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_visual_edit_preview_artifact_should_reject_stale_base(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求基线旧于 Backend 当前版本时应在调用 Runtime 前返回 409。"""

    page = await _create_page(authenticated_client)
    analyze_mock = AsyncMock()
    monkeypatch.setattr(RuntimeVisualEditClient, "analyze", analyze_mock)

    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/preview-artifacts",
        json={"protocol_version": 1, "base_version_no": 2},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PAGE_VISUAL_EDIT_BASE_VERSION_STALE"
    analyze_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_visual_edit_preview_artifact_should_require_login(
    client: AsyncClient,
) -> None:
    """未登录用户不得访问页面可视化编辑 artifact 接口。"""

    response = await client.post(
        "/api/pages/1/visual-edit/preview-artifacts",
        json={"protocol_version": 1, "base_version_no": 1},
    )

    assert response.status_code == 401
