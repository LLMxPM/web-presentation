"""文件功能：处理 Agent 会话 Facade 中 HITL requirement、确认、用户反馈和建议 patch 的归一化。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from agno.models.response import ToolExecution
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunOutput
from fastapi.encoders import jsonable_encoder

from app.ai.agent import AgentRuntimeContext
from app.ai.session_facade_common import _coerce_str, _extract_member_event_data
from app.ai.tools.shared import apply_source_edits
from app.core.exceptions import AppException
from app.schemas.agent import AgentPendingRequirement, AgentSuggestedPatch
from app.schemas.page import PageItem


def _normalize_user_feedback_schema(raw_schema: Any) -> list[dict[str, Any]]:
    """把 Agno 的结构化提问 schema 归一成前端可直接渲染的单选列表。"""

    if not isinstance(raw_schema, list):
        return []
    questions: list[dict[str, Any]] = []
    for raw_question in raw_schema:
        question_payload = jsonable_encoder(raw_question)
        if not isinstance(question_payload, dict):
            continue
        question_text = _coerce_str(question_payload.get("question"))
        if not question_text:
            continue
        options: list[dict[str, Any]] = []
        for raw_option in question_payload.get("options") or []:
            option_payload = jsonable_encoder(raw_option)
            if not isinstance(option_payload, dict):
                continue
            label = _coerce_str(option_payload.get("label"))
            if not label:
                continue
            options.append(
                {
                    "label": label,
                    "description": _coerce_str(option_payload.get("description")),
                    "selected": bool(option_payload.get("selected", False)),
                }
            )
        questions.append(
            {
                "question": question_text,
                "header": _coerce_str(question_payload.get("header")),
                "options": options,
                "multi_select": False,
                "selected_options": question_payload.get("selected_options"),
            }
        )
    return questions



def _apply_user_feedback_selections(
    tool_execution: dict[str, Any],
    feedback_selections: list[dict[str, Any]],
) -> dict[str, Any]:
    """把前端单选或自定义回答写回 Agno ask_user 的 ToolExecution。"""

    selection_map: dict[str, dict[str, Any]] = {}
    for raw_selection in feedback_selections:
        if not isinstance(raw_selection, dict):
            continue
        question = _coerce_str(raw_selection.get("question"))
        if question:
            selection_map[question] = raw_selection

    schema = _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    for question in schema:
        selection = selection_map.get(str(question.get("question") or ""))
        if not selection:
            continue
        custom_text = _coerce_str(selection.get("custom_text"))
        selected_label = _coerce_str(selection.get("selected_label"))
        selected_options = [f"用户补充：{custom_text}"] if custom_text else ([selected_label] if selected_label else [])
        question["selected_options"] = selected_options
        for option in question.get("options") or []:
            if isinstance(option, dict):
                option["selected"] = option.get("label") in selected_options

    updated_tool_execution = dict(tool_execution)
    updated_tool_execution["requires_user_input"] = True
    updated_tool_execution["user_feedback_schema"] = schema
    if schema and all(question.get("selected_options") for question in schema):
        updated_tool_execution["answered"] = True
    return updated_tool_execution



def _apply_resolved_requirement_to_agno_run(run: RunOutput | TeamRunOutput, *, requirement: RunRequirement) -> None:
    """把本次 HITL 决策同步到 Agno run 的 requirement 与 tool 列表。"""

    tool_execution = requirement.tool_execution
    tool_call_id = _tool_call_id(tool_execution)
    if not tool_call_id:
        return
    updated_requirements: list[Any] = []
    replaced = False
    for item in list(getattr(run, "requirements", None) or []):
        if _requirement_tool_call_id(item) == tool_call_id:
            updated_requirements.append(requirement)
            replaced = True
        else:
            updated_requirements.append(item)
    if not replaced:
        updated_requirements.append(requirement)
    run.requirements = updated_requirements

    updated_tools: list[Any] = []
    tool_replaced = False
    for item in list(getattr(run, "tools", None) or []):
        if _tool_call_id(item) == tool_call_id:
            _copy_tool_execution_state(item, tool_execution)
            updated_tools.append(item)
            tool_replaced = True
        else:
            updated_tools.append(item)
    if not tool_replaced and tool_execution is not None:
        updated_tools.append(tool_execution)
    run.tools = updated_tools



def _normalize_agno_terminal_run_payload(
    run: RunOutput | TeamRunOutput,
    *,
    status: RunStatus,
    resolved_tool_execution: dict[str, Any] | None = None,
    fallback_tool_result: Any = None,
) -> None:
    """终态 run 不再携带未解决 HITL，避免后续刷新把旧动作恢复为 paused。"""

    if status not in {RunStatus.completed, RunStatus.cancelled, RunStatus.error}:
        return
    clear_all_requirements = status in {RunStatus.completed, RunStatus.cancelled}
    if status == RunStatus.error and resolved_tool_execution is None:
        return
    tool_call_id = _coerce_str((resolved_tool_execution or {}).get("tool_call_id"))
    if clear_all_requirements:
        run.requirements = []
    elif tool_call_id:
        run.requirements = [
            item
            for item in list(getattr(run, "requirements", None) or [])
            if _requirement_tool_call_id(item) != tool_call_id
        ]
    for item in list(getattr(run, "tools", None) or []):
        item_call_id = _tool_call_id(item)
        is_target_tool = bool(tool_call_id and item_call_id == tool_call_id)
        should_resolve_tool = clear_all_requirements or is_target_tool
        if is_target_tool and resolved_tool_execution is not None:
            _copy_tool_execution_payload_state(item, resolved_tool_execution)
        if should_resolve_tool and _tool_execution_field(item, "requires_confirmation"):
            _set_tool_execution_field(item, "requires_confirmation", False)
            if _tool_execution_field(item, "confirmed") is None:
                _set_tool_execution_field(item, "confirmed", status == RunStatus.completed)
        if should_resolve_tool and _tool_execution_field(item, "requires_user_input"):
            _set_tool_execution_field(item, "requires_user_input", False)
            if _tool_execution_field(item, "answered") is not True:
                _set_tool_execution_field(item, "answered", status == RunStatus.completed)
        if (
            should_resolve_tool
            and _tool_execution_field(item, "external_execution_required")
            and _tool_execution_field(item, "result") is not None
        ):
            _set_tool_execution_field(item, "external_execution_required", False)
        if is_target_tool and fallback_tool_result is not None and _tool_execution_field(item, "result") is None:
            _set_tool_execution_field(item, "result", fallback_tool_result)



def _copy_tool_execution_state(target: Any, source: Any) -> None:
    """把 Agno ToolExecution 对象中的决策字段复制到旧对象。"""

    if target is None or source is None:
        return
    for field_name in (
        "confirmed",
        "confirmation_note",
        "requires_user_input",
        "user_input_schema",
        "user_feedback_schema",
        "answered",
        "external_execution_required",
        "external_execution_silent",
        "result",
    ):
        value = _tool_execution_field(source, field_name)
        if value is not None:
            _set_tool_execution_field(target, field_name, value)



def _copy_tool_execution_payload_state(target: Any, source: dict[str, Any]) -> None:
    """把前端 ToolExecution payload 中的决策字段复制到 Agno ToolExecution。"""

    for field_name in (
        "confirmed",
        "confirmation_note",
        "requires_user_input",
        "user_input_schema",
        "user_feedback_schema",
        "answered",
        "external_execution_required",
        "external_execution_silent",
        "result",
    ):
        if field_name in source and source[field_name] is not None:
            if field_name in {"user_input_schema", "user_feedback_schema"} and not isinstance(target, dict):
                continue
            if isinstance(target, dict):
                target[field_name] = source[field_name]
                continue
            setattr(target, field_name, source[field_name])



def _requirement_tool_call_id(requirement: Any) -> str:
    """提取 Agno RunRequirement 中的 tool_call_id。"""

    if isinstance(requirement, dict):
        return _tool_call_id(requirement.get("tool_execution"))
    return _tool_call_id(getattr(requirement, "tool_execution", None))



def _tool_call_id(tool_execution: Any) -> str:
    """兼容对象与 dict，提取 ToolExecution 的稳定调用 ID。"""

    if isinstance(tool_execution, dict):
        return _coerce_str(tool_execution.get("tool_call_id"))
    return _coerce_str(getattr(tool_execution, "tool_call_id", None))



def _tool_execution_field(tool_execution: Any, field_name: str) -> Any:
    """兼容对象与 dict，读取 ToolExecution 字段。"""

    if isinstance(tool_execution, dict):
        return tool_execution.get(field_name)
    return getattr(tool_execution, field_name, None)



def _set_tool_execution_field(tool_execution: Any, field_name: str, value: Any) -> None:
    """兼容对象与 dict，写入 ToolExecution 字段。"""

    if isinstance(tool_execution, dict):
        tool_execution[field_name] = value
        return
    setattr(tool_execution, field_name, value)



def _build_run_requirement_from_tool_execution_payload(tool_execution: dict[str, Any]) -> RunRequirement:
    """从前端提交的 ToolExecution payload 构造 Agno requirement，并补齐 Agno 反序列化遗漏字段。"""

    execution = ToolExecution.from_dict(tool_execution)
    confirmed = tool_execution.get("confirmed")
    confirmation_note = _coerce_str(tool_execution.get("confirmation_note"))
    answered = tool_execution.get("answered")
    if answered is True or _tool_execution_payload_has_complete_user_answers(tool_execution):
        execution.answered = True
    if execution.tool_name == "ask_user" and execution.answered is True:
        # Agno 2.5.x 的 Team continue 路径没有 ask_user 专用处理，会把已答复的问题再次执行成工具。
        # 这里将用户选择转为普通工具结果消息，让 Team/Agent 两条路径都能继续同一个 tool_call_id。
        execution.requires_user_input = False
        execution.external_execution_required = True
        execution.result = _build_user_feedback_tool_result(tool_execution)
        requirement = RunRequirement(tool_execution=execution)
        requirement.external_execution_result = execution.result
        return requirement
    requirement = RunRequirement(tool_execution=execution)
    if confirmed is True:
        requirement.confirmation = True
        execution.confirmed = True
    elif confirmed is False:
        requirement.confirmation = False
        requirement.confirmation_note = confirmation_note
        execution.confirmed = False
        execution.confirmation_note = confirmation_note
    return requirement



def _build_user_feedback_tool_result(tool_execution: dict[str, Any]) -> str:
    """把 ask_user 结构化选择编码为 Agno 工具结果消息内容。"""

    feedback_result = [
        {
            "question": question.get("question"),
            "selected": question.get("selected_options") or [],
        }
        for question in _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    ]
    return f"User feedback received: {json.dumps(feedback_result, ensure_ascii=False)}"



def _tool_execution_payload_has_complete_user_answers(tool_execution: dict[str, Any]) -> bool:
    """判断已序列化的用户输入/反馈是否已经完整回答。"""

    feedback_schema = _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    if feedback_schema:
        return all(question.get("selected_options") for question in feedback_schema)

    input_schema = tool_execution.get("user_input_schema")
    if isinstance(input_schema, list) and input_schema:
        values: list[Any] = []
        for raw_field in input_schema:
            field = jsonable_encoder(raw_field)
            if isinstance(field, dict):
                values.append(field.get("value"))
        return len(values) == len(input_schema) and all(value is not None for value in values)

    return False



def _extract_pending_requirement(
    *,
    payload: dict[str, Any],
    runtime_context: AgentRuntimeContext | None = None,
    current_page: PageItem | None = None,
    ) -> AgentPendingRequirement | None:
    """从 RunPaused 事件中提取第一个待确认需求，并补齐页面 patch 信息。"""

    if runtime_context is None and current_page is not None:
        runtime_context = AgentRuntimeContext(
            scope_type="page",
            workspace_id=int(current_page.workspace_id or 0),
            project_id=current_page.project_id,
            page_id=current_page.id,
            page_title=current_page.title,
            page_summary=current_page.summary,
            page_code=current_page.code,
            page_content=current_page.page_content,
            file_type=current_page.file_type.value,
            source="editor-page-detail",
        )
    requirement_payload = _resolve_requirement_payload(payload)
    if requirement_payload is None:
        return None
    member_event_data = _extract_member_event_data(payload)

    tool_execution = requirement_payload.get("tool_execution") or {}
    tool_name = tool_execution.get("tool_name")
    tool_args = tool_execution.get("tool_args") or {}
    user_feedback_schema = _normalize_user_feedback_schema(
        requirement_payload.get("user_feedback_schema")
        or tool_execution.get("user_feedback_schema")
        or tool_args.get("questions")
    )
    requirement_kind = "user_feedback" if (tool_name == "ask_user" or user_feedback_schema) else "confirmation"
    suggested_patch, preview_note = (None, None)
    if runtime_context is not None and runtime_context.page_id is not None and runtime_context.page_content is not None:
        suggested_patch, preview_note = _build_suggested_patch(
            current_page=PageItem(
                id=runtime_context.page_id,
                code=runtime_context.page_code or "",
                page_content=runtime_context.page_content,
                current_version_no=1,
                file_type=runtime_context.file_type or "vue",
                title=runtime_context.page_title or "",
                summary=runtime_context.page_summary,
                status="active",
                workspace_id=runtime_context.workspace_id,
                project_id=runtime_context.project_id,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
                created_by=None,
                updated_by=None,
            ),
            tool_name=tool_name,
            tool_args=tool_args,
        )
    normalized_tool_execution = tool_execution
    if user_feedback_schema:
        normalized_tool_execution = {
            **normalized_tool_execution,
            "requires_user_input": True,
            "user_feedback_schema": user_feedback_schema,
        }

    return AgentPendingRequirement(
        id=requirement_payload.get("id"),
        kind=requirement_kind,
        run_id=str(payload.get("run_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        member_agent_id=_coerce_str(member_event_data.get("member_agent_id")),
        member_agent_name=_coerce_str(member_event_data.get("member_agent_name")),
        member_run_id=_coerce_str(member_event_data.get("member_run_id")),
        tool_name=tool_name,
        tool_execution=normalized_tool_execution,
        suggested_patch=suggested_patch,
        user_feedback_schema=user_feedback_schema,
        note=normalized_tool_execution.get("confirmation_note") or preview_note,
    )



def _pending_requirement_timeline_content(requirement: AgentPendingRequirement) -> str:
    """生成 requirement 时间线文案，ask_user 优先展示真实问题而不是内部工具名。"""

    if requirement.kind == "user_feedback" or requirement.tool_name == "ask_user":
        for item in requirement.user_feedback_schema or []:
            if not isinstance(item, dict):
                continue
            question = _coerce_str(item.get("question"))
            if question:
                return question
        return requirement.note or "等待用户回复。"
    return requirement.note or requirement.tool_name or "等待用户处理。"



def _resolve_requirement_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """优先从 requirements 提取待确认项；若缺失，则从暂停 tools 中兜底合成。"""

    requirements = payload.get("requirements") or []
    if requirements:
        for requirement_payload in reversed(requirements):
            if isinstance(requirement_payload, dict) and _is_requirement_payload_active(requirement_payload):
                return requirement_payload

    tools = payload.get("tools") or []
    for tool_payload in reversed(tools):
        if not isinstance(tool_payload, dict):
            continue
        if _is_tool_execution_payload_active(tool_payload):
            return {
                "id": None,
                "tool_execution": tool_payload,
            }
    return None



def _is_requirement_payload_active(requirement_payload: dict[str, Any]) -> bool:
    """判断 JSON 化后的 Agno RunRequirement 是否仍需要人工处理。"""

    tool_execution = requirement_payload.get("tool_execution") or {}
    if not isinstance(tool_execution, dict):
        return False
    if tool_execution.get("requires_confirmation") and (
        requirement_payload.get("confirmation") is None and tool_execution.get("confirmed") is None
    ):
        return True
    if tool_execution.get("requires_user_input") and tool_execution.get("answered") is not True:
        return True
    if tool_execution.get("external_execution_required") and (
        requirement_payload.get("external_execution_result") is None and tool_execution.get("result") is None
    ):
        return True
    return False



def _is_tool_execution_payload_active(tool_execution: dict[str, Any]) -> bool:
    """判断 JSON 化后的 Agno ToolExecution 是否仍处于暂停等待态。"""

    if tool_execution.get("requires_confirmation") and tool_execution.get("confirmed") is None:
        return True
    if tool_execution.get("requires_user_input") and tool_execution.get("answered") is not True:
        return True
    if tool_execution.get("external_execution_required") and tool_execution.get("result") is None:
        return True
    return False



def _build_suggested_patch(
    *,
    current_page: PageItem,
    tool_name: Any,
    tool_args: dict[str, Any],
) -> tuple[AgentSuggestedPatch | None, str | None]:
    """尽量为页面写回工具构造预览 patch；若预生成失败，不中断整个暂停事件。"""

    if tool_name != "apply_page_edits" or not isinstance(tool_args.get("edits"), list):
        return None, None

    try:
        edit_result = apply_source_edits(current_page.page_content, tool_args["edits"])
    except AppException as exc:
        return None, f"页面改写已进入待确认状态，但当前无法预生成 edits 预览：{exc.detail}"

    return AgentSuggestedPatch(
        tool_name=tool_name,
        target_page_id=current_page.id,
        change_note=tool_args.get("change_note"),
        proposed_content=edit_result.next_content,
        unified_diff=edit_result.canonical_diff,
    ), None
