"""文件功能：定义与 Runtime `protocol.ts` 对齐的页面可视化编辑 Manifest v1 共享模型。"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.schemas.page_visual_edit_json import validate_page_visual_edit_json


PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1
PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH = 5_000_000
PAGE_VISUAL_EDIT_MAX_INSTRUMENTED_SOURCE_LENGTH = 7_500_000
PAGE_VISUAL_EDIT_MAX_MANIFEST_NODES = 5_000
PAGE_VISUAL_EDIT_MAX_MANIFEST_BINDINGS = 10_000

PageVisualEditProtocolVersion: TypeAlias = Literal[1]
PageVisualEditLiteral: TypeAlias = str | int | float | bool | None
PageVisualEditInstanceKey: TypeAlias = str | int
PageVisualEditReadonlyReason: TypeAlias = Literal[
    "SFC_PARSE_ERROR",
    "TEMPLATE_UNSUPPORTED",
    "DYNAMIC_EXPRESSION",
    "DYNAMIC_SCRIPT_SOURCE",
    "SCRIPT_SOURCE_NOT_FOUND",
    "LOOP_SOURCE_UNSUPPORTED",
    "NESTED_LOOP_UNSUPPORTED",
    "LOOP_MEMBER_UNSUPPORTED",
    "MEMBER_NOT_FOUND",
    "MEMBER_VALUE_DYNAMIC",
    "ATTRIBUTE_VALUE_MISSING",
    "RICH_TEXT_DYNAMIC_CONTENT",
    "RICH_TEXT_UNSUPPORTED_STRUCTURE",
    "STRUCTURE_ROOT_UNSUPPORTED",
    "STRUCTURE_CONTROL_FLOW_UNSUPPORTED",
    "STRUCTURE_LOOP_INSTANCE_REQUIRED",
]
PageVisualEditBindingKind: TypeAlias = Literal[
    "text", "rich_text", "class", "prop", "json"
]
PageVisualEditValueType: TypeAlias = Literal[
    "string", "number", "boolean", "null", "json", "unknown"
]
PageVisualEditNodeKind: TypeAlias = Literal["root", "element", "component"]
PageVisualEditScriptCollectionKind: TypeAlias = Literal[
    "const-array", "ref-array", "reactive-array"
]

VisualEditIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]
VisualEditMemberName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_$][A-Za-z0-9_$]*$",
    ),
]
VisualEditSourceHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VisualEditModulePath = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=15, max_length=512)
]
VisualEditSource = Annotated[
    str,
    StringConstraints(min_length=1, max_length=PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH),
]
VisualEditInstrumentedSource = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=PAGE_VISUAL_EDIT_MAX_INSTRUMENTED_SOURCE_LENGTH,
    ),
]


class PageVisualEditStrictModel(BaseModel):
    """为协议模型提供禁止额外字段、严格类型和 camelCase 入参兼容。"""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        validate_by_name=True,
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=lambda field_name: field_name,
        ),
    )


class PageVisualEditSourceRange(PageVisualEditStrictModel):
    """描述节点或绑定在 Vue SFC 中的 UTF-16 半开偏移区间。"""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """确保结束偏移严格位于开始偏移之后。"""

        if self.end < self.start:
            raise ValueError("源码区间 end 必须大于或等于 start。")
        return self


class PageVisualEditScriptMemberLocation(PageVisualEditStrictModel):
    """描述 script setup 数组中单个成员的静态写入位置。"""

    index: int = Field(ge=0)
    key: PageVisualEditInstanceKey | None = None
    value: PageVisualEditLiteral = None
    source_range: PageVisualEditSourceRange | None = None
    editable: bool
    readonly_reason: PageVisualEditReadonlyReason | None = None


class PageVisualEditScriptArrayBindingSource(PageVisualEditStrictModel):
    """描述模板成员绑定与 const/ref/reactive 数组字面量的静态关系。"""

    kind: Literal["script-array-item"]
    collection_name: VisualEditMemberName
    collection_kind: PageVisualEditScriptCollectionKind
    item_alias: VisualEditMemberName
    member: VisualEditMemberName
    key_member: VisualEditMemberName | None = None
    locations: list[PageVisualEditScriptMemberLocation] = Field(
        default_factory=list, max_length=10_000
    )


class PageVisualEditTemplateBindingSource(PageVisualEditStrictModel):
    """标识绑定值直接来自 Vue template 字面量。"""

    kind: Literal["template-literal"]


class PageVisualEditTemplateRichTextBindingSource(PageVisualEditStrictModel):
    """标识绑定覆盖模板元素内部的受限富文本片段。"""

    kind: Literal["template-rich-text"]


class PageVisualEditJsonBindingSource(PageVisualEditStrictModel):
    """标识 binding 引用 Manifest 中去重的整块 JSON 源。"""

    kind: Literal["json-source"]
    source_id: VisualEditIdentifier


PageVisualEditBindingSource = Annotated[
    PageVisualEditScriptArrayBindingSource
    | PageVisualEditTemplateBindingSource
    | PageVisualEditTemplateRichTextBindingSource
    | PageVisualEditJsonBindingSource,
    Field(discriminator="kind"),
]


class PageVisualEditBinding(PageVisualEditStrictModel):
    """描述模板中一个可展示在属性面板的文本、class 或 prop 绑定。"""

    binding_id: VisualEditIdentifier
    node_id: VisualEditIdentifier
    kind: PageVisualEditBindingKind
    name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
        ]
        | None
    ) = None
    value_type: PageVisualEditValueType
    value: JsonValue = None
    expression: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
        ]
        | None
    ) = None
    source_range: PageVisualEditSourceRange
    editable: bool
    readonly_reason: PageVisualEditReadonlyReason | None = None
    source: PageVisualEditBindingSource | None = None


class PageVisualEditLoopContext(PageVisualEditStrictModel):
    """描述模板节点上的单层 v-for 静态语义。"""

    loop_node_id: VisualEditIdentifier
    source_expression: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
    ]
    source_binding: VisualEditMemberName | None = None
    item_alias: VisualEditMemberName
    index_alias: VisualEditMemberName | None = None
    key_expression: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
        ]
        | None
    ) = None
    key_member: VisualEditMemberName | None = None
    editable: bool
    readonly_reason: PageVisualEditReadonlyReason | None = None


class PageVisualEditLoopItemLocation(PageVisualEditStrictModel):
    """描述可由稳定 key 定位的循环数组项。"""

    index: int = Field(ge=0)
    key: PageVisualEditInstanceKey


class PageVisualEditTemplateActions(PageVisualEditStrictModel):
    """描述节点模板级复制、删除能力。"""

    can_duplicate: bool
    can_delete: bool
    readonly_reason: PageVisualEditReadonlyReason | None = None


class PageVisualEditLoopItemActions(PageVisualEditStrictModel):
    """描述节点所在循环的数据项级复制、删除能力。"""

    can_duplicate: bool
    can_delete: bool
    loop_node_id: VisualEditIdentifier
    collection_name: VisualEditMemberName
    key_member: VisualEditMemberName
    instances: list[PageVisualEditLoopItemLocation] = Field(max_length=10_000)
    readonly_reason: PageVisualEditReadonlyReason | None = None


class PageVisualEditNode(PageVisualEditStrictModel):
    """描述保留 Vue 模板容器和组件语义的节点树。"""

    node_id: VisualEditIdentifier
    kind: PageVisualEditNodeKind
    tag: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    source_range: PageVisualEditSourceRange
    loop_context: PageVisualEditLoopContext | None = None
    template_actions: PageVisualEditTemplateActions
    loop_item_actions: PageVisualEditLoopItemActions | None = None
    bindings: list[PageVisualEditBinding] = Field(default_factory=list, max_length=256)
    children: list[PageVisualEditNode] = Field(default_factory=list, max_length=1_000)

    @model_validator(mode="after")
    def validate_local_bindings(self) -> Self:
        """确保节点内部绑定归属正确且 binding_id 不重复。"""

        binding_ids: set[str] = set()
        for binding in self.bindings:
            if binding.node_id != self.node_id:
                raise ValueError("绑定 node_id 必须与所属节点一致。")
            if binding.binding_id in binding_ids:
                raise ValueError(f"节点内 binding_id 重复：{binding.binding_id}。")
            binding_ids.add(binding.binding_id)
        if (
            self.loop_context is not None
            and self.loop_context.loop_node_id != self.node_id
        ):
            raise ValueError("loop_context.loop_node_id 必须与所属节点一致。")
        return self


class PageVisualEditDiagnostic(PageVisualEditStrictModel):
    """描述 SFC 分析产生的稳定错误或只读警告。"""

    severity: Literal["warning", "error"]
    code: PageVisualEditReadonlyReason
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
    ]
    source_range: PageVisualEditSourceRange | None = None


class PageVisualEditTailwindOption(PageVisualEditStrictModel):
    """描述可视化样式面板允许选择的单个 Tailwind class。"""

    class_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]


class PageVisualEditTailwindGroup(PageVisualEditStrictModel):
    """描述一个互斥 Tailwind 样式组及其可视化选项。"""

    key: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=64,
            pattern=r"^[a-z][a-z0-9_-]*$",
        ),
    ]
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    options: list[PageVisualEditTailwindOption] = Field(
        default_factory=list, max_length=1_000
    )

    @model_validator(mode="after")
    def validate_unique_options(self) -> Self:
        """确保同一组内 className 唯一，避免 UI 选择产生歧义。"""

        class_names = [item.class_name for item in self.options]
        if len(class_names) != len(set(class_names)):
            raise ValueError("Tailwind group 内 class_name 不能重复。")
        return self


class PageVisualEditTailwindCatalog(PageVisualEditStrictModel):
    """描述 Runtime 提供的版本化 Tailwind 可视化编辑白名单。"""

    version: Literal[1]
    groups: list[PageVisualEditTailwindGroup] = Field(
        default_factory=list, max_length=256
    )

    @model_validator(mode="after")
    def validate_unique_groups(self) -> Self:
        """确保 Catalog 样式组 key 全局唯一。"""

        group_keys = [item.key for item in self.groups]
        if len(group_keys) != len(set(group_keys)):
            raise ValueError("Tailwind Catalog group key 不能重复。")
        return self


class PageVisualEditManifest(PageVisualEditStrictModel):
    """与 Runtime VisualEditSfcManifest 完全对齐的单页源码分析结果。"""

    protocol_version: PageVisualEditProtocolVersion
    module_path: VisualEditModulePath
    source_hash: VisualEditSourceHash
    root: PageVisualEditNode
    diagnostics: list[PageVisualEditDiagnostic] = Field(
        default_factory=list, max_length=1_000
    )
    tailwind_catalog: PageVisualEditTailwindCatalog
    json_sources: list["PageVisualEditJsonSource"] = Field(max_length=10_000)

    @field_validator("module_path")
    @classmethod
    def validate_module_path(cls, value: str) -> str:
        """限制可视化编辑入口为规范页面 Vue 模块路径。"""

        if (
            "\\" in value
            or ".." in value
            or not value.startswith("src/views/")
            or not value.endswith(".vue")
        ):
            raise ValueError("module_path 必须是 src/views/*.vue 规范路径。")
        return value

    @model_validator(mode="after")
    def validate_tree_identity(self) -> Self:
        """限制整棵树规模，并保证 node_id 与 binding_id 全局唯一。"""

        node_ids: set[str] = set()
        binding_ids: set[str] = set()
        referenced_json_source_ids: set[str] = set()
        pending = [self.root]
        node_count = 0
        binding_count = 0
        while pending:
            node = pending.pop()
            node_count += 1
            if node_count > PAGE_VISUAL_EDIT_MAX_MANIFEST_NODES:
                raise ValueError("可视化编辑 Manifest 节点数量超过限制。")
            if node.node_id in node_ids:
                raise ValueError(f"Manifest node_id 重复：{node.node_id}。")
            node_ids.add(node.node_id)
            for binding in node.bindings:
                binding_count += 1
                if binding_count > PAGE_VISUAL_EDIT_MAX_MANIFEST_BINDINGS:
                    raise ValueError("可视化编辑 Manifest 绑定数量超过限制。")
                if binding.binding_id in binding_ids:
                    raise ValueError(
                        f"Manifest binding_id 重复：{binding.binding_id}。"
                    )
                binding_ids.add(binding.binding_id)
                if isinstance(binding.source, PageVisualEditJsonBindingSource):
                    referenced_json_source_ids.add(binding.source.source_id)
            pending.extend(node.children)
        source_ids = [item.source_id for item in self.json_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Manifest JSON source_id 不能重复。")
        missing_source_ids = referenced_json_source_ids.difference(source_ids)
        if missing_source_ids:
            raise ValueError("JSON binding 引用了不存在的 source_id。")
        return self


class PageVisualEditJsonSource(PageVisualEditStrictModel):
    """描述可由 set_json 原子替换的静态 JSON 字面量。"""

    source_id: VisualEditIdentifier
    kind: Literal["const", "ref", "reactive", "template-expression"]
    name: VisualEditMemberName | None = None
    value: JsonValue
    source_range: PageVisualEditSourceRange
    editable: Literal[True]

    @field_validator("value")
    @classmethod
    def validate_json_value(cls, value: JsonValue) -> JsonValue:
        """限制 Manifest JSON 值的递归规模。"""

        return validate_page_visual_edit_json(value)


def build_page_visual_edit_source_hash(source: str) -> str:
    """按 UTF-8 字节计算 Runtime canonical 的 64 位小写 SHA-256 源码 hash。"""

    return hashlib.sha256(source.encode("utf-8")).hexdigest()
