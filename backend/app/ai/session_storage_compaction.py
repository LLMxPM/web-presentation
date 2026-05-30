"""文件功能：压缩 Agno 运行事件的持久化 payload，避免大媒体和工具结果重复写入数据库。"""

from __future__ import annotations

import json
from typing import Any

_MAX_STORED_EVENT_JSON_CHARS = 256_000
_MAX_STORED_EVENT_FIELD_CHARS = 64_000
_MAX_STORED_TOOL_ARGS_CHARS = 64_000
_MAX_STORED_TOOL_RESULT_CHARS = 64_000
_MAX_COMPACTED_PREVIEW_CHARS = 8_000
_MAX_MEDIA_RETAINED_FIELD_CHARS = 2_048
_COMPACTED_MEDIA_CONTENT = "storage-compacted"
_EVENT_MEDIA_FIELDS = ("image", "images", "videos", "audio", "response_audio")
_MEDIA_RETAIN_KEYS = (
    "id",
    "url",
    "filepath",
    "mime_type",
    "detail",
    "sample_rate",
    "channels",
    "format",
    "filename",
)
_EVENT_RETAIN_LARGE_FIELD_KEYS = {
    "event",
    "run_id",
    "session_id",
    "agent_id",
    "agent_name",
    "team_id",
    "team_name",
    "parent_run_id",
    "member_agent_id",
    "member_agent_name",
    "member_run_id",
    "tool",
    "content",
    "reasoning_content",
    "created_at",
    "nested_depth",
}


def compact_agno_event_payload_for_storage(event: Any) -> dict[str, Any] | None:
    """读取并压缩 Agno 事件 payload；无法读取 payload 时返回 None。"""

    payload = _payload_from_storage_object(event)
    if not isinstance(payload, dict):
        return None
    return _compact_event_payload_for_storage(payload)


def _payload_from_storage_object(value: Any) -> Any:
    """读取对象的可 JSON 化 payload；优先使用 Agno 自身的 to_dict 语义。"""

    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:  # noqa: BLE001
            return None
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="python", exclude_none=True)
        except TypeError:
            return value.model_dump()
    return None


def _compact_event_payload_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """裁剪事件 payload 中不适合重复保存的大字段，同时保留回放排序和工具展示信息。"""

    data = dict(payload)
    for field_name in _EVENT_MEDIA_FIELDS:
        if field_name in data and data[field_name] is not None:
            data[field_name] = _compact_media_value(data[field_name])
    if isinstance(data.get("tool"), dict):
        data["tool"] = _compact_tool_payload(data["tool"])
    if "content" in data:
        data["content"] = _compact_json_value(data["content"], _MAX_STORED_EVENT_FIELD_CHARS)
    if "reasoning_content" in data:
        data["reasoning_content"] = _compact_json_value(data["reasoning_content"], _MAX_STORED_EVENT_FIELD_CHARS)
    return _compact_oversized_event_fields(data)


def _compact_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """裁剪工具参数和结果，避免页面源码、截图等大对象随事件重复写入。"""

    data = dict(payload)
    if "tool_args" in data:
        data["tool_args"] = _compact_json_value(data["tool_args"], _MAX_STORED_TOOL_ARGS_CHARS)
    if "result" in data:
        data["result"] = _compact_json_value(data["result"], _MAX_STORED_TOOL_RESULT_CHARS)
    return data


def _compact_media_value(value: Any) -> Any:
    """把图片、音视频内容替换为轻量引用，保留 id/mime 等可诊断信息。"""

    if isinstance(value, list):
        return [_compact_media_item(item) for item in value]
    return _compact_media_item(value)


def _compact_media_item(item: Any) -> Any:
    """裁剪单个媒体对象；没有外部引用时写入短占位内容以通过 Agno 校验。"""

    payload = _payload_from_storage_object(item)
    if not isinstance(payload, dict):
        return {"content": _COMPACTED_MEDIA_CONTENT}
    compacted = {
        key: payload[key]
        for key in _MEDIA_RETAIN_KEYS
        if payload.get(key) is not None and _is_small_media_field_value(payload[key])
    }
    if not any(compacted.get(key) for key in ("url", "filepath", "content")):
        compacted["content"] = _COMPACTED_MEDIA_CONTENT
    return compacted


def _is_small_media_field_value(value: Any) -> bool:
    """只保留短媒体元数据，过滤 data URL 等大字段伪装成引用的情况。"""

    if isinstance(value, str):
        return len(value) <= _MAX_MEDIA_RETAINED_FIELD_CHARS
    return _json_payload_size(value) <= _MAX_MEDIA_RETAINED_FIELD_CHARS


def _compact_oversized_event_fields(data: dict[str, Any]) -> dict[str, Any]:
    """事件整体仍超阈值时，对非核心字段继续做预览化压缩。"""

    if _json_payload_size(data) <= _MAX_STORED_EVENT_JSON_CHARS:
        return data
    compacted = dict(data)
    for key, value in list(compacted.items()):
        if key in _EVENT_RETAIN_LARGE_FIELD_KEYS:
            continue
        if _json_payload_size(value) > _MAX_STORED_EVENT_FIELD_CHARS:
            compacted[key] = _compact_json_value(value, _MAX_STORED_EVENT_FIELD_CHARS)
    if _json_payload_size(compacted) <= _MAX_STORED_EVENT_JSON_CHARS:
        return compacted
    for key, value in list(compacted.items()):
        if key in {"event", "run_id", "session_id", "tool", "content", "reasoning_content"}:
            continue
        if _json_payload_size(value) > _MAX_COMPACTED_PREVIEW_CHARS:
            compacted[key] = _compact_json_value(value, _MAX_COMPACTED_PREVIEW_CHARS)
    return compacted


def _compact_json_value(value: Any, max_chars: int) -> Any:
    """保留小 JSON 原值；大 JSON 改为可读预览，避免持久化完整大对象。"""

    size = _json_payload_size(value)
    if size <= max_chars:
        return value
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    preview = _truncate_text(_json_preview(value), min(max_chars, _MAX_COMPACTED_PREVIEW_CHARS))
    return {
        "storage_compacted": True,
        "original_type": type(value).__name__,
        "original_size_chars": size,
        "preview": preview,
    }


def _json_payload_size(value: Any) -> int:
    """估算写入 JSONB 的字符体积；无法编码时按字符串兜底。"""

    return len(_json_preview(value))


def _json_preview(value: Any) -> str:
    """把值转换成稳定 JSON 预览，供体积估算和压缩摘要使用。"""

    try:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def _truncate_text(value: str, max_chars: int) -> str:
    """截断长文本并记录原始长度，前端仍可展示可读摘要。"""

    if len(value) <= max_chars:
        return value
    keep_chars = max(0, max_chars - 64)
    return f"{value[:keep_chars]}...[已截断，原始长度 {len(value)} 字符]"
