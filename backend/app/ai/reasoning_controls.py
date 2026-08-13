"""文件功能：规范化 Models.dev 推理控制元数据，并计算协议可安全发送的控制能力。"""

from __future__ import annotations

from typing import Any

REASONING_CONTROL_TYPES = {"toggle", "effort", "budget_tokens"}

PROTOCOL_REASONING_CONTROLS: dict[str, frozenset[str]] = {
    "openai_chat": frozenset({"toggle", "effort"}),
    "openai_compatible_chat": frozenset({"effort"}),
    "openrouter_chat": frozenset({"toggle", "effort"}),
    "google_chat": frozenset({"effort"}),
    "alibaba_openai_compatible": frozenset({"toggle", "budget_tokens"}),
    "deepseek_openai_compatible": frozenset({"toggle", "effort"}),
    "xiaomi_openai_compatible": frozenset({"toggle"}),
    "ollama_openai_compatible": frozenset({"toggle", "effort"}),
}


def normalize_reasoning_options(value: Any) -> dict[str, Any]:
    """把 Models.dev 当前的选项对象数组和旧格式统一为稳定的内部结构。"""

    controls: list[dict[str, Any]] = []
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        controls = [value]
    elif isinstance(value, (list, tuple)):
        if all(isinstance(item, str) for item in value):
            controls = [{"type": "effort", "values": list(value)}]
        else:
            controls = [item for item in value if isinstance(item, dict)]
    elif isinstance(value, dict):
        nested = value.get("options")
        if isinstance(nested, (list, tuple)) and any(isinstance(item, dict) for item in nested):
            controls = [item for item in nested if isinstance(item, dict)]
        else:
            effort = value.get("effort") or value.get("efforts") or value.get("levels") or nested
            if isinstance(effort, dict):
                effort = list(effort)
            if isinstance(effort, (list, tuple)):
                controls.append({"type": "effort", "values": list(effort)})
            if isinstance(value.get("budget_tokens"), dict):
                controls.append({"type": "budget_tokens", **value["budget_tokens"]})
            for control_type in value.get("types", []) if isinstance(value.get("types"), list) else []:
                if control_type == "toggle":
                    controls.append({"type": "toggle"})

    types: list[str] = []
    efforts: list[str] = []
    budget: dict[str, int] = {}
    for control in controls:
        control_type = str(control.get("type") or "").strip()
        if control_type not in REASONING_CONTROL_TYPES:
            continue
        if control_type not in types:
            types.append(control_type)
        if control_type == "effort":
            values = control.get("values")
            if isinstance(values, (list, tuple)):
                for item in values:
                    normalized = str(item).strip() if isinstance(item, str) else ""
                    if normalized and normalized not in efforts:
                        efforts.append(normalized)
        if control_type == "budget_tokens":
            for key in ("min", "max"):
                item = control.get(key)
                if isinstance(item, int) and item > 0:
                    budget[key] = item

    result: dict[str, Any] = {"types": types}
    if efforts:
        result["effort"] = efforts
    if budget:
        result["budget_tokens"] = budget
    return result


def reasoning_control_types(value: Any) -> frozenset[str]:
    """返回模型目录明确声明的推理控制类型。"""

    return frozenset(normalize_reasoning_options(value).get("types", []))


def reasoning_effort_options(value: Any) -> list[str]:
    """返回模型明确公布的推理强度枚举。"""

    options = normalize_reasoning_options(value).get("effort", [])
    return [item for item in options if isinstance(item, str)]


def reasoning_budget_limits(value: Any) -> dict[str, int]:
    """返回模型公布的推理 token 预算边界。"""

    limits = normalize_reasoning_options(value).get("budget_tokens", {})
    return {key: item for key, item in limits.items() if key in {"min", "max"} and isinstance(item, int)}


def protocol_reasoning_controls(protocol_key: str) -> frozenset[str]:
    """返回固定协议转换器已经实现且可安全发送的推理控制类型。"""

    return PROTOCOL_REASONING_CONTROLS.get(protocol_key, frozenset())


def supports_explicit_disable(options: Any, protocol_key: str) -> bool:
    """仅当模型声明与协议转换器均能表达关闭语义时返回真。"""

    model_controls = reasoning_control_types(options)
    protocol_controls = protocol_reasoning_controls(protocol_key)
    return bool(
        "toggle" in model_controls.intersection(protocol_controls)
        or ("effort" in protocol_controls and "none" in reasoning_effort_options(options))
    )
