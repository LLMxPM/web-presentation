"""文件功能：提供只读 AI Agent 诊断 CLI，便于按 run_id 或 session_id 查看运行态。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.ai_agent_runtime import (
    AiAgentMessage,
    AiAgentRequirement,
    AiAgentRun,
    AiAgentRunEvent,
    AiAgentSession,
    AiAgentToolCall,
)


OutputFormat = Literal["summary", "json"]


def load_backend_env_for_cli(env_path: Path | None = None) -> Path | None:
    """从 backend/.env 补充当前进程缺失的环境变量，支持从根仓运行 CLI。"""

    path = env_path or _default_backend_env_path()
    if not path.is_file():
        return None

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in os.environ:
            os.environ[key] = value
            loaded = True
    if loaded:
        from app.core.config import get_settings

        get_settings.cache_clear()
    return path


async def collect_ai_run_diagnostics(session: AsyncSession, run_id: str) -> dict[str, Any] | None:
    """按 run_id 收集 AI run 诊断信息；只读查询，不修改运行态表。"""

    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None

    run_model = await session.get(AiAgentRun, normalized_run_id)
    if run_model is None:
        return None

    events = (
        await session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.run_id == normalized_run_id)
            .order_by(AiAgentRunEvent.event_index.asc(), AiAgentRunEvent.id.asc())
        )
    ).scalars().all()
    tool_calls = (
        await session.execute(
            select(AiAgentToolCall)
            .where(AiAgentToolCall.run_id == normalized_run_id)
            .order_by(AiAgentToolCall.created_at.asc(), AiAgentToolCall.id.asc())
        )
    ).scalars().all()
    requirements = (
        await session.execute(
            select(AiAgentRequirement)
            .where(AiAgentRequirement.run_id == normalized_run_id)
            .order_by(AiAgentRequirement.created_at.asc(), AiAgentRequirement.id.asc())
        )
    ).scalars().all()
    messages = (
        await session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.run_id == normalized_run_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
    ).scalars().all()

    return {
        "run": _dump_run(run_model),
        "events": [_dump_event(item) for item in events],
        "tool_calls": [_dump_tool_call(item) for item in tool_calls],
        "requirements": [_dump_requirement(item) for item in requirements],
        "messages": [_dump_message(item) for item in messages],
        "message_history_summary": _summarize_message_history(run_model.message_history_json),
        "message_history": run_model.message_history_json or [],
    }


async def collect_ai_session_diagnostics(session: AsyncSession, session_id: str) -> dict[str, Any] | None:
    """按 session_id 收集 AI 会话诊断信息；包含会话下所有 run 的诊断 payload。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        return None

    session_model = await session.get(AiAgentSession, normalized_session_id)
    if session_model is None:
        return None

    run_ids = (
        await session.execute(
            select(AiAgentRun.run_id)
            .where(AiAgentRun.session_id == normalized_session_id)
            .order_by(AiAgentRun.created_at.asc(), AiAgentRun.run_id.asc())
        )
    ).scalars().all()
    messages = (
        await session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.session_id == normalized_session_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
    ).scalars().all()
    runs = []
    for run_id in run_ids:
        run_payload = await collect_ai_run_diagnostics(session, run_id)
        if run_payload is not None:
            runs.append(run_payload)

    return {
        "session": _dump_session(session_model),
        "runs": runs,
        "messages": [_dump_message(item) for item in messages],
    }


