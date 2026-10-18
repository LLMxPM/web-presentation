"""文件功能：页面与组件保存链路的 AssetAudio 播放参数静态校验入口。"""

from __future__ import annotations

from typing import Final

from pydantic import ValidationError

from app.schemas.audio import AssetAudioPropsContract
from app.services.resource_reference_parser import ResourceReferenceParser

AUDIO_ERROR_OPTIONS_INVALID: Final = "AUDIO_OPTIONS_INVALID"

# 单次保存最多上报的错误条数，避免多实例源码产生超长错误详情。
_MAX_REPORTED_ERRORS = 10

_FIELD_LABELS = {
    "name": "name",
    "purpose": "purpose",
    "controls": "controls",
    "volume": "volume",
    "playback_rate": "playbackRate",
    "preload": "preload",
    "loop": "loop",
    "fallback": "fallback",
}
_FIELD_MESSAGES = {
    "purpose": "purpose 只允许 content 或 narration。",
    "preload": "preload 只允许 none、metadata 或 auto。",
    "controls": "controls 必须是布尔值。",
    "loop": "loop 必须是布尔值。",
    "volume": "volume 必须是 0 到 1 之间的有限数字。",
    "playback_rate": "playbackRate 必须是 0.5 到 2 之间的有限数字。",
}


def collect_asset_audio_errors(source: str) -> list[str]:
    """静态校验 Vue 源码中 AssetAudio 实例的公开协议属性，返回有界错误列表。

    只校验可静态求值的字面量属性；动态绑定交给 Runtime 归一化兜底。
    资源身份与动态 name 由资源引用冻结链路负责，这里用占位 name 跳过必填检查。
    """

    payloads = ResourceReferenceParser.collect_vue_audio_prop_payloads(source)
    errors: list[str] = []
    narration_count = 0
    for index, payload in enumerate(payloads, start=1):
        try:
            contract = AssetAudioPropsContract.model_validate(payload)
        except ValidationError as error:
            for item in error.errors(include_input=False, include_url=False):
                errors.append(f"AssetAudio 实例 #{index}：{_format_validation_error(item)}")
                if len(errors) >= _MAX_REPORTED_ERRORS:
                    return errors
            continue
        if contract.purpose == "narration":
            narration_count += 1

    if narration_count > 1:
        errors.append(
            f"同一源码最多只能有一个 purpose=\"narration\" 的 AssetAudio 实例（当前 {narration_count} 个）。"
        )
    return errors[:_MAX_REPORTED_ERRORS]


def _format_validation_error(item: dict[str, object]) -> str:
    """把 Pydantic 错误转换成中文、无输入回显的稳定文案。"""

    location = item.get("loc")
    field = str(location[0]) if isinstance(location, tuple) and location else ""
    label = _FIELD_LABELS.get(field, field or "音频属性")
    error_type = str(item.get("type") or "")

    if error_type == "missing":
        return f"缺少必填属性 {label}。"
    if error_type == "string_too_short":
        return f"{label} 不能为空。"
    if error_type == "string_too_long":
        return f"{label} 不能超过 255 个字符。"
    if error_type in {"literal_error"}:
        return _FIELD_MESSAGES.get(field, f"{label} 取值为空或不在允许范围内。")
    if error_type in {"greater_than_equal", "less_than_equal", "bool_type", "float_type", "int_type"}:
        message = _FIELD_MESSAGES.get(field)
        if message:
            return message
        return _strip_value_error_prefix(str(item.get("msg") or f"{label} 取值不合法。"))
    if error_type == "value_error":
        return _strip_value_error_prefix(str(item.get("msg") or f"{label} 取值不合法。"))
    return _strip_value_error_prefix(str(item.get("msg") or f"{label} 取值不合法。"))


def _strip_value_error_prefix(message: str) -> str:
    """移除 Pydantic 为自定义 ValueError 添加的固定前缀。"""

    return message.removeprefix("Value error, ").strip()
