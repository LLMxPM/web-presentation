"""文件功能：验证内容助手通用归档工具的工作空间隔离与整批事务语义。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic_ai import ApprovalRequired
from sqlalchemy import select

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import (
    CODE_CHECK_TOOL_SCOPES,
    PAGE_TOOL_READ_SCOPES,
    PAGE_TOOL_WRITE_SCOPES,
    PROJECT_TOOL_READ_SCOPES,
    PROJECT_TOOL_WRITE_SCOPES,
    RESOURCE_TOOL_READ_SCOPES,
    RESOURCE_TOOL_WRITE_SCOPES,
    build_agent_tool_token,
)
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.generic import build_generic_business_tools
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.user import User
from app.models.workspace import Project
from app.models.workspace_style import WorkspaceStyle
from app.services.auth_service import AuthContext


async def test_batch_archive_should_be_atomic_and_isolated_by_workspace(authenticated_client: AsyncClient) -> None:
    """跨工作空间目标导致整批失败，合法批次确认后一次性归档。"""

    first_workspace_id = await _create_workspace(authenticated_client, "通用归档工作空间")
    second_workspace_id = await _create_workspace(authenticated_client, "通用归档其他空间")
    first_style_id = await _create_style(authenticated_client, first_workspace_id, "first_style", "样式一")
    second_style_id = await _create_style(authenticated_client, first_workspace_id, "second_style", "样式二")
    foreign_style_id = await _create_style(authenticated_client, second_workspace_id, "foreign_style", "其他样式")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}
    archive_tool = tools["archive_entity"]
    context = _build_tool_run_context(first_workspace_id, approved=True)

    guide_index = await tools["get_operation_guide"].entrypoint(context)
    assert any(item["operation_key"] == "style.archive" for item in guide_index["operations"])
    archive_guide = await tools["get_operation_guide"].entrypoint(context, "style.archive")
    assert archive_guide["operation_key"] == "style.archive"
    assert "versions" not in archive_guide["parameters"]["properties"]

    with pytest.raises(AppException) as error:
        await archive_tool.entrypoint(context, "style", [first_style_id, foreign_style_id], "整理")
    assert error.value.code == "AI_ENTITY_TARGETS_NOT_FOUND"
    assert await _read_deleted_at(first_style_id) is None

    style_detail = await tools["get_entity"].entrypoint(context, "style", "detail", first_style_id, None, {})
    assert 'view="configuration", target_id=' + str(first_style_id) in style_detail["message"]

    result = await archive_tool.entrypoint(context, "style", [first_style_id, second_style_id], "整理")

    assert result["success"] is True
    assert result["data"]["archived_count"] == 2
    assert await _read_deleted_at(first_style_id) is not None
    assert await _read_deleted_at(second_style_id) is not None

    listed = await tools["list_entities"].entrypoint(context, "style", {}, "items")
    assert first_style_id not in {item["id"] for item in listed["data"]["items"]}
    with pytest.raises(AppException):
        await tools["get_entity"].entrypoint(context, "style", "detail", first_style_id, None, {})


async def test_workspace_session_should_query_pages_across_projects_but_reject_foreign_project(authenticated_client: AsyncClient) -> None:
    """同一工作空间会话可切换项目目标，但显式外部项目 ID 必须拒绝。"""

    workspace_id = await _create_workspace(authenticated_client, "跨项目工具工作空间")
    first_project_id = await _create_project(authenticated_client, workspace_id, "项目一")
    second_project_id = await _create_project(authenticated_client, workspace_id, "项目二")
    foreign_workspace_id = await _create_workspace(authenticated_client, "跨项目工具外部空间")
    foreign_project_id = await _create_project(authenticated_client, foreign_workspace_id, "外部项目")
    await _create_page(authenticated_client, workspace_id, first_project_id, "项目一页面")
    await _create_page(authenticated_client, workspace_id, second_project_id, "项目二页面")

    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}
    context = _build_tool_run_context(workspace_id, approved=False)
    first = await tools["list_entities"].entrypoint(context, "page", {"project_id": first_project_id}, "items")
    second = await tools["list_entities"].entrypoint(context, "page", {"project_id": second_project_id}, "items")

    assert [item["title"] for item in first["data"]["items"]] == ["项目一页面"]
    assert [item["title"] for item in second["data"]["items"]] == ["项目二页面"]
    with pytest.raises(AppException) as error:
        await tools["list_entities"].entrypoint(context, "page", {"project_id": foreign_project_id}, "items")
    assert error.value.code == "AI_ENTITY_SCOPE_DENIED"


async def test_selected_projects_should_filter_queries_and_hide_archived_pages(authenticated_client: AsyncClient) -> None:
    """项目工作集覆盖列表与详情，归档页面随后退出 AI 查询边界。"""

    workspace_id = await _create_workspace(authenticated_client, "工作集与焦点确认")
    first_project_id = await _create_project(authenticated_client, workspace_id, "焦点项目")
    second_project_id = await _create_project(authenticated_client, workspace_id, "焦点外项目")
    second_page_id = await _create_page(authenticated_client, workspace_id, second_project_id, "待恢复页面")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}

    selected_context = _build_tool_run_context(
        workspace_id,
        approved=False,
        focus_project_id=first_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[first_project_id],
    )
    listed = await tools["list_entities"].entrypoint(selected_context, "project", {}, "items")
    assert [item["id"] for item in listed["data"]["items"]] == [first_project_id]
    with pytest.raises(AppException) as error:
        await tools["get_entity"].entrypoint(selected_context, "project", "detail", second_project_id, None, {})
    assert error.value.code == "AI_PROJECT_OUTSIDE_WORK_SCOPE"

    cross_focus_context = _build_tool_run_context(
        workspace_id,
        approved=False,
        focus_project_id=first_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[first_project_id, second_project_id],
    )
    with pytest.raises(ApprovalRequired):
        await tools["update_entity"].entrypoint(cross_focus_context, "project", second_project_id, {"name": "已修改"}, "metadata")

    approved_context = _build_tool_run_context(
        workspace_id,
        approved=True,
        focus_project_id=first_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[first_project_id, second_project_id],
    )
    listed_projects = await tools["list_entities"].entrypoint(approved_context, "project", {}, "items")
    assert not any("first_page_screenshot_url" in item for item in listed_projects["data"]["items"])
    project_detail = await tools["get_entity"].entrypoint(approved_context, "project", "detail", second_project_id, None, {})
    assert "first_page_screenshot_url" not in project_detail["data"]
    assert 'view="configuration"' in project_detail["message"]
    assert 'view="route_tree"' in project_detail["message"]
    detail = await tools["get_entity"].entrypoint(approved_context, "page", "detail", second_page_id, None, {})
    assert detail["data"]["id"] == second_page_id
    assert 'view="content"' in detail["message"]
    assert 'view="versions"' in detail["message"]
    assert 'view="version_content"' in detail["message"]
    assert 'options={"version_no": <version_no>}' in detail["message"]
    assert 'view="dependencies"' in detail["message"]
    assert not {
        "page_content",
        "created_by",
        "updated_by",
        "screenshot_url",
        "screenshot_version_no",
        "screenshot_config_hash",
        "screenshot_viewport_width",
        "screenshot_viewport_height",
        "screenshot_is_latest",
        "screenshot_updated_at",
    }.intersection(detail["data"])
    listed_pages = await tools["list_entities"].entrypoint(
        approved_context,
        "page",
        {"project_id": second_project_id},
        "items",
    )
    assert listed_pages["data"]["items"][0]["id"] == second_page_id
    assert not {
        "page_content",
        "created_by",
        "updated_by",
        "screenshot_url",
        "screenshot_version_no",
        "screenshot_config_hash",
        "screenshot_viewport_width",
        "screenshot_viewport_height",
        "screenshot_is_latest",
        "screenshot_updated_at",
    }.intersection(listed_pages["data"]["items"][0])
    versions = await tools["get_entity"].entrypoint(approved_context, "page", "versions", second_page_id, None, {})
    assert versions["data"][0]["version_no"] == 1
    version_content = await tools["get_entity"].entrypoint(
        approved_context,
        "page",
        "version_content",
        second_page_id,
        None,
        {"version_no": 1},
    )
    assert "跨项目页面" in version_content["data"]["content"]
    dependencies = await tools["get_entity"].entrypoint(approved_context, "page", "dependencies", second_page_id, None, {})
    assert dependencies["data"]["page_id"] == second_page_id
    await tools["archive_entity"].entrypoint(approved_context, "page", [second_page_id], "暂存")
    archived_list = await tools["list_entities"].entrypoint(approved_context, "page", {"project_id": second_project_id}, "items")
    assert archived_list["data"]["items"] == []
    with pytest.raises(AppException) as archived_error:
        await tools["get_entity"].entrypoint(approved_context, "page", "detail", second_page_id, None, {})
    assert archived_error.value.code == "AI_ENTITY_NOT_FOUND"
    with pytest.raises(AppException):
        await tools["get_entity"].entrypoint(approved_context, "page", "versions", second_page_id, None, {})


async def test_project_archive_should_respect_work_scope_and_keep_child_pages(authenticated_client: AsyncClient) -> None:
    """项目归档应遵守工作集，并且不得级联归档项目页面。"""

    workspace_id = await _create_workspace(authenticated_client, "项目归档边界")
    focus_project_id = await _create_project(authenticated_client, workspace_id, "焦点项目")
    target_project_id = await _create_project(authenticated_client, workspace_id, "待归档项目")
    page_id = await _create_page(authenticated_client, workspace_id, target_project_id, "保留页面")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}

    denied_context = _build_tool_run_context(
        workspace_id,
        approved=False,
        focus_project_id=focus_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[focus_project_id],
    )
    with pytest.raises(AppException) as denied:
        await tools["archive_entity"].entrypoint(denied_context, "project", [target_project_id], "整理")
    assert denied.value.code == "AI_PROJECT_OUTSIDE_WORK_SCOPE"

    cross_focus_context = _build_tool_run_context(
        workspace_id,
        approved=False,
        focus_project_id=focus_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[focus_project_id, target_project_id],
    )
    with pytest.raises(ApprovalRequired):
        await tools["archive_entity"].entrypoint(cross_focus_context, "project", [target_project_id], "整理")

    approved_context = _build_tool_run_context(
        workspace_id,
        approved=True,
        focus_project_id=focus_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[focus_project_id, target_project_id],
    )
    result = await tools["archive_entity"].entrypoint(
        approved_context,
        "project",
        [target_project_id],
        "整理",
    )

    assert result["success"] is True
    assert result["data"]["archived_count"] == 1
    async with get_session_factory()() as session:
        project = await session.scalar(select(Project).where(Project.id == target_project_id))
        page = await session.scalar(select(Page).where(Page.id == page_id))
        assert project is not None
        assert project.status == RecordStatus.ARCHIVED.value
        assert project.archived_at is not None
        assert page is not None
        assert page.status == RecordStatus.ACTIVE.value


async def test_page_copy_create_mode_should_use_project_id_for_cross_focus_confirmation(authenticated_client: AsyncClient) -> None:
    """页面复制创建模式应按 project_id 识别目标项目并触发跨焦点确认。"""

    workspace_id = await _create_workspace(authenticated_client, "页面复制字段契约")
    source_project_id = await _create_project(authenticated_client, workspace_id, "源项目")
    target_project_id = await _create_project(authenticated_client, workspace_id, "目标项目")
    source_page_id = await _create_page(authenticated_client, workspace_id, source_project_id, "待复制页面")
    create_entity = {item.name: item for item in build_generic_business_tools(get_session_factory())}["create_entity"]
    context = _build_tool_run_context(
        workspace_id,
        approved=False,
        focus_project_id=source_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[source_project_id, target_project_id],
    )

    with pytest.raises(ApprovalRequired) as error:
        await create_entity.entrypoint(
            context,
            "page",
            "copy",
            {"source_id": source_page_id, "project_id": target_project_id},
        )

    assert error.value.metadata["target"] == {"project_id": target_project_id}

    approved_context = _build_tool_run_context(
        workspace_id,
        approved=True,
        focus_project_id=source_project_id,
        work_scope_mode="selected_projects",
        allowed_project_ids=[source_project_id, target_project_id],
    )
    copied = await create_entity.entrypoint(
        approved_context,
        "page",
        "copy",
        {"source_id": source_page_id, "project_id": target_project_id, "route_placement": "root"},
    )
    assert copied["effect"] == "create"
    assert copied["source"] == {"id": source_page_id, "resource_type": "page"}
    assert copied["target"]["id"] != source_page_id
    assert copied["data"]["project_id"] == target_project_id


async def test_asset_create_detail_and_validation_should_use_stable_envelopes(authenticated_client: AsyncClient) -> None:
    """文本资源创建、详情读取和差异预览应分别返回 create/read 语义。"""

    workspace_id = await _create_workspace(authenticated_client, "资源创建与校验")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}
    context = _build_tool_run_context(workspace_id, approved=True)

    created = await tools["create_entity"].entrypoint(
        context,
        "asset",
        "new",
        {
            "asset_type": "chart",
            "name": "validation_chart",
            "original_name": "validation_chart.json",
            "content": '{"value": 1}',
        },
    )
    asset_id = created["target"]["id"]
    assert created["effect"] == "create"

    detail = await tools["get_entity"].entrypoint(context, "asset", "detail", asset_id, None, {})
    assert detail["effect"] == "read"
    assert detail["data"]["id"] == asset_id
    assert detail["data"]["content_editable"] is True
    assert detail["data"]["references"]["page_count"] == 0
    assert 'view="content", target_id=' + str(asset_id) in detail["message"]

    preview = await tools["validate_entity"].entrypoint(
        context,
        "asset",
        "preview",
        asset_id,
        {"content": '{"value": 2}'},
    )
    assert preview["success"] is True
    assert preview["effect"] == "read"
    assert preview["mutation"] is None
    assert preview["data"]["valid"] is True


async def test_page_new_mode_should_create_page_and_route_atomically(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面 new 模式应接受 content 字段，并在同一事务加入项目路由。"""

    workspace_id = await _create_workspace(authenticated_client, "页面创建路由")
    project_id = await _create_project(authenticated_client, workspace_id, "路由项目")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}
    context = _build_tool_run_context(workspace_id, approved=True, focus_project_id=project_id)

    async def fake_check_page_code(self, **kwargs):  # noqa: ANN001
        """跳过浏览器检查，聚焦页面与路由事务。"""

        _ = self, kwargs
        return {"success": True, "status": "passed", "summary": "通过", "diagnostics": []}

    monkeypatch.setattr("app.ai.tools.project.project_pages.CodeCheckService.check_page_code", fake_check_page_code)
    created = await tools["create_entity"].entrypoint(
        context,
        "page",
        "new",
        {
            "project_id": project_id,
            "title": "原子路由页面",
            "content": "<template><main>原子路由</main></template>",
            "route_placement": "root",
            "route": "atomic-page",
        },
    )
    route_tree = await tools["get_entity"].entrypoint(context, "project", "route_tree", project_id, None, {})

    assert created["effect"] == "create"
    assert created["target"]["id"] == created["data"]["page_id"]
    assert any(item["page_id"] == created["target"]["id"] for item in route_tree["data"]["routes"])