def format_ai_run_diagnostics_summary(payload: dict[str, Any]) -> str:
    """把诊断 payload 格式化为适合终端阅读的摘要文本。"""

    run = payload["run"]
    lines = [
        f"AI run: {run['run_id']}",
        f"- session_id: {run['session_id']}",
        f"- agent_id: {run['agent_id']}",
        f"- status: {run['status']}",
        f"- event_index: {run['event_index']}",
        f"- started_at: {run['started_at'] or '-'}",
        f"- finished_at: {run['finished_at'] or '-'}",
    ]
    if run.get("error_code") or run.get("error_message"):
        lines.append(f"- error: {run.get('error_code') or '-'} {run.get('error_message') or ''}".rstrip())

    history_summary = payload["message_history_summary"]
    lines.extend([
        "",
        f"Events ({len(payload['events'])}):",
        *[
            f"- #{item['event_index']} {item['event']} {_preview_event_payload(item)}".rstrip()
            for item in payload["events"]
        ],
        "",
        f"Tool calls ({len(payload['tool_calls'])}):",
        *[
            f"- {item['tool_name']} [{item['status']}] call_id={item['tool_call_id'] or '-'} input={_preview(item['input_payload'])} output={_preview(item['output_payload'])}"
            for item in payload["tool_calls"]
        ],
        "",
        f"Requirements ({len(payload['requirements'])}):",
        *[
            f"- {item['requirement_id']} [{item['status']}] kind={item['kind']} tool={item['tool_name'] or '-'} call_id={item['tool_call_id'] or '-'}"
            for item in payload["requirements"]
        ],
        "",
        f"Messages ({len(payload['messages'])}):",
        *[
            f"- {item['role']} order={item['order_index']} content={_preview(item['content'])}"
            for item in payload["messages"]
        ],
        "",
        "Message history:",
        f"- count: {history_summary['count']}",
        f"- kinds: {', '.join(history_summary['kinds']) if history_summary['kinds'] else '-'}",
    ])
    return "\n".join(lines)


def format_ai_session_diagnostics_summary(payload: dict[str, Any]) -> str:
    """把会话级诊断 payload 格式化为终端摘要。"""

    session = payload["session"]
    runs = payload["runs"]
    checkpoint = session.get("summary") if isinstance(session.get("summary"), dict) else None
    lines = [
        f"AI session: {session['session_id']}",
        f"- agent_id: {session['agent_id']}",
        f"- user_id: {session['user_id']}",
        f"- scope: {session['scope_type']} workspace={session['workspace_id']} project={session['project_id'] or '-'} page={session['page_id'] or '-'} component={session['component_id'] or '-'}",
        f"- source: {session['source']}",
        f"- compression_checkpoint: {_format_summary_checkpoint(checkpoint)}",
        f"- deleted_at: {session['deleted_at'] or '-'}",
        f"- created_at: {session['created_at'] or '-'}",
        "",
        f"Runs ({len(runs)}):",
    ]
    lines.extend([
        f"- {item['run']['run_id']} [{item['run']['status']}] events={len(item['events'])} tools={len(item['tool_calls'])} requirements={len(item['requirements'])} messages={len(item['messages'])}"
        for item in runs
    ])
    if not runs:
        lines.append("-")

    lines.extend([
        "",
        f"Session messages ({len(payload['messages'])}):",
        *[
            f"- {item['role']} run={item['run_id'] or '-'} order={item['order_index']} content={_preview(item['content'])}"
            for item in payload["messages"]
        ],
    ])

    for run_payload in runs:
        lines.extend([
            "",
            "=" * 72,
            format_ai_run_diagnostics_summary(run_payload),
        ])
    return "\n".join(lines)


def render_ai_diagnostics(payload: dict[str, Any], output_format: OutputFormat) -> str:
    """把 run 或 session 诊断 payload 渲染为指定格式。"""

    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if "session" in payload:
        return format_ai_session_diagnostics_summary(payload)
    return format_ai_run_diagnostics_summary(payload)


