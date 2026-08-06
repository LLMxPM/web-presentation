"""文件功能：验证统一内容助手目录、配置接口与运行时工具规格防漂移。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.agent_catalog import get_agent_catalog_entry, list_agent_catalog_entries
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    build_agent_tools_from_group_specs,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.db.session import get_session_factory


EXPECTED_TOOL_KEYS = {
    "get_operation_guide",
    "query_entities",
    "create_entity",
    "update_entity",
    "archive_entity",
    "execute_action",
    "execute_dangerous_action",
    "ask_user",
    "analyze_visuals",
    "generate_image",
    "delegate_task_to_self",
}


async def test_agent_catalog_should_only_expose_unified_content_agent(
    authenticated_client: AsyncClient,
) -> None:
    """目录与配置接口只应公开一个工作空间级内容助手。"""

    catalog_response = await authenticated_client.get("/api/ai/agent-catalog")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert [item["id"] for item in catalog] == [AGENT_COORDINATOR_AGENT_ID]

    coordinator = catalog[0]
    assert coordinator["name"] == "内容助手"
    assert coordinator["scope_type"] == "workspace"
    assert coordinator["entry_kind"] == "agent"
    assert "delegate_task_to_self" in coordinator["default_prompt"]
    assert "delegate_task_to_member" not in coordinator["default_prompt"]
    assert "组件助手" not in coordinator["default_prompt"]
    assert "资源助手" not in coordinator["default_prompt"]

    tool_items = [tool for group in coordinator["tool_groups"] for tool in group["tools"]]
    assert {tool["key"] for tool in tool_items} == EXPECTED_TOOL_KEYS
    configs_response = await authenticated_client.get("/api/ai/agent-configs")
    assert configs_response.status_code == 200
    assert [item["id"] for item in configs_response.json()] == [AGENT_COORDINATOR_AGENT_ID]


async def test_unified_agent_config_should_still_support_prompt_and_tool_overrides(
    authenticated_client: AsyncClient,
) -> None:
    """合并助手后仍允许配置唯一助手的提示词和固定工具说明。"""

    update_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}",
        json={"description_override": "统一内容处理", "prompt_override": "优先直接完成任务。"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["effective_prompt"] == "优先直接完成任务。"

    tool_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/query_entities",
        json={"enabled": False, "description_override": "读取业务对象。"},
    )
    assert tool_response.status_code == 200
    query_tool = next(
        tool
        for group in tool_response.json()["tool_groups"]
        for tool in group["tools"]
        if tool["key"] == "query_entities"
    )
    assert query_tool["enabled"] is False
    assert query_tool["description"] == "读取业务对象。"


def test_unified_tool_specs_should_match_runtime_and_guides() -> None:
    """唯一助手的目录、运行时工具与操作手册处理器必须一致。"""

    assert [item.id for item in list_agent_catalog_entries()] == [AGENT_COORDINATOR_AGENT_ID]
    assert get_agent_catalog_entry("component-manager") is None
    assert get_agent_catalog_entry("resource-manager") is None

    specs = {spec.key: spec for spec in list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID)}
    tools = build_agent_tools_from_group_specs(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        session_factory=get_session_factory(),
        supports_image_input=True,
    )
    assert set(specs) == EXPECTED_TOOL_KEYS == {tool.name for tool in tools}
    delegate_tool = next(tool for tool in tools if tool.name == "delegate_task_to_self")
    assert set(delegate_tool.parameters["properties"]) == {"task", "handoff_context", "expected_output"}
    assert "member_id" not in str(delegate_tool.parameters)
    assert list_agent_tool_specs("component-manager") == ()
    assert list_agent_tool_specs("resource-manager") == ()
    assert all(guide.handler_tool_key in EXPECTED_TOOL_KEYS for guide in list_operation_guide_specs())
    assert not any("delete" in key or "purge" in key for key in EXPECTED_TOOL_KEYS)


def test_unified_prompt_should_keep_runtime_and_fixed_canvas_guidance() -> None:
    """统一提示词保留页面与组件代码工作需要的 Runtime 和固定画布约束。"""

    catalog = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    assert catalog is not None
    for phrase in (
        "page_content 要写成完整、可运行的 Vue SFC 文件源码",
        "页面是固定画布大小，不是流式网页",
        "base_font_size / 16px",
        "PAGE_RENDER_BOTTOM_OVERFLOW",
    ):
        assert phrase in catalog.default_prompt
