"""文件功能：验证用户级智能体提示词、工具目录和工具开关配置。"""

from __future__ import annotations

import json

from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.run import RunContext
from agno.run.team import TeamRunInput, TeamRunOutput
from agno.session import TeamSession
from httpx import AsyncClient

from app.ai.agent import COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID
from app.ai.agent import AGENT_COORDINATOR_AGENT_ID, AgentRuntimeContext, build_agent_coordinator_agent
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig
from app.ai.tool_specs import (
    apply_tool_spec_metadata,
    build_agent_tools_from_group_specs,
    list_agent_group_specs,
    list_agent_tool_specs,
)
from app.ai.tools.component import build_component_manager_tools
from app.ai.tools.resource import build_resource_manager_tools
from app.ai.tools.disclosure import get_tool_group_definitions
from app.db.session import get_session_factory
from app.services.ai_agent_config_service import AiAgentConfigService


class _FakeModel(Model):
    """用于构造 Agno system message 的最小测试模型。"""

    def invoke(self, *args, **kwargs):
        """同步调用占位，测试不实际请求模型。"""

        return ModelResponse(content="")

    async def ainvoke(self, *args, **kwargs):
        """异步调用占位，测试不实际请求模型。"""

        return ModelResponse(content="")

    def invoke_stream(self, *args, **kwargs):
        """同步流式调用占位，测试不实际请求模型。"""

        if False:
            yield ModelResponse(content="")

    async def ainvoke_stream(self, *args, **kwargs):
        """异步流式调用占位，测试不实际请求模型。"""

        if False:
            yield ModelResponse(content="")

    def _parse_provider_response(self, response, **kwargs):
        """返回空响应，满足 Agno Model 抽象接口。"""

        return ModelResponse(content="")

    def _parse_provider_response_delta(self, response, **kwargs):
        """返回空增量，满足 Agno Model 抽象接口。"""

        return ModelResponse(content="")


