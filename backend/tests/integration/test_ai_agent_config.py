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
    assert "## 1. 身份与硬边界" in coordinator["default_prompt"]
    assert "工作空间 workspace 是资源库和已发布组件库的资产边界" in coordinator["default_prompt"]
    assert "项目 project 是一组页面、路由树、项目样式配置、主题/画布配置和预览/构建入口" in coordinator["default_prompt"]
    assert "页面 page 是项目中的一个可渲染页面记录" in coordinator["default_prompt"]
    assert "## 3. 事实来源与上下文优先级" in coordinator["default_prompt"]
    assert "## 4. 对象边界与成员委派" in coordinator["default_prompt"]
    assert "## 6. Runtime 渲染机制与代码边界" in coordinator["default_prompt"]
    assert "## 7. 固定画布、主题、组件与资源使用" in coordinator["default_prompt"]
    assert "## 8. 写入校验与回复契约" in coordinator["default_prompt"]
    assert "成员委派只能通过 delegate_task_to_member 工具发生" in coordinator["default_prompt"]
    assert "组件列表/用法查询、资源列表/内容读取或 Runtime Kit 查询" in coordinator["default_prompt"]
    assert "只有需要新增、修改、发布、删除组件，或创建、修改、复制、归档资源时，才进入成员委派流程" in coordinator["default_prompt"]
    assert "组件列表查询、已发布组件用法查询、组件筛选和页面内组件引用决策由你直接完成" in coordinator["default_prompt"]
    assert "资源列表查询、资源内容读取、资源筛选和页面内资源引用决策由你直接完成" in coordinator["default_prompt"]
    assert "可用颜色键包括 primary、secondary、invert、background" in coordinator["default_prompt"]
    assert "--tw-color-text-primary" in coordinator["default_prompt"]
    assert "主题 Logo 渲染优先使用 Runtime Kit 的 ThemeLogo 组件" in coordinator["default_prompt"]
    assert "建议先通过 Runtime Kit 工具查询并使用 DataTable 的公开 import_path 搭建" in coordinator["default_prompt"]
    assert "组件库中基于DataTable 封装的表格组件" in coordinator["default_prompt"]
    assert "尽量不要使用 HTML <table>/<tr>/<td> 表格" in coordinator["default_prompt"]
    assert "主题颜色/字体摘要默认不完整注入" in coordinator["default_prompt"]
    assert "不要为了重复获取已注入的 style_spec_markdown 而调用它" in coordinator["default_prompt"]
    assert "include_style_spec_markdown=true" in coordinator["default_prompt"]
    assert "项目建议组件摘要和项目建议资源摘要可以作为本轮初始事实使用" in coordinator["default_prompt"]
    assert "组件摘要只能用于筛选" in coordinator["default_prompt"]
    assert "组件库或资源库专长任务才进入成员委派流程" not in coordinator["default_prompt"]
    assert "组件助手负责工作空间组件库专长任务" not in coordinator["default_prompt"]
    assert "资源助手负责工作空间资源库专长任务" not in coordinator["default_prompt"]
    assert "应委委派" not in coordinator["default_prompt"]
    assert "不是单纯任务分发者" not in coordinator["default_prompt"]
    assert "内容 Team 的入口" not in coordinator["default_prompt"]
    assert "处理页面与项目任务" not in coordinator["default_prompt"]
    assert "直接查询并使用已发布组件、资源和 Runtime Kit 能力" in coordinator["description"]
    assert "仅在需要新增、修改或归档组件/资源时通过工具委派成员" in coordinator["description"]
    assert "优先直接使用页面、项目、组件读取、资源读取和检查工具" in coordinator["role"]
    assert "仅在需要组件或资源维护时调用 delegate_task_to_member" in coordinator["role"]
    assert "team_members" not in coordinator
    component_prompt = catalog_items[COMPONENT_MANAGER_AGENT_ID]["default_prompt"]
    assert "## 1. 身份与硬边界" in component_prompt
    assert "## 2. 任务分类与执行原则" in component_prompt
    assert "## 3. 事实来源与上下文优先级" in component_prompt
    assert "## 4. 对象边界与协作职责" in component_prompt
    assert "## 9. 写入校验与回复契约" in component_prompt
    assert "组件助手不负责直接维护 page_content、页面元数据、项目页面列表、路由树、项目样式配置" in component_prompt
    assert "资源名、组件 import 和 Runtime Kit import 都必须来自工具结果" in component_prompt
    assert "组件助手只能委派资源助手" in component_prompt
    assert "delegate_task_to_member" in component_prompt
    assert "建议先通过 Runtime Kit 工具查询并使用 DataTable 的公开 import_path 搭建" in component_prompt
    assert "尽量不要使用 HTML <table>/<tr>/<td> 表格" in component_prompt
    assert "页面组件必须具备整页画布承载能力" in component_prompt
    assert "也可以基于已发布页面组件复用其真实画布、定位上下文和裁剪" in component_prompt
    assert "不要改用已发布衍生容器组件替代 DefaultContainer" not in component_prompt
    assert "style_spec_markdown" not in component_prompt
    assert "资源助手委派" in catalog_items[COMPONENT_MANAGER_AGENT_ID]["capabilities"]
    assert "按需委派资源助手" in catalog_items[COMPONENT_MANAGER_AGENT_ID]["description"]
    component_team_delegation = next(
        group for group in catalog_items[COMPONENT_MANAGER_AGENT_ID]["tool_groups"] if group["key"] == "team_delegation"
    )
    assert [tool["key"] for tool in component_team_delegation["tools"]] == [
        "delegate_task_to_member",
    ]
    component_delegate_tool = _find_tool(catalog_items[COMPONENT_MANAGER_AGENT_ID], "delegate_task_to_member")
    component_delegate_schema = component_delegate_tool["agent_guide"]["parameters_schema"]
    assert set(_schema_enum_values(component_delegate_schema["properties"]["member_id"])) == {
        "resource-manager",
    }
    assert "team_delegation" in component_delegate_tool["agent_guide"]["runtime_disclosure_groups"]
    create_component_tool = _find_tool(catalog_items[COMPONENT_MANAGER_AGENT_ID], "create_component")
    assert "必须具备整页画布承载能力" in create_component_tool["agent_guide"]["instructions"]
    assert "也可以基于已发布页面组件复用其画布承载能力" in create_component_tool["agent_guide"]["instructions"]
    resource_prompt = catalog_items[RESOURCE_MANAGER_AGENT_ID]["default_prompt"]
    assert "## 1. 身份与硬边界" in resource_prompt
    assert "## 2. 任务分类与执行原则" in resource_prompt
    assert "## 3. 事实来源与对象边界" in resource_prompt
    assert "## 4. 可维护资源类型" in resource_prompt
    assert "## 7. 写入校验与回复契约" in resource_prompt
    assert "如果用户目标实际是页面布局、组件 API、组件源码、项目路由、项目样式或页面源码写入" in resource_prompt
    assert "资源归档是安全整理动作，不等同于删除；你不暴露删除工具" in resource_prompt
    assert "当前只能归档资源，不能执行删除" in resource_prompt
    assert "资源助手不负责说明资源在页面或组件中如何渲染" in resource_prompt
    assert "Draw.io 内容必须是 diagrams.net/draw.io XML" in resource_prompt
    assert "SVG 内容必须是以 <svg> 为根节点的可解析 XML" in resource_prompt
    assert "Runtime Kit" not in resource_prompt
    assert "useAssetSrc" not in resource_prompt
    assert "AssetImage" not in resource_prompt
    assert "style_spec_markdown" not in resource_prompt
    resource_manager_list_tool = _find_tool(catalog_items[RESOURCE_MANAGER_AGENT_ID], "list_resource_assets")
    assert "读取当前工作空间资源库摘要" in resource_manager_list_tool["description"]
    assert "项目建议优先" not in resource_manager_list_tool["description"]
    assert "资源助手按工作空间资源库维护资产" in resource_manager_list_tool["agent_guide"]["instructions"]
    assert "默认 scope=suggested，优先返回项目建议引用资源" not in resource_manager_list_tool["agent_guide"]["instructions"]
    for config_item in catalog_items.values():
        resource_content_tool = _find_tool(config_item, "get_resource_asset_content")
        assert "读取 content_editable=true 资源的 UTF-8 文本内容" in resource_content_tool["description"]
        assert "仅对资源列表中 content_editable=true 的资源调用" in resource_content_tool["agent_guide"]["instructions"]
        assert "复制/归档" not in resource_content_tool["agent_guide"]["instructions"]
        assert "渲染素材" not in resource_content_tool["agent_guide"]["instructions"]
    resource_list_tool = _find_tool(coordinator, "list_resource_assets")
    assert "scope" in resource_list_tool["agent_guide"]["parameters_schema"]["properties"]
    font_asset_tool = _find_tool(coordinator, "list_workspace_font_assets")
    assert "tags" in font_asset_tool["agent_guide"]["parameters_schema"]["properties"]
    assert "resource_read" in font_asset_tool["agent_guide"]["runtime_disclosure_groups"]
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
    style_tool = _find_tool(coordinator, "get_project_style_config")
    assert "include_style_spec_markdown" in style_tool["agent_guide"]["parameters_schema"]["properties"]
    assert "不要为了重复获取 style_spec_markdown 全文而调用本工具" in style_tool["agent_guide"]["instructions"]

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
    assert "组件助手默认不知道当前项目基础字号" in component_prompt
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
    assert "不要为了重复获取 style_spec_markdown 全文而调用本工具" in coordinator_specs["get_project_style_config"].default_instructions
    assert "style_spec_markdown_in_runtime_context" in coordinator_specs["get_project_style_config"].response_example
    assert "style_spec_markdown" not in coordinator_specs["get_project_style_config"].response_example


