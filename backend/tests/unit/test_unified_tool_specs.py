"""文件功能：工具目录/运行时工具/操作手册防漂移与统一提示词基线的 PR 阻塞单元测试。

原 `tests/integration/test_ai_agent_config.py` 中的纯函数用例移到 unit，保证
`test:backend:unit` 在 PR 默认门禁里就能拦住 tool_specs 派生链漂移。
"""

from __future__ import annotations

from app.ai.agent_catalog import get_agent_catalog_entry, list_agent_catalog_entries
from app.ai.code_standards import get_default_code_standard
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    build_agent_tools_from_group_specs,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.db.session import get_session_factory


EXPECTED_TOOL_KEYS = {
    "get_operation_guide",
    "get_code_standards",
    "list_entities",
    "get_entity",
    "create_entity",
    "update_entity",
    "archive_entity",
    "validate_entity",
    "execute_action",
    "ask_user",
    "analyze_visuals",
    "generate_image",
}


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
    assert "delegate_task_to_self" not in {tool.name for tool in tools}
    assert list_agent_tool_specs("component-manager") == ()
    assert list_agent_tool_specs("resource-manager") == ()
    assert all(guide.handler_tool_key in EXPECTED_TOOL_KEYS for guide in list_operation_guide_specs())
    assert not any("delete" in key or "purge" in key for key in EXPECTED_TOOL_KEYS)


def test_unified_prompt_should_keep_runtime_baseline_and_query_guidance() -> None:
    """统一提示词保留通用 Runtime 基线，并把类型细则交给规范查询。"""

    catalog = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    assert catalog is not None
    for phrase in (
        "page_content 要写成完整、可运行的 Vue SFC 文件源码",
        "页面和组件源码应使用 Runtime、主题、字体、资源和 Icon 的公开契约",
        "页面或组件源码创建、写入、修改前，必须先调用 `get_code_standards`",
        "固定画布、页面布局、组件契约以及页面或组件专属的主题、字体、资源和 Icon 细则",
    ):
        assert phrase in catalog.default_prompt
    assert "固定演示画布与网页流式布局" not in catalog.default_prompt
    assert "不是可以随着内容自然变高的网页文档" not in catalog.default_prompt
    assert "Runtime 主题语义颜色键包括" not in catalog.default_prompt
    assert "页面按真实画布的安全边距、模块间距、字号层级、分栏与内容密度编写" not in catalog.default_prompt
    assert "useTheme().themeStyles 提供的是 --theme-* 变量" not in catalog.default_prompt
    assert "Editor" not in catalog.default_prompt
    assert "固定尺寸的演示画布" in get_default_code_standard("page")
    assert "Runtime 主题语义颜色键包括" in get_default_code_standard("page")
    assert "preview_schema" in get_default_code_standard("component")
    assert "Runtime 主题语义颜色键包括" in get_default_code_standard("component")


def test_unified_prompt_should_describe_platform_assets_and_relations() -> None:
    """统一提示词应提供稳定的平台背景、资产结构和对象关联知识。"""

    catalog = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    assert catalog is not None
    assert catalog.default_prompt.count("\n## ") == 9
    for phrase in (
        "工作空间是权限、数据隔离和共享资产的最高业务边界",
        "页面通过 project_id 归属项目",
        "组件是工作空间级共享代码资产",
        "项目建议资源只是优先参考集合",
        "样式应用到项目时会把当前样式完整复制为项目自己的独立快照",
        "项目样式、建议组件、建议资源、路由树、页面源码和组件源码默认不会完整注入",
        "页面和组件创建、源码更新，以及组件 `preview_schema` 或 `component_type` 修改，都会由平台自动执行编译、渲染和布局校验",
        "项目、页面、组件、资源、主题和样式归档后退出查询与操作边界",
    ):
        assert phrase in catalog.default_prompt