async def test_agent_config_api_should_manage_prompt_and_tool_overrides(authenticated_client: AsyncClient) -> None:
    """智能体配置接口应能返回目录、编辑提示词、关闭工具并恢复默认。"""

    catalog_response = await authenticated_client.get("/api/ai/agent-catalog")
    assert catalog_response.status_code == 200
    catalog_items = {item["id"]: item for item in catalog_response.json()}
    assert set(catalog_items) == {"agent-coordinator", "component-manager", "resource-manager"}
    assert {item["icon"] for item in catalog_items.values()} == {"content-spark", "component-blocks", "resource-images"}
    assert "enabled" not in catalog_items["agent-coordinator"]
    assert catalog_items["agent-coordinator"]["default_prompt"] == ""
    assert catalog_items["component-manager"]["default_prompt"] == ""
    assert catalog_items["resource-manager"]["default_prompt"] == ""
    assert catalog_items["agent-coordinator"]["default_description"] == catalog_items["agent-coordinator"]["description"]
    assert catalog_items["agent-coordinator"]["description_override"] is None
    assert {member["id"] for member in catalog_items["agent-coordinator"]["team_members"]} == {
        "component-manager",
        "resource-manager",
    }
    coordinator_prompt = catalog_items["agent-coordinator"]["system_prompt"]
    assert "主执行助手" in coordinator_prompt
    assert "不要为了形式化协作而委派" in coordinator_prompt
    assert "平台会处理工具确认、执行暂停、校验失败和恢复流程" in coordinator_prompt
    assert "不要自行模拟确认机制" in coordinator_prompt
    assert "Runtime 是页面和组件代码的运行环境" in coordinator_prompt
    assert "Runtime Kit 是 Runtime 暴露给页面和组件源码的公开能力入口" in coordinator_prompt
    assert "它不是通用 UI 组件库，也不是页面模板库" in coordinator_prompt
    assert "工作空间是页面、资源和可复用组件的业务资产边界" in coordinator_prompt
    assert "DefaultContainer" in coordinator_prompt
    assert "衍生容器组件" in coordinator_prompt
    assert "作者画布" in coordinator_prompt
    assert "生成或改写页面时必须考虑当前作者画布尺寸" in coordinator_prompt
    assert "不要无视画布尺寸套用同一种版式" in coordinator_prompt
    assert "常规编写 Vue 与 Tailwind" in coordinator_prompt
    assert "不要手算字号、间距或比例" in coordinator_prompt
    assert "页面按固定演示页/PPT 画布生成" in coordinator_prompt
    assert "若项目样式规范提供字号、密度或拆页规则，必须优先遵守" in coordinator_prompt
    assert "relative h-full w-full overflow-hidden" in coordinator_prompt
    assert "高度上下文" in coordinator_prompt
    assert "不能把它放进普通流式容器" in coordinator_prompt
    assert "100vh/100vw" in coordinator_prompt
    assert "transform: scale 或 zoom" in coordinator_prompt
    assert "卡片、页头、页脚、封面模板、目录模板" in coordinator_prompt
    assert "沉淀为工作空间组件" in coordinator_prompt
    assert "父级需提供 h-full w-full 高度上下文" in coordinator_prompt
    assert "Vue 3、Vite、Vue Router 和 Tailwind" in coordinator_prompt
    assert "以字面量出现的 Tailwind 语义类和常用工具类" in coordinator_prompt
    assert "枚举映射对象返回完整类名字符串" in coordinator_prompt
    assert "不要拼接 text-${tone}、from-${color}" in coordinator_prompt
    assert "主题用于把项目品牌、文字层级、背景层级、边框、链接、强调色、字体和 Logo 抽象成可切换的视觉语义" in coordinator_prompt
    assert "primary、secondary、invert、background、background-subtle、background-invert、border、border-subtle、link、link-hover、link-visited、accent1 到 accent6" in coordinator_prompt
    assert "accent1 到 accent6" in coordinator_prompt
    assert "text-accent2-600、bg-primary/80" in coordinator_prompt
    assert "字号类 text-xs 到 text-9xl、间距类仍按 Tailwind 常规写法使用" in coordinator_prompt
    assert "--tw-font-body" in coordinator_prompt
    assert "--tw-font-size-base" not in coordinator_prompt
    assert "--tw-spacing-unit" not in coordinator_prompt
    assert "themeLogo、themeInvertLogo、themeStyles" in coordinator_prompt
    assert "useAssetFontFamily" in coordinator_prompt
    assert "按资源元数据的 render_type 显式选择 Runtime Kit 资源组件" in coordinator_prompt
    assert "AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart、AssetFormula" in coordinator_prompt
    assert "资源使用逻辑名" in coordinator_prompt
    assert "公开 import_path" in coordinator_prompt
    assert "顶层 const 数组对象字面量" in coordinator_prompt
    assert ":name=\"item.icon\"" in coordinator_prompt
    assert "不要用 computed、函数返回、imported data、拼接或条件表达式生成资源名" in coordinator_prompt
    assert "背景图和蒙版应作为画布内视觉层实现" in coordinator_prompt
    assert "absolute inset-0 h-full w-full" in coordinator_prompt
    assert "relative z-10 h-full w-full" in coordinator_prompt
    assert "useAssetBackground" in coordinator_prompt
    assert "bg-cover bg-center bg-no-repeat" in coordinator_prompt
    assert "AssetBackground" in coordinator_prompt
    assert "useAssetBackground(() => props.backgroundImage)" in coordinator_prompt
    assert "pointer-events-none" in coordinator_prompt
    assert "--tw-color-text-primary" in coordinator_prompt
    for forbidden_text in (
        "app.config.yaml",
        "PDF",
        "Runtime shell",
        "AssetRenderer",
        "@runtime-kit/internal",
        "@runtime-kit/components",
        "外层缩放由 Runtime 处理",
        "tokenScale",
        "typographyScale",
        "runtime_canvas",
    ):
        assert forbidden_text not in coordinator_prompt
    assert "页面源码修改必须先读取目标页面源码" not in coordinator_prompt
    assert "整树覆盖路由前必须先调用 preview_project_route_tree" not in coordinator_prompt
    component_prompt = catalog_items["component-manager"]["system_prompt"]
    assert "生成组件草稿、修改组件源码和 preview_schema" in catalog_items["component-manager"]["description"]
    assert "Runtime 是页面和组件代码的运行环境" in component_prompt
    assert "Runtime Kit 是 Runtime 暴露给页面和组件源码的公开能力入口" in component_prompt
    assert "工作空间是页面、资源和可复用组件的业务资产边界" in component_prompt
    assert "Vue 3、Vite、Tailwind" in component_prompt
    assert "以字面量出现的 Tailwind 语义类和常用工具类" in component_prompt
    assert "枚举映射对象返回完整类名字符串" in component_prompt
    assert "不要拼接 text-${tone}、from-${color}" in component_prompt
    assert "整页模板、布局容器、内容区块、数据展示、资源渲染、样式能力、路由能力" in component_prompt
    assert "component_type 为整页模板" in component_prompt
    assert "component_type 为布局容器" in component_prompt
    assert "component_type 为内容区块" in component_prompt
    assert "component_type 为数据展示" in component_prompt
    assert "component_type 为资源渲染" in component_prompt
    assert "component_type 为样式能力" in component_prompt
    assert "component_type 为路由能力" in component_prompt
    assert "基础页面画布容器 DefaultContainer 或已发布衍生容器组件" in component_prompt
    assert "不承载具体业务内容" in component_prompt
    assert "不在组件内维护项目路由树" in component_prompt
    assert "DefaultContainer" in component_prompt
    assert "衍生容器组件" in component_prompt
    assert "作者画布" in component_prompt
    assert "常规编写 Vue 与 Tailwind" in component_prompt
    assert "不要手算字号、间距或比例" in component_prompt
    assert "页面按固定演示页/PPT 画布生成" in component_prompt
    assert "若项目样式规范提供字号、密度或拆页规则，必须优先遵守" in component_prompt
    assert "relative h-full w-full overflow-hidden" in component_prompt
    assert "高度上下文" in component_prompt
    assert "不能把它放进普通流式容器" in component_prompt
    assert "卡片、页头、页脚、封面模板、目录模板" in component_prompt
    assert "沉淀为工作空间组件" in component_prompt
    assert "不要只依赖根节点 h-full 假设有页面高度" in component_prompt
    assert "主题用于把项目品牌、文字层级、背景层级、边框、链接、强调色、字体和 Logo 抽象成可切换的视觉语义" in component_prompt
    assert "primary、secondary、invert、background、background-subtle、background-invert、border、border-subtle、link、link-hover、link-visited、accent1 到 accent6" in component_prompt
    assert "accent1 到 accent6" in component_prompt
    assert "text-accent2-600、bg-primary/80" in component_prompt
    assert "字号类 text-xs 到 text-9xl、间距类仍按 Tailwind 常规写法使用" in component_prompt
    assert "--tw-font-body" in component_prompt
    assert "--tw-font-size-base" not in component_prompt
    assert "--tw-spacing-unit" not in component_prompt
    assert "themeLogo、themeInvertLogo、themeStyles" in component_prompt
    assert "useAssetFontFamily" in component_prompt
    assert "按资源元数据的 render_type 显式选择 Runtime Kit 资源组件" in component_prompt
    assert "AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart、AssetFormula" in component_prompt
    assert "资源使用逻辑名" in component_prompt
    assert "公开 import_path" in component_prompt
    assert "顶层 const 数组对象字面量" in component_prompt
    assert ":name=\"item.icon\"" in component_prompt
    assert "不要用 computed、函数返回、imported data、拼接或条件表达式生成资源名" in component_prompt
    assert "背景图和蒙版应作为画布内视觉层实现" in component_prompt
    assert "absolute inset-0 h-full w-full" in component_prompt
    assert "relative z-10 h-full w-full" in component_prompt
    assert "useAssetBackground" in component_prompt
    assert "bg-cover bg-center bg-no-repeat" in component_prompt
    assert "AssetBackground" in component_prompt
    assert "useAssetBackground(() => props.backgroundImage)" in component_prompt
    assert "pointer-events-none" in component_prompt
    assert "--tw-color-text-primary" in component_prompt
    for forbidden_text in (
        "app.config.yaml",
        "截图",
        "PDF",
        "Runtime shell",
        "AssetRenderer",
        "@runtime-kit/internal",
        "@runtime-kit/components",
        "外层缩放由 Runtime 处理",
        "tokenScale",
        "typographyScale",
        "runtime_canvas",
    ):
        assert forbidden_text not in component_prompt
    resource_prompt = catalog_items["resource-manager"]["system_prompt"]
    assert "ECharts option 对象" in resource_prompt
    assert "Chart.js" in resource_prompt
    assert "diagrams.net/draw.io XML" in resource_prompt
    assert "<mxfile>" in resource_prompt
    assert "Mermaid 图表源码" in resource_prompt
    assert "Markdown 代码围栏" in resource_prompt
    assert "MathJax 可渲染的 LaTeX" in resource_prompt
    assert "MathML" in resource_prompt
    assert "<svg>" in resource_prompt
    assert "foreignObject" in resource_prompt
    assert "真实的 asset.name" in resource_prompt
    assert "不要编造示例资源名" in resource_prompt
    assert "useAssetBackground" in resource_prompt
    assert "useAssetBackground(() => props.backgroundImage)" in resource_prompt
    assert "不要传初始化时的 props.backgroundImage 字符串" in resource_prompt
    assert "useAssetSrc" in resource_prompt
    assert "computed、条件分支或普通函数" in resource_prompt
    assert "absolute inset-0 h-full w-full" in resource_prompt
    assert "bg-cover bg-center bg-no-repeat" in resource_prompt
    assert "AssetBackground" in resource_prompt
    assert "backgroundSize: 'cover'" in resource_prompt
    assert "AssetImage" in resource_prompt
    assert "pointer-events-none" in resource_prompt
    assert "Tailwind 类作为可配置 props 动态拼接" in resource_prompt
    assert "themeLogo" not in resource_prompt
    assert "themeInvertLogo" not in resource_prompt

    configs_response = await authenticated_client.get("/api/ai/agent-configs")
    assert configs_response.status_code == 200
    configs = {item["id"]: item for item in configs_response.json()}
    assert configs[AGENT_COORDINATOR_AGENT_ID]["prompt_customized"] is False
    assert configs[AGENT_COORDINATOR_AGENT_ID]["default_prompt"] == ""
    assert configs[AGENT_COORDINATOR_AGENT_ID]["effective_prompt"] == ""
    assert configs[COMPONENT_MANAGER_AGENT_ID]["default_prompt"] == ""
    assert configs[COMPONENT_MANAGER_AGENT_ID]["effective_prompt"] == ""
    assert configs[RESOURCE_MANAGER_AGENT_ID]["default_prompt"] == ""
    assert configs[RESOURCE_MANAGER_AGENT_ID]["effective_prompt"] == ""
    assert configs[AGENT_COORDINATOR_AGENT_ID]["description_customized"] is False
    assert {member["id"] for member in configs[AGENT_COORDINATOR_AGENT_ID]["team_members"]} == {
        COMPONENT_MANAGER_AGENT_ID,
        RESOURCE_MANAGER_AGENT_ID,
    }
    assert configs[AGENT_COORDINATOR_AGENT_ID]["disabled_tool_count"] == 0
    content_project_group = next(
        group for group in configs[AGENT_COORDINATOR_AGENT_ID]["tool_groups"] if group["key"] == "content_project"
    )
    assert {group["key"] for group in configs[AGENT_COORDINATOR_AGENT_ID]["tool_groups"]} == {
        "user_feedback",
        "content_project",
        "component_read",
        "runtime_kit",
        "resource_read",
    }
    guide_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "apply_page_edits")
    assert guide_tool["agent_guide"]["tool_name"] == "apply_page_edits"
    assert set(guide_tool["agent_guide"]["parameters_schema"]["required"]) == {"page_id", "edits", "base_version_no"}
    assert "page_id" in guide_tool["agent_guide"]["call_example"]["arguments"]
    assert "edits" in guide_tool["agent_guide"]["call_example"]["arguments"]
    assert guide_tool["agent_guide"]["call_example"]["arguments"]["edits"][0]["type"] == "replace_exact"
    assert guide_tool["agent_guide"]["response_example"]["success"] is True
    assert "page_write" in guide_tool["agent_guide"]["runtime_disclosure_groups"]
    page_diff_instructions = guide_tool["agent_guide"]["instructions"] or ""
    assert "读取目标页面源码" in page_diff_instructions
    assert "每个对象必须带 type" in page_diff_instructions
    assert "check_page_code" in page_diff_instructions
    assert {tool["key"] for tool in content_project_group["tools"]} == {
        "get_page_content",
        "get_project_style_config",
        "list_project_pages",
        "get_project_route_tree",
        "preview_project_route_tree",
        "check_page_code",
        "apply_page_edits",
        "get_page_screenshot",
        "create_project_page",
        "update_page_metadata",
        "update_project_style_config",
        "apply_project_route_tree",
        "remove_project_route_node",
    }
    coordinator_component_group = next(
        group for group in configs[AGENT_COORDINATOR_AGENT_ID]["tool_groups"] if group["key"] == "component_read"
    )
    assert {tool["key"] for tool in coordinator_component_group["tools"]} == {
        "list_workspace_components",
        "get_workspace_component_usage",
    }
    coordinator_component_usage_tool = next(
        tool for tool in coordinator_component_group["tools"] if tool["key"] == "get_workspace_component_usage"
    )
    assert coordinator_component_usage_tool["agent_guide"]["required_context_fields"] == ["workspace_id"]
    assert coordinator_component_usage_tool["agent_guide"]["runtime_disclosure_groups"] == ["component_read"]
    coordinator_runtime_kit_group = next(
        group for group in configs[AGENT_COORDINATOR_AGENT_ID]["tool_groups"] if group["key"] == "runtime_kit"
    )
    assert {tool["key"] for tool in coordinator_runtime_kit_group["tools"]} == {
        "list_runtime_kit_capabilities",
        "get_runtime_kit_capability",
    }
    coordinator_runtime_kit_tool = next(
        tool for tool in coordinator_runtime_kit_group["tools"] if tool["key"] == "list_runtime_kit_capabilities"
    )
    assert coordinator_runtime_kit_tool["agent_guide"]["required_context_fields"] == ["workspace_id"]
    assert coordinator_runtime_kit_tool["agent_guide"]["runtime_disclosure_groups"] == ["runtime_kit"]
    assert "@runtime-kit/public/components/page/layout/DefaultContainer.vue" in json.dumps(
        coordinator_runtime_kit_tool["agent_guide"]["response_example"],
        ensure_ascii=False,
    )
    coordinator_resource_group = next(
        group for group in configs[AGENT_COORDINATOR_AGENT_ID]["tool_groups"] if group["key"] == "resource_read"
    )
    assert {tool["key"] for tool in coordinator_resource_group["tools"]} == {
        "list_resource_assets",
        "get_resource_asset_content",
        "list_resource_tags",
    }
    coordinator_resource_tool = next(
        tool for tool in coordinator_resource_group["tools"] if tool["key"] == "list_resource_assets"
    )
    assert coordinator_resource_tool["agent_guide"]["required_context_fields"] == ["workspace_id"]
    assert coordinator_resource_tool["agent_guide"]["runtime_disclosure_groups"] == ["resource_read"]
    style_read_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "get_project_style_config")
    style_read_response = style_read_tool["agent_guide"]["response_example"]
    assert "作者画布" in (style_read_tool["agent_guide"]["instructions"] or "")
    assert {"authoring_width", "authoring_height", "theme", "style_spec_markdown"} <= set(style_read_response)
    assert "theme_key" not in style_read_response
    assert "page_width" not in style_read_response
    assert "effective_theme_config" not in style_read_response
    style_update_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "update_project_style_config")
    assert style_update_tool["agent_guide"]["requires_confirmation"] is True
    assert "get_project_style_config" in (style_update_tool["agent_guide"]["instructions"] or "")
    style_update_schema = style_update_tool["agent_guide"]["parameters_schema"] or {}
    assert set(style_update_schema["properties"]) == {"style_spec_markdown"}
    route_preview_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "preview_project_route_tree")
    route_preview_instructions = route_preview_tool["agent_guide"]["instructions"] or ""
    assert "必经预览步骤" in route_preview_instructions
    assert "完整路由树覆盖内容，不是局部 patch" in route_preview_instructions
    assert "单段相对片段" in route_preview_instructions
    assert "page 节点必须传" in route_preview_instructions
    assert "group 节点必须传" in route_preview_instructions
    assert "page_id 只能来自 list_project_pages" in route_preview_instructions
    route_preview_schema = route_preview_tool["agent_guide"]["parameters_schema"] or {}
    route_item_schema = route_preview_schema["properties"]["routes"]["items"]
    route_item_properties = route_item_schema["properties"]
    assert {"route_type", "route", "order", "page_id", "group_title", "children"}.issubset(route_item_properties)
    assert "route_type" in route_item_schema["required"]
    assert "route" in route_item_schema["required"]
    assert "page_id" in route_item_properties["children"]["items"]["properties"]
    create_page_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "create_project_page")
    create_page_instructions = create_page_tool["agent_guide"]["instructions"] or ""
    assert "页面标题" in create_page_instructions
    assert "页面说明" in create_page_instructions
    assert "是否需要加入路由" in create_page_instructions
    assert "page_content" in create_page_instructions
    assert "非空、可运行的 Vue SFC" in create_page_instructions
    assert "check_page_code" in create_page_instructions
    assert "不会自动维护项目路由" in create_page_instructions
    assert "读取、预览并写入路由树" in create_page_instructions
    assert "读取新页面源码" in create_page_instructions
    assert "结构化 edits" in create_page_instructions
    for global_rule_text in (
        "DefaultContainer",
        "AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart、AssetFormula",
        "useAssetBackground",
        "100vh/100vw",
        "transform: scale 或 zoom",
        "不要拼接 text-${tone}、from-${color}",
    ):
        assert global_rule_text not in create_page_instructions
    route_apply_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "apply_project_route_tree")
    route_apply_instructions = route_apply_tool["agent_guide"]["instructions"] or ""
    assert "读取项目页面列表" in route_apply_instructions
    assert "preview_project_route_tree" in route_apply_instructions
    assert "完整路由树覆盖内容，不是局部 patch" in route_apply_instructions
    assert "page_id 只能来自 list_project_pages" in route_apply_instructions
    assert route_apply_tool["agent_guide"]["requires_confirmation"] is True
    route_remove_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "remove_project_route_node")
    route_remove_instructions = route_remove_tool["agent_guide"]["instructions"] or ""
    assert "route_id 必须来自 get_project_route_tree" in route_remove_instructions
    assert "不是 page_id、page_code 或 route 字符串" in route_remove_instructions
    component_library_group = next(
        group for group in configs[COMPONENT_MANAGER_AGENT_ID]["tool_groups"] if group["key"] == "component_library"
    )
    assert {group["key"] for group in configs[COMPONENT_MANAGER_AGENT_ID]["tool_groups"]} == {
        "user_feedback",
        "component_library",
    }
    runtime_kit_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "list_runtime_kit_capabilities")
    runtime_kit_detail_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "get_runtime_kit_capability")
    runtime_kit_examples = json.dumps(
        [
            runtime_kit_tool["agent_guide"]["response_example"],
            runtime_kit_detail_tool["agent_guide"]["response_example"],
        ],
        ensure_ascii=False,
    )
    assert "@runtime-kit/public/components/page/layout/DefaultContainer.vue" in runtime_kit_examples
    assert "@runtime-kit/components" not in runtime_kit_examples
    assert "按工具返回 import_path 原样使用" in runtime_kit_examples
    metadata_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "update_component_metadata")
    metadata_instructions = metadata_tool["agent_guide"]["instructions"] or ""
    assert "import_name" in metadata_instructions
    assert "PascalCase" in metadata_instructions
    assert "省略该参数" in metadata_instructions
    assert "preview_schema" in metadata_instructions
    assert "季度经营概览" in metadata_instructions
    assert "@runtime-kit/public/components/primitives/Icon.vue" in metadata_instructions
    component_tool_keys = {tool["key"] for tool in component_library_group["tools"]}
    assert "create_component_draft" not in component_tool_keys
    assert "publish_component" in component_tool_keys
    assert {"list_resource_assets", "get_resource_asset_content", "list_resource_tags"} <= component_tool_keys
    component_resource_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "list_resource_assets")
    assert component_resource_tool["agent_guide"]["required_context_fields"] == ["workspace_id"]
    assert "resource_read" in component_resource_tool["agent_guide"]["runtime_disclosure_groups"]
    create_component_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "create_component")
    create_component_instructions = create_component_tool["agent_guide"]["instructions"] or ""
    assert "PascalCase import_name" in create_component_instructions
    assert "component_type" in create_component_instructions
    assert "默认使用内容区块" in create_component_instructions
    assert "content 必须是非空、可运行的 Vue SFC" in create_component_instructions
    assert "check_component_code" in create_component_instructions
    assert "不要用 preview_component_edits 校验新建组件" in create_component_instructions
    assert "props" in create_component_instructions
    assert "slots" in create_component_instructions
    assert "presets" in create_component_instructions
    assert "JSON 对象字符串或 JSON 对象" in create_component_instructions
    assert "previewSchema 导出" in create_component_instructions
    assert "publish_component" in create_component_instructions
    for global_rule_text in (
        "component_type 为整页模板",
        "DefaultContainer",
        "AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart、AssetFormula",
        "useAssetBackground",
        "transform: scale 或 zoom",
        "不要拼接 text-${tone}、from-${color}",
    ):
        assert global_rule_text not in create_component_instructions
    publish_component_tool = next(tool for tool in component_library_group["tools"] if tool["key"] == "publish_component")
    publish_component_instructions = publish_component_tool["agent_guide"]["instructions"] or ""
    assert "不可变正式版本" in publish_component_instructions
    assert "@workspace-components/<component_code>/v/<version_no>" in publish_component_instructions
    resource_library_group = next(
        group for group in configs[RESOURCE_MANAGER_AGENT_ID]["tool_groups"] if group["key"] == "resource_library"
    )
    create_resource_tool = next(tool for tool in resource_library_group["tools"] if tool["key"] == "create_resource_asset")
    create_resource_instructions = create_resource_tool["agent_guide"]["instructions"] or ""
    assert "ECharts option 对象" in create_resource_instructions
    assert "ECharts setOption" in create_resource_instructions
    assert "diagrams.net/draw.io XML" in create_resource_instructions
    assert "<mxfile>" in create_resource_instructions
    assert "Mermaid 图表源码" in create_resource_instructions
    assert "Markdown 代码围栏" in create_resource_instructions
    assert "MathJax 可渲染的 LaTeX" in create_resource_instructions
    assert "MathML" in create_resource_instructions
    assert "<svg>" in create_resource_instructions
    assert "foreignObject" in create_resource_instructions
    assert "tags 必须传 JSON 数组/list[str]" in create_resource_instructions
    assert "不要传 JSON 字符串" in create_resource_instructions
    preview_resource_tool = next(
        tool for tool in resource_library_group["tools"] if tool["key"] == "preview_resource_content_diff"
    )
    preview_resource_instructions = preview_resource_tool["agent_guide"]["instructions"] or ""
    assert "ECharts option 对象" in preview_resource_instructions
    assert "diagrams.net/draw.io XML" in preview_resource_instructions
    assert "Mermaid 图表源码" in preview_resource_instructions
    assert "MathJax 可渲染的 LaTeX" in preview_resource_instructions
    assert "foreignObject" in preview_resource_instructions

    prompt_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}",
        json={
            "description_override": "用户自定义内容助手描述。",
            "prompt_override": "用户自定义业务补充提示词：优先给出简短结论。",
        },
    )
    assert prompt_response.status_code == 200
    assert prompt_response.json()["description_customized"] is True
    assert prompt_response.json()["description"] == "用户自定义内容助手描述。"
    assert prompt_response.json()["prompt_customized"] is True
    assert "简短结论" in prompt_response.json()["effective_prompt"]

    member_description_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{COMPONENT_MANAGER_AGENT_ID}",
        json={"description_override": "用户自定义组件助手 Team 成员描述。"},
    )
    assert member_description_response.status_code == 200
    assert member_description_response.json()["description_customized"] is True
    configs_response_after_member_update = await authenticated_client.get("/api/ai/agent-configs")
    assert configs_response_after_member_update.status_code == 200
    coordinator_config = next(
        item for item in configs_response_after_member_update.json() if item["id"] == AGENT_COORDINATOR_AGENT_ID
    )
    component_member = next(
        member for member in coordinator_config["team_members"] if member["id"] == COMPONENT_MANAGER_AGENT_ID
    )
    assert component_member["description"] == "用户自定义组件助手 Team 成员描述。"
    assert component_member["description_customized"] is True

    tool_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/apply_page_edits",
        json={"enabled": False, "description_override": "此工具暂时不允许被模型使用。"},
    )
    assert tool_response.status_code == 200
    content_project_group = next(group for group in tool_response.json()["tool_groups"] if group["key"] == "content_project")
    apply_tool = next(tool for tool in content_project_group["tools"] if tool["key"] == "apply_page_edits")
    assert apply_tool["enabled"] is False
    assert apply_tool["description"] == "此工具暂时不允许被模型使用。"
    assert apply_tool["agent_guide"]["effective_description"] == "此工具暂时不允许被模型使用。"
    assert apply_tool["agent_guide"]["system_description"] == "对指定 page_id 页面应用结构化 edits，并自动保存为新版本。"

    restore_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/apply_page_edits",
        json={"restore_default": True},
    )
    assert restore_response.status_code == 200
    restored_group = next(group for group in restore_response.json()["tool_groups"] if group["key"] == "content_project")
    restored_tool = next(tool for tool in restored_group["tools"] if tool["key"] == "apply_page_edits")
    assert restored_tool["enabled"] is True
    assert restored_tool["description_override"] is None


