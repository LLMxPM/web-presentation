"""文件功能：验证统一内容助手目录、配置接口与运行时工具规格防漂移。"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.ai.agent_catalog import get_agent_catalog_entry, list_agent_catalog_entries
from app.ai.code_standards import get_default_code_standard
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    build_agent_tools_from_group_specs,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.db.session import get_session_factory
from app.models.ai_agent_config import AiAgentToolUserConfig
from app.models.enums import UserRole
from app.models.user import User
from app.core.security import hash_password
from app.services.ai_agent_config_service import AiAgentConfigService


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
    assert "delegate_task_to_self" not in coordinator["default_prompt"]
    assert "delegate_task_to_member" not in coordinator["default_prompt"]
    assert "组件助手" not in coordinator["default_prompt"]
    assert "资源助手" not in coordinator["default_prompt"]

    tool_items = [tool for group in coordinator["tool_groups"] for tool in group["tools"]]
    assert {tool["key"] for tool in tool_items} == EXPECTED_TOOL_KEYS
    standards_tool = next(tool for tool in tool_items if tool["key"] == "get_code_standards")
    assert standards_tool["configurable"] is False
    assert "standard_type=page" in standards_tool["default_instructions"]
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


async def test_code_standard_config_should_support_default_override_and_restore(
    authenticated_client: AsyncClient,
) -> None:
    """页面与组件规范应按类型返回，并支持整段覆盖和恢复默认。"""

    list_response = await authenticated_client.get(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/code-standards"
    )
    assert list_response.status_code == 200
    defaults = {item["standard_type"]: item for item in list_response.json()}
    assert set(defaults) == {"page", "component"}
    assert defaults["page"]["source"] == "system_default"
    assert defaults["page"]["customized"] is False
    assert defaults["page"]["content"] == defaults["page"]["default_content"]

    custom_content = "## 我的页面规范\n\n- 页面标题必须使用结论句。"
    update_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/code-standards/page",
        json={"content_override": custom_content},
    )
    assert update_response.status_code == 200
    updated = {item["standard_type"]: item for item in update_response.json()}
    assert updated["page"]["content"] == custom_content
    assert updated["page"]["default_content"] != custom_content
    assert updated["page"]["source"] == "user_custom"
    assert updated["component"]["content"] == updated["component"]["default_content"]

    async with get_session_factory()() as session:
        session.add(
            User(
                username="code-standard-user",
                password_hash=hash_password("CodeStandard123456"),
                display_name="规范测试用户",
                role=UserRole.WORKSPACE_USER.value,
                preview_size_presets=[],
            )
        )
        await session.commit()

    login_response = await authenticated_client.post(
        "/api/auth/login",
        json={"username": "code-standard-user", "password": "CodeStandard123456"},
    )
    assert login_response.status_code == 200
    other_user_response = await authenticated_client.get(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/code-standards"
    )
    assert other_user_response.status_code == 200
    other_user_defaults = {item["standard_type"]: item for item in other_user_response.json()}
    assert other_user_defaults["page"]["customized"] is False
    assert other_user_defaults["page"]["content"] == other_user_defaults["page"]["default_content"]

    restore_response = await authenticated_client.patch(
        f"/api/ai/agent-configs/{AGENT_COORDINATOR_AGENT_ID}/code-standards/page",
        json={"restore_default": True},
    )
    assert restore_response.status_code == 200
    restored = {item["standard_type"]: item for item in restore_response.json()}
    assert restored["page"]["customized"] is False
    assert restored["page"]["content"] == restored["page"]["default_content"]


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
