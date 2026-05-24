"""文件功能：修复 Redis 已终态但 Agno session 仍残留 HITL 暂停态的历史 run。"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from agno.db.base import SessionType
from agno.run.base import RunStatus
from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from fastapi.encoders import jsonable_encoder

from app.ai.db import build_agno_db
from app.services.ai_agent_run_service import sync_agno_run_status
from app.services.ai_run_state_store import AI_RUN_TERMINAL_STATUSES, AiRunRecord, AiRunStateStore


async def main() -> None:
    """扫描 Redis 终态 run，并按需修正 Agno session。"""

    parser = argparse.ArgumentParser(description="修复 Agno HITL 终态残留。")
    parser.add_argument("--apply", action="store_true", help="实际写入修复；默认只打印将要修复的 run。")
    args = parser.parse_args()

    store = AiRunStateStore()
    ai_db = build_agno_db()
    records = await _iter_terminal_records(store)
    repaired = 0
    for record in records:
        status = _task_status_to_agno_status(record.status)
        if status not in {RunStatus.completed, RunStatus.cancelled}:
            continue
        if not await _needs_repair(ai_db, record=record, expected_status=status):
            continue
        repaired += 1
        print(
            f"{'[APPLY]' if args.apply else '[DRY-RUN]'} "
            f"session={record.session_id} run={record.run_id} status={record.status}"
        )
        if args.apply:
            await sync_agno_run_status(
                ai_db=ai_db,
                user_id=str(record.user_id),
                session_id=record.session_id,
                agent_id=record.agent_id,
                run_id=record.run_id,
                status=status,
                content=record.error_message,
            )
    print(f"matched={repaired} total_terminal={len(records)}")


async def _iter_terminal_records(store: AiRunStateStore) -> list[AiRunRecord]:
    """从 Redis 中扫描仍在 TTL 内的终态 run 记录。"""

    keys = await asyncio.to_thread(list, store.runtime.client.scan_iter(match=store.runtime.key("ai:run:*")))
    records: list[AiRunRecord] = []
    for key in keys:
        if str(key).endswith(":events") or ":cancel" in str(key):
            continue
        payload = await asyncio.to_thread(store.runtime.client.hgetall, key)
        record = store._record_from_hash(payload)  # noqa: SLF001
        if record is not None and record.status in AI_RUN_TERMINAL_STATUSES:
            records.append(record)
    return records


async def _needs_repair(ai_db: Any, *, record: AiRunRecord, expected_status: RunStatus) -> bool:
    """判断 Agno session 中的 run 是否仍保留错误状态或未解决 HITL。"""

    for session_type in (SessionType.TEAM, SessionType.AGENT):
        detail = await asyncio.to_thread(ai_db.get_session, record.session_id, session_type, str(record.user_id), True)
        if not isinstance(detail, (AgentSession, TeamSession)):
            continue
        owner_id = getattr(detail, "team_id", None) or getattr(detail, "agent_id", None)
        if owner_id and str(owner_id) != record.agent_id:
            continue
        run = detail.get_run(record.run_id)
        if run is None:
            return False
        if getattr(run, "status", None) != expected_status:
            return True
        payload = jsonable_encoder(run)
        return isinstance(payload, dict) and _has_active_hitl(payload)
    return False


def _has_active_hitl(payload: dict[str, Any]) -> bool:
    """按 Agno 序列化字段判断是否仍存在未解决 HITL。"""

    for requirement in payload.get("requirements") or []:
        if isinstance(requirement, dict) and _requirement_active(requirement):
            return True
    for tool in payload.get("tools") or []:
        if isinstance(tool, dict) and _tool_active(tool):
            return True
    return False


def _requirement_active(requirement: dict[str, Any]) -> bool:
    """判断单个 requirement 是否仍未解决。"""

    tool = requirement.get("tool_execution") or {}
    if not isinstance(tool, dict):
        return False
    if tool.get("requires_confirmation") and requirement.get("confirmation") is None and tool.get("confirmed") is None:
        return True
    if tool.get("requires_user_input") and tool.get("answered") is not True:
        return True
    if tool.get("external_execution_required") and requirement.get("external_execution_result") is None and tool.get("result") is None:
        return True
    return False


def _tool_active(tool: dict[str, Any]) -> bool:
    """判断单个 ToolExecution 是否仍处于暂停态。"""

    if tool.get("requires_confirmation") and tool.get("confirmed") is None:
        return True
    if tool.get("requires_user_input") and tool.get("answered") is not True:
        return True
    if tool.get("external_execution_required") and tool.get("result") is None:
        return True
    return False


def _task_status_to_agno_status(status: str) -> RunStatus:
    """把 Redis run 状态映射为 Agno 状态。"""

    if status == "completed":
        return RunStatus.completed
    if status == "cancelled":
        return RunStatus.cancelled
    return RunStatus.error


if __name__ == "__main__":
    asyncio.run(main())
