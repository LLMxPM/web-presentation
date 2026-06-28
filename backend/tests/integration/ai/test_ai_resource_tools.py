"""文件功能：覆盖 AI 资源工具的真实调用路径与可恢复业务错误返回。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.ai.agent import RESOURCE_MANAGER_AGENT_ID
from app.ai.auth_tokens import (
    PAGE_TOOL_READ_SCOPES,
    RESOURCE_TOOL_READ_SCOPES,
    RESOURCE_TOOL_WRITE_SCOPES,
    build_agent_tool_token,
)
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.resource.resource_library import (
    build_create_resource_asset_tool,
    build_get_resource_asset_content_tool,
    build_list_resource_assets_tool,
    build_update_resource_asset_metadata_tool,
)
from app.ai.tools.workspace.assets import build_list_workspace_font_assets_tool, build_list_workspace_render_assets_tool
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.enums import AssetType, UserRole
from app.models.user import User
from app.services.auth_service import AuthContext


async def test_get_resource_asset_content_tool_should_return_recoverable_error_for_bitmap(
    authenticated_client: AsyncClient,
) -> None:
    """位图资源不可读取文本内容时，应返回可恢复错误和资源摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源读取错误工作空间")
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("bitmap.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "name": "bitmap_image", "tags": "[]"},
    )
    assert upload_response.status_code == 200, upload_response.text
    asset = upload_response.json()
    tool = build_get_resource_asset_content_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id, scopes=RESOURCE_TOOL_READ_SCOPES)

    result = await tool.entrypoint(run_context, asset_id=asset["id"])

    assert result["success"] is False
    assert result["kind"] == "recoverable_tool_error"
    assert result["error"]["code"] == "ASSET_CONTENT_READ_UNSUPPORTED"
    assert result["data"]["asset"]["id"] == asset["id"]
    assert result["data"]["asset"]["content_editable"] is False


async def test_list_resource_assets_tool_should_prefer_project_suggested_assets(
    authenticated_client: AsyncClient,
) -> None:
    """资源列表默认应优先返回当前项目建议引用资源，并保留精简字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议资源工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议资源项目")
    hero_asset = await _create_text_asset(authenticated_client, workspace_id, "hero_image", tags=["主视觉"])
    flow_asset = await _create_text_asset(authenticated_client, workspace_id, "process_flow", tags=["流程"])
    await _replace_project_suggested_assets(authenticated_client, project_id, [flow_asset["id"], hero_asset["id"]])

    tool = build_list_resource_assets_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id, project_id=project_id)

    result = await tool.entrypoint(run_context)

    assert result["source"] == "project_suggested"
    assert result["fallback_reason"] is None
    assert [item["id"] for item in result["items"]] == [flow_asset["id"], hero_asset["id"]]
    assert set(result["items"][0]) == {
        "id",
        "name",
        "original_name",
        "description",
        "asset_type",
        "content_editable",
        "approx_aspect_ratio",
        "approx_aspect_ratio_value",
        "aspect_ratio_source",
    }
    assert result["items"][0]["approx_aspect_ratio"] == "1:1"


async def test_list_resource_assets_tool_should_fallback_without_project_context(
    authenticated_client: AsyncClient,
) -> None:
    """缺少 project_id 时默认 scope 应回退全工作空间资源。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 无项目资源工作空间")
    asset = await _create_text_asset(authenticated_client, workspace_id, "workspace_asset", tags=["通用"])
    tool = build_list_resource_assets_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id)

    result = await tool.entrypoint(run_context)

    assert result["source"] == "workspace_all"
    assert result["fallback_reason"] == "no_project_context"
    assert [item["id"] for item in result["items"]] == [asset["id"]]
    assert result["items"][0]["tags"] == ["通用"]


