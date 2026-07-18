"""文件功能：定义 Backend 调用 Runtime 可视化编辑 AST 分析与改写端点的内部协议外壳。"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.schemas.page_visual_edit import (
    PAGE_VISUAL_EDIT_MAX_OPERATIONS,
    PageVisualEditOperation,
    validate_page_visual_edit_operation_targets,
)
from app.schemas.page_visual_edit_manifest import (
    PageVisualEditDiagnostic,
    PageVisualEditManifest,
    PageVisualEditProtocolVersion,
    PageVisualEditStrictModel,
    VisualEditInstrumentedSource,
    VisualEditModulePath,
    VisualEditSource,
    VisualEditSourceHash,
    build_page_visual_edit_source_hash,
)


class RuntimePageVisualEditAnalyzeRequest(PageVisualEditStrictModel):
    """Backend 调用 Runtime SFC 分析端点的内部请求。"""

    protocol_version: PageVisualEditProtocolVersion
    source_hash: VisualEditSourceHash
    module_path: VisualEditModulePath
    source: VisualEditSource

    @model_validator(mode="after")
    def validate_source_hash(self) -> Self:
        """确保内部请求 hash 与实际传递的规范源码一致。"""

        if build_page_visual_edit_source_hash(self.source) != self.source_hash:
            raise ValueError("source_hash 与 source 内容不一致。")
        return self


class RuntimePageVisualEditAnalyzeResponse(PageVisualEditStrictModel):
    """Runtime SFC 分析端点返回的 canonical Manifest 与可选插桩源码。"""

    protocol_version: PageVisualEditProtocolVersion
    manifest: PageVisualEditManifest
    instrumented_source: VisualEditInstrumentedSource

    @model_validator(mode="after")
    def validate_protocol(self) -> Self:
        """确保内部响应外壳与 Manifest 使用相同协议版本。"""

        if self.manifest.protocol_version != self.protocol_version:
            raise ValueError("Runtime Manifest 协议版本不一致。")
        return self


class RuntimePageVisualEditApplyRequest(PageVisualEditStrictModel):
    """Backend 调用 Runtime AST 改写端点的内部请求。"""

    protocol_version: PageVisualEditProtocolVersion
    source_hash: VisualEditSourceHash
    module_path: VisualEditModulePath
    source: VisualEditSource
    operations: list[PageVisualEditOperation] = Field(
        min_length=1, max_length=PAGE_VISUAL_EDIT_MAX_OPERATIONS
    )

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """校验规范源码 hash，并拒绝内部请求中的重复操作目标。"""

        if build_page_visual_edit_source_hash(self.source) != self.source_hash:
            raise ValueError("source_hash 与 source 内容不一致。")
        validate_page_visual_edit_operation_targets(self.operations)
        return self


class RuntimePageVisualEditApplyResponse(PageVisualEditStrictModel):
    """Runtime AST 改写端点返回的候选源码、差异与 canonical 诊断。"""

    protocol_version: PageVisualEditProtocolVersion
    base_source_hash: VisualEditSourceHash
    next_source_hash: VisualEditSourceHash
    next_source: VisualEditSource
    operations_applied: int = Field(ge=1, le=PAGE_VISUAL_EDIT_MAX_OPERATIONS)
    canonical_diff: str
    diagnostics: list[PageVisualEditDiagnostic] = Field(
        default_factory=list, max_length=1_000
    )

    @model_validator(mode="after")
    def validate_next_source_hash(self) -> Self:
        """确保 Runtime 返回候选源码的 hash 可由 Backend 独立复算。"""

        if (
            build_page_visual_edit_source_hash(self.next_source)
            != self.next_source_hash
        ):
            raise ValueError("next_source_hash 与 next_source 内容不一致。")
        return self
