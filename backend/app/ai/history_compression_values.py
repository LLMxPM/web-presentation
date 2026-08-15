"""文件功能：递归规整压缩输入中的工具参数、结果和长文本值。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import tiktoken

MAX_COMPACTION_LEVEL = 3
TOOL_ARGS_SOFT_LIMIT_TOKENS = 2_048
TOOL_RESULT_SOFT_LIMIT_TOKENS = 4_096
MESSAGE_SOFT_LIMIT_TOKENS = 8_192

ENCODING = tiktoken.get_encoding("cl100k_base")
IMPORTANT_KEY_PATTERN = re.compile(
    r"(?:^|_)(?:id|ids|run_id|workspace_id|project_id|page_id|component_id|asset_id|"
    r"attachment_id|version_id|draft_hash|sha256|tool_call_id|status|code|valid|success|"
    r"retryable|unavailable|message|error|summary|changed|created|updated|deleted)$",
    re.IGNORECASE,
)
LARGE_KEY_PATTERN = re.compile(
    r"(?:source|preview_schema|raw_source|raw_html|raw_css|base64|data_url|signed_url|"
    r"full_content|binary|pixel|embedding)",
    re.IGNORECASE,
)


def compact_value(value: Any, *, level: int, max_tokens: int, key: str | None = None, depth: int = 0) -> Any:
    """递归规整任意工具载荷，保留身份、状态和错误字段。"""

    normalized_level = max(0, min(MAX_COMPACTION_LEVEL, int(level)))
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if key and LARGE_KEY_PATTERN.search(key):
            return {"omitted": True, "field": key, "reason": "large_payload"}
        string_limit = max(64, min(max_tokens, 8_192 if normalized_level < 2 else 2_048))
        return truncate_text(value, string_limit)
    if depth >= 7:
        return {"omitted": True, "reason": "nested_payload"}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key in value:
            field = str(raw_key)
            if normalized_level >= 1 and LARGE_KEY_PATTERN.search(field):
                result[field] = {"omitted": True, "field": field, "reason": "large_payload"}
                continue
            if normalized_level >= 3 and not is_important_key(field):
                continue
            result[field] = compact_value(
                value[raw_key],
                level=normalized_level,
                max_tokens=max_tokens,
                key=field,
                depth=depth + 1,
            )
        return fit_json_value(result, max_tokens=max_tokens)
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        item_limit = 64 if normalized_level == 0 else 32 if normalized_level == 1 else 16 if normalized_level == 2 else 8
        selected = values if len(values) <= item_limit else [*values[: item_limit // 2], *values[-(item_limit // 2) :]]
        compacted = [
            compact_value(item, level=normalized_level, max_tokens=max_tokens, depth=depth + 1)
            for item in selected
        ]
        if len(values) > item_limit:
            compacted.insert(item_limit // 2, {"omitted_count": len(values) - item_limit})
        return fit_json_value(compacted, max_tokens=max_tokens)
    return truncate_text(str(value), max_tokens)


def fit_json_value(value: Any, *, max_tokens: int) -> Any:
    """在递归规整后再次限制单个 JSON 值的 token 大小。"""

    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(ENCODING.encode(serialized)) <= max_tokens:
        return value
    essential = essential_value(value)
    essential_text = json.dumps(essential, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(ENCODING.encode(essential_text)) <= max_tokens:
        return essential
    return {
        "truncated": True,
        "original_tokens": len(ENCODING.encode(serialized)),
        "preview": truncate_text(essential_text, max(64, max_tokens - 32)),
    }


def essential_value(value: Any) -> Any:
    """只保留嵌套值中的身份、状态、错误和摘要字段。"""

    if isinstance(value, Mapping):
        return {
            str(key): essential_value(child)
            for key, child in value.items()
            if is_important_key(str(key))
        }
    if isinstance(value, list):
        return [essential_value(item) for item in value[:8]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def collect_important_scalars(value: Any, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """提取工具载荷中的关键 ID、状态和校验字段。"""

    output = result if result is not None else {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            field = str(key)
            if is_important_key(field) and isinstance(child, (str, int, float, bool)):
                output[field] = child
            else:
                collect_important_scalars(child, result=output)
    elif isinstance(value, list):
        for child in value:
            collect_important_scalars(child, result=output)
    return output


def is_important_key(key: str) -> bool:
    """判断字段是否属于压缩后必须保留的事实字段。"""

    return bool(IMPORTANT_KEY_PATTERN.search(key))


def strip_internal_fields(item: dict[str, Any]) -> dict[str, Any]:
    """移除工具配对阶段使用的内部字段。"""

    return {key: value for key, value in item.items() if not key.startswith("_")}


def contains_truncation(value: Any) -> bool:
    """判断结构化输入是否包含省略或截断标记。"""

    if isinstance(value, Mapping):
        return any(
            key in {"truncated", "omitted", "omitted_count"} or contains_truncation(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_truncation(child) for child in value)
    return False


def truncate_text(value: str, max_tokens: int) -> str:
    """按 token 截断文本并附带明确的省略标记。"""

    tokens = ENCODING.encode(value)
    limit = max(1, int(max_tokens))
    if len(tokens) <= limit:
        return value
    marker = "\n[内容已省略，需按真实 ID 重新查询]"
    marker_tokens = len(ENCODING.encode(marker))
    keep = max(1, limit - marker_tokens)
    head = keep // 2
    tail = keep - head
    return ENCODING.decode(tokens[:head]) + marker + ENCODING.decode(tokens[-tail:])


def truncate_text_by_tokens(value: str, max_tokens: int) -> str:
    """按 token 限制确定性摘要文本长度。"""

    return ENCODING.decode(ENCODING.encode(value)[: max(1, int(max_tokens))])


def render_item_line(item: Mapping[str, Any]) -> str:
    """把结构化事实渲染为不依赖 JSON 完整性的纯文本行。"""

    kind = str(item.get("kind") or "item")
    if kind == "run_context":
        return (
            f"Run {item.get('run_id') or 'unattributed'}：workspace={item.get('workspace_id')}; "
            f"project={item.get('project_id')}; page={item.get('page_id')}; component={item.get('component_id')}"
        )
    if kind == "tool_interaction":
        tool = item.get("tool_name") or "unknown"
        status = item.get("status") or "unknown"
        identifiers = json.dumps(item.get("important_ids") or {}, ensure_ascii=False, default=str)
        return f"工具 {tool}（call_id={item.get('tool_call_id') or 'unknown'}）：status={status}；ids={identifiers}；result={short_text(item.get('result'))}"
    if kind == "orphan_tool_return":
        return f"孤立工具返回 {item.get('tool_name') or 'unknown'}：status=unknown；必须重新查询确认"
    return f"{kind}（run_id={item.get('run_id') or 'unattributed'}）：{short_text(item.get('content'))}"


def short_text(value: Any) -> str:
    """生成适合确定性摘要单行展示的短文本。"""

    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return " ".join(str(text).split())[:1_000]