async def test_list_resource_assets_tool_should_fallback_when_suggested_empty_or_filtered(
    authenticated_client: AsyncClient,
) -> None:
    """建议资源为空或筛选为空时，应使用同样筛选条件回退全量资源。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议回退资源工作空间")
    empty_project_id = await _create_project(authenticated_client, workspace_id, "空建议资源项目")
    filtered_project_id = await _create_project(authenticated_client, workspace_id, "筛选回退资源项目")
    hero_asset = await _create_text_asset(authenticated_client, workspace_id, "hero_image", tags=["主视觉"])
    diagram_asset = await _create_text_asset(authenticated_client, workspace_id, "library_only_diagram", tags=["图表"])
    await _replace_project_suggested_assets(authenticated_client, filtered_project_id, [hero_asset["id"]])

    tool = build_list_resource_assets_tool(get_session_factory())
    empty_result = await tool.entrypoint(
        _build_tool_run_context(workspace_id=workspace_id, project_id=empty_project_id),
    )
    filtered_result = await tool.entrypoint(
        _build_tool_run_context(workspace_id=workspace_id, project_id=filtered_project_id),
        keyword="library_only",
    )

    assert empty_result["source"] == "workspace_all"
    assert empty_result["fallback_reason"] == "no_project_suggested_assets"
    assert {item["id"] for item in empty_result["items"]} == {hero_asset["id"], diagram_asset["id"]}
    assert filtered_result["source"] == "workspace_all"
    assert filtered_result["fallback_reason"] == "suggested_filter_empty"
    assert [item["id"] for item in filtered_result["items"]] == [diagram_asset["id"]]


async def test_list_resource_assets_tool_scope_all_should_query_workspace_assets(
    authenticated_client: AsyncClient,
) -> None:
    """scope=all 应跳过项目建议资源，直接查询工作空间资源库。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 全量资源工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 全量资源项目")
    suggested_asset = await _create_text_asset(authenticated_client, workspace_id, "suggested_asset", tags=["建议"])
    library_asset = await _create_text_asset(authenticated_client, workspace_id, "library_only_asset", tags=["素材库"])
    await _replace_project_suggested_assets(authenticated_client, project_id, [suggested_asset["id"]])

    tool = build_list_resource_assets_tool(get_session_factory())
    result = await tool.entrypoint(
        _build_tool_run_context(workspace_id=workspace_id, project_id=project_id),
        keyword="library_only",
        scope="all",
    )

    assert result["source"] == "workspace_all"
    assert result["fallback_reason"] is None
    assert [item["id"] for item in result["items"]] == [library_asset["id"]]


async def test_list_resource_assets_tool_should_reject_invalid_scope(
    authenticated_client: AsyncClient,
) -> None:
    """scope 只能使用 suggested 或 all。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 非法 scope 资源工作空间")
    tool = build_list_resource_assets_tool(get_session_factory())
    run_context = _build_tool_run_context(workspace_id=workspace_id)

    with pytest.raises(AppException) as exc_info:
        await tool.entrypoint(run_context, scope="project")

    assert exc_info.value.code == "AI_TOOL_ARGUMENT_INVALID"


async def test_workspace_render_assets_tool_should_return_aspect_ratio_summary(
    authenticated_client: AsyncClient,
) -> None:
    """页面渲染资源查询工具应返回近似比例摘要，不暴露宽高尺寸。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 渲染资源比例工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 渲染资源比例项目")
    page_id = await _create_page(authenticated_client, workspace_id, project_id, "AI 渲染资源比例页面")
    await _create_text_asset(authenticated_client, workspace_id, "wide_hero", tags=["封面"])
    tool = build_list_workspace_render_assets_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(
            workspace_id=workspace_id,
            project_id=project_id,
            page_id=page_id,
            scopes=PAGE_TOOL_READ_SCOPES,
        ),
        render_type="image",
    )

    assert result[0]["name"] == "wide_hero"
    assert result[0]["approx_aspect_ratio"] == "1:1"
    assert result[0]["aspect_ratio_source"] == "auto"
    assert "width" not in result[0]
    assert "height" not in result[0]


