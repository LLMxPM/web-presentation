"""文件功能：提供智能体结构化源码编辑操作、内容指纹与 canonical diff 生成能力。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from difflib import unified_diff
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf

SourceEditType = Literal["replace_exact", "insert_after", "rewrite_file"]


class _SourceEditBase(BaseModel):
    """结构化源码编辑对象基类，禁止模型生成未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class ReplaceExactEdit(_SourceEditBase):
    """精确替换源码中唯一命中的 old_text。"""

    type: Literal["replace_exact"] = Field(description="精确替换唯一命中的 old_text。")
    old_text: str = Field(min_length=1, description="来自读取工具返回的真实源码片段，必须唯一命中。")
    new_text: str = Field(description="替换后的源码片段；允许为空字符串以删除内容。")


class InsertAfterEdit(_SourceEditBase):
    """在源码中唯一命中的 anchor_text 后插入 new_text。"""

    type: Literal["insert_after"] = Field(description="在唯一命中的 anchor_text 后插入内容。")
    anchor_text: str = Field(min_length=1, description="来自读取工具返回的真实源码片段，必须唯一命中。")
    new_text: str = Field(min_length=1, description="要插入的源码片段。")


class RewriteFileEdit(_SourceEditBase):
    """用完整 content 重写整个源码文件。"""

    type: Literal["rewrite_file"] = Field(description="用完整 content 重写整个源码文件。")
    content: str = Field(min_length=1, description="完整的新源码内容。")


SourceEditInput = Annotated[
    ReplaceExactEdit | InsertAfterEdit | RewriteFileEdit,
    Field(discriminator="type"),
]
SourceEditPayload = dict[str, Any] | ReplaceExactEdit | InsertAfterEdit | RewriteFileEdit


@dataclass(slots=True, frozen=True)
class SourceEditApplyResult:
    """描述结构化编辑应用结果。"""

    next_content: str
    canonical_diff: str
    applied_edit_count: int


def calculate_source_hash(source_content: str) -> str:
    """计算源码草稿锁使用的稳定 SHA-256 指纹。"""

    normalized_content = normalize_text_to_lf(source_content or "")
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def apply_source_edits(current_content: str, edits: list[SourceEditPayload]) -> SourceEditApplyResult:
    """按顺序应用结构化 edits，并返回新源码与 canonical diff。"""

    if not isinstance(edits, list) or not edits:
        raise AppException(status_code=400, code="AI_SOURCE_EDITS_EMPTY", detail="edits 不能为空。")

    current_normalized = normalize_text_to_lf(current_content or "")
    next_content = current_normalized
    applied_count = 0
    for index, raw_edit in enumerate(edits, start=1):
        next_content = _apply_single_edit(next_content, _normalize_edit_payload(raw_edit, edit_index=index), edit_index=index)
        applied_count += 1

    return SourceEditApplyResult(
        next_content=next_content,
        canonical_diff=build_source_edits_diff(current_normalized, next_content),
        applied_edit_count=applied_count,
    )


def build_source_edits_diff(current_content: str, next_content: str) -> str:
    """生成结构化编辑应用后的标准展示 diff。"""

    return "".join(
        unified_diff(
            normalize_text_to_lf(current_content or "").splitlines(keepends=True),
            normalize_text_to_lf(next_content or "").splitlines(keepends=True),
            fromfile="current",
            tofile="proposed",
        )
    )


def _normalize_edit_payload(raw_edit: SourceEditPayload, *, edit_index: int) -> dict[str, Any]:
    """把 Pydantic edit 对象或 dict 统一转换为内部处理字典。"""

    if isinstance(raw_edit, BaseModel):
        return raw_edit.model_dump()
    if isinstance(raw_edit, dict):
        return raw_edit
    raise AppException(
        status_code=400,
        code="AI_SOURCE_EDIT_INVALID",
        detail=f"第 {edit_index} 个 edit 必须是对象。",
    )