def write_diagnostics_output(content: str, output_path: str | None) -> None:
    """输出诊断内容；未指定路径时写 stdout，指定路径时写 UTF-8 文件。"""

    if not output_path:
        print(content)
        return

    path = Path(output_path)
    if path.parent and path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{content}\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="诊断 AI Agent run 或 session 运行态。")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--run-id", help="要诊断的 ai_agent_runs.run_id。")
    target_group.add_argument("--session-id", help="要诊断的 ai_agent_sessions.session_id，会输出该会话下所有 run。")
    parser.add_argument("--format", choices=("summary", "json"), default="summary", help="输出格式。")
    parser.add_argument("--output", help="输出文件路径；未指定时输出到 stdout。")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    """CLI 异步入口。"""

    args = build_parser().parse_args(argv)
    load_backend_env_for_cli()
    async with get_session_factory()() as session:
        if args.run_id:
            payload = await collect_ai_run_diagnostics(session, args.run_id)
            missing_message = f"AI run 不存在：{args.run_id}"
        else:
            payload = await collect_ai_session_diagnostics(session, args.session_id)
            missing_message = f"AI session 不存在：{args.session_id}"
    if payload is None:
        print(missing_message, file=sys.stderr)
        return 1
    write_diagnostics_output(render_ai_diagnostics(payload, args.format), args.output)
    return 0


def main() -> None:
    """CLI 同步入口。"""

    raise SystemExit(asyncio.run(async_main()))


def _default_backend_env_path() -> Path:
    """返回仓库内 backend/.env 路径；从根仓或 backend 子目录运行时均稳定。"""

    return Path(__file__).resolve().parents[2] / ".env"


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """解析简单 .env 行，支持注释、export 前缀和单双引号。"""

    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, _normalize_env_value(value)


def _normalize_env_value(value: str) -> str:
    """清理 .env 值中的包裹引号，并保留未加引号值的原始内容。"""

    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _dump_run(run_model: AiAgentRun) -> dict[str, Any]:
    """转换 run ORM 为诊断字典。"""

    return {
        "run_id": run_model.run_id,
        "session_id": run_model.session_id,
        "agent_id": run_model.agent_id,
        "user_id": run_model.user_id,
        "status": run_model.status,
        "scope_type": run_model.scope_type,
        "workspace_id": run_model.workspace_id,
        "project_id": run_model.project_id,
        "page_id": run_model.page_id,
        "component_id": run_model.component_id,
        "source": run_model.source,
        "input_payload": run_model.input_payload_json or {},
        "content": run_model.content,
        "reasoning_content": run_model.reasoning_content,
        "pending_requirement": run_model.pending_requirement_json,
        "event_index": run_model.event_index,
        "cancel_requested_at": _iso(run_model.cancel_requested_at),
        "started_at": _iso(run_model.started_at),
        "finished_at": _iso(run_model.finished_at),
        "error_code": run_model.error_code,
        "error_message": run_model.error_message,
        "created_at": _iso(run_model.created_at),
        "updated_at": _iso(run_model.updated_at),
    }


def _dump_session(session: AiAgentSession) -> dict[str, Any]:
    """转换 session ORM 为诊断字典。"""

    return {
        "session_id": session.session_id,
        "agent_id": session.agent_id,
        "user_id": session.user_id,
        "session_name": session.session_name,
        "scope_type": session.scope_type,
        "workspace_id": session.workspace_id,
        "project_id": session.project_id,
        "page_id": session.page_id,
        "component_id": session.component_id,
        "source": session.source,
        "metadata": session.metadata_json or {},
        "summary": session.summary_json,
        "deleted_at": _iso(session.deleted_at),
        "created_at": _iso(session.created_at),
        "updated_at": _iso(session.updated_at),
    }


def _dump_event(event: AiAgentRunEvent) -> dict[str, Any]:
    """转换事件 ORM 为诊断字典。"""

    return {
        "id": event.id,
        "session_id": event.session_id,
        "run_id": event.run_id,
        "event_index": event.event_index,
        "event": event.event,
        "payload": event.payload_json or {},
        "created_at": _iso(event.created_at),
    }


