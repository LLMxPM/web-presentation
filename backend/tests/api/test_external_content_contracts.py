"""文件功能：验证外部响应与 OpenAPI 对拍、源码完整性及组件可直接编辑的版本/hash 基线。"""

from pathlib import Path

import pytest
from httpx import AsyncClient
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text_normalizer import calculate_source_hash
from app.models.page import Page
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService


@pytest.fixture
async def content_targets(app_session: AsyncSession) -> tuple[dict[str, str], Page, WorkspaceComponent]:
    """建立隔离的长源码页面和组件草稿，并授予读取/文本资源权限。"""

    user = User(username="content-contract", password_hash="hash", display_name="内容契约",
                role="workspace_user", preview_size_presets=build_default_preview_size_presets())
    app_session.add(user)
    await app_session.flush()
    workspace = Workspace(code="content-contract", name="内容契约空间", created_by=user.id, updated_by=user.id)
    app_session.add(workspace)
    await app_session.flush()
    project = Project(workspace_id=workspace.id, code="content-project", name="内容项目", theme_config_yaml="{}")
    app_session.add(project)
    app_session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    await app_session.flush()
    source = "<template>\r\n<div>" + "完整源码内容" * 18000 + "</div>\r\n</template>"
    page = Page(workspace_id=workspace.id, project_id=project.id, code="content-page", title="长源码页面",
                page_content=source, current_version_no=7)
    component = WorkspaceComponent(workspace_id=workspace.id, code="content-component", name="长源码草稿",
                                   import_name="ContentContract", content=source, current_version_no=3, draft_base_version_no=2)
    app_session.add_all([page, component])
    await app_session.flush()
    token = await ApiAccessTokenService(app_session).create_token(
        user_id=user.id,
        payload=ApiAccessTokenCreateRequest(name="内容测试", workspace_ids=[workspace.id],
                                            scopes=["page:read", "component:read", "asset:read", "asset:write"]),
    )
    await app_session.commit()
    return {"Authorization": f"Bearer {token.token}", "X-Workspace-ID": str(workspace.id)}, page, component


async def test_full_sources_and_draft_baselines_match_actual_response_schema(
    client: AsyncClient, content_targets: tuple[dict[str, str], Page, WorkspaceComponent],
) -> None:
    """完整内容与版本/hash 基线都符合服务端响应 Schema，可直接用于乐观编辑。"""

    headers, page, component = content_targets
    document = (await client.get("/openapi.json")).json()
    paths = [
        (f"/api/v1/pages/{page.id}/source", "/api/v1/pages/{page_id}/source"),
        (f"/api/v1/components/{component.id}/draft", "/api/v1/components/{component_id}/draft"),
        (f"/api/v1/components/{component.id}/dependencies", "/api/v1/components/{component_id}/dependencies"),
    ]
    bodies = []
    for url, template in paths:
        response = await client.get(url, headers=headers)
        assert response.status_code == 200
        schema = document["paths"][template]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        Draft202012Validator({**schema, "components": document["components"]}).validate(response.json())
        bodies.append(response.json())
    source, draft, dependencies = bodies
    assert source["source_code"] == page.page_content
    assert source["version_no"] == 7
    assert draft["content"] == component.content
    assert draft["current_version_no"] == 3
    assert draft["draft_base_version_no"] == 2
    assert draft["draft_hash"] == calculate_source_hash(component.content)
    assert draft["preview_schema"] is None
    assert dependencies["current_version_no"] == 3
    assert dependencies["dependencies"] == []


async def test_asset_preview_result_matches_schema_without_writing_content(
    client: AsyncClient, content_targets: tuple[dict[str, str], Page, WorkspaceComponent],
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """使用独立存储建立文本资源，验证 diff 响应并确认候选内容没有写穿。"""

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "asset_storage_driver", "local")
    monkeypatch.setattr(get_settings(), "page_screenshot_local_root", str(tmp_path / "assets"))
    headers, _page, _component = content_targets
    created = await client.post("/api/v1/assets/content", headers={**headers, "Idempotency-Key": "content-preview-create"},
                                json={"name": "测试文本", "original_name": "test.mmd", "asset_type": "mermaid", "content": "graph TD\n  A-->B"})
    assert created.status_code == 201
    asset_id = created.json()["id"]
    response = await client.post(f"/api/v1/assets/{asset_id}/content/preview", headers=headers, json={"content": "graph TD\n  A-->C"})
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert "+  A-->C" in response.json()["unified_diff"]
    document = (await client.get("/openapi.json")).json()
    schema = document["paths"]["/api/v1/assets/{asset_id}/content/preview"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft202012Validator({**schema, "components": document["components"]}).validate(response.json())
    current = await client.get(f"/api/v1/assets/{asset_id}/content", headers=headers)
    assert current.json()["content"] == "graph TD\n  A-->B"
