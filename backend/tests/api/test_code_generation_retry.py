"""文件功能：验证业务编码唯一冲突时页面与组件创建接口会自动重试。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def _create_workspace_project(client: AsyncClient) -> tuple[int, int]:
    """创建页面编码测试所需的工作空间和项目。"""

    workspace_response = await client.post("/api/workspaces", json={"name": "页面编码重试空间", "status": "active"})
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "页面编码重试项目", "status": "active"},
    )
    assert project_response.status_code == 200
    return workspace_id, project_response.json()["id"]


async def test_page_create_should_retry_when_generated_code_conflicts(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面创建遇到 pages.code 并发撞号时应重新生成编码并保留初始版本。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client)
    first_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>first</div></template>",
            "file_type": "vue",
            "title": "已有页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert first_response.status_code == 200
    existing_code = first_response.json()["code"]

    _patch_first_generated_code(monkeypatch, Page, existing_code)

    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>second</div></template>",
            "file_type": "vue",
            "title": "并发重试页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["code"] != existing_code
    assert created["current_version_no"] == 1

    versions_response = await authenticated_client.get(f"/api/pages/{created['id']}/versions")
    assert versions_response.status_code == 200
    assert [item["version_no"] for item in versions_response.json()] == [1]


async def test_component_create_should_retry_when_generated_code_conflicts(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件创建遇到 workspace_components.code 并发撞号时应重新生成编码。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件编码重试工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    first_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "content": "<template><div>first component</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "name": "已有组件",
            "import_name": "ExistingRetryComponent",
            "status": "active",
        },
    )
    assert first_response.status_code == 200
    existing_code = first_response.json()["code"]

    _patch_first_generated_code(monkeypatch, WorkspaceComponent, existing_code)

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "content": "<template><div>second component</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "name": "并发重试组件",
            "import_name": "CreatedRetryComponent",
            "status": "active",
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["code"] != existing_code
    assert created["current_version_no"] == 0


def _patch_first_generated_code(monkeypatch, model_class: type, conflicting_code: str) -> None:
    """让指定模型的下一次编码生成先返回已存在编码，用于稳定复现唯一冲突。"""

    from app.core import code_generator

    real_generate_code: Callable[[AsyncSession, type, str], Awaitable[str]] = code_generator.generate_code
    returned_conflict = False

    async def fake_generate_code(session: AsyncSession, current_model_class: type, prefix: str) -> str:
        """首次返回冲突编码，后续回到真实编码生成逻辑。"""

        nonlocal returned_conflict
        if current_model_class is model_class and not returned_conflict:
            returned_conflict = True
            return conflicting_code
        return await real_generate_code(session, current_model_class, prefix)

    monkeypatch.setattr(code_generator, "generate_code", fake_generate_code)
