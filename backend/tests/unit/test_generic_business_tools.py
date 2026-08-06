"""文件功能：验证内容助手固定通用工具、操作手册与条件归档确认行为。"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from pydantic_ai import ApprovalRequired

import app.ai.tools.generic.business_tools as generic_tools_module
from app.ai.platform_tools import AgentToolContext
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    get_operation_guide_spec,
    list_operation_guide_options,
    list_agent_tool_specs,
    list_operation_guide_specs,
)
from app.ai.tools.generic.business_tools import ThemeCreatePayload, ThemeUpdatePayload, build_generic_business_tools
from app.ai.tools.self_delegation import build_self_delegation_tools
from app.core.exceptions import AppException


EXPECTED_GENERIC_TOOL_KEYS = {
    "get_operation_guide",
    "list_entities",
    "get_entity",
    "create_entity",
    "update_entity",
    "archive_entity",
    "execute_action",
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

    create_guide = get_operation_guide_spec("theme.create")
    update_guide = get_operation_guide_spec("theme.update.metadata")
    assert create_guide is not None and update_guide is not None
    serialized = str(create_guide.parameters) + str(update_guide.parameters)
    assert "logo" not in serialized
    assert "font" not in serialized
    assert create_guide.parameters["properties"]["payload"]["additionalProperties"] is False
    payload = create_guide.to_payload()
    assert payload["handler_tool_key"] == "create_entity"
    assert payload["mutation_kind"] == "theme"
    assert payload["response_example"]["success"] is True


def test_operation_guides_should_expose_action_index_and_precise_schemas() -> None:
    """多 action 操作应支持先发现后精确查询，且 payload 与 filters 不再接受任意字段。"""

    options = list_operation_guide_options()
    project_query_options = [item for item in options if str(item["operation_key"]).startswith("project.query.")]
    execute_options = [item for item in options if str(item["operation_key"]).startswith("page.action.")]

    assert {item["operation_key"] for item in project_query_options} == {
        "project.query.list", "project.query.detail", "project.query.route_tree", "project.query.style_config",
    }
    assert {item["operation_key"] for item in execute_options} == {"page.action.check", "page.action.copy"}
    assert len({guide.operation_key for guide in list_operation_guide_specs()}) == len(list_operation_guide_specs())
    assert not any("restore" in guide.operation_key for guide in list_operation_guide_specs())

    for guide in list_operation_guide_specs():
        properties = guide.parameters["properties"]
        Draft202012Validator.check_schema(guide.parameters)
        assert guide.parameters["additionalProperties"] is False
        assert all(property_schema.get("description") for property_schema in properties.values())
        nested = properties.get("payload") or properties.get("filters")
        if nested is not None:
            assert nested.get("additionalProperties") is False
        for definition in guide.parameters.get("$defs", {}).values():
            assert all(
                property_schema.get("description") or property_schema.get("$ref")
                for property_schema in definition.get("properties", {}).values()
            )
        if guide.call_example is not None:
            Draft202012Validator(guide.parameters).validate(guide.call_example)


def test_project_configuration_guides_should_replace_dangerous_actions() -> None:
    """项目配置与路由应统一由 update 承载，主题 key 不提供修改入口。"""

    routes = get_operation_guide_spec("project.update.route_tree")
    configuration = get_operation_guide_spec("project.update.configuration")
    apply_style = get_operation_guide_spec("project.update.apply_style")

    assert routes is not None and configuration is not None and apply_style is not None
    assert set(routes.parameters["properties"]["payload"]["properties"]) == {"routes", "change_note"}
    assert "全量覆盖" in "".join(routes.constraints)
    assert set(configuration.parameters["properties"]["payload"]["properties"]) == {"presentation", "suggested_components"}
    assert set(apply_style.parameters["properties"]["payload"]["properties"]) == {"source_style_id"}
    assert not any("rename_key" in guide.operation_key for guide in list_operation_guide_specs())


def test_generic_tools_should_expose_discriminated_top_level_schemas() -> None:
    """常驻 Schema 应只披露合法顶层组合，复杂业务字段继续按手册查询。"""

    tools = {item.name: item for item in build_generic_business_tools(None)}  # type: ignore[arg-type]

    guide_schema = tools["get_operation_guide"].parameters
    operation_key_variants = guide_schema["properties"]["operation_key"]["anyOf"]
    assert operation_key_variants[0]["enum"]
    assert "page.update.content" in operation_key_variants[0]["enum"]

    for tool_name in ("list_entities", "get_entity", "create_entity", "update_entity", "archive_entity", "execute_action"):
        schema = tools[tool_name].parameters
        Draft202012Validator.check_schema(schema)
        assert schema["oneOf"]
        assert all(branch["additionalProperties"] is False for branch in schema["oneOf"])

    for guide in list_operation_guide_specs():
        if guide.call_example is not None:
            Draft202012Validator(tools[guide.handler_tool_key].parameters).validate(guide.call_example)

    execute_pairs = {
        (branch["properties"]["resource_type"]["const"], branch["properties"]["action"]["const"])
        for branch in tools["execute_action"].parameters["oneOf"]
    }
    assert ("page", "check") in execute_pairs
    assert ("component", "publish") in execute_pairs
    assert not any(action == "restore" for _, action in execute_pairs)
    update_pairs = {
        (branch["properties"]["resource_type"]["const"], branch["properties"]["action"]["const"])
        for branch in tools["update_entity"].parameters["oneOf"]
    }
    assert {action for resource_type, action in update_pairs if resource_type == "project"} == {
        "metadata", "configuration", "apply_style", "route_tree", "build_assets",
    }
    assert ("style", "configuration") in update_pairs
    execute_validator = Draft202012Validator(tools["execute_action"].parameters)
    assert not execute_validator.is_valid({
        "resource_type": "page",
        "action": "publish",
        "target_id": 8,
        "payload": {},
    })
    archive_properties = tools["archive_entity"].parameters["oneOf"][0]["properties"]
    assert "versions" not in archive_properties


def test_read_tools_should_separate_collection_and_single_entity_parameters() -> None:
    """集合查询与单项读取工具不得继续混用 action、target_id 和分页筛选。"""

    tools = {item.name: item for item in build_generic_business_tools(None)}  # type: ignore[arg-type]
    list_branches = tools["list_entities"].parameters["oneOf"]
    get_branches = tools["get_entity"].parameters["oneOf"]
    list_properties = {name for branch in list_branches for name in branch["properties"]}
    get_properties = {name for branch in get_branches for name in branch["properties"]}

    assert list_properties == {"resource_type", "filters", "collection"}
    assert get_properties == {"resource_type", "view", "target_id", "lookup", "options"}
    assert "action" not in list_properties | get_properties
    assert "target_id" not in list_properties
    assert "filters" not in get_properties
    asset_tags = next(
        branch for branch in list_branches
        if branch["properties"]["resource_type"]["const"] == "asset"
        and branch["properties"]["collection"]["const"] == "tags"
    )
    assert set(asset_tags["properties"]) == {"resource_type", "collection"}
    page_detail = next(
        branch for branch in get_branches
        if branch["properties"]["resource_type"]["const"] == "page"
        and branch["properties"]["view"]["const"] == "detail"
    )
    assert set(page_detail["properties"]) == {"resource_type", "view", "target_id"}
    runtime_detail = next(
        branch for branch in get_branches
        if branch["properties"]["resource_type"]["const"] == "runtime_kit"
    )
    assert "lookup" in runtime_detail["properties"]
    assert "target_id" not in runtime_detail["properties"]


async def test_action_payload_validation_should_return_recoverable_business_error() -> None:
    """动作 payload 不符合精确手册时应返回可恢复业务错误，而不是泄漏 Pydantic 异常。"""

    execute_action = {item.name: item for item in build_generic_business_tools(None)}["execute_action"]  # type: ignore[arg-type]

    with pytest.raises(AppException) as error:
        await execute_action.entrypoint(
            AgentToolContext(run_id="run-1", session_id="session-1", dependencies={}),
            resource_type="page",
            action="copy",
            target_id=31,
            payload={"project_id": 9},
        )

    assert error.value.code == "AI_OPERATION_ARGUMENTS_INVALID"
    assert "target_project_id" in error.value.detail


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
        await archive_tool.entrypoint(plain_context, "asset", [3, 3, 4], "整理")
    assert captured == []

    approved_context = AgentToolContext(
        run_id="run-1",
        session_id="session-1",
        dependencies={"current_tool_call_approved": True},
    )
    result = await archive_tool.entrypoint(approved_context, "asset", [3, 3, 4], "整理")

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
