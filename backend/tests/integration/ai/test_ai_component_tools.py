"""文件功能：覆盖 AI 组件管理工具的真实调用路径与权限上下文传递。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.agent import COMPONENT_MANAGER_AGENT_ID
from app.ai.auth_tokens import COMPONENT_TOOL_DELETE_SCOPES, build_agent_tool_token
from app.ai.tools.component import build_component_manager_tools
from app.db.session import get_session_factory
from tests.integration.ai.ai_agents_cases import (
    CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
    _build_auth_context,
    _build_tool_run_context,
    _create_workspace,
    _find_tool,
)


async def test_delete_component_tool_should_pass_user_context_and_soft_delete(
    authenticated_client: AsyncClient,
) -> None:
    """删除组件工具应把当前用户传给服务层，并让组件从普通读取接口中消失。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件删除工具工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "删除测试组件",
            "import_name": "DeleteTestComponent",
            "content": "<template><article>delete</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    delete_tool = _find_tool(build_component_manager_tools(get_session_factory()), "delete_component")
    current = _build_auth_context()
    run_context = await _build_tool_run_context(
        current=current,
        tool_scopes=COMPONENT_TOOL_DELETE_SCOPES,
        workspace_id=workspace_id,
    )
    dependencies = run_context.dependencies
    assert isinstance(dependencies, dict)
    dependencies["agent_id"] = COMPONENT_MANAGER_AGENT_ID
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=dependencies["run_id"],
        session_id=dependencies["session_id"],
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        workspace_id=workspace_id,
        project_id=None,
        page_id=None,
        component_id=None,
        source=dependencies["source"],
        scopes=COMPONENT_TOOL_DELETE_SCOPES,
    )

    result = await delete_tool.entrypoint(run_context, component_id=component["id"])

    assert result["success"] is True
    assert result["component_id"] == component["id"]
    assert result["operator_id"] == 1
    assert result["component_code"] == component["code"]
    detail_response = await authenticated_client.get(f"/api/components/{component['id']}")
    assert detail_response.status_code == 404
