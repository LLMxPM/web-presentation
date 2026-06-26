"""文件功能：验证用户级智能体配置、平台工具目录和工具规格防漂移。"""

from __future__ import annotations

from typing import Any

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
    for catalog_item in catalog_items.values():
        tool_keys = {
            tool["key"]
            for group in catalog_item["tool_groups"]
            for tool in group["tools"]
        }
        group_keys = {group["key"] for group in catalog_item["tool_groups"]}
        assert "list_project_suggested_reference_assets" not in tool_keys
        assert "project_suggested_reference_read" not in group_keys

    coordinator = catalog_items[AGENT_COORDINATOR_AGENT_ID]
    resource_list_tool = _find_tool(coordinator, "list_resource_assets")
    assert "scope" in resource_list_tool["agent_guide"]["parameters_schema"]["properties"]
    ask_user = _find_tool(coordinator, "ask_user")
    assert ask_user["configurable"] is False
    assert ask_user["requires_confirmation"] is True
    ask_user_schema = ask_user["agent_guide"]["parameters_schema"]
    assert ask_user_schema["properties"]["questions"]
    question_schema = ask_user_schema["$defs"]["AskUserQuestion"]
    assert "question" in question_schema["required"]
    assert "title" not in question_schema["properties"]
    assert "value" not in question_schema["properties"]
    assert question_schema["additionalProperties"] is False
    option_schema = ask_user_schema["$defs"]["AskUserOption"]
    assert "value" not in option_schema["properties"]
    assert option_schema["additionalProperties"] is False
    assert ask_user["agent_guide"]["requires_confirmation"] is True
    assert ask_user["agent_guide"]["risk_level"] == "system"
    team_delegation = next(group for group in coordinator["tool_groups"] if group["key"] == "team_delegation")
    assert [tool["key"] for tool in team_delegation["tools"]] == [
        "delegate_task_to_member",
    ]
    delegate_tool = _find_tool(coordinator, "delegate_task_to_member")
    delegate_schema = delegate_tool["agent_guide"]["parameters_schema"]
    assert set(_schema_enum_values(delegate_schema["properties"]["member_id"])) == {
        "component-manager",
        "resource-manager",
    }
    assert "team_delegation" in delegate_tool["agent_guide"]["runtime_disclosure_groups"]
    route_tool = _find_tool(coordinator, "update_project_route_tree")
    assert route_tool["requires_confirmation"] is False
    assert route_tool["agent_guide"]["requires_confirmation"] is False
    assert route_tool["agent_guide"]["risk_level"] == "write"

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
        if agent_id == AGENT_COORDINATOR_AGENT_ID:
            assert actual["update_project_route_tree"].requires_confirmation is False
            assert specs["update_project_route_tree"].requires_confirmation is False
        for tool_name, tool in actual.items():
            assert isinstance(tool.parameters, dict), tool_name
            assert tool.description == specs[tool_name].description
        if agent_id == RESOURCE_MANAGER_AGENT_ID:
            for tool_name in (
                "create_resource_asset",
                "update_resource_asset_metadata",
                "copy_resource_asset",
            ):
                tags_schema = actual[tool_name].parameters["properties"]["tags"]
                assert _schema_allows_string_array(tags_schema), tool_name
                assert not _schema_allows_untyped_array(tags_schema), tool_name


def test_write_and_danger_tool_specs_should_have_runtime_instructions() -> None:
    """写入和危险工具必须提供模型可见的具体使用提示。"""

    missing: list[str] = []
    for agent_id in (AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
        for spec in list_agent_tool_specs(agent_id):
            if spec.risk_level in {"write", "danger"} and not (spec.default_instructions or "").strip():
                missing.append(f"{agent_id}:{spec.key}")

    assert missing == []


def _find_tool(config_item: dict, tool_key: str) -> dict:
    """从配置响应中按 key 找到工具项。"""

    for group in config_item["tool_groups"]:
        for tool in group["tools"]:
            if tool["key"] == tool_key:
                return tool
    raise AssertionError(f"tool not found: {tool_key}")


def _schema_allows_string_array(schema: dict[str, Any]) -> bool:
    """判断 JSON Schema 是否允许 string 数组。"""

    if schema.get("type") == "array":
        return (schema.get("items") or {}).get("type") == "string"
    return any(_schema_allows_string_array(option) for option in _schema_composition_options(schema))


def _schema_allows_untyped_array(schema: dict[str, Any]) -> bool:
    """判断 JSON Schema 是否仍包含未声明 item 类型的数组。"""

    if schema.get("type") == "array":
        return (schema.get("items") or {}).get("type") != "string"
    return any(_schema_allows_untyped_array(option) for option in _schema_composition_options(schema))


def _schema_enum_values(schema: dict[str, Any]) -> list[str]:
    """递归提取 JSON Schema 中的枚举值，兼容 anyOf/oneOf 包装。"""

    values = schema.get("enum")
    if isinstance(values, list):
        return [str(value) for value in values]
    result: list[str] = []
    for option in _schema_composition_options(schema):
        result.extend(_schema_enum_values(option))
    return result


def _schema_composition_options(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """取出 JSON Schema 组合分支，便于递归检查 anyOf/oneOf/allOf。"""

    options: list[dict[str, Any]] = []
    for key in ("anyOf", "oneOf", "allOf"):
        for item in schema.get(key) or []:
            if isinstance(item, dict):
                options.append(item)
    return options