async def test_resource_manager_should_create_and_update_manual_aspect_ratio(
    authenticated_client: AsyncClient,
) -> None:
    """资源助手创建和维护 Mermaid 资源时可设置近似比例。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源助手比例工作空间")
    run_context = _build_tool_run_context(workspace_id=workspace_id, scopes=RESOURCE_TOOL_WRITE_SCOPES)
    create_tool = build_create_resource_asset_tool(get_session_factory())
    update_tool = build_update_resource_asset_metadata_tool(get_session_factory())

    created = await create_tool.entrypoint(
        run_context,
        asset_type=AssetType.MERMAID,
        name="agent_flow",
        original_name="agent_flow.mmd",
        content="flowchart TD\n  A --> B",
        approx_aspect_ratio="16:9",
    )
    asset_id = created["asset"]["id"]
    assert created["asset"]["approx_aspect_ratio"] == "16:9"
    assert created["asset"]["aspect_ratio_source"] == "agent"

    updated = await update_tool.entrypoint(run_context, asset_id=asset_id, approx_aspect_ratio="4:3")

    assert updated["asset"]["approx_aspect_ratio"] == "4:3"
    assert updated["asset"]["aspect_ratio_source"] == "agent"


async def test_list_workspace_font_assets_tool_should_return_registered_fonts(
    authenticated_client: AsyncClient,
) -> None:
    """字体资源工具应使用资源读取权限返回已注册字体声明摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 字体资源工作空间")
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("BrandSerif.woff2", b"font-content", "font/woff2")},
        data={
            "asset_type": "font",
            "name": "BrandSerif",
            "description": "品牌标题字体",
            "tags": "[\"品牌\"]",
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    asset = upload_response.json()
    create_font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset["id"],
            "font_family": "Brand Serif",
            "font_weight": "500",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert create_font_response.status_code == 200, create_font_response.text
    tool = build_list_workspace_font_assets_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(workspace_id=workspace_id),
        keyword="brand",
        tags=["品牌"],
    )

    assert result == [
        {
            "name": "BrandSerif",
            "asset_name": "BrandSerif",
            "font_family": "Brand Serif",
            "font_weight": "500",
            "font_style": "normal",
            "font_display": "swap",
            "extension": "woff2",
            "type": "font",
            "description": "品牌标题字体",
        }
    ]


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目并返回 ID。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_page(authenticated_client: AsyncClient, workspace_id: int, project_id: int, title: str) -> int:
    """创建测试页面并返回 ID。"""

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": "<template><div>测试页面</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_text_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    tags: list[str] | None = None,
) -> dict:
    """创建文本型图片资源并返回接口载荷。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": AssetType.IMAGE.value,
            "name": name,
            "original_name": f"{name}.svg",
            "description": f"{name} 描述",
            "content": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\"><rect width=\"16\" height=\"16\"/></svg>",
            "tags": tags or [],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _replace_project_suggested_assets(
    authenticated_client: AsyncClient,
    project_id: int,
    asset_ids: list[int],
) -> None:
    """覆盖保存项目建议引用资源。"""

    response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": asset_ids},
    )
    assert response.status_code == 200


def _build_tool_run_context(
    *,
    workspace_id: int,
    project_id: int | None = None,
    page_id: int | None = None,
    scopes: tuple[str, ...] = RESOURCE_TOOL_READ_SCOPES,
) -> AgentToolContext:
    """构造资源读取工具需要的运行上下文和签名 token。"""

    current = _build_auth_context()
    run_id = "resource-tool-run"
    session_id = "resource-tool-session"
    dependencies = {
        "user_id": current.user.id,
        "agent_id": RESOURCE_MANAGER_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "page_id": page_id,
        "component_id": None,
        "source": "test",
        "backend_session_id": current.backend_session_id,
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=RESOURCE_MANAGER_AGENT_ID,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=None,
        source="test",
        scopes=scopes,
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id=str(current.user.id),
        dependencies=dependencies,
    )


def _build_auth_context() -> AuthContext:
    """构造带管理员身份的测试鉴权上下文。"""

    return AuthContext(
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
