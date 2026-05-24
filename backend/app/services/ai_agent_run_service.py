"""文件功能：管理智能体后台 run 任务、事件回放与状态收敛。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from agno.db.base import SessionType
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput
from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_run import AiAgentRunEvent, AiAgentRunTask
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentPendingRequirement,
    AgentRunEvent,
    AgentScopeContext,
    AgentToolCallDetailItem,
)
from app.services.ai_run_state_store import AiRunRecord, AiRunStateStore

AI_RUN_ACTIVE_STATUSES = {"pending", "running", "paused", "cancelling"}
AI_RUN_TERMINAL_STATUSES = {"completed", "cancelled", "failed"}
AI_RUN_EVENT_TERMINAL = {"run.completed", "run.cancelled", "run.error", "run.paused"}
AI_TOOL_AUTH_RUN_STATUSES = {"pending", "running"}


class AiAgentRunService:
    """封装后台 run task 的创建、查询、事件写入和状态更新。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.run_state_store = AiRunStateStore()

    async def create_task(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        user_id: int,
        backend_session_id: str | None,
        scope: AgentScopeContext,
        input_summary: str | None,
        input_payload_json: dict[str, Any] | None = None,
        tool_scopes: Iterable[str] | None = None,
    ) -> AiRunRecord:
        """创建后台执行任务运行态；Redis 负责会话互斥与短租约。"""

        return await self.run_state_store.create_run(
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            backend_session_id=backend_session_id,
            scope=scope,
            input_summary=input_summary,
            input_payload_json=input_payload_json,
            tool_scopes=_dedupe_tool_scopes(tool_scopes or ()),
        )

    async def get_latest_task(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: int,
    ) -> AiRunRecord | None:
        """读取当前会话最近一次 Redis run 运行态。"""

        return await self.run_state_store.get_latest_run(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
        )

    async def authorize_tool_call(
        self,
        *,
        run_id: str,
        user_id: int,
        session_id: str,
        agent_id: str,
        backend_session_id: str | None,
        source: str,
        required_scopes: Iterable[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """按 Redis run 校验工具授权，并在成功后刷新短租约。"""

        return await self.run_state_store.authorize_tool_call(
            run_id=run_id,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            backend_session_id=backend_session_id,
            source=source,
            required_scopes=list(required_scopes),
        )

    async def get_latest_active_task(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: int,
    ) -> AiRunRecord | None:
        """读取当前会话最近的非终态 Redis run。"""

        return await self.run_state_store.get_latest_active_run(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
        )

    async def get_task_by_run(
        self,
        *,
        run_id: str,
        user_id: int,
    ) -> AiRunRecord | None:
        """按 run_id 读取当前用户的 Redis 运行态。"""

        return await self.run_state_store.get_run(run_id=run_id, user_id=user_id)

    async def append_event(self, *, run_id: str, event: AgentRunEvent) -> AgentRunEvent | None:
        """追加一个标准化事件并同步 Redis run 状态。"""

        return await self.run_state_store.append_event(run_id=run_id, user_id=None, event=event)

    async def _is_replayed_pause_event_after_continue(self, *, task: AiAgentRunTask, event: AgentRunEvent) -> bool:
        """继续运行后忽略 Agno 回放的上一条 pause，避免 task 被误写回暂停态。"""

        if task.status != "running" or event.event != "run.paused":
            return False
        current_requirement = _extract_event_requirement(event.data)
        current_identity = _pending_requirement_identity(current_requirement)
        if current_identity is None:
            return False

        result = await self.session.execute(
            select(AiAgentRunEvent.payload_json)
            .where(
                AiAgentRunEvent.task_id == task.task_id,
                AiAgentRunEvent.event == "run.paused",
            )
            .order_by(AiAgentRunEvent.sequence.desc(), AiAgentRunEvent.id.desc())
            .limit(1)
        )
        previous_payload = result.scalar_one_or_none()
        if not isinstance(previous_payload, dict):
            return False
        previous_requirement = _extract_event_requirement(previous_payload.get("data"))
        return current_identity == _pending_requirement_identity(previous_requirement)

    async def list_events_after(
        self,
        *,
        run_id: str,
        user_id: int,
        after_sequence: int,
    ) -> list[AgentRunEvent]:
        """按序读取指定 run 在某个序号后的 Redis Stream 事件。"""

        return await self.run_state_store.list_events_after(
            run_id=run_id,
            user_id=user_id,
            after_sequence=after_sequence,
        )

    async def mark_cancelling(self, *, task: AiRunRecord | AiAgentRunTask) -> AgentRunEvent | None:
        """把 running/pending 任务标记为停止中，并写入可回放事件。"""

        if task.status in AI_RUN_TERMINAL_STATUSES:
            return None
        return await self.append_event(
            run_id=task.run_id,
            event=AgentRunEvent(
                event="run.cancelling",
                run_id=task.run_id,
                session_id=task.session_id,
                data={"message": "用户请求停止当前运行。"},
            ),
        )

    async def mark_running(self, *, task: AiRunRecord | AiAgentRunTask, reset_tool_auth: bool = False) -> AiRunRecord | AiAgentRunTask:
        """把待继续或待启动任务预先标记为 running，必要时重置工具授权周期。"""

        if isinstance(task, AiRunRecord):
            return await self.run_state_store.mark_running(record=task, reset_tool_auth=reset_tool_auth)
        return await self.run_state_store.mark_running(record=await self._coerce_redis_record(task), reset_tool_auth=reset_tool_auth)

    @staticmethod
    def _refresh_tool_auth_window(
        *,
        task: AiAgentRunTask,
        now: datetime,
        reset_max: bool = False,
    ) -> None:
        """刷新工具短租约；继续 paused run 时可同步重置绝对上限。"""

        settings = get_settings()
        if reset_max:
            task.tool_auth_max_expires_at = now + timedelta(seconds=settings.ai_tool_auth_max_seconds)
        if task.tool_auth_max_expires_at is None:
            return
        task.tool_auth_expires_at = min(
            now + timedelta(seconds=settings.ai_tool_auth_window_seconds),
            _ensure_aware(task.tool_auth_max_expires_at),
        )

    async def mark_paused(
        self,
        *,
        task: AiRunRecord | AiAgentRunTask,
        pending_requirement: AgentPendingRequirement,
        append_event: bool = True,
        allow_terminal_restore: bool = False,
    ) -> AiRunRecord | AiAgentRunTask:
        """把 run 收敛到暂停态，用于恢复 Agno 中仍未解决的 HITL requirement。"""

        record = task if isinstance(task, AiRunRecord) else await self._coerce_redis_record(task)
        return await self.run_state_store.mark_paused(
            record=record,
            pending_requirement=pending_requirement,
            append_event=append_event,
            allow_terminal_restore=allow_terminal_restore,
        )

    async def mark_terminal(
        self,
        *,
        task: AiRunRecord | AiAgentRunTask,
        status: str,
        content: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunEvent:
        """强制把任务推进到终态，并补写一个终态事件。"""

        record = task if isinstance(task, AiRunRecord) else await self._coerce_redis_record(task)
        return await self.run_state_store.mark_terminal(
            record=record,
            status=status,
            content=content,
            error_code=error_code,
            error_message=error_message,
        )

    async def preserve_user_cancelled_run_output(self, *, ai_db: Any | None, task: AiRunRecord | AiAgentRunTask) -> bool:
        """把用户停止前的完整回合补写回 Agno run.messages。"""

        if ai_db is None:
            return False
        task = await self._coerce_redis_record(task)
        if task.status != "cancelled":
            return False
        if not await self._task_has_user_cancel_request(task):
            return False
        turn_payload = await self._aggregate_cancelled_turn_payload(task)
        user_content = _resolve_task_input_content(task)
        assistant_content = turn_payload["content"]
        reasoning_content = turn_payload["reasoning_content"]
        should_add_assistant = bool(assistant_content or reasoning_content or turn_payload["has_tool_events"])

        detail = await _to_thread_get_session(
            ai_db,
            session_id=task.session_id,
            user_id=str(task.user_id),
            owner_id=task.agent_id,
        )
        if not isinstance(detail, (AgentSession, TeamSession)):
            return False
        run = detail.get_run(task.run_id)
        if run is None:
            if isinstance(detail, TeamSession):
                run = TeamRunOutput(
                    run_id=task.run_id,
                    session_id=task.session_id,
                    team_id=task.agent_id,
                    user_id=str(task.user_id),
                    status=RunStatus.cancelled,
                    created_at=_message_timestamp(task.created_at),
                )
            else:
                run = RunOutput(
                    run_id=task.run_id,
                    session_id=task.session_id,
                    agent_id=task.agent_id,
                    user_id=str(task.user_id),
                    status=RunStatus.cancelled,
                    created_at=_message_timestamp(task.created_at),
                )
        changed = False
        messages = list(run.messages or [])
        if not _has_current_run_message(messages, "user"):
            messages.append(Message(role="user", content=user_content, created_at=_message_timestamp(task.created_at)))
            changed = True
        assistant_message = _find_current_run_message(messages, "assistant")
        if should_add_assistant:
            if assistant_message is None:
                messages.append(
                    Message(
                        role="assistant",
                        content=assistant_content,
                        reasoning_content=reasoning_content or None,
                        created_at=turn_payload["assistant_created_at"],
                    )
                )
                changed = True
            else:
                if assistant_content and not _coerce_str(getattr(assistant_message, "content", None)):
                    assistant_message.content = assistant_content
                    changed = True
                if reasoning_content and not _coerce_str(getattr(assistant_message, "reasoning_content", None)):
                    assistant_message.reasoning_content = reasoning_content
                    changed = True
        run.messages = messages
        if should_add_assistant:
            run.content = assistant_content
            if hasattr(run, "reasoning_content"):
                run.reasoning_content = reasoning_content or None
        run.status = RunStatus.cancelled
        metadata = dict(run.metadata or {})
        metadata["user_cancel_preserved"] = True
        metadata["user_message_preserved"] = True
        metadata["preserved_tool_event_count"] = turn_payload["tool_event_count"]
        run.metadata = metadata
        detail.upsert_run(run)
        await _to_thread_upsert_session(ai_db, detail)
        return changed

    async def finalize_user_cancelled_task_if_needed(self, *, task: AiRunRecord | AiAgentRunTask) -> AgentRunEvent | None:
        """后台流结束时兜底收敛已请求停止但未收到 Agno 终态事件的任务。"""

        if task.status in AI_RUN_TERMINAL_STATUSES:
            return None
        if not await self._task_has_user_cancel_request(task):
            return None
        return await self.mark_terminal(
            task=task,
            status="cancelled",
            content="当前运行已被用户取消。",
        )

    async def list_tool_details_for_session(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: int,
        assistant_message_ids_by_run: dict[str, str] | None = None,
    ) -> list[AgentToolCallDetailItem]:
        """从 Redis Stream 与旧事件表恢复会话历史工具详情，避免污染 Agno 消息历史。"""

        result = await self.session.execute(
            select(AiAgentRunTask, AiAgentRunEvent)
            .join(AiAgentRunEvent, AiAgentRunEvent.task_id == AiAgentRunTask.task_id)
            .where(
                AiAgentRunTask.session_id == session_id,
                AiAgentRunTask.agent_id == agent_id,
                AiAgentRunTask.user_id == user_id,
                AiAgentRunEvent.event.in_({"tool.started", "tool.completed", "tool.error"}),
            )
            .order_by(AiAgentRunTask.created_at.asc(), AiAgentRunEvent.sequence.asc())
        )
        detail_by_id: dict[str, AgentToolCallDetailItem] = {}
        pending_without_call_id: dict[tuple[str, str], str] = {}
        assistant_ids = assistant_message_ids_by_run or {}
        for task, event_row in result.all():
            payload = event_row.payload_json if isinstance(event_row.payload_json, dict) else {}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            tool_name = _coerce_str(data.get("tool_name")) or "工具调用"
            tool_call_id = _coerce_str(data.get("tool_call_id"))
            detail_id = _resolve_tool_detail_id(
                run_id=task.run_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                event_name=event_row.event,
                sequence=event_row.sequence,
                pending_without_call_id=pending_without_call_id,
            )
            existing = detail_by_id.get(detail_id)
            member_agent_id = _coerce_str(data.get("member_agent_id")) or (existing.member_agent_id if existing else None)
            member_agent_name = _coerce_str(data.get("member_agent_name")) or (existing.member_agent_name if existing else None)
            member_run_id = _coerce_str(data.get("member_run_id")) or (existing.member_run_id if existing else None)
            input_payload = _first_present(data, "arguments", "args", "tool_args", fallback=existing.input_payload if existing else None)
            output_payload = _first_present(data, "result", "output", fallback=existing.output_payload if existing else None)
            message = _coerce_str(data.get("message")) or _coerce_str(payload.get("content")) or (existing.message if existing else "")
            detail_by_id[detail_id] = AgentToolCallDetailItem(
                id=detail_id,
                run_id=task.run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                member_agent_id=member_agent_id,
                member_agent_name=member_agent_name,
                member_run_id=member_run_id,
                status=_tool_status_for_event(event_row.event),  # type: ignore[arg-type]
                assistant_message_id=assistant_ids.get(task.run_id),
                input_payload=input_payload,
                output_payload=output_payload,
                message=message,
                created_at=existing.created_at if existing else _format_datetime(event_row.created_at),
            )
        for record in await self.run_state_store.list_runs_for_session(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
        ):
            for event in await self.run_state_store.list_events_after(
                run_id=record.run_id,
                user_id=user_id,
                after_sequence=0,
            ):
                if event.event not in {"tool.started", "tool.completed", "tool.error"}:
                    continue
                data = event.data if isinstance(event.data, dict) else {}
                tool_name = _coerce_str(data.get("tool_name")) or "工具调用"
                tool_call_id = _coerce_str(data.get("tool_call_id"))
                sequence = int(event.sequence or 0)
                detail_id = _resolve_tool_detail_id(
                    run_id=record.run_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    event_name=event.event,
                    sequence=sequence,
                    pending_without_call_id=pending_without_call_id,
                )
                existing = detail_by_id.get(detail_id)
                member_agent_id = _coerce_str(data.get("member_agent_id")) or (existing.member_agent_id if existing else None)
                member_agent_name = _coerce_str(data.get("member_agent_name")) or (existing.member_agent_name if existing else None)
                member_run_id = _coerce_str(data.get("member_run_id")) or (existing.member_run_id if existing else None)
                input_payload = _first_present(data, "arguments", "args", "tool_args", fallback=existing.input_payload if existing else None)
                output_payload = _first_present(data, "result", "output", fallback=existing.output_payload if existing else None)
                message = _coerce_str(data.get("message")) or _coerce_str(event.content) or (existing.message if existing else "")
                detail_by_id[detail_id] = AgentToolCallDetailItem(
                    id=detail_id,
                    run_id=record.run_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    member_agent_id=member_agent_id,
                    member_agent_name=member_agent_name,
                    member_run_id=member_run_id,
                    status=_tool_status_for_event(event.event),  # type: ignore[arg-type]
                    assistant_message_id=assistant_ids.get(record.run_id),
                    input_payload=input_payload,
                    output_payload=output_payload,
                    message=message,
                    created_at=existing.created_at if existing else _format_datetime(record.updated_at or record.created_at),
                )
        return list(detail_by_id.values())

    async def recover_interrupted_tasks(self, *, ai_db: Any | None = None) -> int:
        """应用启动时终止上次进程遗留的 Redis 非终态 run，避免会话永久占用。"""

        tasks = await self.run_state_store.iter_active_orphan_runs()
        for task in tasks:
            pending_requirement = None
            if ai_db is not None and task.cancel_requested_at is None:
                pending_requirement = await _extract_pending_requirement_from_agno(ai_db=ai_db, task=task)
            if pending_requirement is not None:
                await self.mark_paused(task=task, pending_requirement=pending_requirement)
                continue
            await self.mark_terminal(
                task=task,
                status="cancelled",
                content="后端服务已重启，上一次运行已被系统终止。",
            )
            if ai_db is not None:
                await sync_agno_run_status(
                    ai_db=ai_db,
                    user_id=str(task.user_id),
                    session_id=task.session_id,
                    agent_id=task.agent_id,
                    run_id=task.run_id,
                    status=RunStatus.cancelled,
                    content="后端服务已重启，上一次运行已被系统终止。",
                )
        return len(tasks)

    async def _coerce_redis_record(self, task: AiRunRecord | AiAgentRunTask) -> AiRunRecord:
        """按 run_id 取得 Redis 运行态；兼容旧 DB task 参数。"""

        if isinstance(task, AiRunRecord):
            return task
        record = await self.run_state_store.get_run(run_id=task.run_id, user_id=task.user_id)
        if record is None:
            raise RuntimeError(f"AI run state not found: {task.run_id}")
        return record

    async def _get_task_by_run_for_update(self, run_id: str) -> AiAgentRunTask | None:
        """锁定任务行后写事件序号，避免后台流和取消接口并发抢同一 sequence。"""

        result = await self.session.execute(
            select(AiAgentRunTask)
            .where(AiAgentRunTask.run_id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _task_has_user_cancel_request(self, task: AiRunRecord | AiAgentRunTask) -> bool:
        """判断当前 task 是否由用户主动停止触发。"""

        if task.cancel_requested_at is not None:
            return True
        if isinstance(task, AiRunRecord):
            events = await self.run_state_store.list_events_after(
                run_id=task.run_id,
                user_id=task.user_id,
                after_sequence=0,
            )
            return any(event.event == "run.cancelling" for event in events)
        result = await self.session.execute(
            select(AiAgentRunEvent.id)
            .where(
                AiAgentRunEvent.task_id == task.task_id,
                AiAgentRunEvent.event == "run.cancelling",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _aggregate_cancelled_turn_payload(self, task: AiRunRecord | AiAgentRunTask) -> dict[str, Any]:
        """聚合本轮已向 UI 暴露的正文、thinking 与工具事件信息。"""

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_event_count = 0
        assistant_created_at = _message_timestamp(task.updated_at or task.created_at)
        if isinstance(task, AiRunRecord):
            events = await self.run_state_store.list_events_after(
                run_id=task.run_id,
                user_id=task.user_id,
                after_sequence=0,
            )
            for event in events:
                payload = event.model_dump(mode="json")
                if event.event == "message.delta":
                    content = payload.get("content")
                    if isinstance(content, str):
                        content_parts.append(content)
                    data = payload.get("data")
                    reasoning_content = data.get("reasoning_content") if isinstance(data, dict) else None
                    if isinstance(reasoning_content, str):
                        reasoning_parts.append(reasoning_content)
                if event.event in {"tool.started", "tool.completed", "tool.error"}:
                    tool_event_count += 1
            return {
                "content": "".join(content_parts),
                "reasoning_content": "".join(reasoning_parts),
                "has_tool_events": tool_event_count > 0,
                "tool_event_count": tool_event_count,
                "assistant_created_at": assistant_created_at,
            }

        result = await self.session.execute(
            select(AiAgentRunEvent)
            .where(
                AiAgentRunEvent.task_id == task.task_id,
            )
            .order_by(AiAgentRunEvent.sequence.asc())
        )
        for item in result.scalars().all():
            payload = item.payload_json or {}
            if item.event == "message.delta" and isinstance(payload, dict):
                content = payload.get("content")
                if isinstance(content, str):
                    content_parts.append(content)
                data = payload.get("data")
                reasoning_content = data.get("reasoning_content") if isinstance(data, dict) else None
                if isinstance(reasoning_content, str):
                    reasoning_parts.append(reasoning_content)
                assistant_created_at = _message_timestamp(item.created_at)
            if item.event in {"tool.started", "tool.completed", "tool.error"}:
                tool_event_count += 1
                assistant_created_at = _message_timestamp(item.created_at)
        return {
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
            "has_tool_events": tool_event_count > 0,
            "tool_event_count": tool_event_count,
            "assistant_created_at": assistant_created_at,
        }

    def _apply_event_to_task(self, task: AiAgentRunTask, event: AgentRunEvent) -> None:
        """根据事件类型同步任务状态、待确认动作和错误信息。"""

        if task.status in AI_RUN_TERMINAL_STATUSES:
            return
        now = utc_now()
        if event.event in {"run.started", "run.continued"}:
            task.status = "running"
            task.pending_requirement_json = None
            task.started_at = task.started_at or now
            return
        if event.event == "run.cancelling":
            task.status = "cancelling"
            task.pending_requirement_json = None
            task.cancel_requested_at = task.cancel_requested_at or now
            return
        if event.event == "run.paused":
            task.status = "paused"
            requirement = event.data.get("requirement") if isinstance(event.data, dict) else None
            task.pending_requirement_json = requirement if isinstance(requirement, dict) else None
            return
        if event.event == "run.completed":
            task.status = "completed"
            task.pending_requirement_json = None
            task.finished_at = now
            return
        if event.event == "run.cancelled":
            task.status = "cancelled"
            task.pending_requirement_json = None
            task.finished_at = now
            return
        if event.event == "run.error":
            task.status = "failed"
            task.pending_requirement_json = None
            task.finished_at = now
            if isinstance(event.data, dict):
                task.error_code = _coerce_str(event.data.get("code"))
                task.error_message = _coerce_str(event.data.get("message"))

    def _append_event_for_task(self, task: AiAgentRunTask, event: AgentRunEvent) -> AgentRunEvent:
        """直接为指定 task 追加事件；用于状态恢复时记录修正事件。"""

        sequence = int(task.event_sequence or 0) + 1
        event.sequence = sequence
        event.run_id = event.run_id or task.run_id
        event.session_id = event.session_id or task.session_id
        self.session.add(
            AiAgentRunEvent(
                task_id=task.task_id,
                run_id=task.run_id,
                sequence=sequence,
                event=event.event,
                payload_json=event.model_dump(mode="json"),
            )
        )
        task.event_sequence = sequence
        return event


def map_task_to_active_run(task: AiAgentRunTask) -> AgentActiveRunItem:
    """把后台任务模型映射为 active-run 响应。"""

    return AgentActiveRunItem(
        run_id=task.run_id,
        session_id=task.session_id,
        agent_id=task.agent_id,
        status=task.status,  # type: ignore[arg-type]
        pending_requirement=task.pending_requirement_json,
        content=task.error_message,
        created_at=_format_datetime(task.created_at),
        updated_at=_format_datetime(task.updated_at),
        cancel_requested_at=_format_datetime(task.cancel_requested_at),
        event_sequence=int(task.event_sequence or 0),
    )


async def recover_ai_agent_runs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ai_db: Any | None = None,
) -> int:
    """应用启动入口：清理上次进程遗留的后台 run。"""

    async with session_factory() as session:
        return await AiAgentRunService(session).recover_interrupted_tasks(ai_db=ai_db)


async def sync_agno_run_status(
    *,
    ai_db: Any,
    user_id: str,
    session_id: str,
    agent_id: str,
    run_id: str,
    status: RunStatus,
    content: str | None,
) -> None:
    """同步 Agno session.runs 状态，避免历史非终态 run 阻塞新消息。"""

    detail = await _to_thread_get_session(ai_db, session_id=session_id, user_id=user_id, owner_id=agent_id)
    if not isinstance(detail, (AgentSession, TeamSession)):
        return
    run = detail.get_run(run_id)
    if run is None:
        if isinstance(detail, TeamSession):
            run = TeamRunOutput(run_id=run_id, session_id=session_id, team_id=agent_id, user_id=user_id)
        else:
            run = RunOutput(run_id=run_id, session_id=session_id, agent_id=agent_id, user_id=user_id)
    run.status = status
    if content is not None:
        run.content = content
    _normalize_agno_terminal_run_payload(run, status=status)
    detail.upsert_run(run)
    await _to_thread_upsert_session(ai_db, detail)


async def _to_thread_get_session(ai_db: Any, *, session_id: str, user_id: str, owner_id: str | None = None) -> Any:
    """在线程池中读取 Agno session，优先兼容历史 AgentSession。"""

    import asyncio

    for session_type in (SessionType.AGENT, SessionType.TEAM):
        detail = await asyncio.to_thread(ai_db.get_session, session_id, session_type, user_id, True)
        if isinstance(detail, (AgentSession, TeamSession)):
            if owner_id is not None and _resolve_session_owner_id(detail) != owner_id:
                continue
            return detail
    return None


async def _to_thread_upsert_session(ai_db: Any, detail: AgentSession | TeamSession) -> Any:
    """在线程池中写回 Agno session。"""

    import asyncio

    return await asyncio.to_thread(ai_db.upsert_session, detail)


async def _extract_pending_requirement_from_agno(
    *,
    ai_db: Any,
    task: AiAgentRunTask,
) -> AgentPendingRequirement | None:
    """从 Agno run 中恢复未解决 HITL requirement，供启动恢复使用。"""

    detail = await _to_thread_get_session(
        ai_db,
        session_id=task.session_id,
        user_id=str(task.user_id),
        owner_id=task.agent_id,
    )
    if not isinstance(detail, (AgentSession, TeamSession)):
        return None
    run = detail.get_run(task.run_id)
    if run is None:
        return None
    payload = jsonable_encoder(run)
    if not isinstance(payload, dict):
        return None
    payload.setdefault("run_id", task.run_id)
    payload.setdefault("session_id", task.session_id)
    member_event_data = _extract_member_event_data(payload)
    requirement_payload = _resolve_requirement_payload(payload)
    if requirement_payload is None:
        return None
    tool_execution = requirement_payload.get("tool_execution") or {}
    if not isinstance(tool_execution, dict):
        return None
    user_feedback_schema = _normalize_user_feedback_schema(
        requirement_payload.get("user_feedback_schema") or tool_execution.get("user_feedback_schema")
    )
    tool_name = _coerce_str(tool_execution.get("tool_name"))
    normalized_tool_execution = dict(tool_execution)
    if user_feedback_schema:
        normalized_tool_execution["requires_user_input"] = True
        normalized_tool_execution["user_feedback_schema"] = user_feedback_schema
    return AgentPendingRequirement(
        id=_coerce_str(requirement_payload.get("id")),
        kind="user_feedback" if (tool_name == "ask_user" or user_feedback_schema) else "confirmation",
        run_id=task.run_id,
        session_id=task.session_id,
        member_agent_id=_coerce_str(member_event_data.get("member_agent_id")),
        member_agent_name=_coerce_str(member_event_data.get("member_agent_name")),
        member_run_id=_coerce_str(member_event_data.get("member_run_id")),
        tool_name=tool_name,
        tool_execution=normalized_tool_execution,
        user_feedback_schema=user_feedback_schema,
        note=_coerce_str(normalized_tool_execution.get("confirmation_note")),
    )


def _resolve_requirement_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """从 Agno run payload 中提取第一个仍需要人工处理的 requirement。"""

    requirements = payload.get("requirements") or []
    if isinstance(requirements, list):
        for requirement_payload in reversed(requirements):
            if isinstance(requirement_payload, dict) and _is_requirement_payload_active(requirement_payload):
                return requirement_payload

    tools = payload.get("tools") or []
    if isinstance(tools, list):
        for tool_payload in reversed(tools):
            if isinstance(tool_payload, dict) and _is_tool_execution_payload_active(tool_payload):
                return {"id": None, "tool_execution": tool_payload}
    return None


def _is_requirement_payload_active(requirement_payload: dict[str, Any]) -> bool:
    """判断 Agno RunRequirement 是否仍未解决。"""

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
    """判断 Agno ToolExecution 是否仍处于 HITL 等待态。"""

    if tool_execution.get("requires_confirmation") and tool_execution.get("confirmed") is None:
        return True
    if tool_execution.get("requires_user_input") and tool_execution.get("answered") is not True:
        return True
    if tool_execution.get("external_execution_required") and tool_execution.get("result") is None:
        return True
    return False


def _resolve_session_owner_id(detail: AgentSession | TeamSession) -> str | None:
    """提取 Agno session 所属的 Agent/Team ID。"""

    owner_id = getattr(detail, "agent_id", None) or getattr(detail, "team_id", None)
    if not owner_id:
        agent_data = getattr(detail, "agent_data", None)
        team_data = getattr(detail, "team_data", None)
        if isinstance(agent_data, dict):
            owner_id = agent_data.get("agent_id")
        if not owner_id and isinstance(team_data, dict):
            owner_id = team_data.get("agent_id") or team_data.get("team_id")
    return str(owner_id) if owner_id else None


def _extract_member_event_data(payload: dict[str, Any]) -> dict[str, Any]:
    """从已持久化 run payload 中恢复 Team 成员来源字段。"""

    result: dict[str, Any] = {}
    if payload.get("parent_run_id") is not None:
        result["member_run_id"] = payload.get("run_id")
        result["member_agent_id"] = payload.get("agent_id")
        result["member_agent_name"] = payload.get("agent_name")
    for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
        if payload.get(field_name) is not None:
            result[field_name] = payload.get(field_name)
    requirements = payload.get("requirements") or []
    if isinstance(requirements, list):
        for requirement_payload in reversed(requirements):
            if not isinstance(requirement_payload, dict):
                continue
            for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                if field_name not in result and requirement_payload.get(field_name) is not None:
                    result[field_name] = requirement_payload.get(field_name)
            tool_execution = requirement_payload.get("tool_execution")
            if isinstance(tool_execution, dict):
                for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                    if field_name not in result and tool_execution.get(field_name) is not None:
                        result[field_name] = tool_execution.get(field_name)
    return result


def _normalize_agno_terminal_run_payload(run: RunOutput | TeamRunOutput, *, status: RunStatus) -> None:
    """终态 Agno run 不保留未解决 HITL，避免旧 requirement 被恢复为暂停。"""

    if status not in {RunStatus.completed, RunStatus.cancelled}:
        return
    run.requirements = []
    for item in list(getattr(run, "tools", None) or []):
        if getattr(item, "requires_confirmation", None):
            item.requires_confirmation = False
            if getattr(item, "confirmed", None) is None:
                item.confirmed = status == RunStatus.completed
        if getattr(item, "requires_user_input", None):
            item.requires_user_input = False
            if getattr(item, "answered", None) is not True:
                item.answered = status == RunStatus.completed
        if getattr(item, "external_execution_required", None) and getattr(item, "result", None) is not None:
            item.external_execution_required = False


def _normalize_user_feedback_schema(raw_schema: Any) -> list[dict[str, Any]]:
    """把 Agno ask_user schema 规整为前端单选问题结构。"""

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


def _extract_event_requirement(data: Any) -> dict[str, Any] | None:
    """从标准事件 data 中取出待处理 requirement。"""

    if not isinstance(data, dict):
        return None
    requirement = data.get("requirement")
    return requirement if isinstance(requirement, dict) else None


def _pending_requirement_identity(requirement: dict[str, Any] | None) -> tuple[str, str, str, str] | None:
    """生成 HITL requirement 身份，优先使用稳定的 tool_call_id。"""

    if not isinstance(requirement, dict):
        return None
    tool_execution = requirement.get("tool_execution")
    if not isinstance(tool_execution, dict):
        tool_execution = {}
    member_agent_id = _coerce_str(requirement.get("member_agent_id") or tool_execution.get("member_agent_id")) or ""
    member_run_id = _coerce_str(requirement.get("member_run_id") or tool_execution.get("member_run_id")) or ""
    tool_call_id = _coerce_str(tool_execution.get("tool_call_id"))
    if tool_call_id:
        return ("tool_call_id", tool_call_id, member_agent_id, member_run_id)
    requirement_id = _coerce_str(requirement.get("id"))
    if requirement_id:
        return ("requirement_id", requirement_id, member_agent_id, member_run_id)
    tool_name = _coerce_str(requirement.get("tool_name") or tool_execution.get("tool_name"))
    if tool_name:
        return ("tool_name", tool_name, member_agent_id, member_run_id)
    return None


def task_is_active(task: AiAgentRunTask | None) -> bool:
    """判断后台任务是否仍会阻塞同会话新 run。"""

    return task is not None and task.status in AI_RUN_ACTIVE_STATUSES


def task_status_to_run_status(status: str) -> RunStatus:
    """把 task 状态转换为 Agno RunStatus。"""

    if status == "completed":
        return RunStatus.completed
    if status == "cancelled":
        return RunStatus.cancelled
    if status == "paused":
        return RunStatus.paused
    if status == "failed":
        return RunStatus.error
    return RunStatus.running


def _ensure_tool_context_matches(
    task: AiAgentRunTask,
    *,
    session_id: str,
    agent_id: str,
    backend_session_id: str | None,
    source: str,
) -> None:
    """校验工具调用定位字段与 run task 一致。"""

    expected_values = {
        "session_id": task.session_id,
        "agent_id": task.agent_id,
        "backend_session_id": task.backend_session_id,
        "source": task.source,
    }
    actual_values = {
        "session_id": session_id,
        "agent_id": agent_id,
        "backend_session_id": backend_session_id,
        "source": source,
    }
    for field_name, expected_value in expected_values.items():
        actual_value = actual_values[field_name]
        if expected_value is None and actual_value is None:
            continue
        if str(expected_value) != str(actual_value):
            raise AppException(
                status_code=403,
                code="AI_TOOL_CONTEXT_MISMATCH",
                detail=f"工具上下文校验失败：{field_name} 不匹配。",
            )


def _dedupe_tool_scopes(scopes: Iterable[str]) -> list[str]:
    """按原始顺序去重并清理工具权限 scope。"""

    result: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        normalized = str(scope or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_tool_scopes(value: Any) -> list[str]:
    """把数据库中的工具权限快照规整为字符串列表。"""

    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _ensure_aware(value: datetime) -> datetime:
    """将数据库时间规整为 UTC aware datetime，兼容 SQLite 测试库。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_agent_run_input_payload(*, message: str, image_attachment_ids: list[int]) -> dict[str, Any]:
    """构造后台 run 的完整用户输入快照，取消回写时优先使用。"""

    return {
        "kind": "agent_user_turn",
        "message": message,
        "image_attachment_ids": list(image_attachment_ids),
        "created_at": utc_now().isoformat(),
    }


def _resolve_task_input_content(task: AiAgentRunTask) -> str:
    """从 task 的完整输入 payload 中恢复用户消息正文。"""

    payload = task.input_payload_json if isinstance(task.input_payload_json, dict) else {}
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message
    image_attachment_ids = payload.get("image_attachment_ids")
    if isinstance(image_attachment_ids, list) and image_attachment_ids:
        return "（已发送图片）"
    if task.input_summary and task.input_summary.strip():
        return task.input_summary
    return "（已发送图片）"


def _has_current_run_message(messages: list[Message], role: str) -> bool:
    """判断当前 run 是否已有非历史消息，避免重复补写。"""

    return _find_current_run_message(messages, role) is not None


def _find_current_run_message(messages: list[Message], role: str) -> Message | None:
    """查找当前 run 中指定角色的非 history 消息。"""

    for message in messages:
        if getattr(message, "role", None) == role and not getattr(message, "from_history", False):
            return message
    return None


def _message_timestamp(value: datetime | None) -> int:
    """把数据库时间转换为 Agno Message/Run 使用的秒级时间戳。"""

    if value is None:
        value = utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def _resolve_tool_detail_id(
    *,
    run_id: str,
    tool_name: str,
    tool_call_id: str | None,
    event_name: str,
    sequence: int,
    pending_without_call_id: dict[tuple[str, str], str],
) -> str:
    """为工具详情生成稳定 id，并合并缺少 tool_call_id 的 started/completed 事件。"""

    if tool_call_id:
        return tool_call_id
    pending_key = (run_id, tool_name)
    if event_name == "tool.started":
        detail_id = f"{run_id}:{tool_name}:{sequence}"
        pending_without_call_id[pending_key] = detail_id
        return detail_id
    detail_id = pending_without_call_id.pop(pending_key, None)
    return detail_id or f"{run_id}:{tool_name}:{sequence}"


def _tool_status_for_event(event_name: str) -> str:
    """把工具事件名转换为前端工具状态。"""

    if event_name == "tool.completed":
        return "completed"
    if event_name == "tool.error":
        return "error"
    return "running"


def _trim_input_summary(value: str | None) -> str | None:
    """限制任务输入摘要长度，避免长消息污染列表查询。"""

    if value is None:
        return None
    normalized = value.strip()
    return normalized[:500] if normalized else None


def _format_datetime(value: datetime | None) -> str | None:
    """统一输出 ISO 时间字符串。"""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _coerce_str(value: Any) -> str | None:
    """把事件 payload 中的可选字段规整为字符串。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _first_present(payload: dict[str, Any], *field_names: str, fallback: Any = None) -> Any:
    """按字段优先级取值，保留空字典、空列表和 None 等显式结果。"""

    for field_name in field_names:
        if field_name in payload:
            return payload[field_name]
    return fallback