def test_page_design_guidance_should_use_wireframe_as_internal_method() -> None:
    """页面设计类默认提示词应把文本线框图限定为内部布局方法。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    component_manager = get_agent_catalog_entry(COMPONENT_MANAGER_AGENT_ID)
    assert coordinator is not None
    assert component_manager is not None

    coordinator_prompt = coordinator.default_prompt
    component_prompt = component_manager.default_prompt

    assert "先在内部使用文本线框图或区域清单梳理布局，再写 Vue SFC 代码" in coordinator_prompt
    assert "文本线框图是布局思考方法" in coordinator_prompt
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
        coordinator: ("## 5. 重点任务建议工作流程", "会创建或改动 page_content、页面元数据、路由树或项目样式配置", "可以委派资源助手创建资源", "按委派边界调用成员并整合可用结果"),
        component_manager: ("## 5. 重点任务建议工作流程", "会创建、修改、发布或删除工作空间组件", "组件 API 与预览约束"),
        resource_manager: ("## 5. 重点任务工作流程", "处理创建、修改、复制或归档资源", "内容格式"),
    }
    for catalog, expected_phrases in workflow_expectations.items():
        prompt = catalog.default_prompt
        for phrase in expected_phrases:
            assert phrase in prompt


def test_content_agent_prompt_should_describe_page_rendering_workflow() -> None:
    """内容助手默认提示词应说明 page_content 的 Runtime 渲染方式与固定画布流程。"""

    coordinator = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    assert coordinator is not None

    prompt = coordinator.default_prompt
    expected_phrases = (
        "page_content 要写成完整、可运行的 Vue SFC 文件源码",
        "物化为 src/views/<page.code>.vue 逻辑模块",
        "由 Runtime 通过 Vue 3/Vite 动态导入并渲染",
        "依据页面类型优先从项目建议组件中选择合适的已发布页面组件",
        "找不到合适页面组件时再使用 Runtime Kit 的 DefaultContainer",
        "选择需要渲染的真实资源，包括图片、图表、Mermaid、Draw.io、公式、视频等",
        "选择合适的内容组件、原子组件、Runtime Kit 组件或能力",
        "页面是固定画布大小，不是流式网页",
        "特别注意高度上下文",
    )
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
    assert "普通资源 URL 默认用 useAssetSrc" not in resource_prompt
    assert "项目资源背景优先用 useAssetBackground" not in resource_prompt
    assert "不要传初始化时的 props.xxx 字符串" not in resource_prompt
    assert "resolveResourcePath 只用于非响应式工具代码" not in resource_prompt
    assert "资源助手不负责说明资源在页面或组件中如何渲染" in resource_prompt


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
    if "const" in schema:
        return [str(schema["const"])]
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