def _dump_tool_call(tool_call: AiAgentToolCall) -> dict[str, Any]:
    """转换工具调用 ORM 为诊断字典。"""

    return {
        "id": tool_call.id,
        "session_id": tool_call.session_id,
        "run_id": tool_call.run_id,
        "member_run_id": tool_call.member_run_id,
        "tool_call_id": tool_call.tool_call_id,
        "tool_name": tool_call.tool_name,
        "status": tool_call.status,
        "risk_level": tool_call.risk_level,
        "input_payload": tool_call.input_payload_json,
        "output_payload": tool_call.output_payload_json,
        "message": tool_call.message,
        "created_at": _iso(tool_call.created_at),
        "updated_at": _iso(tool_call.updated_at),
    }


def _dump_requirement(requirement: AiAgentRequirement) -> dict[str, Any]:
    """转换 HITL requirement ORM 为诊断字典。"""

    return {
        "id": requirement.id,
        "requirement_id": requirement.requirement_id,
        "session_id": requirement.session_id,
        "run_id": requirement.run_id,
        "kind": requirement.kind,
        "status": requirement.status,
        "tool_call_id": requirement.tool_call_id,
        "tool_name": requirement.tool_name,
        "member_agent_id": requirement.member_agent_id,
        "member_agent_name": requirement.member_agent_name,
        "member_run_id": requirement.member_run_id,
        "payload": requirement.payload_json or {},
        "resolved_payload": requirement.resolved_payload_json,
        "resolved_at": _iso(requirement.resolved_at),
        "created_at": _iso(requirement.created_at),
        "updated_at": _iso(requirement.updated_at),
    }


def _dump_message(message: AiAgentMessage) -> dict[str, Any]:
    """转换会话消息 ORM 为诊断字典。"""

    return {
        "id": message.id,
        "session_id": message.session_id,
        "run_id": message.run_id,
        "role": message.role,
        "content": message.content,
        "reasoning_content": message.reasoning_content,
        "message_json": message.message_json,
        "attachments": message.attachments_json or [],
        "order_index": message.order_index,
        "created_at": _iso(message.created_at),
        "updated_at": _iso(message.updated_at),
    }


def _summarize_message_history(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """生成 Pydantic AI message history 的轻量摘要。"""

    items = history if isinstance(history, list) else []
    kinds: list[str] = []
    part_kinds: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind:
            kinds.append(kind)
        parts = item.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                part_kind = str(part.get("part_kind") or "").strip()
                if part_kind:
                    part_kinds.append(part_kind)
    return {
        "count": len(items),
        "kinds": kinds,
        "part_kinds": part_kinds,
    }


def _format_summary_checkpoint(checkpoint: dict[str, Any] | None) -> str:
    """格式化 session.summary_json 压缩检查点边界，便于诊断压缩覆盖范围。"""

    if not checkpoint:
        return "-"
    kind = str(checkpoint.get("kind") or "unknown")
    covered_run_id = str(checkpoint.get("covered_until_run_id") or "-")
    covered_created_at = str(checkpoint.get("covered_until_created_at") or "-")
    summary = _preview(checkpoint.get("summary"))
    return f"{kind} covered_until_run_id={covered_run_id} covered_until_created_at={covered_created_at} summary={summary}"


def _preview_event_payload(item: dict[str, Any]) -> str:
    """提取事件 payload 的短摘要，避免 summary 输出过长。"""

    payload = item.get("payload")
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    data = payload.get("data")
    parts = []
    if content:
        parts.append(f"content={_preview(content)}")
    if data:
        parts.append(f"data={_preview(data)}")
    return " ".join(parts)


def _preview(value: Any, *, max_length: int = 160) -> str:
    """把任意值压缩为单行短文本，供 summary 输出。"""

    if value is None:
        return "-"
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length - 1]}…"


def _iso(value: datetime | None) -> str | None:
    """把 datetime 转为 ISO 字符串。"""

    return value.isoformat() if value is not None else None


if __name__ == "__main__":
    main()
