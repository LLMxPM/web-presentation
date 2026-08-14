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
from app.ai.tools.generic.operation_models import (
    AssetCreatePayload,
    AssetMetadataPayload,
    ComponentCreatePayload,
    PageCopyPayload,
    PageCreatePayload,
    PageMetadataPayload,
    ProjectApplyStylePayload,
    ProjectCreatePayload,
)
from app.ai.tools.self_delegation import build_self_delegation_tools
from app.core.exceptions import AppException


EXPECTED_GENERIC_TOOL_KEYS = {
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


def test_operation_guides_should_not_define_delete_or_workspace_archive() -> None:
    """逻辑操作手册不得开放永久删除或工作空间归档。"""

    guides = list_operation_guide_specs()

    assert guides
    assert not any("delete" in (guide.action or "") or "purge" in (guide.action or "") for guide in guides)
    assert not any(guide.resource_type == "workspace" and guide.operation == "archive" for guide in guides)
    assert {guide.resource_type for guide in guides if guide.operation == "archive"} == {
        "project", "page", "component", "asset", "theme", "style",
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
    assert all(guide.mutation_kind == guide.resource_type for guide in guides if guide.operation not in {"query", "validate"})
    assert all(guide.mutation_kind is None for guide in guides if guide.operation in {"query", "validate"})

    create_guide = get_operation_guide_spec("theme.create.new")
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
    validate_options = [item for item in options if str(item["operation_key"]).startswith("page.validate.")]

    assert {item["operation_key"] for item in project_query_options} == {
        "project.query.list", "project.query.detail", "project.query.route_tree", "project.query.configuration",
    }
    assert {item["operation_key"] for item in validate_options} == {"page.validate.check"}
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


def test_asset_create_guide_should_expose_executable_content_contract() -> None:
    """资源创建手册应披露类型映射、内容限制、恢复方式和可直接调用的示例。"""

    guide = get_operation_guide_spec("asset.create.new")

    assert guide is not None
    payload_schema = guide.parameters["properties"]["payload"]
    properties = payload_schema["properties"]
    serialized_constraints = "".join(guide.constraints)
    assert "不存在独立的 svg 类型" in properties["asset_type"]["description"]
    assert set(properties["asset_type"]["enum"]) == {"icon", "image", "drawio", "mermaid", "chart", "formula"}
    assert ".drawio/.xml" in properties["original_name"]["description"]
    assert "512 KiB" in properties["content"]["description"]
    assert "currentColor" in serialized_constraints
    assert "顶层为对象" in serialized_constraints
    assert guide.prerequisites
    assert guide.side_effects
    assert len(guide.error_recovery) >= 3
    assert guide.call_example is not None
    assert guide.call_example["payload"]["asset_type"] == "icon"
    assert guide.response_example["data"]["asset"]["name"] == "trend-up"
    assert guide.response_example["mutation"]["target"]["id"] == 91
    Draft202012Validator(guide.parameters).validate(guide.call_example)


def test_asset_create_payload_should_allow_svg_image_resource() -> None:
    """统一资源创建参数应允许创建 SVG 图片，但不扩展为位图生成。"""

    payload = AssetCreatePayload.model_validate(
        {
            "asset_type": "image",
            "name": "business-illustration",
            "original_name": "business-illustration.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect width="16" height="9" fill="currentColor"/></svg>',
        }
    )

    assert payload.asset_type == "image"


def test_component_create_guide_should_require_and_explain_preview_schema() -> None:
    """组件创建手册必须披露 preview_schema 结构、必填约束和可执行示例。"""

    guide = get_operation_guide_spec("component.create.new")

    assert guide is not None
    payload_schema = guide.parameters["properties"]["payload"]
    assert "preview_schema" in payload_schema["required"]
    description = payload_schema["properties"]["preview_schema"]["description"]
    serialized_constraints = "".join(guide.constraints)
    assert "不是组件 props 的实际预览值" in serialized_constraints
    assert "preview_schema.props" in serialized_constraints
    assert "尺寸控制字段" in description
    assert guide.call_example is not None
    preview_schema = guide.call_example["payload"]["preview_schema"]
    assert set(preview_schema["props"]) >= {"title", "width", "height"}
    assert len(guide.error_recovery) >= 2
    Draft202012Validator(guide.parameters).validate(guide.call_example)

    summary_example = guide.response_example["data"]["component"]
    assert "content" not in summary_example
    assert "preview_schema" not in summary_example
    assert summary_example["draft_hash"]
    assert any("不回显" in side_effect for side_effect in guide.side_effects)

    with pytest.raises(ValidationError):
        ComponentCreatePayload.model_validate({
            "name": "缺少预览 Schema",
            "import_name": "MissingPreviewSchema",
            "content": "<template><div /></template>",
        })


def test_runtime_theme_guidance_should_cover_source_and_mutation_boundaries() -> None:
    """页面、组件、主题和 Runtime Kit 手册应覆盖主题类与源码边界。"""

    page_create = get_operation_guide_spec("page.create.new")
    page_update = get_operation_guide_spec("page.update.content")
    page_validate = get_operation_guide_spec("page.validate.check")
    component_create = get_operation_guide_spec("component.create.new")
    component_update = get_operation_guide_spec("component.update.content")
    component_validate = get_operation_guide_spec("component.validate.check")
    theme_create = get_operation_guide_spec("theme.create.new")
    theme_update = get_operation_guide_spec("theme.update.metadata")
    runtime_list = get_operation_guide_spec("runtime_kit.query.list")
    runtime_detail = get_operation_guide_spec("runtime_kit.query.detail")

    assert all(
        guide is not None
        for guide in (
            page_create,
            page_update,
            page_validate,
            component_create,
            component_update,
            component_validate,
            theme_create,
            theme_update,
            runtime_list,
            runtime_detail,
        )
    )

    page_create_text = "".join(page_create.prerequisites + page_create.constraints)  # type: ignore[union-attr]
    page_update_text = "".join(page_update.prerequisites + page_update.constraints)  # type: ignore[union-attr]
    component_text = "".join(component_create.constraints + component_update.constraints)  # type: ignore[union-attr]
    validation_text = "".join(page_validate.constraints + component_validate.constraints)  # type: ignore[union-attr]
    theme_text = "".join(theme_create.constraints + theme_update.constraints)  # type: ignore[union-attr]
    runtime_text = "".join(runtime_list.constraints + runtime_detail.constraints)  # type: ignore[union-attr]

    assert "读取项目 configuration" in page_create_text
    assert "Runtime 主题语义类" in page_create_text
    assert "text-${tone}" in page_create_text
    assert "Runtime 主题语义类" in page_update_text
    assert "跨项目和主题复用" in component_text
    assert "完整静态字符串" in component_text
    assert "未列出的主题 Token" in validation_text
    assert "模型调用前应依据 Runtime 主题契约自行复核" in validation_text
    assert "不会单独报告未列出的主题 Token" in validation_text
    assert "Editor" not in page_create_text + page_update_text + component_text + validation_text + theme_text + runtime_text
    assert "动态 Tailwind 类拼接" in validation_text
    assert "palette 只接受当前主题 Schema" in theme_text
    assert "Tailwind 类名" in theme_text
    assert "Runtime Tailwind 主题类属于 Runtime" in runtime_text
    assert "不通过 import 暴露" in runtime_text


def test_project_configuration_guides_should_replace_dangerous_actions() -> None:
    """项目配置与路由应统一由 update 承载，主题 key 不提供修改入口。"""

    routes = get_operation_guide_spec("project.update.route_tree")
    configuration = get_operation_guide_spec("project.update.configuration")
    apply_style = get_operation_guide_spec("project.update.apply_style")

    assert routes is not None and configuration is not None and apply_style is not None
    assert set(routes.parameters["properties"]["payload"]["properties"]) == {"routes", "change_note"}
    assert "全量覆盖" in "".join(routes.constraints)
    assert set(configuration.parameters["properties"]["payload"]["properties"]) == {"presentation", "suggested_components"}
    assert set(apply_style.parameters["properties"]["payload"]["properties"]) == {"style_id"}
    assert not any("rename_key" in guide.operation_key for guide in list_operation_guide_specs())


def test_generic_tools_should_expose_discriminated_top_level_schemas() -> None:
    """常驻 Schema 应只披露合法顶层组合，复杂业务字段继续按手册查询。"""

    tools = {item.name: item for item in build_generic_business_tools(None)}  # type: ignore[arg-type]

    guide_schema = tools["get_operation_guide"].parameters
    operation_key_variants = guide_schema["properties"]["operation_key"]["anyOf"]
    assert operation_key_variants[0]["enum"]
    assert "page.update.content" in operation_key_variants[0]["enum"]

    for tool_name in ("list_entities", "get_entity", "create_entity", "update_entity", "archive_entity", "validate_entity", "execute_action"):
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
    assert execute_pairs == {("component", "publish")}
    validate_pairs = {
        (branch["properties"]["resource_type"]["const"], branch["properties"]["action"]["const"])
        for branch in tools["validate_entity"].parameters["oneOf"]
    }
    assert validate_pairs == {("page", "check"), ("component", "check"), ("asset", "preview")}
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
    assert {
        branch["properties"]["resource_type"]["const"]
        for branch in tools["archive_entity"].parameters["oneOf"]
    } == {"project", "page", "component", "asset", "theme", "style"}

    create_pairs = {
        (branch["properties"]["resource_type"]["const"], branch["properties"]["mode"]["const"])
        for branch in tools["create_entity"].parameters["oneOf"]
    }
    assert create_pairs == {
        ("project", "new"), ("page", "new"), ("page", "copy"), ("component", "new"),
        ("asset", "new"), ("asset", "copy"), ("asset", "upload"),
        ("theme", "new"), ("theme", "copy"), ("style", "new"), ("style", "copy"),
    }


def test_update_and_route_payloads_should_reject_noop_or_conflicting_fields() -> None:
    """更新补丁和页面路由条件字段应在同源模型层直接拒绝非法组合。"""

    with pytest.raises(ValidationError):
        PageMetadataPayload.model_validate({})
    with pytest.raises(ValidationError):
        PageMetadataPayload.model_validate({"change_note": "仅备注"})
    with pytest.raises(ValidationError):
        AssetMetadataPayload.model_validate({"approx_aspect_ratio": "16:9", "clear_approx_aspect_ratio": True})
    with pytest.raises(ValidationError):
        PageCopyPayload.model_validate({"source_id": 1, "project_id": 2, "route_placement": "group"})
    with pytest.raises(ValidationError):
        PageCopyPayload.model_validate({"source_id": 1, "project_id": 2, "parent_route_id": 3})


def test_ai_create_fields_should_hide_storage_or_legacy_names() -> None:
    """创建与样式应用参数只接受统一后的模型可见名称。"""

    page = PageCreatePayload.model_validate({"project_id": 1, "title": "封面", "content": "<template />"})
    project = ProjectCreatePayload.model_validate({"name": "报告", "build_assets": {"asset_names": ["hero"]}})
    assert page.content == "<template />"
    assert project.build_assets is not None and project.build_assets.asset_names == ["hero"]
    assert ProjectApplyStylePayload.model_validate({"style_id": 2}).style_id == 2
    with pytest.raises(ValidationError):
        PageCreatePayload.model_validate({"project_id": 1, "title": "封面", "page_content": "<template />"})
    with pytest.raises(ValidationError):
        ProjectApplyStylePayload.model_validate({"source_style_id": 2})


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


async def test_removed_action_should_return_unsupported_business_error() -> None:
    """复制已迁入创建工具，旧生命周期调用必须被明确拒绝。"""

    execute_action = {item.name: item for item in build_generic_business_tools(None)}["execute_action"]  # type: ignore[arg-type]

    with pytest.raises(AppException) as error:
        await execute_action.entrypoint(
            AgentToolContext(run_id="run-1", session_id="session-1", dependencies={}),
            resource_type="page",
            action="copy",
            target_id=31,
            payload={"project_id": 9},
        )

    assert error.value.code == "AI_OPERATION_UNSUPPORTED"


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
