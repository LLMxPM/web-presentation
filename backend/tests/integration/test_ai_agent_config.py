"""文件功能：验证统一内容助手目录与配置接口的集成契约。"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.ai.tool_specs import AGENT_COORDINATOR_AGENT_ID
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


# 工具目录/运行时工具/操作手册防漂移与统一提示词基线测试已迁至
# `backend/tests/unit/test_unified_tool_specs.py`，保证 PR 默认 `test:backend:unit` 可拦住派生链漂移。
