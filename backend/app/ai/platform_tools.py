"""文件功能：定义平台自有智能体工具抽象，替代第三方框架工具对象与运行上下文。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints

from pydantic import ConfigDict, create_model

RECOVERABLE_TOOL_ERROR_KIND = "recoverable_tool_error"


@dataclass(slots=True)
class AgentToolContext:
    """平台工具运行上下文，承载鉴权依赖和本轮运行标识。"""

    run_id: str
    session_id: str
    user_id: str | None = None
    dependencies: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentToolResult:
    """平台工具返回值；纯文本和可选媒体分开保存，便于模型与 UI 消费。"""

    content: str = ""
    images: list[Any] | None = None
    videos: list[Any] | None = None
    audios: list[Any] | None = None
    files: list[Any] | None = None


@dataclass(slots=True)
class PlatformTool:
    """平台工具定义，保留函数入口、参数 schema 和运行时元数据。"""

    name: str
    entrypoint: Callable[..., Any]
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    instructions: str | None = None
    requires_confirmation: bool = False
    show_result: bool = False
    sequential: bool = False


def recoverable_tool_error_result(
    *,
    code: str,
    message: str,
    status_code: int | None = None,
    hint: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造可交回模型继续处理的工具业务错误结果。"""

    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "recoverable": True,
    }
    if status_code is not None:
        error["status_code"] = status_code
    if hint:
        error["hint"] = hint
    payload: dict[str, Any] = {
        "success": False,
        "kind": RECOVERABLE_TOOL_ERROR_KIND,
        "error": error,
    }
    if data:
        payload["data"] = data
    return payload


def is_recoverable_tool_error_result(value: Any) -> bool:
    """判断工具返回值是否是可恢复业务错误结构。"""

    if not isinstance(value, dict):
        return False
    error = value.get("error")
    return (
        value.get("success") is False
        and value.get("kind") == RECOVERABLE_TOOL_ERROR_KIND
        and isinstance(error, dict)
        and error.get("recoverable") is True
    )


def agent_tool(
    *,
    show_result: bool = False,
    requires_confirmation: bool = False,
    sequential: bool = False,
    **_: Any,
) -> Callable[[Callable[..., Any]], PlatformTool]:
    """把普通 Python 函数声明为平台工具，忽略第三方框架专有参数。"""

    def decorator(func: Callable[..., Any]) -> PlatformTool:
        return PlatformTool(
            name=func.__name__,
            entrypoint=func,
            description=inspect.getdoc(func) or "",
            parameters=build_parameters_schema(func),
            requires_confirmation=requires_confirmation,
            show_result=show_result,
            sequential=sequential,
        )

    return decorator


def build_parameters_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """根据函数签名生成 JSON Schema，跳过第一个工具上下文参数。"""

    signature = inspect.signature(func)
    try:
        type_hints = get_type_hints(func, include_extras=True)
    except Exception:  # noqa: BLE001
        type_hints = {}
    fields: dict[str, tuple[Any, Any]] = {}
    parameters = list(signature.parameters.values())
    for parameter in parameters[1:]:
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        annotation = type_hints.get(
            parameter.name,
            parameter.annotation if parameter.annotation is not inspect.Signature.empty else Any,
        )
        default = parameter.default if parameter.default is not inspect.Signature.empty else ...
        fields[parameter.name] = (annotation, default)
    if not fields:
        return {"type": "object", "properties": {}}
    model = create_model(
        f"{func.__name__}_ToolParameters",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **fields,
    )
    schema = model.model_json_schema()
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return schema
