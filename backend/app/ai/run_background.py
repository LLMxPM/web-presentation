"""文件功能：把智能体 run 从 SSE 请求中解耦为后台任务并提供事件订阅。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from agno.agent import Agent as AgnoAgent
from agno.run.base import RunStatus
from agno.team import Team as AgnoTeam
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID, AgentRuntimeContext
from app.ai.session_facade import AgentSessionFacade
from app.core.exceptions import AppException
from app.schemas.agent import (
    AgentCancelRunResponse,
    AgentRunEvent,
    AgentScopeContext,
)
from app.services.ai_agent_run_service import (
    AI_RUN_EVENT_TERMINAL,
    AiAgentRunService,
    sync_agno_run_status,
    task_is_active,
)
from app.services.auth_service import AuthContext

logger = logging.getLogger(__name__)


class AgentBackgroundRunManager:
    """管理后台智能体 run 的启动、取消、事件持久化与订阅。"""

    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_run(
        self,
        *,
        app: FastAPI,
        current: AuthContext,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        message: str,
        image_attachment_ids: list[int] | None,
        reserved_lock: asyncio.Lock,
        run_id: str,
    ) -> None:
        """启动一次新的后台 run。"""

        task = asyncio.create_task(
            self._run_new_agent_stream(
                app=app,
                current=current,
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                runtime_context=runtime_context,
                message=message,
                image_attachment_ids=image_attachment_ids,
                reserved_lock=reserved_lock,
                run_id=run_id,
            )
        )
        self._tasks[run_id] = task

    async def start_continue(
        self,
        *,
        app: FastAPI,
        current: AuthContext,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        run_id: str,
    ) -> None:
        """在后台继续一个 paused run。"""

        task = asyncio.create_task(
            self._run_continue_agent_stream(
                app=app,
                current=current,
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                runtime_context=runtime_context,
                tool_execution=tool_execution,
                decision=decision,
                note=note,
                feedback_selections=feedback_selections,
                run_id=run_id,
            )
        )
        self._tasks[run_id] = task

    async def stream_events(
        self,
        *,
        run_id: str,
        current: AuthContext,
        after_sequence: int = 0,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """先回放 Redis Stream，再用 XREAD BLOCK 等待新事件。"""

        last_sequence = max(0, after_sequence)
        while True:
            async with self._session_factory() as session:
                service = AiAgentRunService(session)
                for event in await service.list_events_after(
                    run_id=run_id,
                    user_id=current.user.id,
                    after_sequence=last_sequence,
                ):
                    last_sequence = event.sequence or last_sequence
                    yield event
                    if event.event in AI_RUN_EVENT_TERMINAL:
                        return
                task = await service.get_task_by_run(run_id=run_id, user_id=current.user.id)
                if task is None or not task_is_active(task):
                    return
                await service.run_state_store.wait_events_after(
                    run_id=run_id,
                    user_id=current.user.id,
                    after_sequence=last_sequence,
                    block_ms=1000,
                )

    async def stream_sse_events(
        self,
        *,
        run_id: str,
        current: AuthContext,
        after_sequence: int = 0,
    ) -> AsyncGenerator[bytes, None]:
        """把标准事件订阅编码为 SSE 字节流。"""

        async for event in self.stream_events(
            run_id=run_id,
            current=current,
            after_sequence=after_sequence,
        ):
            yield f"event: {event.event}\ndata: {event.model_dump_json()}\n\n".encode("utf-8")

    async def cancel_active_run(
        self,
        *,
        app: FastAPI,
        current: AuthContext,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        force: bool,
    ) -> AgentCancelRunResponse:
        """幂等取消当前 active run；优先 graceful，必要时直接清理占位。"""

        async with self._session_factory() as session:
            facade = AgentSessionFacade(app=app, current=current, session=session)
            await facade.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
            service = AiAgentRunService(session)
            task = await service.get_latest_active_task(
                session_id=session_id,
                agent_id=agent_id,
                user_id=current.user.id,
            )
            if task is not None:
                if force or task.status == "paused" or task.run_id not in self._tasks:
                    event = await service.mark_terminal(
                        task=task,
                        status="cancelled",
                        content="当前运行已被用户取消。",
                    )
                    ai_db = getattr(app.state, "ai_db", None)
                    if ai_db is not None:
                        await sync_agno_run_status(
                            ai_db=ai_db,
                            user_id=str(current.user.id),
                            session_id=session_id,
                            agent_id=agent_id,
                            run_id=task.run_id,
                            status=RunStatus.cancelled,
                            content="当前运行已被用户取消。",
                        )
                        await self._preserve_user_cancelled_run_output(service=service, ai_db=ai_db, task=task)
                    return AgentCancelRunResponse(run_id=task.run_id, session_id=session_id, cancel_requested=True)

                cancelling_event = await service.mark_cancelling(task=task)
                _ = cancelling_event
                await service.run_state_store.publish_cancel(run_id=task.run_id, force=force)
                if agent_id == AGENT_COORDINATOR_AGENT_ID:
                    cancel_requested = AgnoTeam.cancel_run(task.run_id)
                    if cancel_requested is False:
                        AgnoAgent.cancel_run(task.run_id)
                else:
                    AgnoAgent.cancel_run(task.run_id)
                return AgentCancelRunResponse(run_id=task.run_id, session_id=session_id, cancel_requested=True)

            response = await facade.cancel_active_run(session_id=session_id, agent_id=agent_id, scope=scope)
            return response

    async def _run_new_agent_stream(
        self,
        *,
        app: FastAPI,
        current: AuthContext,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        message: str,
        image_attachment_ids: list[int] | None,
        reserved_lock: asyncio.Lock,
        run_id: str,
    ) -> None:
        """执行新 run，并把事件写入数据库与 live 订阅者。"""

        try:
            async with self._session_factory() as session:
                facade = AgentSessionFacade(app=app, current=current, session=session)
                async for event in facade.run_events(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    message=message,
                    runtime_context=runtime_context,
                    reserved_lock=reserved_lock,
                    image_attachment_ids=image_attachment_ids,
                    run_id=run_id,
                ):
                    await self._persist_and_publish(
                        run_id=run_id,
                        event=event,
                        ai_db=getattr(app.state, "ai_db", None),
                        user_id=current.user.id,
                    )
        except Exception as exc:  # noqa: BLE001
            await self._persist_and_publish(
                run_id=run_id,
                event=AgentRunEvent(
                    event="run.error",
                    run_id=run_id,
                    session_id=session_id,
                    data={"message": "智能体后台执行失败。", "code": exc.__class__.__name__},
                ),
                ai_db=getattr(app.state, "ai_db", None),
                user_id=current.user.id,
            )
        finally:
            self._tasks.pop(run_id, None)
            terminal_event = await self._finalize_and_preserve_user_cancelled_run_by_id(
                ai_db=getattr(app.state, "ai_db", None),
                run_id=run_id,
                user_id=current.user.id,
            )
            _ = terminal_event

    async def _run_continue_agent_stream(
        self,
        *,
        app: FastAPI,
        current: AuthContext,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        run_id: str,
    ) -> None:
        """执行 continue_run，并把事件写入数据库与 live 订阅者。"""

        try:
            async with self._session_factory() as session:
                facade = AgentSessionFacade(app=app, current=current, session=session)
                async for event in facade.continue_active_events(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    tool_execution=tool_execution,
                    decision=decision,
                    note=note,
                    feedback_selections=feedback_selections,
                    runtime_context=runtime_context,
                ):
                    await self._persist_and_publish(
                        run_id=run_id,
                        event=event,
                        ai_db=getattr(app.state, "ai_db", None),
                        user_id=current.user.id,
                    )
        except Exception as exc:  # noqa: BLE001
            await self._persist_and_publish(
                run_id=run_id,
                event=AgentRunEvent(
                    event="run.error",
                    run_id=run_id,
                    session_id=session_id,
                    data={"message": "智能体继续执行失败。", "code": exc.__class__.__name__},
                ),
                ai_db=getattr(app.state, "ai_db", None),
                user_id=current.user.id,
            )
        finally:
            self._tasks.pop(run_id, None)
            terminal_event = await self._finalize_and_preserve_user_cancelled_run_by_id(
                ai_db=getattr(app.state, "ai_db", None),
                run_id=run_id,
                user_id=current.user.id,
            )
            _ = terminal_event

    async def _persist_and_publish(
        self,
        *,
        run_id: str,
        event: AgentRunEvent,
        ai_db: Any | None = None,
        user_id: int | None = None,
    ) -> None:
        """持久化事件后再广播，确保订阅断开后可回放。"""

        async with self._session_factory() as session:
            service = AiAgentRunService(session)
            persisted = await service.append_event(run_id=run_id, event=event)
            if persisted is not None and persisted.event == "run.cancelled" and user_id is not None:
                task = await service.get_task_by_run(run_id=run_id, user_id=user_id)
                if task is not None:
                    await self._preserve_user_cancelled_run_output(service=service, ai_db=ai_db, task=task)
        if persisted is None:
            return

    async def _preserve_user_cancelled_run_output(
        self,
        *,
        service: AiAgentRunService,
        ai_db: Any | None,
        task: Any,
    ) -> None:
        """尽力把用户停止前已输出内容写回 Agno，不让补偿失败影响取消。"""

        try:
            _ = service
            async with self._session_factory() as session:
                await AiAgentRunService(session).preserve_user_cancelled_run_output(ai_db=ai_db, task=task)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to preserve user-cancelled AI run output: %s", getattr(task, "run_id", ""), exc_info=True)

    async def _finalize_and_preserve_user_cancelled_run_by_id(
        self,
        *,
        ai_db: Any | None,
        run_id: str,
        user_id: int,
    ) -> AgentRunEvent | None:
        """按 run_id 兜底收敛用户取消任务，并补偿写回 Agno 历史。"""

        async with self._session_factory() as session:
            service = AiAgentRunService(session)
            task = await service.get_task_by_run(run_id=run_id, user_id=user_id)
            if task is not None:
                terminal_event = await service.finalize_user_cancelled_task_if_needed(task=task)
                if terminal_event is not None and ai_db is not None:
                    await sync_agno_run_status(
                        ai_db=ai_db,
                        user_id=str(user_id),
                        session_id=task.session_id,
                        agent_id=task.agent_id,
                        run_id=task.run_id,
                        status=RunStatus.cancelled,
                        content="当前运行已被用户取消。",
                    )
                if ai_db is not None:
                    await self._preserve_user_cancelled_run_output(service=service, ai_db=ai_db, task=task)
                return terminal_event
        return None


def get_agent_run_manager(app: FastAPI) -> AgentBackgroundRunManager:
    """从应用状态读取或创建后台 run 管理器。"""

    manager = getattr(app.state, "ai_run_manager", None)
    if manager is None:
        raise RuntimeError("AI run manager is not initialized.")
    return manager
