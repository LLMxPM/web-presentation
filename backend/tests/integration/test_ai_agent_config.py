"""文件功能：验证用户级智能体配置、平台工具目录和工具规格防漂移。"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, build_effective_instructions
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
    assert coordinator["default_prompt"]
    assert coordinator["system_prompt"] == coordinator["default_prompt"]
    assert "## 1. 身份、权限与安全边界" in coordinator["default_prompt"]
    assert "## 8. 写入校验与异常处理" in coordinator["default_prompt"]
    assert "## 1. 身份、权限与安全边界" in catalog_items[COMPONENT_MANAGER_AGENT_ID]["default_prompt"]
    assert "## 7. 组件质量、写入校验与归属" in catalog_items[COMPONENT_MANAGER_AGENT_ID]["default_prompt"]
    assert "## 1. 身份、权限与动作边界" in catalog_items[RESOURCE_MANAGER_AGENT_ID]["default_prompt"]
    assert "## 6. 归档与删除边界" in catalog_items[RESOURCE_MANAGER_AGENT_ID]["default_prompt"]
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

    restored_prompt_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}",
        json={"prompt_override": None},
    )
    assert restored_prompt_response.status_code == 200
    restored_prompt = restored_prompt_response.json()
    assert restored_prompt["description"] == "专注页面布局调整的内容助手"
    assert restored_prompt["prompt_customized"] is False
    assert restored_prompt["effective_prompt"] == coordinator["default_prompt"]

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


def test_effective_instructions_should_be_single_prompt_text() -> None:
    """运行时应只向 Pydantic AI 传入一段完整提示词文本。"""

    catalog = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    assert catalog is not None
    runtime_config = EffectiveAgentRuntimeConfig(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        description_override=None,
        prompt_override="用户修改后的完整提示词。",
        tool_configs={},
    )

    instructions = build_effective_instructions(
        catalog,
        runtime_config,
        "当前业务范围如下：\n- 工作空间 ID：1",
    )

    assert instructions == [
        "用户修改后的完整提示词。\n\n当前业务范围如下：\n- 工作空间 ID：1"
    ]
    assert catalog.default_prompt not in instructions[0]


def test_write_and_danger_tool_specs_should_have_runtime_instructions() -> None:
    """写入和危险工具必须提供模型可见的具体使用提示。"""

    missing: list[str] = []
    for agent_id in (AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
        for spec in list_agent_tool_specs(agent_id):
            if spec.risk_level in {"write", "danger"} and not (spec.default_instructions or "").strip():
                missing.append(f"{agent_id}:{spec.key}")

    assert missing == []


def test_base_font_size_guidance_should_use_tailwind_default_ratio() -> None:
    """智能体提示和工具规格应使用 Tailwind 默认 16px 倍率口径。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    component_manager = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    assert coordinator is not None
    assert component_manager is not None

    coordinator_prompt = coordinator.default_prompt
    component_prompt = component_manager.default_prompt
    assert "base_font_size / 16px" in coordinator_prompt
    assert "base_font_size / 16px" in component_prompt
    assert "size、density、variant、tone" in component_prompt
    assert "裸 fontSize/padding 数值 props" in component_prompt

    forbidden_phrases = (
        "text-base 等于该值",
        "按 Runtime Tailwind 预设比例派生",
        "以 base_font_size 为基准计算",
    )
    for phrase in forbidden_phrases:
        assert phrase not in coordinator_prompt
        assert phrase not in component_prompt

    coordinator_specs = {spec.key: spec for spec in list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID)}
    assert "1.25 倍" in str(coordinator_specs["get_page_content"].response_example)
    assert "base_font_size / 16px" in coordinator_specs["get_project_style_config"].default_instructions


def test_page_design_guidance_should_use_wireframe_as_internal_method() -> None:
    """页面设计类默认提示词应把文本线框图限定为内部布局方法。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    component_manager = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    assert coordinator is not None
    assert component_manager is not None

    coordinator_prompt = coordinator.default_prompt
    component_prompt = component_manager.default_prompt

    assert "先在内部使用文本线框图或区域清单梳理布局，再写 Vue SFC 代码" in coordinator_prompt
    assert "不作为默认回复内容输出" in coordinator_prompt
    assert "不要为了展示线框图而暂停等待用户确认" in coordinator_prompt
    assert "先在内部使用文本线框图或区域清单梳理布局，再写 Vue SFC 代码" in component_prompt
    assert "文本线框图是组件布局思考方法" in component_prompt
    assert "不要为了展示线框图而暂停等待用户确认" in component_prompt


def test_agent_default_prompts_should_include_key_task_workflow() -> None:
    """所有内置智能体默认提示词应包含重点任务建议工作流程。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    component_manager = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    resource_manager = get_agent_catalog_entry(RESOURCE_MANAGER_AGENT_ID)
    assert coordinator is not None
    assert component_manager is not None
    assert resource_manager is not None

    workflow_expectations = {
        coordinator: ("## 3. 重点任务建议工作流程", "页面或项目重点任务", "组件/资源维护任务再决定是否委派"),
        component_manager: ("## 2. 重点任务建议工作流程", "组件重点任务", "组件 API 与预览约束"),
        resource_manager: ("## 2. 重点任务建议工作流程", "资源重点任务", "Diff 预览或引用检查"),
    }
    for catalog, expected_phrases in workflow_expectations.items():
        prompt = catalog.default_prompt
        for phrase in expected_phrases:
            assert phrase in prompt


def test_runtime_asset_guidance_should_prefer_sfc_composables() -> None:
    """智能体提示应明确 SFC 资源解析优先使用响应式组合式能力。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    component_manager = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    resource_manager = get_agent_catalog_entry(RESOURCE_MANAGER_AGENT_ID)
    assert coordinator is not None
    assert component_manager is not None
    assert resource_manager is not None

    for catalog in (coordinator, component_manager):
        prompt = catalog.default_prompt
        assert "普通资源 URL 默认用 useAssetSrc" in prompt
        assert "背景层默认用 useAssetBackground" in prompt
        assert "resolveResourcePath 只用于非响应式工具代码" in prompt
        assert "不要在 SFC 中直接写 resolveResourcePath(props.xxx)" in prompt
        assert "只有在自定义背景图、非响应式代码或确实需要自行组织 DOM/CSS 的场景" not in prompt

    resource_prompt = resource_manager.default_prompt
    assert "普通资源 URL 默认用 useAssetSrc" in resource_prompt
    assert "项目资源背景优先用 useAssetBackground" in resource_prompt
    assert "不要传初始化时的 props.xxx 字符串" in resource_prompt
    assert "resolveResourcePath 只用于非响应式工具代码" in resource_prompt


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
