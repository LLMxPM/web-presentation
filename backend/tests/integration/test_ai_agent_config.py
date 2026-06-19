"""文件功能：验证用户级智能体配置、平台工具目录和工具规格防漂移。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    COMPONENT_MANAGER_AGENT_ID,
    RESOURCE_MANAGER_AGENT_ID,
    build_agent_tools_from_group_specs,
    list_agent_tool_specs,
)
from app.db.session import get_session_factory


async def test_agent_config_api_should_manage_prompt_and_tool_overrides(
    authenticated_client: AsyncClient,
) -> None:
    """智能体配置接口应能展示平台工具 guide，并支持提示词与工具覆盖。"""

    catalog_response = await authenticated_client.get("/api/ai/agent-catalog")
    assert catalog_response.status_code == 200
    catalog_items = {item["id"]: item for item in catalog_response.json()}
    assert set(catalog_items) == {
        AGENT_COORDINATOR_AGENT_ID,
        COMPONENT_MANAGER_AGENT_ID,
        RESOURCE_MANAGER_AGENT_ID,
    }

    coordinator = catalog_items[AGENT_COORDINATOR_AGENT_ID]
    ask_user = _find_tool(coordinator, "ask_user")
    assert ask_user["configurable"] is False
    assert ask_user["requires_confirmation"] is True
    ask_user_schema = ask_user["agent_guide"]["parameters_schema"]
    assert ask_user_schema["properties"]["questions"]
    question_schema = ask_user_schema["$defs"]["AskUserQuestion"]
    assert "question" in question_schema["required"]
    assert "title" not in question_schema["properties"]
    assert question_schema["additionalProperties"] is False
    assert ask_user["agent_guide"]["requires_confirmation"] is True
    assert ask_user["agent_guide"]["risk_level"] == "system"

    update_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}",
        json={
            "description_override": "专注页面布局调整的内容助手",
            "prompt_override": "优先解释将要修改的布局区域。",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["description"] == "专注页面布局调整的内容助手"
    assert updated["prompt_customized"] is True
    assert updated["effective_prompt"] == "优先解释将要修改的布局区域。"

    tool_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/get_page_content",
        json={
            "enabled": False,
            "description_override": "读取页面源码并返回可编辑文本。",
            "instructions_override": "读取后再编辑。",
        },
    )
    assert tool_response.status_code == 200
    tool_config = _find_tool(tool_response.json(), "get_page_content")
    assert tool_config["enabled"] is False
    assert tool_config["description"] == "读取页面源码并返回可编辑文本。"
    assert tool_config["instructions"] == "读取后再编辑。"


def test_agent_tool_specs_should_match_platform_tools() -> None:
    """统一工具规格应覆盖实际平台工具，防止运行态和配置页工具 key 漂移。"""

    session_factory = get_session_factory()
    for agent_id in (AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
        specs = {spec.key: spec for spec in list_agent_tool_specs(agent_id)}
        tools = build_agent_tools_from_group_specs(
            agent_id=agent_id,
            session_factory=session_factory,
            supports_image_input=True,
        )
        actual = {tool.name: tool for tool in tools}
        assert set(actual) == set(specs)
        assert actual["ask_user"].requires_confirmation is True
        for tool_name, tool in actual.items():
            assert isinstance(tool.parameters, dict), tool_name
            assert tool.description == specs[tool_name].description


def _find_tool(config_item: dict, tool_key: str) -> dict:
    """从配置响应中按 key 找到工具项。"""

    for group in config_item["tool_groups"]:
        for tool in group["tools"]:
            if tool["key"] == tool_key:
                return tool
    raise AssertionError(f"tool not found: {tool_key}")
