"""文件功能：提供 Redis 运行态切换前的旧 Agent run 检查、暂停态迁移与强制收敛 CLI。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from agno.run.base import RunStatus
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.ai.db import build_agno_db
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.ai_agent_run import AiAgentRunEvent, AiAgentRunTask
from app.schemas.agent import AgentRunEvent, AgentScopeContext
from app.services.ai_agent_run_service import sync_agno_run_status
from app.services.ai_run_state_store import AiRunStateStore
from app.services.redis_runtime_client import ensure_redis_runtime_available

BLOCKING_STATUSES = {"pending", "running", "cancelling"}
PAUSED_STATUS = "paused"
TERMINAL_CANCEL_REASON = "Redis 运行态切换维护窗口强制取消。"


async def async_main(argv: list[str] | None = None) -> int:
    """解析 CLI 参数并执行维护窗口检查或迁移动作。"""

    args = _parse_args(argv)
    await ensure_redis_runtime_available()
    session_factory = get_session_factory()
    async with session_factory() as session:
        blocking_tasks = await _list_old_tasks(session, BLOCKING_STATUSES)
        paused_tasks = await _list_old_tasks(session, {PAUSED_STATUS})

        _print_summary(blocking_tasks=blocking_tasks, paused_tasks=paused_tasks)
        if blocking_tasks and not args.force_cancel_active:
            print("发现旧 DB 中仍有 pending/running/cancelling run，默认阻断切换。")
            print("确认维护窗口内要终止这些 run 时，可追加 --force-cancel-active。")
            return 2

        migrated = 0
        cancelled = 0
        if args.migrate_paused:
            migrated = await _migrate_paused_tasks(paused_tasks)
        elif paused_tasks:
            print("发现旧 DB 中存在 paused run；未指定 --migrate-paused，本次仅检查不迁移。")

        if args.force_cancel_active:
            cancelled = await _force_cancel_active_tasks(session, blocking_tasks)
            await session.commit()

        print(f"Redis 运行态切换检查完成：migrated_paused={migrated}, force_cancelled_active={cancelled}")
        return 0


def main() -> None:
    """同步 CLI 入口。"""

    raise SystemExit(asyncio.run(async_main()))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """解析维护窗口 CLI 参数。"""

    parser = argparse.ArgumentParser(
        description="检查旧 AiAgentRunTask/AiAgentRunEvent，并为 Redis 运行态切换迁移 paused run。",
    )
    parser.add_argument(
        "--migrate-paused",
        action="store_true",
        help="把旧 DB 中 paused run 迁入 Redis run hash、事件 stream 与 active_run key。",
    )
    parser.add_argument(
        "--force-cancel-active",
        action="store_true",
        help="把旧 DB 中 pending/running/cancelling run 标记为 cancelled，并同步 Agno session.runs。",
    )
    return parser.parse_args(argv)


async def _list_old_tasks(session, statuses: set[str]) -> list[AiAgentRunTask]:
    """按状态读取旧 DB run task；旧表不存在或不可读时直接抛出明确错误。"""

    try:
        result = await session.execute(
            select(AiAgentRunTask)
            .where(AiAgentRunTask.status.in_(statuses))
            .order_by(AiAgentRunTask.updated_at.desc(), AiAgentRunTask.run_id.asc())
        )
    except SQLAlchemyError as exc:
        raise RuntimeError("读取旧 ai_agent_run_tasks 表失败，请确认迁移版本与数据库结构。") from exc
    return list(result.scalars().all())


async def _migrate_paused_tasks(tasks: list[AiAgentRunTask]) -> int:
    """把旧 paused run 迁入 Redis，保留事件回放、工具授权与暂停 requirement。"""

    store = AiRunStateStore()
    migrated = 0
    for task in tasks:
        existing = await store.get_run(run_id=task.run_id, user_id=task.user_id)
        if existing is None:
            await store.create_run(
                run_id=task.run_id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                user_id=task.user_id,
                backend_session_id=task.backend_session_id,
                scope=_scope_from_task(task),
                input_summary=task.input_summary,
                input_payload_json=task.input_payload_json,
                tool_scopes=task.tool_scopes_json or [],
            )
            await _copy_old_events_to_redis(store=store, task=task)
        await store.update_run_fields(
            run_id=task.run_id,
            user_id=task.user_id,
            fields={
                "status": PAUSED_STATUS,
                "pending_requirement_json": task.pending_requirement_json,
                "input_payload_json": task.input_payload_json,
                "tool_scopes_json": task.tool_scopes_json or [],
                "tool_auth_expires_at": task.tool_auth_expires_at,
                "tool_auth_max_expires_at": task.tool_auth_max_expires_at,
                "event_sequence": task.event_sequence,
                "cancel_requested_at": task.cancel_requested_at,
                "started_at": task.started_at,
                "finished_at": None,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            },
        )
        await _refresh_paused_active_key(store=store, task=task)
        migrated += 1
        print(f"已迁移 paused run 到 Redis：run_id={task.run_id}, session_id={task.session_id}")
    return migrated


async def _copy_old_events_to_redis(*, store: AiRunStateStore, task: AiAgentRunTask) -> None:
    """把旧事件表内容顺序写入 Redis Stream。"""

    async with get_session_factory()() as session:
        result = await session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.task_id == task.task_id)
            .order_by(AiAgentRunEvent.sequence.asc(), AiAgentRunEvent.id.asc())
        )
        for old_event in result.scalars().all():
            event = _event_from_old_row(old_event)
            event.sequence = None
            await store.append_event(run_id=task.run_id, user_id=task.user_id, event=event)


async def _refresh_paused_active_key(*, store: AiRunStateStore, task: AiAgentRunTask) -> None:
    """把 migrated paused run 的 active_run key TTL 延长为暂停态窗口。"""

    key = store.runtime.key(f"ai:session:{task.user_id}:{task.agent_id}:{task.session_id}:active_run")
    await asyncio.to_thread(
        store.runtime.client.set,
        key,
        task.run_id,
        ex=get_settings().ai_run_paused_ttl_seconds,
    )


async def _force_cancel_active_tasks(session, tasks: list[AiAgentRunTask]) -> int:
    """把旧 DB 中仍活跃的 run 强制收敛为 cancelled，并同步 Agno 会话状态。"""

    if not tasks:
        return 0
    ai_db = build_agno_db()
    now = datetime.now(UTC)
    for task in tasks:
        task.status = "cancelled"
        task.error_message = TERMINAL_CANCEL_REASON
        task.finished_at = now
        task.cancel_requested_at = task.cancel_requested_at or now
        task.event_sequence = int(task.event_sequence or 0) + 1
        session.add(
            AiAgentRunEvent(
                task_id=task.task_id,
                run_id=task.run_id,
                sequence=task.event_sequence,
                event="run.cancelled",
                payload_json=AgentRunEvent(
                    event="run.cancelled",
                    run_id=task.run_id,
                    session_id=task.session_id,
                    content=TERMINAL_CANCEL_REASON,
                    sequence=task.event_sequence,
                    data={"message": TERMINAL_CANCEL_REASON},
                ).model_dump(mode="json"),
            )
        )
        await sync_agno_run_status(
            ai_db=ai_db,
            user_id=str(task.user_id),
            session_id=task.session_id,
            agent_id=task.agent_id,
            run_id=task.run_id,
            status=RunStatus.cancelled,
            content=TERMINAL_CANCEL_REASON,
        )
        print(f"已强制取消旧 active run：run_id={task.run_id}, session_id={task.session_id}")
    return len(tasks)


def _event_from_old_row(row: AiAgentRunEvent) -> AgentRunEvent:
    """把旧事件表行转换为标准 AgentRunEvent。"""

    payload = row.payload_json if isinstance(row.payload_json, dict) else {}
    if payload:
        event = AgentRunEvent.model_validate(payload)
    else:
        event = AgentRunEvent(event=row.event, run_id=row.run_id, data={})
    event.event = event.event or row.event
    event.run_id = event.run_id or row.run_id
    return event


def _scope_from_task(task: AiAgentRunTask) -> AgentScopeContext:
    """从旧 task 行恢复 AgentScopeContext。"""

    return AgentScopeContext(
        scope_type=task.scope_type,  # type: ignore[arg-type]
        workspace_id=task.workspace_id,
        project_id=task.project_id,
        page_id=task.page_id,
        component_id=task.component_id,
        source=task.source,
    )


def _print_summary(*, blocking_tasks: list[AiAgentRunTask], paused_tasks: list[AiAgentRunTask]) -> None:
    """输出切换前检查摘要。"""

    print(
        "旧 Agent run 检查："
        f"blocking={len(blocking_tasks)}(pending/running/cancelling), paused={len(paused_tasks)}"
    )
    for task in [*blocking_tasks[:5], *paused_tasks[:5]]:
        print(
            f"- run_id={task.run_id}, session_id={task.session_id}, "
            f"agent_id={task.agent_id}, status={task.status}, updated_at={task.updated_at}"
        )


if __name__ == "__main__":
    main()