def _apply_single_edit(source_content: str, raw_edit: dict[str, Any], *, edit_index: int) -> str:
    """应用单个编辑对象，并把定位失败转成结构化错误。"""

    if not isinstance(raw_edit, dict):
        raise AppException(
            status_code=400,
            code="AI_SOURCE_EDIT_INVALID",
            detail=f"第 {edit_index} 个 edit 必须是对象。",
        )

    edit_type = _read_edit_type(raw_edit, edit_index=edit_index)
    if edit_type == "replace_exact":
        old_text = _read_text_field(raw_edit, "old_text", edit_index=edit_index, allow_empty=False)
        new_text = _read_text_field(raw_edit, "new_text", edit_index=edit_index, allow_empty=True)
        return _replace_unique(source_content, old_text, new_text, edit_index=edit_index)
    if edit_type == "insert_after":
        anchor_text = _read_text_field(raw_edit, "anchor_text", edit_index=edit_index, allow_empty=False)
        new_text = _read_text_field(raw_edit, "new_text", edit_index=edit_index, allow_empty=False)
        return _insert_after_unique(source_content, anchor_text, new_text, edit_index=edit_index)
    if edit_type == "rewrite_file":
        return _read_text_field(raw_edit, "content", edit_index=edit_index, allow_empty=False)

    raise AppException(
        status_code=400,
        code="AI_SOURCE_EDIT_INVALID",
        detail=f"第 {edit_index} 个 edit 的 type 不受支持：{edit_type}。",
    )


def _read_edit_type(raw_edit: dict[str, Any], *, edit_index: int) -> str:
    """读取编辑类型，兼容 type/operation/op 三种字段名。"""

    raw_type = raw_edit.get("type", raw_edit.get("operation", raw_edit.get("op")))
    edit_type = str(raw_type or "").strip()
    if not edit_type:
        raise AppException(
            status_code=400,
            code="AI_SOURCE_EDIT_INVALID",
            detail=f"第 {edit_index} 个 edit 缺少 type 字段。",
        )
    return edit_type


def _read_text_field(raw_edit: dict[str, Any], field_name: str, *, edit_index: int, allow_empty: bool) -> str:
    """读取并规范化编辑文本字段。"""

    if field_name not in raw_edit or raw_edit[field_name] is None:
        raise AppException(
            status_code=400,
            code="AI_SOURCE_EDIT_INVALID",
            detail=f"第 {edit_index} 个 edit 缺少 {field_name} 字段。",
        )
    value = normalize_text_to_lf(str(raw_edit[field_name]))
    if not allow_empty and value == "":
        raise AppException(
            status_code=400,
            code="AI_SOURCE_EDIT_INVALID",
            detail=f"第 {edit_index} 个 edit 的 {field_name} 不能为空。",
        )
    return value


def _replace_unique(source_content: str, old_text: str, new_text: str, *, edit_index: int) -> str:
    """仅当 old_text 唯一命中时执行替换。"""

    match_count = source_content.count(old_text)
    if match_count == 0:
        raise AppException(
            status_code=409,
            code="AI_SOURCE_EDIT_NO_MATCH",
            detail=f"第 {edit_index} 个 replace_exact 未找到匹配的 old_text，请重新读取源码或扩大 old_text 上下文。",
        )
    if match_count > 1:
        raise AppException(
            status_code=409,
            code="AI_SOURCE_EDIT_AMBIGUOUS",
            detail=f"第 {edit_index} 个 replace_exact 命中 {match_count} 处，无法安全判断替换位置。",
        )
    return source_content.replace(old_text, new_text, 1)


def _insert_after_unique(source_content: str, anchor_text: str, new_text: str, *, edit_index: int) -> str:
    """仅当 anchor_text 唯一命中时在锚点后插入内容。"""

    match_count = source_content.count(anchor_text)
    if match_count == 0:
        raise AppException(
            status_code=409,
            code="AI_SOURCE_EDIT_NO_MATCH",
            detail=f"第 {edit_index} 个 insert_after 未找到匹配的 anchor_text，请重新读取源码或扩大 anchor_text 上下文。",
        )
    if match_count > 1:
        raise AppException(
            status_code=409,
            code="AI_SOURCE_EDIT_AMBIGUOUS",
            detail=f"第 {edit_index} 个 insert_after 命中 {match_count} 处，无法安全判断插入位置。",
        )
    anchor_index = source_content.index(anchor_text) + len(anchor_text)
    return f"{source_content[:anchor_index]}{new_text}{source_content[anchor_index:]}"
