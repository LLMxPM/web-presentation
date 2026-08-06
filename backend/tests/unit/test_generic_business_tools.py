"""文件功能：验证内容助手固定通用工具、操作手册与条件归档确认行为。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai import ApprovalRequired

import app.ai.tools.generic.business_tools as generic_tools_module
from app.ai.platform_tools import AgentToolContext
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    get_operation_guide_spec,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.ai.tools.generic.business_tools import ThemeCreatePayload, ThemeUpdatePayload, build_generic_business_tools
from app.ai.tools.self_delegation import build_self_delegation_tools


EXPECTED_GENERIC_TOOL_KEYS = {
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


def test_coordinator_should_only_expose_fixed_generic_and_special_tools() -> None:
    """内容助手目录不得继续暴露旧细粒度工具或删除工具。"""

    tool_keys = {item.key for item in list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID)}

    assert tool_keys == EXPECTED_GENERIC_TOOL_KEYS
    assert not any("delete" in tool_key or "purge" in tool_key for tool_key in tool_keys)


async def test_self_delegation_should_inject_unified_agent_without_member_parameter() -> None:
    """自委派工具不接收成员 ID，并固定创建同一内容助手身份的子运行。"""

    class FakeExecutor:
        async def delegate_task_to_self(self, **kwargs):  # noqa: ANN003, ANN202
            return kwargs

    tool = build_self_delegation_tools(None)[0]  # type: ignore[arg-type]
    context = AgentToolContext(
        run_id="run-1",
        session_id="session-1",
        dependencies={"member_delegation_executor": FakeExecutor(), "current_tool_call_id": "call-1"},
    )

    result = await tool.entrypoint(context, task="核对组件引用", handoff_context=None, expected_output="返回影响列表")

    assert result["member_id"] == AGENT_COORDINATOR_AGENT_ID
    assert result["delegate_tool_name"] == "delegate_task_to_self"
    assert "member_id" not in tool.parameters["properties"]


def test_operation_guides_should_not_define_delete_or_project_archive() -> None:
    """逻辑操作手册不得通过 action 绕过删除与项目归档边界。"""

    guides = list_operation_guide_specs()

    assert guides
    assert not any("delete" in (guide.action or "") or "purge" in (guide.action or "") for guide in guides)
    assert not any(guide.resource_type in {"project", "workspace"} and guide.operation == "archive" for guide in guides)
    assert {guide.resource_type for guide in guides if guide.operation == "archive"} == {
        "page", "component", "asset", "theme", "style",
    }


def test_theme_payload_should_reject_logo_and_font_fields() -> None:
    """主题通用写入 Schema 只接受文本与色板字段。"""

    with pytest.raises(ValidationError):
        ThemeUpdatePayload.model_validate({"name": "新主题", "logo_asset_id": 9})
    with pytest.raises(ValidationError):
        ThemeCreatePayload.model_validate({
            "key": "demo",
            "name": "演示",
            "heading_font_family_id": 2,
            "palette": _palette(),
        })


def test_operation_guides_should_bind_handlers_and_expose_strict_theme_schema() -> None:
    """操作手册需关联真实处理器和刷新类型，主题 Schema 不得出现品牌资源或字体字段。"""

    guides = list_operation_guide_specs()
    runtime_keys = {item.key for item in list_agent_tool_specs(AGENT_COORDINATOR_AGENT_ID)}
    assert all(guide.handler_tool_key in runtime_keys for guide in guides)
    assert all(guide.mutation_kind == guide.resource_type for guide in guides if guide.operation != "query")

    create_guide = get_operation_guide_spec("theme", "create")
    update_guide = get_operation_guide_spec("theme", "update")
    assert create_guide is not None and update_guide is not None
    serialized = str(create_guide.parameters) + str(update_guide.parameters)
    assert "logo" not in serialized
    assert "font" not in serialized
    assert create_guide.parameters["properties"]["payload"]["additionalProperties"] is False
    payload = create_guide.to_payload()
    assert payload["handler_tool_key"] == "create_entity"
    assert payload["mutation_kind"] == "theme"
    assert payload["response_example"]["success"] is True


async def test_batch_archive_should_require_approval_and_preserve_deduplicated_targets(monkeypatch) -> None:
    """批量归档先暂停确认，恢复后沿用同一调用并只传递去重目标。"""

    captured: list[list[int]] = []

    async def fake_archive(_session_factory, _run_context, arguments):
        captured.append(arguments.target_ids)
        return {"success": True, "target_ids": arguments.target_ids}

    async def fake_confirmation(_session_factory, _run_context, arguments):
        return {
            "resource_type": arguments.resource_type,
            "target_count": len(arguments.target_ids),
            "targets": [{"id": item} for item in arguments.target_ids],
            "reference_impact": "测试引用影响",
        }

    monkeypatch.setattr(generic_tools_module, "archive_entities", fake_archive)
    monkeypatch.setattr(generic_tools_module, "build_archive_confirmation", fake_confirmation)
    tools = {item.name: item for item in build_generic_business_tools(None)}  # type: ignore[arg-type]
    archive_tool = tools["archive_entity"]
    plain_context = AgentToolContext(run_id="run-1", session_id="session-1", dependencies={})

    with pytest.raises(ApprovalRequired):
        await archive_tool.entrypoint(plain_context, "asset", [3, 3, 4], "整理", None)
    assert captured == []

    approved_context = AgentToolContext(
        run_id="run-1",
        session_id="session-1",
        dependencies={"current_tool_call_approved": True},
    )
    result = await archive_tool.entrypoint(approved_context, "asset", [3, 3, 4], "整理", None)

    assert result["success"] is True
    assert captured == [[3, 4]]


async def test_single_archive_should_not_require_approval(monkeypatch) -> None:
    """单项归档无需批准即可进入原子归档处理器。"""

    async def fake_archive(_session_factory, _run_context, arguments):
        return {"success": True, "target_ids": arguments.target_ids}

    monkeypatch.setattr(generic_tools_module, "archive_entities", fake_archive)
    tools = {item.name: item for item in build_generic_business_tools(None)}  # type: ignore[arg-type]
    result = await tools["archive_entity"].entrypoint(
        AgentToolContext(run_id="run-1", session_id="session-1", dependencies={}),
        "page",
        [8],
        None,
        None,
    )

    assert result == {"success": True, "target_ids": [8]}


def _palette() -> dict[str, object]:
    """返回主题 Schema 测试使用的最小合法色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#222222", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#cccccc", "subtle": "#eeeeee"},
        "link": {"default": "#0000ff", "hover": "#0000cc", "visited": "#660099"},
        "accent": ["#3366ff"],
    }
