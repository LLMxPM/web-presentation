"""文件功能：验证 External API 元数据更新、版本化 Guides 与操作注册表契约。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.external_operations import OPERATION_REGISTRY
from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


async def _seed_contract_targets() -> tuple[str, int, int, int]:
    """创建页面、组件与具备读写权限的 PAT，返回测试请求所需标识。"""

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
        token = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name="External-Contract-PAT",
                workspace_ids=[workspace.id],
                scopes=["page:read", "page:write", "component:read", "component:write"],
                expires_in_days=30,
            ),
        )
        result = token.token, workspace.id, page.id, component.id
        await session.commit()
        return result


@pytest.mark.asyncio
async def test_metadata_patch_whitelist_and_idempotency(client: AsyncClient) -> None:
    """页面和组件 PATCH 仅接受安全字段，并重放首次完整实体响应。"""

    token, workspace_id, page_id, component_id = await _seed_contract_targets()
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

    token, _, _, _ = await _seed_contract_targets()
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


def test_corrected_operations_have_distinct_http_contracts() -> None:
    """恢复、创建和编辑动作不得继续复用 update/create operation。"""

    expected = {
        "page.update": ("PATCH", "/pages/{page_id}"),
        "page.version.restore": ("POST", "/pages/{page_id}/versions/{version_no}/restore"),
        "component.update": ("PATCH", "/components/{component_id}"),
        "component.version.restore_draft": ("POST", "/components/{component_id}/versions/{version_no}/restore-draft"),
        "component.restore": ("POST", "/components/{component_id}/restore"),
        "jobs.mutation.page.create": ("POST", "/jobs/mutations/pages"),
        "jobs.mutation.page.edit": ("POST", "/jobs/mutations/pages/edits"),
        "jobs.mutation.component.create": ("POST", "/jobs/mutations/components"),
        "jobs.mutation.component.edit": ("POST", "/jobs/mutations/components/edits"),
    }
    assert {
        key: (OPERATION_REGISTRY[key].http_method, OPERATION_REGISTRY[key].path_template)
        for key in expected
    } == expected
