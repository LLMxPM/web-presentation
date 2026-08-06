"""文件功能：构造统一内容助手自委派子运行的任务提示词。"""

from __future__ import annotations

import json
from typing import Any


def build_member_prompt(
    *,
    task: str,
    handoff_context: str | None,
    expected_output: str | None,
    completed_results: list[dict[str, Any]],
) -> str:
    """根据委派任务、上下文和前置结果构造自身子运行收到的用户提示词。"""

    parts = [
        "这是内容助手委派给自身子运行的独立任务，请在当前工作空间权限和通用工具边界内完成。",
        f"任务：{task}",
    ]
    if handoff_context:
        parts.append(f"上下文：{handoff_context}")
    if completed_results:
        parts.append(f"前置子任务结果：{json.dumps(completed_results, ensure_ascii=False)}")
    if expected_output:
        parts.append(f"期望返回：{expected_output}")
    parts.append("完成后用中文简要返回已执行动作、关键对象 ID/名称、主运行需要整合的事实。")
    return "\n\n".join(parts)


def build_member_prompt_from_payload(payload: dict[str, Any]) -> str | None:
    """从历史成员运行的 input_payload 中恢复可展示的传入提示词。"""

    existing_prompt = _optional_text(payload.get("input_prompt"))
    if existing_prompt:
        return existing_prompt
    task = _optional_text(payload.get("task"))
    if not task:
        return None
    return build_member_prompt(
        task=task,
        handoff_context=_optional_text(payload.get("handoff_context")),
        expected_output=_optional_text(payload.get("expected_output")),
        completed_results=[
            item for item in (payload.get("completed_results") or [])
            if isinstance(item, dict)
        ],
    )


def _optional_text(value: Any) -> str | None:
    """把可选文本字段规整为空值或非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None