async def test_agent_list_should_use_lightweight_config_summary(authenticated_client: AsyncClient, monkeypatch) -> None:
    """Agent 列表接口只应读取轻量摘要，避免为侧栏入口生成完整工具说明。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "AI 列表性能工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    def reject_full_tool_map(agent_id: str) -> dict[str, object]:
        raise AssertionError(f"/ai/agents 不应构建完整工具说明：{agent_id}")

    monkeypatch.setattr(
        AiAgentConfigService,
        "_build_runtime_tool_map",
        staticmethod(reject_full_tool_map),
    )

    response = await authenticated_client.get(
        "/api/ai/agents",
        params={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "source": "editor-agent-sidebar",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == AGENT_COORDINATOR_AGENT_ID
    assert payload[0]["icon"] == "content-spark"
    assert payload[0]["prompt_customized"] is False
    assert payload[0]["enabled_tool_count"] == len(list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID))
    assert payload[0]["disabled_tool_count"] == 0
    assert "tool_groups" not in payload[0]


async def test_agent_runtime_config_should_filter_disabled_tools_and_apply_prompt(
    authenticated_client: AsyncClient,
) -> None:
    """用户关闭工具后，新 Agent run 不应再把该工具交给模型。"""

    prompt_text = "用户自定义业务补充提示词：回答前先说明使用了哪些工具。"
    prompt_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}",
        json={"prompt_override": prompt_text},
    )
    assert prompt_response.status_code == 200

    disable_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/apply_page_edits",
        json={"enabled": False},
    )
    assert disable_response.status_code == 200

    description_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/get_page_content",
        json={"description_override": "读取页面源码的用户自定义工具说明。"},
    )
    assert description_response.status_code == 200
    member_description_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{COMPONENT_MANAGER_AGENT_ID}",
        json={"description_override": "运行时使用的组件助手成员描述。"},
    )
    assert member_description_response.status_code == 200

    async with get_session_factory()() as session:
        config_service = AiAgentConfigService(session, user_id=1)
        runtime_config = await config_service.get_effective_runtime_config(AGENT_COORDINATOR_AGENT_ID)
        component_runtime_config = await config_service.get_effective_runtime_config(COMPONENT_MANAGER_AGENT_ID)

    agent = build_agent_coordinator_agent(
        agno_db=None,
        session_factory=get_session_factory(),
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="page",
            workspace_id=1,
            project_id=1,
            page_id=1,
            source="editor-page-detail",
        ),
        session_metadata={"model_supports_image_input": False},
        agent_config=runtime_config,
        component_agent_config=component_runtime_config,
    )

    tool_map = {tool.name: tool for tool in agent.tools}
    assert "apply_page_edits" not in tool_map
    assert "create_project_page" in tool_map
    assert "get_page_screenshot" not in tool_map
    assert tool_map["get_page_content"].description == "读取页面源码的用户自定义工具说明。"
    assert prompt_text in agent.instructions
    component_member = next(member for member in agent.members if member.id == COMPONENT_MANAGER_AGENT_ID)
    assert component_member.description == "运行时使用的组件助手成员描述。"

    definitions = get_tool_group_definitions(
        session_factory=get_session_factory(),
        agent_config=runtime_config,
    )
    assert "apply_page_edits" not in definitions["page_write"].tool_keys


def test_agent_coordinator_system_message_should_use_main_executor_framework() -> None:
    """内容助手同步 system message 应移除 Agno 英文协调框架并保留动态上下文。"""

    content = _build_coordinator_system_message(supports_image_input=False)

    assert "You coordinate a team" not in content
    assert "You operate in coordinate mode" not in content
    assert "内容任务主执行助手" in content
    assert "不要为了形式化协作而委派" in content
    assert "<team_members>" in content
    assert "Tools: ask_user, list_components" in content
    assert "页面源码、页面元数据、项目路由和项目样式写入必须遵守对应工具说明" in content
    assert "<additional_context>" in content
    assert "当前模型不支持图片输入" in content
    assert "页面截图视觉工具不会进入本轮工具列表" in content


async def test_agent_coordinator_async_system_message_should_use_main_executor_framework() -> None:
    """内容助手异步 system message 应移除 Agno 英文协调框架。"""

    content = await _build_coordinator_system_message_async(supports_image_input=True)

    assert "You coordinate a team" not in content
    assert "You operate in coordinate mode" not in content
    assert "内容任务主执行助手" in content
    assert "调用成员后，你必须判断成员结果是否可用" in content
    assert "<team_members>" in content
    assert "<additional_context>" in content
    assert "当前模型支持图片输入" in content
    assert "页面截图视觉工具可见" in content


def test_agent_coordinator_system_message_should_keep_user_overrides_after_localization() -> None:
    """用户配置描述和业务补充提示词后，仍应移除 Agno 英文框架。"""

    runtime_config = EffectiveAgentRuntimeConfig(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        description_override="用户覆盖后的内容助手描述。",
        prompt_override="用户补充后的业务提示词：先给出执行摘要。",
        tool_configs={},
    )
    content = _build_coordinator_system_message(
        supports_image_input=False,
        agent_config=runtime_config,
    )

    assert "You coordinate a team" not in content
    assert "<description>\n用户覆盖后的内容助手描述。\n</description>" in content
    assert "用户补充后的业务提示词：先给出执行摘要。" in content
    assert "页面源码以 Vue SFC 作为最小构建单元" in content
    assert "内容任务主执行助手" in content


def test_agent_tool_specs_should_match_actual_agno_tools() -> None:
    """统一工具规格应覆盖目录、工具组和实际 Agno Function，防止后续增删工具漂移。"""

    session_factory = get_session_factory()
    coordinator_tools = []
    for definition in get_tool_group_definitions(session_factory=session_factory).values():
        coordinator_tools.extend(definition.build_tools())
    coordinator_tools = apply_tool_spec_metadata(agent_id=AGENT_COORDINATOR_AGENT_ID, tools=coordinator_tools)
    _assert_agent_specs_match_tools(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        actual_tools=coordinator_tools,
    )

    component_tools = build_agent_tools_from_group_specs(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_factory=session_factory,
    )
    raw_component_tool_keys = {tool.name for tool in build_component_manager_tools(session_factory)}
    assert raw_component_tool_keys | {"ask_user"} == {tool.name for tool in component_tools}
    _assert_agent_specs_match_tools(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        actual_tools=component_tools,
    )

    resource_tools = build_agent_tools_from_group_specs(
        agent_id=RESOURCE_MANAGER_AGENT_ID,
        session_factory=session_factory,
    )
    raw_resource_tool_keys = {tool.name for tool in build_resource_manager_tools(session_factory)}
    assert raw_resource_tool_keys | {"ask_user"} == {tool.name for tool in resource_tools}
    _assert_agent_specs_match_tools(
        agent_id=RESOURCE_MANAGER_AGENT_ID,
        actual_tools=resource_tools,
    )


def test_page_screenshot_tool_schema_should_only_accept_page_id() -> None:
    """页面截图视觉工具只应允许 Agent 传 page_id，其他刷新细节由后端决定。"""

    definitions = get_tool_group_definitions(session_factory=get_session_factory())
    screenshot_tool = definitions["page_visual_read"].build_tools()[0]
    assert screenshot_tool.name == "get_page_screenshot"
    assert screenshot_tool.parameters == {
        "type": "object",
        "properties": {"page_id": {"type": "integer"}},
        "required": ["page_id"],
    }


def test_page_content_tool_schema_should_accept_optional_page_id() -> None:
    """页面源码工具应允许 Agent 不传 page_id，以便回退到上下文页面。"""

    definitions = get_tool_group_definitions(session_factory=get_session_factory())
    page_content_tool = definitions["content_read"].build_tools()[0]
    assert page_content_tool.name == "get_page_content"
    assert page_content_tool.parameters == {
        "type": "object",
        "properties": {"page_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
        "required": [],
    }


def test_apply_page_edits_schema_should_require_page_id() -> None:
    """页面写入工具应要求 Agent 显式传入目标 page_id。"""

    definitions = get_tool_group_definitions(session_factory=get_session_factory())
    page_write_tools = {tool.name: tool for tool in definitions["page_write"].build_tools()}
    apply_page_tool = page_write_tools["apply_page_edits"]
    assert "page_id" in apply_page_tool.parameters["properties"]
    assert "page_id" in apply_page_tool.parameters["required"]
    assert "edits" in apply_page_tool.parameters["required"]
    assert "base_version_no" in apply_page_tool.parameters["required"]
    edit_variants = apply_page_tool.parameters["properties"]["edits"]["items"]["anyOf"]
    replace_exact_schema = next(item for item in edit_variants if item["properties"]["type"]["const"] == "replace_exact")
    insert_after_schema = next(item for item in edit_variants if item["properties"]["type"]["const"] == "insert_after")
    rewrite_file_schema = next(item for item in edit_variants if item["properties"]["type"]["const"] == "rewrite_file")
    assert replace_exact_schema["required"] == ["type", "old_text", "new_text"]
    assert insert_after_schema["required"] == ["type", "anchor_text", "new_text"]
    assert rewrite_file_schema["required"] == ["type", "content"]


def test_agent_tool_schemas_should_not_expose_unstructured_object_arrays() -> None:
    """工具入参不应暴露无法约束元素字段的 object 数组。"""

    agent_ids = (AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID)
    findings: list[str] = []
    for agent_id in agent_ids:
        tools = build_agent_tools_from_group_specs(
            agent_id=agent_id,
            session_factory=get_session_factory(),
        )
        for tool in tools:
            parameters = getattr(tool, "parameters", None)
            findings.extend(
                f"{agent_id}.{tool.name}:{path}"
                for path in _find_unstructured_object_array_paths(parameters)
            )

    assert findings == []


def test_component_preview_schema_tools_should_accept_preview_schema_object() -> None:
    """组件 preview_schema 相关工具应允许 Agent 传入 JSON 对象或对象字符串。"""

    tools = build_agent_tools_from_group_specs(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_factory=get_session_factory(),
    )

    for tool_name in ("check_component_code", "create_component", "update_component_metadata"):
        tool = next(tool for tool in tools if tool.name == tool_name)
        preview_schema = tool.parameters["properties"]["preview_schema"]
        assert preview_schema == {
            "anyOf": [
                {"type": "string"},
                {"additionalProperties": True, "type": "object"},
                {"type": "null"},
            ]
        }


def test_write_tool_response_examples_should_expose_refresh_identity() -> None:
    """写入工具响应示例应包含前端刷新所需的实体 ID，避免只能反推工具入参。"""

    coordinator_specs = {spec.key: spec for spec in list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID)}
    apply_page_example = coordinator_specs["apply_page_edits"].response_example
    assert apply_page_example["success"] is True
    assert apply_page_example["page_id"] == 3

    component_specs = {spec.key: spec for spec in list_agent_tool_specs(COMPONENT_MANAGER_AGENT_ID)}
    apply_component_example = component_specs["apply_component_edits"].response_example
    assert apply_component_example["success"] is True
    assert apply_component_example["component_id"] == apply_component_example["component"]["id"]
    assert apply_component_example["component"]["code"] == "cmp_hero_card"

    resource_specs = {spec.key: spec for spec in list_agent_tool_specs(RESOURCE_MANAGER_AGENT_ID)}
    apply_resource_example = resource_specs["apply_resource_content_diff"].response_example
    assert apply_resource_example["success"] is True
    assert apply_resource_example["asset"]["id"] == 8


def test_user_feedback_tool_should_be_system_tool_for_all_agents() -> None:
    """所有智能体都应暴露单选结构化提问工具，且不暴露自由字段提问工具。"""

    for agent_id in (AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
        specs = {spec.key: spec for spec in list_agent_tool_specs(agent_id)}
        assert "ask_user" in specs
        assert "get_user_input" not in specs
        assert specs["ask_user"].configurable is False
        assert specs["ask_user"].risk_level == "system"

        groups = {group.key: group for group in list_agent_group_specs(agent_id)}
        assert groups["user_feedback"].tool_keys == ("ask_user",)


def _find_unstructured_object_array_paths(schema: object, path: str = "$") -> list[str]:
    """递归查找数组元素仍是宽松 object 的参数路径。"""

    if not isinstance(schema, dict):
        return []
    findings: list[str] = []
    if schema.get("type") == "array":
        items = schema.get("items")
        if _is_unstructured_object_schema(items):
            findings.append(f"{path}.items")
        findings.extend(_find_unstructured_object_array_paths(items, f"{path}.items"))

    for key in ("properties", "$defs", "definitions"):
        value = schema.get(key)
        if isinstance(value, dict):
            for name, child in value.items():
                findings.extend(_find_unstructured_object_array_paths(child, f"{path}.{key}.{name}"))

    for key in ("anyOf", "oneOf", "allOf"):
        value = schema.get(key)
        if isinstance(value, list):
            for index, child in enumerate(value):
                findings.extend(_find_unstructured_object_array_paths(child, f"{path}.{key}[{index}]"))
    return findings


def _is_unstructured_object_schema(schema: object) -> bool:
    """判断 schema 是否只是宽松 object，没有固定属性、联合分支或引用。"""

    if not isinstance(schema, dict) or schema.get("type") != "object":
        return False
    if any(key in schema for key in ("properties", "anyOf", "oneOf", "allOf", "$ref")):
        return False
    return True


def _build_coordinator_system_message(
    *,
    supports_image_input: bool,
    agent_config: EffectiveAgentRuntimeConfig | None = None,
) -> str:
    """构造内容助手同步 system message，并先触发工具提示词装配。"""

    agent = _build_coordinator_for_system_message(
        supports_image_input=supports_image_input,
        agent_config=agent_config,
    )
    session = TeamSession(session_id="system-message-test")
    run_context = RunContext(run_id="run-system-message-test", session_id=session.session_id, user_id="1")
    run_response = TeamRunOutput(
        run_id=run_context.run_id,
        session_id=session.session_id,
        team_id=agent.id,
        team_name=agent.name,
        input=TeamRunInput(input_content="测试 system message"),
    )
    tools = agent._determine_tools_for_model(
        model=agent.model,
        run_response=run_response,
        run_context=run_context,
        team_run_context={},
        session=session,
        user_id="1",
        input_message="测试 system message",
        stream=True,
        stream_events=True,
        check_mcp_tools=False,
    )
    message = agent.get_system_message(session=session, run_context=run_context, tools=tools)
    assert message is not None
    return str(message.content)


async def _build_coordinator_system_message_async(*, supports_image_input: bool) -> str:
    """构造内容助手异步 system message，并先触发工具提示词装配。"""

    agent = _build_coordinator_for_system_message(supports_image_input=supports_image_input)
    session = TeamSession(session_id="system-message-async-test")
    run_context = RunContext(run_id="run-system-message-async-test", session_id=session.session_id, user_id="1")
    run_response = TeamRunOutput(
        run_id=run_context.run_id,
        session_id=session.session_id,
        team_id=agent.id,
        team_name=agent.name,
        input=TeamRunInput(input_content="测试 async system message"),
    )
    tools = agent._determine_tools_for_model(
        model=agent.model,
        run_response=run_response,
        run_context=run_context,
        team_run_context={},
        session=session,
        user_id="1",
        input_message="测试 async system message",
        async_mode=True,
        stream=True,
        stream_events=True,
        check_mcp_tools=False,
    )
    message = await agent.aget_system_message(session=session, run_context=run_context, tools=tools)
    assert message is not None
    return str(message.content)


def _build_coordinator_for_system_message(
    *,
    supports_image_input: bool,
    agent_config: EffectiveAgentRuntimeConfig | None = None,
):
    """创建用于 system message 断言的内容助手 Team。"""

    return build_agent_coordinator_agent(
        agno_db=None,
        session_factory=get_session_factory(),
        model=_FakeModel(id="fake"),
        runtime_context=AgentRuntimeContext(
            scope_type="page",
            workspace_id=1,
            project_id=1,
            page_id=1,
            source="editor-page-detail",
        ),
        session_metadata={"model_supports_image_input": supports_image_input},
        agent_config=agent_config,
    )


def _assert_agent_specs_match_tools(*, agent_id: str, actual_tools: list[object]) -> None:
    """校验某个智能体的规格、分组与实际工具对象一致。"""

    spec_map = {spec.key: spec for spec in list_agent_tool_specs(agent_id)}
    actual_map = {str(getattr(tool, "name", "")): tool for tool in actual_tools}
    assert set(spec_map) == set(actual_map)

    grouped_tool_keys = {
        tool_key
        for group in list_agent_group_specs(agent_id)
        for tool_key in group.tool_keys
    }
    assert set(spec_map) == grouped_tool_keys

    for tool_key, spec in spec_map.items():
        tool = actual_map[tool_key]
        assert getattr(tool, "description") == spec.description
        assert bool(getattr(tool, "requires_confirmation", False)) == spec.requires_confirmation
        assert isinstance(getattr(tool, "parameters", None), dict)