async def test_project_and_style_configuration_views_should_share_shape(authenticated_client: AsyncClient) -> None:
    """项目与样式 configuration 视图应返回同构展示配置和建议组件 ID。"""

    workspace_id = await _create_workspace(authenticated_client, "共享配置读取")
    project_id = await _create_project(authenticated_client, workspace_id, "配置项目")
    style_id = await _create_style(authenticated_client, workspace_id, "config_style", "配置样式")
    tools = {item.name: item for item in build_generic_business_tools(get_session_factory())}
    context = _build_tool_run_context(workspace_id, approved=True)

    project_config = await tools["get_entity"].entrypoint(context, "project", "configuration", project_id, None, {})
    style_config = await tools["get_entity"].entrypoint(context, "style", "configuration", style_id, None, {})

    assert set(project_config["data"]) == {"presentation", "suggested_components"}
    assert set(style_config["data"]) == {"presentation", "suggested_components"}
    assert set(project_config["data"]["presentation"]) == set(style_config["data"]["presentation"])
    assert project_config["data"]["suggested_components"]["component_ids"] == []


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_style(client: AsyncClient, workspace_id: int, key: str, name: str) -> int:
    """创建待归档样式。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={"key": key, "name": name},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_project(client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建跨项目查询测试使用的项目。"""

    response = await client.post("/api/projects", json={"workspace_id": workspace_id, "name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_page(client: AsyncClient, workspace_id: int, project_id: int, title: str) -> int:
    """创建跨项目查询测试使用的页面。"""

    response = await client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": "<template><main>跨项目页面</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _read_deleted_at(style_id: int):
    """直接读取样式软删除时间，验证事务状态。"""

    async with get_session_factory()() as session:
        style = await session.scalar(select(WorkspaceStyle).where(WorkspaceStyle.id == style_id))
        assert style is not None
        return style.deleted_at


def _build_tool_run_context(
    workspace_id: int,
    *,
    approved: bool,
    focus_project_id: int | None = None,
    work_scope_mode: str = "workspace",
    allowed_project_ids: list[int] | None = None,
) -> AgentToolContext:
    """构造内容助手工作空间工具令牌和运行上下文。"""

    current = AuthContext(
        user=User(
            id=1,
            username="admin",
            password_hash="",
            display_name="管理员",
            role=UserRole.PLATFORM_ADMIN.value,
            preview_size_presets=[],
        ),
        session_token="test-session-token",
        backend_session_id="1",
    )
    run_id = "generic-archive-run"
    session_id = "generic-archive-session"
    dependencies = {
        "user_id": current.user.id,
        "agent_id": AGENT_COORDINATOR_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "project_id": focus_project_id,
        "page_id": None,
        "component_id": None,
        "source": "test",
        "backend_session_id": current.backend_session_id,
        "current_tool_call_approved": approved,
        "work_scope_mode": work_scope_mode,
        "allowed_project_ids": list(allowed_project_ids or []),
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        workspace_id=workspace_id,
        project_id=focus_project_id,
        page_id=None,
        component_id=None,
        source="test",
        scopes=(
            *PAGE_TOOL_READ_SCOPES,
            *PAGE_TOOL_WRITE_SCOPES,
            *PROJECT_TOOL_READ_SCOPES,
            *PROJECT_TOOL_WRITE_SCOPES,
            *RESOURCE_TOOL_READ_SCOPES,
            *RESOURCE_TOOL_WRITE_SCOPES,
            *CODE_CHECK_TOOL_SCOPES,
        ),
        work_scope_mode=work_scope_mode,
        allowed_project_ids=list(allowed_project_ids or []),
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id=str(current.user.id),
        dependencies=dependencies,
    )
