"""文件功能：验证页面可视化编辑协议 v1 的严格结构、定位约束与源码 hash。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.page_visual_edit import (
    PageVisualEditApplyRequest,
    PageVisualEditApplyResponse,
    PageVisualEditInstancePathSegment,
    PageVisualEditPreviewArtifactCreateRequest,
    PageVisualEditPreviewContext,
    PageVisualEditSetRichTextOperation,
    PageVisualEditSetJsonOperation,
    PageVisualEditSetTailwindTokensOperation,
    PageVisualEditSetValueOperation,
    PageVisualEditTailwindTokenChange,
)
from app.schemas.page_visual_edit_manifest import (
    PAGE_VISUAL_EDIT_MAX_INSTRUMENTED_SOURCE_LENGTH,
    PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH,
    PageVisualEditBinding,
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
    build_page_visual_edit_source_hash,
)
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditAnalyzeResponse,
    RuntimePageVisualEditApplyResponse,
)


def _build_binding(
    *, binding_id: str = "binding_title", node_id: str = "node_title"
) -> PageVisualEditBinding:
    """构造一个可编辑静态文本绑定。"""

    return PageVisualEditBinding(
        binding_id=binding_id,
        node_id=node_id,
        kind="text",
        value_type="string",
        value="原标题",
        source_range=PageVisualEditSourceRange(start=16, end=19),
        editable=True,
    )


def _build_manifest(
    source: str = "<template><main>原标题</main></template>",
) -> PageVisualEditManifest:
    """构造最小合法页面可视化编辑 Manifest。"""

    child = PageVisualEditNode(
        node_id="node_title",
        kind="element",
        tag="main",
        source_range=PageVisualEditSourceRange(start=10, end=32),
        template_actions={"can_duplicate": True, "can_delete": True},
        bindings=[_build_binding()],
    )
    return PageVisualEditManifest(
        protocol_version=1,
        source_hash=build_page_visual_edit_source_hash(source),
        module_path="src/views/PGdemo.vue",
        root=PageVisualEditNode(
            node_id="root",
            kind="root",
            tag="#document",
            source_range=PageVisualEditSourceRange(start=0, end=len(source)),
            template_actions={
                "can_duplicate": False,
                "can_delete": False,
                "readonly_reason": "STRUCTURE_ROOT_UNSUPPORTED",
            },
            children=[child],
        ),
        json_sources=[],
        tailwind_catalog={"version": 1, "groups": []},
    )


def test_protocol_models_should_reject_unknown_fields_and_versions() -> None:
    """公开请求必须显式使用协议 v1，且不得携带未声明字段。"""

    with pytest.raises(ValidationError):
        PageVisualEditPreviewArtifactCreateRequest.model_validate(
            {"protocol_version": 2, "base_version_no": 1}
        )
    with pytest.raises(ValidationError):
        PageVisualEditPreviewArtifactCreateRequest.model_validate(
            {"protocol_version": 1, "base_version_no": 1, "unexpected": True}
        )


def test_runtime_camel_case_should_validate_but_public_dump_stays_snake_case() -> None:
    """Runtime camelCase 入参应被接受，公开序列化仍保持 Backend snake_case 约定。"""

    segment = PageVisualEditInstancePathSegment.model_validate(
        {"loopNodeId": "loop_items", "key": "item-b", "index": 1}
    )

    assert segment.loop_node_id == "loop_items"
    assert segment.model_dump(by_alias=True) == {
        "loop_node_id": "loop_items",
        "key": "item-b",
        "index": 1,
    }


def test_runtime_manifest_canonical_payload_should_validate_without_field_drift() -> (
    None
):
    """Runtime protocol.ts 的节点、循环、数据源和 diagnostics 实际形态应可直接校验。"""

    source_hash = build_page_visual_edit_source_hash("<template><li /></template>")
    manifest = PageVisualEditManifest.model_validate(
        {
            "protocolVersion": 1,
            "modulePath": "src/views/PGdemo.vue",
            "sourceHash": source_hash,
            "root": {
                "nodeId": "node_root",
                "kind": "root",
                "tag": "#document",
                "sourceRange": {"start": 0, "end": 27},
                "templateActions": {
                    "canDuplicate": False,
                    "canDelete": False,
                    "readonlyReason": "STRUCTURE_ROOT_UNSUPPORTED",
                },
                "bindings": [],
                "children": [
                    {
                        "nodeId": "node_item",
                        "kind": "element",
                        "tag": "li",
                        "sourceRange": {"start": 10, "end": 16},
                        "templateActions": {"canDuplicate": False, "canDelete": True},
                        "loopItemActions": {
                            "canDuplicate": True,
                            "canDelete": True,
                            "loopNodeId": "node_item",
                            "collectionName": "items",
                            "keyMember": "id",
                            "instances": [{"index": 1, "key": "b"}],
                        },
                        "loopContext": {
                            "loopNodeId": "node_item",
                            "sourceExpression": "items",
                            "sourceBinding": "items",
                            "itemAlias": "item",
                            "indexAlias": "index",
                            "keyExpression": "item.id",
                            "keyMember": "id",
                            "editable": True,
                        },
                        "bindings": [
                            {
                                "bindingId": "binding_title",
                                "nodeId": "node_item",
                                "kind": "text",
                                "valueType": "string",
                                "value": "标题 B",
                                "expression": "item.title",
                                "sourceRange": {"start": 12, "end": 15},
                                "editable": True,
                                "source": {
                                    "kind": "script-array-item",
                                    "collectionName": "items",
                                    "collectionKind": "const-array",
                                    "itemAlias": "item",
                                    "member": "title",
                                    "keyMember": "id",
                                    "locations": [
                                        {
                                            "index": 1,
                                            "key": "b",
                                            "value": "标题 B",
                                            "sourceRange": {"start": 80, "end": 86},
                                            "editable": True,
                                        }
                                    ],
                                },
                            }
                        ],
                        "children": [],
                    }
                ],
            },
            "diagnostics": [
                {
                    "severity": "warning",
                    "code": "NESTED_LOOP_UNSUPPORTED",
                    "message": "嵌套循环首版只读。",
                }
            ],
            "tailwindCatalog": {
                "version": 1,
                "groups": [
                    {
                        "key": "padding",
                        "label": "内边距",
                        "options": [{"className": "p-4", "label": "中"}],
                    }
                ],
            },
            "jsonSources": [],
        }
    )

    binding_source = manifest.root.children[0].bindings[0].source
    assert binding_source is not None
    assert binding_source.kind == "script-array-item"
    assert binding_source.collection_kind == "const-array"
    assert manifest.diagnostics[0].code == "NESTED_LOOP_UNSUPPORTED"
    assert manifest.tailwind_catalog.groups[0].options[0].class_name == "p-4"


def test_component_schema_should_keep_strict_props_ui_metadata_and_pinned_identity() -> (
    None
):
    """组件映射应保留 select/number/boolean 控件，并严格绑定本地名和导入版本。"""

    manifest = _build_manifest()
    context = PageVisualEditPreviewContext(
        protocol_version=1,
        page_id=12,
        base_version_no=3,
        source_hash=manifest.source_hash,
        module_path=manifest.module_path,
        manifest=manifest,
        component_schemas={
            "PinnedCard": {
                "source": "workspace_component",
                "import_path": "@workspace-components/CMP001/v/2",
                "component_code": "CMP001",
                "version_no": 2,
                "props": {
                    "variant": {
                        "type": "select",
                        "options": [{"label": "强调", "value": "strong"}],
                        "default": "strong",
                    },
                    "count": {"type": "number", "default": 3},
                    "enabled": {"type": "boolean", "default": True},
                },
            }
        },
        warnings=[],
    )

    component_schema = context.component_schemas["PinnedCard"]
    assert component_schema.version_no == 2
    assert component_schema.props is not None
    assert component_schema.props["variant"].options[0].value == "strong"
    assert component_schema.props["count"].default == 3
    assert component_schema.props["enabled"].default is True

    with pytest.raises(ValidationError, match="来源身份"):
        component_schema.model_validate(
            {
                "source": "workspace_component",
                "import_path": "@workspace-components/CMP001/v/3",
                "component_code": "CMP001",
                "version_no": 2,
                "props": None,
            }
        )


@pytest.mark.parametrize("key", [True, None])
def test_instance_key_should_reject_bool_or_missing_locator(key: object) -> None:
    """循环实例 key 不接受 bool/null，且缺少 index 时不能形成有效定位。"""

    with pytest.raises(ValidationError):
        PageVisualEditInstancePathSegment.model_validate(
            {"loop_node_id": "loop_items", "key": key}
        )


def test_readonly_reason_should_follow_runtime_canonical_enum() -> None:
    """只读原因必须属于 Runtime canonical 协议声明的稳定枚举。"""

    with pytest.raises(ValidationError):
        PageVisualEditBinding(
            binding_id="binding_dynamic",
            node_id="node_title",
            kind="text",
            value_type="unknown",
            source_range=PageVisualEditSourceRange(start=1, end=2),
            editable=False,
            readonly_reason="UNKNOWN_REASON",
        )


def test_manifest_should_reject_duplicate_binding_identity() -> None:
    """Manifest 全局 binding_id 重复时应拒绝，避免运行实例反向定位歧义。"""

    source = "<template><main>标题</main></template>"
    first = PageVisualEditNode(
        node_id="node_a",
        kind="element",
        tag="section",
        source_range=PageVisualEditSourceRange(start=1, end=2),
        template_actions={"can_duplicate": True, "can_delete": True},
        bindings=[_build_binding(binding_id="same_binding", node_id="node_a")],
    )
    second = PageVisualEditNode(
        node_id="node_b",
        kind="element",
        tag="section",
        source_range=PageVisualEditSourceRange(start=2, end=3),
        template_actions={"can_duplicate": True, "can_delete": True},
        bindings=[_build_binding(binding_id="same_binding", node_id="node_b")],
    )

    with pytest.raises(ValidationError, match="binding_id 重复"):
        PageVisualEditManifest(
            protocol_version=1,
            source_hash=build_page_visual_edit_source_hash(source),
            module_path="src/views/PGdemo.vue",
            root=PageVisualEditNode(
                node_id="root",
                kind="root",
                tag="#document",
                source_range=PageVisualEditSourceRange(start=0, end=len(source)),
                template_actions={
                    "can_duplicate": False,
                    "can_delete": False,
                    "readonly_reason": "STRUCTURE_ROOT_UNSUPPORTED",
                },
                children=[first, second],
            ),
            json_sources=[],
            tailwind_catalog={"version": 1, "groups": []},
        )


def test_tailwind_operation_should_reject_duplicate_groups_and_multiple_classes() -> (
    None
):
    """Tailwind 操作必须按唯一组提交单个受控 class。"""

    with pytest.raises(ValidationError):
        PageVisualEditTailwindTokenChange(group="padding", class_name="p-4 p-6")
    with pytest.raises(ValidationError, match="group 不能重复"):
        PageVisualEditSetTailwindTokensOperation(
            type="set_tailwind_tokens",
            node_id="node_card",
            binding_id="binding_class",
            changes=[
                PageVisualEditTailwindTokenChange(group="padding", class_name="p-4"),
                PageVisualEditTailwindTokenChange(group="padding", class_name="p-6"),
            ],
        )


def test_rich_text_operation_should_enforce_semantic_html_boundary() -> None:
    """富文本允许由 Runtime 锁定的复杂标签，并拒绝坏语法、Vue 文本表达式与超长内容。"""

    operation = PageVisualEditSetRichTextOperation(
        type="set_rich_text",
        node_id="node_paragraph",
        binding_id="binding_rich",
        html='正文<br><span class="text-red-500"><strong class="font-bold">重点</strong></span><em>补充</em>',
    )
    assert operation.html.endswith("</em>")

    complex_operation = PageVisualEditSetRichTextOperation(
        type="set_rich_text",
        node_id="node_paragraph",
        binding_id="binding_rich",
        html='<a href="/docs" :class="tone"><Badge style="color:red">链接文本</Badge></a>',
    )
    assert complex_operation.html.startswith("<a ")

    for invalid_html in [
        "<strong>未闭合",
        "{{ user.name }}",
        "<!-- comment -->",
        "x" * 20_001,
    ]:
        with pytest.raises(ValidationError):
            PageVisualEditSetRichTextOperation(
                type="set_rich_text",
                node_id="node_paragraph",
                binding_id="binding_rich",
                html=invalid_html,
            )


def test_rich_text_binding_should_allow_empty_insertion_range() -> None:
    """空文本容器需要以 start=end 的插入点参与富文本编辑。"""

    binding = PageVisualEditBinding.model_validate(
        {
            "bindingId": "binding_rich",
            "nodeId": "node_paragraph",
            "kind": "rich_text",
            "valueType": "string",
            "value": "",
            "sourceRange": {"start": 20, "end": 20},
            "editable": True,
            "source": {"kind": "template-rich-text"},
        }
    )
    assert binding.source_range.start == binding.source_range.end


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_literal_number_should_reject_non_finite_values(value: float) -> None:
    """数值字面量必须是有限数，避免 NaN/Infinity 绕过 JSON 与 AST 语义。"""

    with pytest.raises(ValidationError):
        PageVisualEditSetValueOperation(
            type="set_value",
            node_id="node_count",
            binding_id="binding_count",
            value=value,
        )


def test_apply_request_should_reject_duplicate_instance_targets() -> None:
    """同一批次不能依赖操作顺序重复覆盖同一个循环实例绑定。"""

    operation = PageVisualEditSetValueOperation(
        type="set_value",
        node_id="node_title",
        binding_id="binding_title",
        instance_path=[
            PageVisualEditInstancePathSegment(
                loop_node_id="loop_items", key="b", index=1
            )
        ],
        value="新标题",
    )

    with pytest.raises(ValidationError, match="不能重复修改"):
        PageVisualEditApplyRequest(
            protocol_version=1,
            artifact_id="rt_demo",
            base_version_no=1,
            source_hash=build_page_visual_edit_source_hash("source"),
            operations=[operation, operation],
        )


def test_internal_request_and_response_should_verify_source_hashes() -> None:
    """Backend 与 Runtime 交互时必须能独立复算输入和候选源码 hash。"""

    source = "<template><main>旧标题</main></template>"
    with pytest.raises(ValidationError, match="source_hash"):
        RuntimePageVisualEditAnalyzeRequest(
            protocol_version=1,
            source_hash=build_page_visual_edit_source_hash("other"),
            module_path="src/views/PGdemo.vue",
            source=source,
        )
    with pytest.raises(ValidationError, match="next_source_hash"):
        RuntimePageVisualEditApplyResponse(
            protocol_version=1,
            base_source_hash=build_page_visual_edit_source_hash(source),
            next_source_hash=build_page_visual_edit_source_hash("other"),
            next_source=source,
            operations_applied=1,
            canonical_diff="diff",
        )


def test_instrumented_source_should_have_separate_controlled_size_budget() -> None:
    """插桩源码可超过 canonical 上限，但仍必须受独立派生源码大小约束。"""

    instrumented_source = "x" * (PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH + 1)
    response = RuntimePageVisualEditAnalyzeResponse(
        protocol_version=1,
        manifest=_build_manifest(),
        instrumented_source=instrumented_source,
    )
    assert len(response.instrumented_source) == PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH + 1

    with pytest.raises(ValidationError):
        RuntimePageVisualEditAnalyzeResponse(
            protocol_version=1,
            manifest=_build_manifest(),
            instrumented_source="x"
            * (PAGE_VISUAL_EDIT_MAX_INSTRUMENTED_SOURCE_LENGTH + 1),
        )


def test_apply_response_should_require_one_continuous_new_version() -> None:
    """成功保存响应只能表示从基础版本连续前进一个版本。"""

    with pytest.raises(ValidationError, match="连续新版本"):
        PageVisualEditApplyResponse(
            protocol_version=1,
            page_id=1,
            previous_version_no=2,
            current_version_no=4,
            source_hash=build_page_visual_edit_source_hash("source"),
            operations_applied=1,
            canonical_diff="diff",
        )


def test_manifest_helper_should_build_valid_protocol_v1_tree() -> None:
    """最小 Manifest 应包含稳定源码 hash、模块路径和语义树。"""

    manifest = _build_manifest()

    assert manifest.protocol_version == 1
    assert manifest.root.children[0].bindings[0].binding_id == "binding_title"
    assert len(manifest.source_hash) == 64

    payload = manifest.model_dump()
    payload.pop("json_sources")
    with pytest.raises(ValidationError, match="jsonSources|json_sources"):
        PageVisualEditManifest.model_validate(payload)


def test_set_json_should_accept_nested_json_and_reject_depth_overflow() -> None:
    """整块 JSON 操作应接受结构化值，并在 Backend 拒绝超深输入。"""

    operation = PageVisualEditSetJsonOperation(
        type="set_json",
        source_id="source_benefits",
        value=["第一项", {"label": "第二项", "enabled": True}],
    )
    assert operation.value[1]["label"] == "第二项"

    value: object = "leaf"
    for _ in range(33):
        value = [value]
    with pytest.raises(ValidationError, match="嵌套深度"):
        PageVisualEditSetJsonOperation(
            type="set_json",
            source_id="source_benefits",
            value=value,
        )
