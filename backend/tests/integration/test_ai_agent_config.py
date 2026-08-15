"""文件功能：验证统一内容助手目录、配置接口与运行时工具规格防漂移。"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.ai.agent_catalog import get_agent_catalog_entry, list_agent_catalog_entries
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    build_agent_tools_from_group_specs,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.db.session import get_session_factory
from app.models.ai_agent_config import AiAgentToolUserConfig
from app.models.user import User
from app.services.ai_agent_config_service import AiAgentConfigService


EXPECTED_TOOL_KEYS = {
    "get_operation_guide",
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
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/tools/list_entities",
        json={"enabled": False, "description_override": "罗列业务对象。"},
    )
    assert tool_response.status_code == 200
    list_tool = next(
        tool
        for group in tool_response.json()["tool_groups"]
        for tool in group["tools"]
        if tool["key"] == "list_entities"
    )
    assert list_tool["enabled"] is False
    assert list_tool["description"] == "罗列业务对象。"


async def test_legacy_query_tool_config_should_apply_to_both_read_tools() -> None:
    """升级前 query_entities 的用户配置应同时继承到新的集合与单项读取入口。"""

    async with get_session_factory()() as session:
        user_id = await session.scalar(select(User.id).where(User.username == "admin"))
        assert user_id is not None
        await session.execute(
            delete(AiAgentToolUserConfig).where(
                AiAgentToolUserConfig.user_id == int(user_id),
                AiAgentToolUserConfig.agent_id == AGENT_COORDINATOR_AGENT_ID,
                AiAgentToolUserConfig.tool_key.in_(("query_entities", "list_entities", "get_entity")),
            )
        )
        session.add(AiAgentToolUserConfig(
            user_id=int(user_id),
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            tool_key="query_entities",
            enabled=False,
            description_override="旧查询说明",
            instructions_override="旧查询提示",
            created_by=int(user_id),
            updated_by=int(user_id),
        ))
        await session.commit()

        runtime_config = await AiAgentConfigService(session, user_id=int(user_id)).get_effective_runtime_config(
            AGENT_COORDINATOR_AGENT_ID
        )

    for tool_key in ("list_entities", "get_entity"):
        config = runtime_config.tool_configs[tool_key]
        assert config.enabled is False
        assert config.description_override == "旧查询说明"
        assert config.instructions_override == "旧查询提示"


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
        "演示页面是固定尺寸的画布，不是可以随着内容自然变高的网页文档",
        "未注入时先读取项目 configuration",
        "页面按真实画布的安全边距、模块间距、字号层级、分栏与内容密度编写，具体数值基线以项目样式规范为准",
        "PAGE_RENDER_BOTTOM_OVERFLOW",
        "Runtime 主题语义颜色键包括",
        "background-subtle 是 Runtime 提供的语义背景槽位",
        "只使用上述 Runtime 主题键，不要猜测其它语义颜色键",
        "未列出的语义 Token 不得自行引入",
        "不要拼接 text-${tone}、from-${color}",
        "var(--tw-color-text-primary)",
        "useTheme().themeStyles 提供的是 --theme-* 变量",
    ):
        assert phrase in catalog.default_prompt
    assert "Editor" not in catalog.default_prompt


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
        "create_entity 创建页面或组件、update_entity 修改页面或组件源码时都会自动执行校验",
        "项目、页面、组件、资源、主题和样式归档后退出查询与操作边界",
    ):
        assert phrase in catalog.default_prompt
