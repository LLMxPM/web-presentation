"""文件功能：定义页面可视化编辑公开 API 的操作、artifact 创建与批量保存协议。"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.runtime_module_policy import (
    get_runtime_kit_capability_by_import_path,
    get_runtime_kit_component_capability,
)
from app.schemas.page_visual_edit_manifest import (
    PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
    PageVisualEditDiagnostic,
    PageVisualEditInstanceKey,
    PageVisualEditLiteral,
    PageVisualEditManifest,
    PageVisualEditProtocolVersion,
    PageVisualEditStrictModel,
    VisualEditIdentifier,
    VisualEditModulePath,
    VisualEditSourceHash,
    build_page_visual_edit_source_hash,
)


PAGE_VISUAL_EDIT_MAX_OPERATIONS = 100

PageVisualEditComponentLocalName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Z][A-Za-z0-9]*$",
    ),
]
PageVisualEditComponentPropName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_$][A-Za-z0-9_$-]*$",
    ),
]


class PageVisualEditComponentSelectOption(PageVisualEditStrictModel):
    """描述组件 select 参数的一个有限选项。"""

    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
    ]
    value: str | int | float | bool


class PageVisualEditComponentPropField(PageVisualEditStrictModel):
    """描述 visual edit 属性面板可安全消费的单个 previewSchema prop。"""

    type: Literal["string", "textarea", "number", "boolean", "select", "json"]
    label: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
        ]
        | None
    ) = None
    description: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
        ]
        | None
    ) = None
    required: bool | None = None
    default: JsonValue = None
    placeholder: Annotated[str, StringConstraints(max_length=1_000)] | None = None
    options: list[PageVisualEditComponentSelectOption] | None = Field(
        default=None,
        max_length=1_000,
    )


class PageVisualEditComponentSchema(PageVisualEditStrictModel):
    """绑定页面本地组件标签、真实导入来源和钉住版本的 props UI 元数据。"""

    source: Literal["workspace_component", "runtime_kit"]
    import_path: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
    ]
    component_code: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ]
    version_no: int = Field(gt=0)
    props: (
        dict[PageVisualEditComponentPropName, PageVisualEditComponentPropField] | None
    ) = Field(
        default=None,
        max_length=512,
    )

    @model_validator(mode="after")
    def validate_source_identity(self) -> Self:
        """确保来源身份与版本化导入路径一致，拒绝伪造 artifact 元数据。"""

        if self.source == "workspace_component":
            expected_path = (
                f"@workspace-components/{self.component_code}/v/{self.version_no}"
            )
            if self.import_path not in {expected_path, f"{expected_path}.vue"}:
                raise ValueError("工作空间组件来源身份与 import_path 不一致。")
        else:
            dependency = get_runtime_kit_capability_by_import_path(self.import_path)
            capability = (
                get_runtime_kit_component_capability(dependency.name)
                if dependency is not None
                else None
            )
            if (
                dependency is None
                or capability is None
                or dependency.base_name != self.component_code
                or dependency.version_no != self.version_no
            ):
                raise ValueError("Runtime Kit 组件来源身份与 manifest 不一致。")
        return self


class PageVisualEditInstancePathSegment(PageVisualEditStrictModel):
    """定位一个 v-for 运行实例，公开写协议首期只接受字符串或整数 key。"""

    loop_node_id: VisualEditIdentifier
    key: PageVisualEditInstanceKey | None = None
    index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_locator(self) -> Self:
        """要求每个循环实例段至少提供稳定 key 或数组 index。"""

        if self.key is None and self.index is None:
            raise ValueError("instance_path 每一段至少需要 key 或 index。")
        return self


class PageVisualEditOperationBase(PageVisualEditStrictModel):
    """定义所有页面可视化编辑操作共享的 Manifest 目标。"""

    node_id: VisualEditIdentifier
    binding_id: VisualEditIdentifier
    instance_path: list[PageVisualEditInstancePathSegment] = Field(
        default_factory=list, max_length=8
    )


class PageVisualEditSetValueOperation(PageVisualEditOperationBase):
    """设置静态文本、简单组件参数或静态数组成员的字面量。"""

    type: Literal["set_value"]
    value: PageVisualEditLiteral


class PageVisualEditTailwindTokenChange(PageVisualEditStrictModel):
    """按互斥样式组设置或移除一个受支持的 Tailwind class。"""

    group: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=64,
            pattern=r"^[a-z][a-z0-9_-]*$",
        ),
    ]
    class_name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
        ]
        | None
    ) = None

    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, value: str | None) -> str | None:
        """拒绝包含空白的多 class 输入，确保一次变更只携带一个 token。"""

        if value is not None and any(character.isspace() for character in value):
            raise ValueError("class_name 只能包含一个 Tailwind class。")
        return value


class PageVisualEditSetTailwindTokensOperation(PageVisualEditOperationBase):
    """通过受控样式组批量更新一个 class 绑定。"""

    type: Literal["set_tailwind_tokens"]
    changes: list[PageVisualEditTailwindTokenChange] = Field(
        min_length=1, max_length=50
    )

    @model_validator(mode="after")
    def validate_unique_groups(self) -> Self:
        """禁止同一操作重复设置相同 Tailwind 样式组。"""

        groups = [item.group for item in self.changes]
        if len(groups) != len(set(groups)):
            raise ValueError("同一个 Tailwind 操作中 group 不能重复。")
        return self


PageVisualEditOperation = Annotated[
    PageVisualEditSetValueOperation | PageVisualEditSetTailwindTokensOperation,
    Field(discriminator="type"),
]


def build_page_visual_edit_operation_target_key(
    operation: PageVisualEditOperation,
) -> tuple[object, ...]:
    """生成操作目标稳定比较键，用于拒绝同一批次的重复写入。"""

    instance_key = tuple(
        (item.loop_node_id, item.key, item.index) for item in operation.instance_path
    )
    return operation.node_id, operation.binding_id, instance_key


def validate_page_visual_edit_operation_targets(
    operations: list[PageVisualEditOperation],
) -> None:
    """校验批次中不存在依赖执行顺序的重复实例绑定目标。"""

    target_keys = [
        build_page_visual_edit_operation_target_key(operation)
        for operation in operations
    ]
    if len(target_keys) != len(set(target_keys)):
        raise ValueError("同一批次不能重复修改同一个实例绑定。")


class PageVisualEditPreviewArtifactCreateRequest(PageVisualEditStrictModel):
    """创建页面可视化编辑预览 artifact 的公开接口入参。"""

    protocol_version: PageVisualEditProtocolVersion
    base_version_no: int = Field(gt=0)


class PageVisualEditPreviewEntryDescriptor(PageVisualEditStrictModel):
    """限制可视化编辑 artifact 只能使用页面模块入口。"""

    entry_type: Literal["module"]
    module_path: VisualEditModulePath
    route: None = None


class PageVisualEditPreviewContext(PageVisualEditStrictModel):
    """描述可视化预览 artifact 绑定的页面版本与源码 Manifest。"""

    protocol_version: PageVisualEditProtocolVersion
    page_id: int = Field(gt=0)
    base_version_no: int = Field(gt=0)
    source_hash: VisualEditSourceHash
    module_path: VisualEditModulePath
    manifest: PageVisualEditManifest
    component_schemas: dict[
        PageVisualEditComponentLocalName,
        PageVisualEditComponentSchema,
    ] = Field(max_length=256)
    warnings: list[PageVisualEditDiagnostic] = Field(
        default_factory=list, max_length=1_000
    )

    @model_validator(mode="after")
    def validate_manifest_scope(self) -> Self:
        """确保上下文与 Manifest 指向同一源码，warnings 是诊断中的 warning 子集。"""

        if self.manifest.protocol_version != self.protocol_version:
            raise ValueError("Manifest 协议版本与编辑上下文不一致。")
        if self.manifest.source_hash != self.source_hash:
            raise ValueError("Manifest source_hash 与编辑上下文不一致。")
        if self.manifest.module_path != self.module_path:
            raise ValueError("Manifest module_path 与编辑上下文不一致。")
        expected_warnings = [
            item for item in self.manifest.diagnostics if item.severity == "warning"
        ]
        if self.warnings != expected_warnings:
            raise ValueError("warnings 必须由 Manifest diagnostics 中的 warning 派生。")
        return self


class PageVisualEditArtifactBinding(PageVisualEditStrictModel):
    """描述 Redis artifact 内由 Backend 签发的页面编辑基线。"""

    protocol_version: PageVisualEditProtocolVersion
    page_id: int = Field(gt=0)
    page_version_id: int = Field(gt=0)
    base_version_no: int = Field(gt=0)
    source_hash: VisualEditSourceHash
    module_path: VisualEditModulePath
    manifest: PageVisualEditManifest
    component_schemas: dict[
        PageVisualEditComponentLocalName,
        PageVisualEditComponentSchema,
    ] = Field(max_length=256)
    warnings: list[PageVisualEditDiagnostic] = Field(
        default_factory=list, max_length=1_000
    )

    @model_validator(mode="after")
    def validate_manifest_scope(self) -> Self:
        """确保 artifact 绑定与 canonical Manifest 指向同一份规范源码。"""

        if self.manifest.protocol_version != self.protocol_version:
            raise ValueError("Artifact Manifest 协议版本不一致。")
        if self.manifest.source_hash != self.source_hash:
            raise ValueError("Artifact Manifest source_hash 不一致。")
        if self.manifest.module_path != self.module_path:
            raise ValueError("Artifact Manifest module_path 不一致。")
        expected_warnings = [
            item for item in self.manifest.diagnostics if item.severity == "warning"
        ]
        if self.warnings != expected_warnings:
            raise ValueError(
                "Artifact warnings 必须由 Manifest warning diagnostics 派生。"
            )
        return self


class PageVisualEditPreviewArtifactResponse(PageVisualEditStrictModel):
    """创建页面可视化编辑预览 artifact 的公开接口响应。"""

    preview_url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_096)
    ]
    artifact_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    preview_kind: Literal["page"]
    entry_descriptor: PageVisualEditPreviewEntryDescriptor
    viewport_width: int = Field(ge=1, le=8_192)
    viewport_height: int = Field(ge=1, le=8_192)
    project_id: int = Field(gt=0)
    workspace_id: int = Field(gt=0)
    visual_edit: PageVisualEditPreviewContext


class PageVisualEditApplyRequest(PageVisualEditStrictModel):
    """批量应用页面可视化编辑操作的公开接口入参。"""

    protocol_version: PageVisualEditProtocolVersion
    artifact_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    base_version_no: int = Field(gt=0)
    source_hash: VisualEditSourceHash
    operations: list[PageVisualEditOperation] = Field(
        min_length=1, max_length=PAGE_VISUAL_EDIT_MAX_OPERATIONS
    )
    change_note: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_unique_targets(self) -> Self:
        """禁止一个批次对同一实例绑定重复写入。"""

        validate_page_visual_edit_operation_targets(self.operations)
        return self


class PageVisualEditApplyDiagnostic(PageVisualEditStrictModel):
    """描述 AST 改写或候选源码检查返回的公开保存诊断。"""

    severity: Literal["error", "warning", "info"]
    source: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]
    code: VisualEditIdentifier
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
    ]
    node_id: VisualEditIdentifier | None = None
    binding_id: VisualEditIdentifier | None = None


class PageVisualEditApplyResponse(PageVisualEditStrictModel):
    """页面可视化编辑成功保存后的公开接口响应。"""

    protocol_version: PageVisualEditProtocolVersion
    success: Literal[True] = True
    page_id: int = Field(gt=0)
    previous_version_no: int = Field(gt=0)
    current_version_no: int = Field(gt=0)
    source_hash: VisualEditSourceHash
    operations_applied: int = Field(ge=1, le=PAGE_VISUAL_EDIT_MAX_OPERATIONS)
    canonical_diff: str
    diagnostics: list[PageVisualEditApplyDiagnostic] = Field(
        default_factory=list, max_length=1_000
    )
    refresh_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_version_advance(self) -> Self:
        """要求成功响应严格生成下一个连续页面版本。"""

        if self.current_version_no != self.previous_version_no + 1:
            raise ValueError("可视化编辑成功后必须生成一个连续新版本。")
        return self


__all__ = [
    "PAGE_VISUAL_EDIT_MAX_OPERATIONS",
    "PAGE_VISUAL_EDIT_PROTOCOL_VERSION",
    "PageVisualEditApplyDiagnostic",
    "PageVisualEditApplyRequest",
    "PageVisualEditApplyResponse",
    "PageVisualEditArtifactBinding",
    "PageVisualEditComponentPropField",
    "PageVisualEditComponentSchema",
    "PageVisualEditComponentSelectOption",
    "PageVisualEditInstancePathSegment",
    "PageVisualEditOperation",
    "PageVisualEditPreviewArtifactCreateRequest",
    "PageVisualEditPreviewArtifactResponse",
    "PageVisualEditPreviewContext",
    "PageVisualEditSetTailwindTokensOperation",
    "PageVisualEditSetValueOperation",
    "PageVisualEditTailwindTokenChange",
    "build_page_visual_edit_source_hash",
    "validate_page_visual_edit_operation_targets",
]
