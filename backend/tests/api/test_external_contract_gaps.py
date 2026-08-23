"""文件功能：验证 External API 元数据更新、版本化 Guides 与操作注册表契约。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.external_operations import OPERATION_REGISTRY
from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.project_suggested_component import ProjectSuggestedComponent
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


async def _seed_contract_targets() -> tuple[str, int, int, int, int]:
    """创建页面、项目、组件与具备读写权限的 PAT，返回测试请求所需标识。"""

    async with get_session_factory()() as session:
        user = User(
            username="external_contract_user",
            password_hash="hash",
            display_name="External Contract User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            code="external-contract-ws",
            name="External Contract Workspace",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
        ))
        project = Project(
            workspace_id=workspace.id,
            code="external-contract-project",
            name="Contract Project",
            theme_config_yaml="{}",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()
        page = Page(
            workspace_id=workspace.id,
            project_id=project.id,
            code="external-contract-page",
            title="Old Page",
            page_content="<template><div /></template>",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        component = WorkspaceComponent(
            workspace_id=workspace.id,
            code="external-contract-component",
            name="Old Component",
            import_name="ExternalContractComponent",
            content="<template><div /></template>",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add_all([page, component])
        await session.flush()
        session.add(ProjectSuggestedComponent(project_id=project.id, component_id=component.id, sort_order=0))
        token = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="External-Contract-PAT",
                workspace_ids=[workspace.id],
                scopes=[
                    "project:write",
                    "page:read",
                    "page:write",
                    "component:read",
                    "component:write",
                    "design-system:read",
                    "design-system:write",
                    "asset:read",
                    "asset:write",
                ],
                expires_in_days=30,
            ),
        )
        result = token.token, workspace.id, project.id, page.id, component.id
        await session.commit()
        return result


async def _seed_cross_workspace_targets() -> tuple[str, int, int, int, int, int]:
    """创建同一用户跨工作空间的对象与仅绑定 A 空间的 PAT。"""

    async with get_session_factory()() as session:
        user = User(
            username="external_cross_workspace_user",
            password_hash="hash",
            display_name="External Cross Workspace User",
            role=UserRole.WORKSPACE_USER.value,
            preview_size_presets=build_default_preview_size_presets(),
        )
        session.add(user)
        await session.flush()

        workspace_a = Workspace(
            code="external-cross-a",
            name="External Cross Workspace A",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        workspace_b = Workspace(
            code="external-cross-b",
            name="External Cross Workspace B",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add_all([workspace_a, workspace_b])
        await session.flush()
        session.add_all([
            WorkspaceMember(
                workspace_id=workspace_a.id,
                user_id=user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            ),
            WorkspaceMember(
                workspace_id=workspace_b.id,
                user_id=user.id,
                role="owner",
                status=RecordStatus.ACTIVE.value,
            ),
        ])
        project = Project(
            workspace_id=workspace_b.id,
            code="external-cross-project",
            name="External Cross Project",
            theme_config_yaml="{}",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()
        page = Page(
            workspace_id=workspace_b.id,
            project_id=project.id,
            code="external-cross-page",
            title="Cross Workspace Page",
            page_content="<template><div /></template>",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        component = WorkspaceComponent(
            workspace_id=workspace_b.id,
            code="external-cross-component",
            name="Cross Workspace Component",
            import_name="ExternalCrossComponent",
            content="<template><div /></template>",
            created_by=user.id,
            updated_by=user.id,
            status=RecordStatus.ACTIVE.value,
        )
        session.add_all([page, component])
        await session.flush()
        token = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="External-Cross-Workspace-PAT",
                workspace_ids=[workspace_a.id],
                scopes=[
                    "project:read",
                    "page:read",
                    "page:write",
                    "component:read",
                    "component:write",
                ],
                expires_in_days=30,
            ),
        )
        result = token.token, workspace_a.id, workspace_b.id, project.id, page.id, component.id
        await session.commit()
        return result


@pytest.mark.asyncio
async def test_component_list_returns_workspace_scoped_items(client: AsyncClient) -> None:
    """组件列表应按 External API 的工作空间请求头查询并返回分页结果。"""

    token, workspace_id, _project_id, _page_id, component_id = await _seed_contract_targets()
    response = await client.get(
        "/api/v1/components",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == component_id
    assert body["items"][0]["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_component_suggested_list_returns_summary_items(client: AsyncClient) -> None:
    """建议组件列表应按摘要模型返回，而不是被完整组件响应模型拦截。"""

    token, workspace_id, project_id, _page_id, component_id = await _seed_contract_targets()
    response = await client.get(
        "/api/v1/components",
        params={"scope": "suggested", "project_id": project_id},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == component_id
    assert body["items"][0]["available"] is False
    assert "content" not in body["items"][0]


@pytest.mark.asyncio
async def test_project_configuration_update_accepts_flat_presentation_fields(client: AsyncClient) -> None:
    """项目配置更新应兼容 CLI 传入的平铺展示字段。"""

    token, workspace_id, project_id, _page_id, _component_id = await _seed_contract_targets()
    response = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={
            "configuration": {
                "page_width": 1920,
                "page_height": 1080,
                "base_font_size": "16px",
                "icon_default_stroke_width": 2,
                "show_pdf_export_button": True,
            }
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
            "Idempotency-Key": "project-configuration-flat-fields",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["page_width"] == 1920
    assert response.json()["page_height"] == 1080
    assert "theme_config_yaml" not in response.json()


@pytest.mark.asyncio
async def test_project_configuration_update_rejects_legacy_theme_config_yaml(client: AsyncClient) -> None:
    """项目配置更新应拒绝历史 theme_config_yaml，并返回标准 422。"""

    token, workspace_id, project_id, _page_id, _component_id = await _seed_contract_targets()
    response = await client.put(
        f"/api/v1/projects/{project_id}/configuration",
        json={
            "configuration": {
                "mode": "patch",
                "presentation": {
                    "theme_config_yaml": "themes:\n  lightblue: {}",
                },
            },
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
            "Idempotency-Key": "project-configuration-legacy-theme-yaml",
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "theme_config_yaml" in body["message"]


@pytest.mark.asyncio
async def test_external_asset_writes_refresh_updated_at_before_serialization(client: AsyncClient) -> None:
    """External 资源更新应在异步 flush 后刷新时间戳再构造响应。"""

    token, workspace_id, _project_id, _page_id, _component_id = await _seed_contract_targets()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_id),
    }
    created = await client.post(
        "/api/v1/assets/content",
        json={
            "asset_type": "mermaid",
            "name": "external-contract-diagram",
            "original_name": "diagram.mmd",
            "content": "graph TD\n  A-->B",
        },
        headers={**headers, "Idempotency-Key": "external-asset-create"},
    )
    assert created.status_code == 201, created.text
    asset_id = created.json()["id"]

    metadata = await client.patch(
        f"/api/v1/assets/{asset_id}",
        json={"description": "updated"},
        headers={**headers, "Idempotency-Key": "external-asset-metadata"},
    )
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["description"] == "updated"

    content = await client.put(
        f"/api/v1/assets/{asset_id}/content",
        json={"content": "graph TD\n  A-->C"},
        headers={**headers, "Idempotency-Key": "external-asset-content"},
    )
    assert content.status_code == 200, content.text


@pytest.mark.asyncio
async def test_metadata_patch_whitelist_and_idempotency(client: AsyncClient) -> None:
    """页面和组件 PATCH 仅接受安全字段，并重放首次完整实体响应。"""

    token, workspace_id, _project_id, page_id, component_id = await _seed_contract_targets()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_id),
        "Idempotency-Key": "metadata-update-1",
    }
    first = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"title": "New Page", "summary": "Summary"},
        headers=headers,
    )
    replay = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"title": "New Page", "summary": "Summary"},
        headers=headers,
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["title"] == "New Page"
    assert first.json()["current_version_no"] == 1

    conflict = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"title": "Different"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"

    invalid = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"page_content": "forbidden"},
        headers={**headers, "Idempotency-Key": "metadata-update-invalid"},
    )
    assert invalid.status_code == 422
    assert (await client.patch(
        f"/api/v1/pages/{page_id}",
        json={},
        headers={**headers, "Idempotency-Key": "metadata-update-empty"},
    )).status_code == 422
    cleared = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"summary": None, "speaker_notes": None},
        headers={**headers, "Idempotency-Key": "metadata-update-clear"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["summary"] is None
    assert cleared.json()["speaker_notes"] is None
    assert cleared.json()["current_version_no"] == 1

    component = await client.patch(
        f"/api/v1/components/{component_id}",
        json={"name": "New Component", "summary": "Safe"},
        headers={**headers, "Idempotency-Key": "component-update-1"},
    )
    assert component.status_code == 200
    assert component.json()["name"] == "New Component"
    forbidden_component = await client.patch(
        f"/api/v1/components/{component_id}",
        json={"import_name": "Forbidden"},
        headers={**headers, "Idempotency-Key": "component-update-invalid"},
    )
    assert forbidden_component.status_code == 422


@pytest.mark.asyncio
async def test_guides_index_and_detail_do_not_require_workspace_header(client: AsyncClient) -> None:
    """Guides 使用 PAT 即可读取，并公开版本、revision、Header 与独立 DTO Schema。"""

    token, _, _, _, _ = await _seed_contract_targets()
    headers = {"Authorization": f"Bearer {token}"}
    index = await client.get("/api/v1/guides", headers=headers)
    assert index.status_code == 200
    assert index.json()["api_version"] == "v1"
    assert index.json()["guide_schema_version"] == 1
    page_item = next(item for item in index.json()["operations"] if item["operation_key"] == "page.update")
    assert page_item["operation_revision"] == 1
    assert page_item["detail_url"] == "/api/v1/guides/page.update"

    detail = await client.get("/api/v1/guides/page.update", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert (body["method"], body["path"]) == ("PATCH", "/pages/{page_id}")
    assert body["required_headers"] == ["Authorization", "X-Workspace-ID", "Idempotency-Key"]
    assert set(body["request_schema"]["properties"]) == {"title", "summary", "speaker_notes"}
    assert "page_content" not in body["request_schema"]["properties"]

    missing = await client.get("/api/v1/guides/not.exists", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "GUIDE_OPERATION_NOT_FOUND"
    alias = await client.get("/api/v1/guides/operation-guide", headers=headers)
    assert alias.status_code == 404


@pytest.mark.asyncio
async def test_pat_workspace_binding_is_checked_for_object_routes(client: AsyncClient) -> None:
    """PAT 仅绑定 A 空间时，不能访问同一用户在 B 空间中的对象。"""

    token, workspace_a_id, _workspace_b_id, project_b_id, page_b_id, component_b_id = await _seed_cross_workspace_targets()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_a_id),
    }

    project_response = await client.get(
        f"/api/v1/projects/{project_b_id}/configuration",
        headers=headers,
    )
    assert project_response.status_code == 403
    assert project_response.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    page_response = await client.post(
        f"/api/v1/pages/{page_b_id}/edits",
        json={
            "page_id": page_b_id,
            "base_version_no": 1,
            "edits": [{"type": "replace_exact", "old": "div", "new": "span"}],
        },
        headers={**headers, "Idempotency-Key": "cross-workspace-page-edit"},
    )
    assert page_response.status_code == 403
    assert page_response.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    component_response = await client.post(
        "/api/v1/validate/entity",
        json={"entity_type": "component", "entity_id": component_b_id, "mode": "current"},
        headers=headers,
    )
    assert component_response.status_code == 403
    assert component_response.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_style_create_without_key_replays_and_copy_returns_created_status(client: AsyncClient) -> None:
    """缺省样式 key 的重试应重放，复制样式应返回 201。"""

    token, workspace_id, _, _, _ = await _seed_contract_targets()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_id),
    }
    create_payload = {"name": "Generated Style", "configuration": {}}
    first = await client.post(
        "/api/v1/styles",
        json=create_payload,
        headers={**headers, "Idempotency-Key": "style-create-without-key"},
    )
    replay = await client.post(
        "/api/v1/styles",
        json=create_payload,
        headers={**headers, "Idempotency-Key": "style-create-without-key"},
    )
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()

    copied = await client.post(
        f"/api/v1/styles/{first.json()['id']}/copy",
        json={},
        headers={**headers, "Idempotency-Key": "style-copy-status"},
    )
    assert copied.status_code == 201


@pytest.mark.asyncio
async def test_style_create_accepts_flat_presentation_fields(client: AsyncClient) -> None:
    """样式创建应兼容 CLI 使用的顶层完整展示配置字段。"""

    token, workspace_id, _, _, _ = await _seed_contract_targets()
    response = await client.post(
        "/api/v1/styles",
        json={
            "key": "flat-style",
            "name": "扁平完整样式",
            "description": "CLI 完整 payload",
            "page_width": 1920,
            "page_height": 1080,
            "base_font_size": "18px",
            "icon_default_stroke_width": 3,
            "show_pdf_export_button": False,
            "menu_mode": "bottom-preview",
            "theme_key": None,
            "style_spec_markdown": "## 规范",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": str(workspace_id),
            "Idempotency-Key": "style-create-flat-payload",
        },
    )

    assert response.status_code == 201, response.text
    style = response.json()
    assert style["key"] == "flat-style"
    assert style["page_width"] == 1920
    assert style["page_height"] == 1080
    assert style["base_font_size"] == "18px"
    assert style["menu_mode"] == "bottom-preview"
    assert style["style_spec_markdown"] == "## 规范"


@pytest.mark.asyncio
async def test_style_create_guide_exposes_flat_presentation_fields(client: AsyncClient) -> None:
    """样式创建 Guide 应公开与接口一致的完整字段 Schema。"""

    token, _workspace_id, _project_id, _page_id, _component_id = await _seed_contract_targets()
    response = await client.get(
        "/api/v1/guides/style.create",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    properties = response.json()["request_schema"]["properties"]
    for field_name in (
        "page_width",
        "page_height",
        "base_font_size",
        "icon_default_stroke_width",
        "show_pdf_export_button",
        "menu_mode",
        "theme_key",
        "style_spec_markdown",
    ):
        assert field_name in properties


def test_corrected_operations_have_distinct_http_contracts() -> None:
    """创建和编辑动作不得继续复用 update/create operation。"""

    expected = {
        "page.update": ("PATCH", "/pages/{page_id}"),
        "component.update": ("PATCH", "/components/{component_id}"),
        "jobs.mutation.page.create": ("POST", "/jobs/mutations/pages"),
        "jobs.mutation.page.edit": ("POST", "/jobs/mutations/pages/edits"),
        "jobs.mutation.component.create": ("POST", "/jobs/mutations/components"),
        "jobs.mutation.component.edit": ("POST", "/jobs/mutations/components/edits"),
    }
    assert {
        key: (OPERATION_REGISTRY[key].http_method, OPERATION_REGISTRY[key].path_template)
        for key in expected
    } == expected


def test_v1_capability_operations_use_canonical_paths() -> None:
    """首版 CLI 依赖的资源操作必须注册为独立 External API 契约。"""

    expected = {
        "project.configuration.get": ("GET", "/projects/{project_id}/configuration"),
        "project.configuration.update": ("PUT", "/projects/{project_id}/configuration"),
        "project.route.get": ("GET", "/projects/{project_id}/route-tree"),
        "project.route.update": ("PUT", "/projects/{project_id}/route-tree"),
        "project.apply_style": ("POST", "/projects/{project_id}/apply-style"),
        "project.build_assets.update": ("PUT", "/projects/{project_id}/build-assets"),
        "page.create": ("POST", "/pages"),
        "page.copy": ("POST", "/pages/{page_id}/copy"),
        "page.edit": ("POST", "/pages/{page_id}/edits"),
        "page.dependencies": ("GET", "/pages/{page_id}/dependencies"),
        "page.validate": ("POST", "/pages/{page_id}/validate"),
        "component.create": ("POST", "/components"),
        "component.edit": ("POST", "/components/{component_id}/edits"),
        "component.dependencies": ("GET", "/components/{component_id}/dependencies"),
        "component.validate": ("POST", "/components/{component_id}/validate"),
        "asset.content.create": ("POST", "/assets/content"),
        "asset.content.get": ("GET", "/assets/{asset_id}/content"),
        "asset.content.update": ("PUT", "/assets/{asset_id}/content"),
        "asset.content.preview": ("POST", "/assets/{asset_id}/content/preview"),
        "asset.copy": ("POST", "/assets/{asset_id}/copy"),
        "asset.tags": ("GET", "/assets/tags"),
    }
    assert {
        key: (OPERATION_REGISTRY[key].http_method, OPERATION_REGISTRY[key].path_template)
        for key in expected
    } == expected
