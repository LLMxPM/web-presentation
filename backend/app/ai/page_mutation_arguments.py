"""文件功能：归一化页面持久化任务从原始 LLM 工具调用中回读的参数。"""

from __future__ import annotations

from typing import Any

from app.ai.tools.generic.models import build_mutation_envelope
from app.core.exceptions import AppException


def normalize_page_mutation_arguments(
    *,
    operation: str,
    tool_name: str,
    raw_arguments: Any,
    project_id: int | None,
    page_id: int | None,
    base_version_no: int | None,
) -> dict[str, Any]:
    """兼容直接工具与通用工具参数形态，并校验任务目标和原始调用保持一致。"""

    if not isinstance(raw_arguments, dict):
        raise _invalid_arguments("页面变更任务缺少对象形式的原始工具参数。")
    arguments = dict(raw_arguments)
    normalized_tool_name = str(tool_name or "").strip()
    if operation == "create_page":
        normalized = _normalize_create_arguments(normalized_tool_name, arguments)
        _ensure_optional_int_matches(normalized.get("project_id"), project_id, field_name="project_id")
        return normalized
    if operation == "apply_page_edits":
        normalized = _normalize_apply_arguments(normalized_tool_name, arguments)
        target_id = arguments.get("target_id") if normalized_tool_name == "update_entity" else normalized.get("page_id")
        _ensure_optional_int_matches(target_id, page_id, field_name="page_id")
        _ensure_optional_int_matches(
            normalized.get("base_version_no"),
            base_version_no,
            field_name="base_version_no",
        )
        return normalized
    raise _invalid_arguments(f"不支持的页面变更操作：{operation}。")


def normalize_page_mutation_result(
    *,
    operation: str,
    tool_name: str,
    result: dict[str, Any],
    page_id: int | None,
) -> dict[str, Any]:
    """让 deferred 成功结果保持原始直接工具或通用工具的返回契约。"""

    if result.get("success") is False:
        return result
    if tool_name == "create_entity" and operation == "create_page":
        created_page_id = result.get("page_id")
        return build_mutation_envelope(
            resource_type="page",
            operation="create",
            message=str(result.get("message") or "页面已创建。"),
            mutation_kind="project-pages",
            data=result,
            target=None if created_page_id is None else {"id": int(created_page_id), "resource_type": "page"},
            effect="create",
        )
    if tool_name == "update_entity" and operation == "apply_page_edits":
        target = None if page_id is None else {"id": page_id, "resource_type": "page"}
        return build_mutation_envelope(
            resource_type="page",
            operation="update",
            action="content",
            message=str(result.get("message") or "页面代码已更新并生成新版本。"),
            target=target,
            mutation_kind="project-pages",
            data=result,
        )
    return result


def _normalize_create_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """把 create_entity(page) 的 payload 解包为页面创建参数。"""

    if tool_name == "create_project_page":
        return arguments
    if tool_name != "create_entity":
        raise _invalid_arguments(f"页面创建任务不支持原始工具：{tool_name or 'unknown'}。")
    if str(arguments.get("resource_type") or "") != "page":
        raise _invalid_arguments("create_entity 页面任务的 resource_type 必须为 page。")
    if str(arguments.get("mode") or "") != "new":
        raise _invalid_arguments("create_entity 页面持久化任务的 mode 必须为 new。")
    payload = _required_payload(arguments, tool_name=tool_name)
    if "content" not in payload:
        raise _invalid_arguments("create_entity 页面任务缺少 content。")
    payload["page_content"] = payload.pop("content")
    return payload


def _normalize_apply_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """把 update_entity(page, content) 的 payload 解包为页面编辑参数。"""

    if tool_name == "apply_page_edits":
        return arguments
    if tool_name != "update_entity":
        raise _invalid_arguments(f"页面编辑任务不支持原始工具：{tool_name or 'unknown'}。")
    if str(arguments.get("resource_type") or "") != "page":
        raise _invalid_arguments("update_entity 页面任务的 resource_type 必须为 page。")
    if str(arguments.get("action") or "metadata") != "content":
        raise _invalid_arguments("update_entity 页面任务的 action 必须为 content。")
    return _required_payload(arguments, tool_name=tool_name)


def _required_payload(arguments: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    """读取通用工具 payload，缺失时返回可定位契约漂移的错误。"""

    payload = arguments.get("payload")
    if not isinstance(payload, dict):
        raise _invalid_arguments(f"{tool_name} 页面任务缺少对象形式的 payload。")
    return dict(payload)


def _ensure_optional_int_matches(raw_value: Any, expected: int | None, *, field_name: str) -> None:
    """原始调用携带目标 ID 时必须与入队快照一致，避免错误任务跨目标执行。"""

    if raw_value is None:
        return
    try:
        actual = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise _invalid_arguments(f"页面任务的 {field_name} 不是有效整数。") from exc
    if expected is None or actual != int(expected):
        raise _invalid_arguments(f"页面任务的 {field_name} 与入队目标不一致。")


def _invalid_arguments(message: str) -> AppException:
    """构造统一的页面任务参数契约错误。"""

    return AppException(
        status_code=422,
        code="AI_PAGE_MUTATION_ARGUMENTS_INVALID",
        detail=message,
    )
