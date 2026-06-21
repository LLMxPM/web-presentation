"""文件功能：提供平台自有智能体运行态的读写、事件追加、快照构建与 SSE 编码能力。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.image_refs import sanitize_message_history_image_refs
from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.message_history import trim_unprocessed_tool_call_history
from app.ai.member_prompts import build_member_prompt_from_payload
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.ai_agent_runtime import (
    AiAgentMemberRun,
    AiAgentMessage,
    AiAgentRequirement,
    AiAgentRun,
    AiAgentRunEvent,
    AiAgentSession,
    AiAgentToolCall,
)
from app.models.enums import RecordStatus
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentContextStatusItem,
    AgentMemberRunItem,
    AgentMessageAttachmentItem,
    AgentMessageItem,
    AgentPendingRequirement,
    AgentRunEvent,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
    AgentTimelineItem,
    AgentTimelineToolItem,
)
from app.services.agent_image_attachment_service import AgentImageAttachmentService

ACTIVE_RUN_STATUSES = {"pending", "running", "paused", "cancelling"}
TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}
STREAM_END_EVENTS = {"run.completed", "run.cancelled", "run.error", "run.paused"}
_EVENT_POLL_INTERVAL_SECONDS = 1.0
_SSE_KEEPALIVE_INTERVAL_SECONDS = 30.0
_SUBSCRIBERS: dict[str, set[asyncio.Queue[AgentRunEvent | None]]] = {}


@dataclass(slots=True)
class PlatformRunStart:
    """描述一次平台 run 启动后的核心对象。"""

    session_model: AiAgentSession
    run_model: AiAgentRun


class PlatformAgentRuntimeStore:
    """封装平台自有 AI 运行态表的读写和事件协议。"""

    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        """保存数据库会话与当前用户，用于后续权限过滤。"""

        self._session = session
        self._user_id = user_id

    async def list_sessions(
        self,
        *,
        agent_id: str,
        scope: AgentScopeContext,
        scope_mode: Literal["exact", "workspace"] = "exact",
    ) -> list[AgentSessionItem]:
        """按当前用户、Agent 与 scope 返回未删除会话列表。"""

        query = select(AiAgentSession)
        if scope_mode == "workspace":
            query = self._workspace_scope_query(
                query,
                agent_id=agent_id,
                workspace_id=scope.workspace_id,
            )
        else:
            query = self._scope_query(query, agent_id=agent_id, scope=scope)

        result = await self._session.execute(
            query
            .where(AiAgentSession.deleted_at.is_(None))
            .order_by(AiAgentSession.updated_at.desc())
        )
        return [self.map_session_item(item) for item in result.scalars().all()]

    async def create_session(
        self,
        *,
        session_id: str,
        agent_id: str,
        session_name: str | None,
        scope: AgentScopeContext,
    ) -> AgentSessionItem:
        """创建平台 Agent 会话。"""

        now = _utc_now()
        model = AiAgentSession(
            session_id=session_id,
            agent_id=agent_id,
            user_id=self._user_id,
            session_name=session_name,
            scope_type=scope.scope_type,
            workspace_id=scope.workspace_id,
            project_id=scope.project_id,
            page_id=scope.page_id,
            component_id=scope.component_id,
            source=scope.source,
            metadata_json=_scope_metadata(scope),
            created_by=self._user_id,
            updated_by=self._user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self.map_session_item(model)

    async def get_session_or_none(self, *, session_id: str, agent_id: str) -> AiAgentSession | None:
        """读取当前用户可见的单个会话。"""

        result = await self._session.execute(
            select(AiAgentSession).where(
                AiAgentSession.session_id == session_id,
                AiAgentSession.agent_id == agent_id,
                AiAgentSession.user_id == self._user_id,
                AiAgentSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def rename_session(self, *, session_id: str, agent_id: str, session_name: str) -> AgentSessionItem:
        """更新会话名称并返回最新会话项。"""

        model = await self.require_session(session_id=session_id, agent_id=agent_id)
        model.session_name = session_name
        model.updated_by = self._user_id
        model.updated_at = _utc_now()
        await self._session.commit()
        await self._session.refresh(model)
        return self.map_session_item(model)

    async def require_session(self, *, session_id: str, agent_id: str) -> AiAgentSession:
        """读取会话；不存在时抛出调用方可转换的 ValueError。"""

        model = await self.get_session_or_none(session_id=session_id, agent_id=agent_id)
        if model is None:
            raise ValueError("AI_SESSION_NOT_FOUND")
        return model

    async def ensure_no_active_run(self, *, session_id: str, agent_id: str) -> None:
        """确保同一会话没有非终态运行。"""

        active_run = await self.get_active_run_model(session_id=session_id, agent_id=agent_id)
        if active_run is not None:
            raise ValueError("AI_SESSION_RUN_ACTIVE")

    async def start_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        run_id: str,
        message: str,
        image_attachment_ids: list[int] | None,
    ) -> PlatformRunStart:
        """创建平台 run、用户消息与首个 run.started 事件。"""

        session_model = await self.require_session(session_id=session_id, agent_id=agent_id)
        await self.ensure_no_active_run(session_id=session_id, agent_id=agent_id)
        now = _utc_now()
        run_model = AiAgentRun(
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            user_id=self._user_id,
            status="running",
            scope_type=scope.scope_type,
            workspace_id=scope.workspace_id,
            project_id=scope.project_id,
            page_id=scope.page_id,
            component_id=scope.component_id,
            source=scope.source,
            input_payload_json={
                "message": message,
                "image_attachment_ids": list(image_attachment_ids or []),
            },
            message_history_json=[],
            event_index=-1,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(run_model)
        # PostgreSQL 会立即校验消息表 run_id 外键；先刷入父 run，避免同批 flush 时子表先插入。
        await self._session.flush([run_model])
        await self._append_message(
            session_id=session_id,
            run_id=run_id,
            role="user",
            content=message or ("（已发送图片）" if image_attachment_ids else ""),
            attachments=await self._attachment_summaries(session_id=session_id, attachment_ids=image_attachment_ids or []),
        )
        await self._session.flush()
        await self.append_event(
            run_model,
            AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id, data={"agent_id": agent_id}),
            commit=False,
        )
        session_model.updated_at = now
        await self._session.commit()
        await self._session.refresh(session_model)
        await self._session.refresh(run_model)
        return PlatformRunStart(session_model=session_model, run_model=run_model)

    async def append_event(self, run_model: AiAgentRun, event: AgentRunEvent, *, commit: bool = True) -> AgentRunEvent:
        """为 run 追加平台事件，分配单调 event_index 并通知订阅者。"""

        await self._refresh_run_event_cursor(run_model)
        current_index = run_model.event_index if run_model.event_index is not None else -1
        next_index = int(current_index) + 1
        event.event_index = next_index
        event.sequence = next_index
        event.run_id = event.run_id or run_model.run_id
        event.session_id = event.session_id or run_model.session_id
        payload = event.model_dump(mode="json")
        row = AiAgentRunEvent(
            session_id=run_model.session_id,
            run_id=run_model.run_id,
            event_index=next_index,
            event=event.event,
            payload_json=payload,
        )
        self._session.add(row)
        run_model.event_index = next_index
        run_model.updated_at = _utc_now()
        self._apply_event_to_run(run_model, event)
        await self._sync_tool_event(run_model, event)
        if commit:
            await self._session.commit()
        _notify_subscribers(run_model.run_id, event)
        return event

    async def _refresh_run_event_cursor(self, run_model: AiAgentRun) -> None:
        """写事件前锁定 run 行并刷新游标，避免停止请求和流式事件并发分配同一序号。"""

        await self._session.refresh(
            run_model,
            attribute_names=["event_index"],
            with_for_update=True,
        )

    async def append_assistant_message(
        self,
        run_model: AiAgentRun,
        *,
        content: str,
        reasoning_content: str | None = None,
        message_history: list[dict[str, Any]] | None = None,
    ) -> None:
        """保存一次运行完成后的助手消息和本 run 新增 Pydantic AI 消息 delta。"""

        sanitized_history = sanitize_message_history_image_refs(message_history or []) if message_history is not None else None
        if content:
            await self._append_message(
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                role="assistant",
                content=content,
                reasoning_content=reasoning_content,
                message_json={"message_history": sanitized_history or []},
            )
        if sanitized_history is not None and isinstance(sanitized_history, list):
            self._replace_run_message_history(run_model, sanitized_history)

    async def save_run_message_history(self, run_model: AiAgentRun, message_history: list[dict[str, Any]], *, commit: bool = True) -> None:
        """替换保存本 run 当前 Pydantic AI 消息快照。"""

        self._replace_run_message_history(run_model, message_history)
        run_model.updated_at = _utc_now()
        if commit:
            await self._session.commit()

    def _replace_run_message_history(self, run_model: AiAgentRun, message_history: list[dict[str, Any]]) -> None:
        """用本 run 当前完整 delta 快照替换旧值，避免多次模型调用重复追加。"""

        sanitized = sanitize_message_history_image_refs(message_history)
        run_model.message_history_json = [
            dict(item)
            for item in sanitized
            if isinstance(item, dict)
        ] if isinstance(sanitized, list) else []

    async def refresh_run_control_state(self, run_model: AiAgentRun) -> str:
        """刷新 run 的控制状态，供流式执行过程感知外部取消请求。"""

        await self._session.refresh(
            run_model,
            attribute_names=["status", "cancel_requested_at"],
        )
        return run_model.status

    async def mark_terminal(
        self,
        run_model: AiAgentRun,
        *,
        status: str,
        content: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunEvent:
        """把运行标记为终态并写入对应终态事件。"""

        if status not in TERMINAL_RUN_STATUSES and status != "paused":
            raise ValueError(f"unsupported terminal status: {status}")
        if status in TERMINAL_RUN_STATUSES:
            run_model.message_history_json = trim_unprocessed_tool_call_history(
                run_model.message_history_json if isinstance(run_model.message_history_json, list) else []
            )
        run_model.status = status
        run_model.finished_at = _utc_now() if status in TERMINAL_RUN_STATUSES else None
        run_model.error_code = error_code
        run_model.error_message = error_message
        if status == "failed":
            await self._append_running_tool_error_events(
                run_model,
                message=error_message or content or "运行中断，工具调用未完成。",
            )
        event_name = {
            "completed": "run.completed",
            "cancelled": "run.cancelled",
            "failed": "run.error",
            "paused": "run.paused",
        }[status]
        event_data: dict[str, Any] = {}
        if error_code:
            event_data["code"] = error_code
        if error_message or content:
            event_data["message"] = error_message or content
        return await self.append_event(
            run_model,
            AgentRunEvent(
                event=event_name,
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                content=content,
                data=event_data,
            ),
        )

    async def _append_running_tool_error_events(self, run_model: AiAgentRun, *, message: str) -> None:
        """运行失败时补齐仍未结束的工具调用，避免 UI 和快照残留进行中状态。"""

        result = await self._session.execute(
            select(AiAgentToolCall).where(
                AiAgentToolCall.run_id == run_model.run_id,
                AiAgentToolCall.status == "running",
            )
        )
        for tool_call in result.scalars().all():
            tool_call.status = "error"
            tool_call.message = tool_call.message or message
            if not tool_call.tool_call_id:
                continue
            await self.append_event(
                run_model,
                AgentRunEvent(
                    event="tool.error",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    data={
                        "tool_name": tool_call.tool_name,
                        "tool_call_id": tool_call.tool_call_id,
                        "message": message,
                    },
                ),
                commit=False,
            )
            await self._session.flush()

    async def pause_for_requirement(
        self,
        run_model: AiAgentRun,
        *,
        requirement: AgentPendingRequirement,
    ) -> AgentRunEvent:
        """保存 pending requirement 并发送 run.paused。"""

        payload = requirement.model_dump(mode="json")
        run_model.status = "paused"
        run_model.pending_requirement_json = payload
        self._session.add(
            AiAgentRequirement(
                requirement_id=requirement.id or f"req-{uuid4().hex}",
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                kind=requirement.kind,
                status="pending",
                tool_call_id=str(requirement.tool_execution.get("tool_call_id") or "") or None,
                tool_name=requirement.tool_name,
                member_agent_id=requirement.member_agent_id,
                member_agent_name=requirement.member_agent_name,
                member_run_id=requirement.member_run_id,
                payload_json=payload,
            )
        )
        return await self.append_event(
            run_model,
            AgentRunEvent(
                event="run.paused",
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                data={"requirement": payload},
            ),
        )

    async def request_cancel(self, *, session_id: str, agent_id: str) -> AiAgentRun:
        """给当前 active run 设置取消标记并发送 run.cancelling。"""

        run_model = await self.get_active_run_model(session_id=session_id, agent_id=agent_id)
        if run_model is None:
            raise ValueError("AI_RUN_NOT_ACTIVE")
        if run_model.status == "cancelling" or run_model.cancel_requested_at is not None:
            return run_model
        run_model.cancel_requested_at = _utc_now()
        run_model.status = "cancelling"
        await self.append_event(
            run_model,
            AgentRunEvent(
                event="run.cancelling",
                run_id=run_model.run_id,
                session_id=session_id,
                data={"message": "正在停止当前运行。"},
            ),
        )
        return run_model

    async def force_cancel(self, *, session_id: str, agent_id: str) -> AiAgentRun:
        """强制把当前 active run 标记为 cancelled，用于停止超时后的人工释放。"""

        run_model = await self.get_active_run_model(session_id=session_id, agent_id=agent_id)
        if run_model is None:
            raise ValueError("AI_RUN_NOT_ACTIVE")
        if run_model.status == "cancelled":
            return run_model
        run_model.cancel_requested_at = run_model.cancel_requested_at or _utc_now()
        await self.mark_terminal(run_model, status="cancelled", content="用户强制停止了当前运行。")
        return run_model

    async def get_pending_requirement(self, *, run_id: str) -> AiAgentRequirement | None:
        """读取 run 当前待处理 requirement。"""

        result = await self._session.execute(
            select(AiAgentRequirement)
            .where(AiAgentRequirement.run_id == run_id, AiAgentRequirement.status == "pending")
            .order_by(AiAgentRequirement.created_at.desc())
        )
        return result.scalars().first()

    async def resolve_requirement(
        self,
        requirement: AiAgentRequirement,
        *,
        payload: dict[str, Any],
    ) -> None:
        """标记 requirement 已解决。"""

        requirement.status = "resolved"
        requirement.resolved_payload_json = payload
        requirement.resolved_at = _utc_now()
        await self._session.flush()

    async def get_active_run_model(self, *, session_id: str, agent_id: str) -> AiAgentRun | None:
        """读取最近一个非终态 run。"""

        result = await self._session.execute(
            select(AiAgentRun)
            .where(
                AiAgentRun.session_id == session_id,
                AiAgentRun.agent_id == agent_id,
                AiAgentRun.user_id == self._user_id,
                AiAgentRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .order_by(AiAgentRun.created_at.desc())
        )
        return result.scalars().first()

    async def get_latest_run_model(self, *, session_id: str, agent_id: str) -> AiAgentRun | None:
        """读取最近一次 run。"""

        result = await self._session.execute(
            select(AiAgentRun)
            .where(
                AiAgentRun.session_id == session_id,
                AiAgentRun.agent_id == agent_id,
                AiAgentRun.user_id == self._user_id,
            )
            .order_by(AiAgentRun.created_at.desc())
        )
        return result.scalars().first()

    async def list_messages(self, *, session_id: str, agent_id: str) -> list[AgentMessageItem]:
        """返回会话可展示消息。"""

        await self.require_session(session_id=session_id, agent_id=agent_id)
        result = await self._session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.session_id == session_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
        return [self.map_message_item(item) for item in result.scalars().all()]

    async def get_runtime_snapshot(
        self,
        *,
        session_id: str,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
    ) -> AgentSessionRuntimeSnapshot:
        """从平台运行态表构建 Editor 恢复快照。"""

        session_model = await self.require_session(session_id=session_id, agent_id=agent_id)
        latest_run = await self.get_latest_run_model(session_id=session_id, agent_id=agent_id)
        active_run = self.map_active_run(latest_run) if latest_run is not None and latest_run.status in ACTIVE_RUN_STATUSES else None
        last_run = self.map_active_run(latest_run) if latest_run is not None and latest_run.status not in ACTIVE_RUN_STATUSES else None
        timeline_items = await self.build_timeline_items(session_id=session_id)
        member_runs = await self.build_member_runs(session_id=session_id, parent_timeline_items=timeline_items)
        pending_requirement = active_run.pending_requirement if active_run is not None else None
        pending_attachments = await AgentImageAttachmentService(
            self._session,
            user_id=self._user_id,
        ).list_pending_attachments(
            workspace_id=session_model.workspace_id,
            session_id=session_id,
        )
        return AgentSessionRuntimeSnapshot(
            session=self.map_session_item(session_model),
            timeline_items=timeline_items,
            member_runs=member_runs,
            context_status=self.build_context_status(session_id=session_id, agent_id=agent_id, runtime_context=runtime_context),
            active_run=active_run,
            last_run=last_run,
            pending_requirement=pending_requirement,
            event_index=active_run.event_index if active_run is not None else (last_run.event_index if last_run else -1),
            pending_attachments=pending_attachments,
        )

    async def replay_events(self, *, run_id: str, event_index: int) -> list[AgentRunEvent]:
        """读取指定 event_index 之后的事件。"""

        result = await self._session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.run_id == run_id, AiAgentRunEvent.event_index > event_index)
            .order_by(AiAgentRunEvent.event_index.asc())
        )
        return [AgentRunEvent.model_validate(row.payload_json) for row in result.scalars().all()]

    async def get_run_status(self, *, run_id: str) -> str | None:
        """读取当前用户可见 run 的状态，供事件流轮询判断是否结束。"""

        result = await self._session.execute(
            select(AiAgentRun.status).where(
                AiAgentRun.run_id == run_id,
                AiAgentRun.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def build_timeline_items(self, *, session_id: str) -> list[AgentTimelineItem]:
        """基于平台消息、工具调用、requirement 与事件生成会话 timeline。"""

        timeline_entries: list[tuple[tuple[int, int, int, str, str], AgentTimelineItem]] = []
        run_order = await self._run_order_map(session_id=session_id)
        event_output_run_ids: set[str] = set()
        message_result = await self._session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.session_id == session_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
        messages = message_result.scalars().all()
        event_result = await self._session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.session_id == session_id)
            .order_by(AiAgentRunEvent.run_id.asc(), AiAgentRunEvent.event_index.asc(), AiAgentRunEvent.id.asc())
        )
        for item in self._timeline_items_from_event_rows(event_result.scalars().all()):
            if item.kind in {"message", "reasoning"}:
                event_output_run_ids.add(item.run_id)
            timeline_entries.append((
                _timeline_sort_key(
                    run_order,
                    run_id=item.run_id,
                    event_index=item.event_index,
                    phase=0,
                    created_at=item.created_at,
                    fallback_id=item.id,
                ),
                item,
            ))

        fallback_run_result = await self._session.execute(
            select(AiAgentRun)
            .where(AiAgentRun.session_id == session_id)
            .order_by(AiAgentRun.created_at.asc())
        )
        for run in fallback_run_result.scalars().all():
            if run.run_id in event_output_run_ids:
                continue
            if run.reasoning_content:
                item = AgentTimelineItem(
                    id=f"run-{run.run_id}-reasoning",
                    session_id=run.session_id,
                    run_id=run.run_id,
                    kind="reasoning",
                    role=None,
                    event_index=run.event_index,
                    order_index=0,
                    content=run.reasoning_content,
                    status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                    tool=None,
                    source="event",
                    created_at=_iso(run.created_at),
                )
                timeline_entries.append((
                    _timeline_sort_key(
                        run_order,
                        run_id=item.run_id,
                        event_index=item.event_index,
                        phase=1,
                        created_at=item.created_at,
                        fallback_id=item.id,
                    ),
                    item,
                ))
            if run.content:
                item = AgentTimelineItem(
                    id=f"run-{run.run_id}-message",
                    session_id=run.session_id,
                    run_id=run.run_id,
                    kind="message",
                    role="assistant",
                    event_index=run.event_index,
                    order_index=0,
                    content=run.content,
                    status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                    tool=None,
                    source="event",
                    created_at=_iso(run.created_at),
                )
                timeline_entries.append((
                    _timeline_sort_key(
                        run_order,
                        run_id=item.run_id,
                        event_index=item.event_index,
                        phase=2,
                        created_at=item.created_at,
                        fallback_id=item.id,
                    ),
                    item,
                ))

        for message in messages:
            if (
                message.role == "assistant"
                and message.reasoning_content
                and (not message.run_id or message.run_id not in event_output_run_ids)
            ):
                self._append_message_timeline_entry(
                    timeline_entries,
                    run_order=run_order,
                    message=message,
                    kind="reasoning",
                    role=None,
                    content=message.reasoning_content,
                    phase=1,
                )
            if message.role != "assistant" or not message.run_id or message.run_id not in event_output_run_ids:
                self._append_message_timeline_entry(
                    timeline_entries,
                    run_order=run_order,
                    message=message,
                    kind="message",
                    role=message.role if message.role in {"user", "assistant"} else None,  # type: ignore[arg-type]
                    content=message.content,
                    phase=-1 if message.role == "user" else 2,
                )

        sorted_items = [item for _, item in sorted(timeline_entries, key=lambda entry: entry[0])]
        tool_attachments = await self._tool_attachment_summaries(session_id=session_id)
        for order_index, item in enumerate(sorted_items):
            item.order_index = order_index
            if item.kind == "tool" and item.tool is not None:
                key = (item.run_id, item.tool.tool_call_id or "")
                fallback_key = (item.run_id, item.tool.tool_name)
                item.attachments = tool_attachments.get(key) or tool_attachments.get(fallback_key, [])
        return sorted_items

    async def _run_order_map(self, *, session_id: str) -> dict[str, int]:
        """按 run 创建顺序建立排序索引，event_index 只在单个 run 内有序。"""

        result = await self._session.execute(
            select(AiAgentRun.run_id)
            .where(AiAgentRun.session_id == session_id)
            .order_by(AiAgentRun.created_at.asc(), AiAgentRun.run_id.asc())
        )
        return {run_id: index for index, run_id in enumerate(result.scalars().all())}

    def _timeline_items_from_event_rows(self, event_rows: list[AiAgentRunEvent]) -> list[AgentTimelineItem]:
        """按事件流重建助手文本、推理、工具和待处理项，保持回放顺序与实时 SSE 一致。"""

        items: list[AgentTimelineItem] = []
        current_text_by_run: dict[str, AgentTimelineItem | None] = {}
        tool_items: dict[tuple[str, str], AgentTimelineItem] = {}
        for event_row in event_rows:
            event = AgentRunEvent.model_validate(event_row.payload_json)
            event.run_id = event.run_id or event_row.run_id
            event.session_id = event.session_id or event_row.session_id
            event.event_index = event.event_index if event.event_index is not None else event_row.event_index
            run_id = event.run_id or event_row.run_id
            if event.event in {"message.delta", "reasoning.delta"}:
                item = self._append_text_event_timeline_item(
                    items,
                    current_text_by_run=current_text_by_run,
                    event_row=event_row,
                    event=event,
                    kind="message" if event.event == "message.delta" else "reasoning",
                )
                if event.content:
                    item.content = f"{item.content or ''}{event.content}"
                continue
            if event.event in {"tool.started", "tool.completed", "tool.error"}:
                current_text_by_run[run_id] = None
                item = self._upsert_tool_event_timeline_item(
                    items,
                    tool_items=tool_items,
                    event_row=event_row,
                    event=event,
                    status={
                        "tool.started": "running",
                        "tool.completed": "completed",
                        "tool.error": "error",
                    }[event.event],
                )
                continue
            if event.event == "run.paused":
                current_text_by_run[run_id] = None
                requirement = event.data.get("requirement") if isinstance(event.data, dict) else None
                if isinstance(requirement, dict):
                    items.append(
                        AgentTimelineItem(
                            id=f"requirement-{requirement.get('id') or event_row.id}",
                            session_id=event_row.session_id,
                            run_id=event_row.run_id,
                            kind="requirement",
                            role=None,
                            event_index=event_row.event_index,
                            order_index=0,
                            content=requirement.get("note"),
                            status="paused",
                            tool=None,
                            source="event",
                            created_at=_iso(event_row.created_at),
                        )
                    )
                continue
            if event.event == "run.error":
                current_text_by_run[run_id] = None
                _mark_open_tool_items_failed(
                    tool_items,
                    run_id=run_id,
                    message=str(event.data.get("message") or event.content or "运行中断，工具调用未完成。"),
                )
                continue
            if event.event.startswith("run.") or event.event == "model.request.started":
                current_text_by_run[run_id] = None
        return items

    def _append_text_event_timeline_item(
        self,
        items: list[AgentTimelineItem],
        *,
        current_text_by_run: dict[str, AgentTimelineItem | None],
        event_row: AiAgentRunEvent,
        event: AgentRunEvent,
        kind: str,
    ) -> AgentTimelineItem:
        """追加或复用当前 run 的连续文本片段。"""

        run_id = event.run_id or event_row.run_id
        role = "assistant" if kind == "message" else None
        current = current_text_by_run.get(run_id)
        if current is not None and current.kind == kind and current.role == role:
            return current
        item = AgentTimelineItem(
            id=f"event-{event_row.id}-{kind}",
            session_id=event_row.session_id,
            run_id=event_row.run_id,
            kind=kind,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            event_index=event_row.event_index,
            order_index=0,
            content="",
            status=None,
            tool=None,
            source="event",
            created_at=_iso(event_row.created_at),
        )
        items.append(item)
        current_text_by_run[run_id] = item
        return item

    def _upsert_tool_event_timeline_item(
        self,
        items: list[AgentTimelineItem],
        *,
        tool_items: dict[tuple[str, str], AgentTimelineItem],
        event_row: AiAgentRunEvent,
        event: AgentRunEvent,
        status: str,
    ) -> AgentTimelineItem:
        """按 tool_call_id 合并工具开始、完成和失败事件。"""

        data = event.data if isinstance(event.data, dict) else {}
        run_id = event.run_id or event_row.run_id
        tool_call_id = str(data.get("tool_call_id") or "").strip()
        tool_name = str(data.get("tool_name") or "工具调用").strip()
        key = (run_id, tool_call_id or f"event-{event_row.id}")
        existing = tool_items.get(key)
        if existing is None:
            existing = AgentTimelineItem(
                id=f"tool-{run_id}-{tool_call_id or event_row.id}",
                session_id=event_row.session_id,
                run_id=event_row.run_id,
                kind="tool",
                role=None,
                event_index=event_row.event_index,
                order_index=0,
                content=None,
                status=status,
                tool=AgentTimelineToolItem(
                    tool_call_id=tool_call_id or None,
                    tool_name=tool_name,
                    member_agent_id=_optional_str(data.get("member_agent_id")),
                    member_agent_name=_optional_str(data.get("member_agent_name")),
                    member_run_id=_optional_str(data.get("member_run_id")),
                    status=status if status in {"running", "completed", "error"} else "running",  # type: ignore[arg-type]
                    input_payload=_first_present(data, ("tool_args", "arguments", "args")),
                    output_payload=_first_present(data, ("result", "output")),
                    message=str(data.get("message") or event.content or ""),
                ),
                source="event",
                created_at=_iso(event_row.created_at),
            )
            tool_items[key] = existing
            items.append(existing)
            return existing
        existing.status = status
        if existing.tool is not None:
            existing.tool.status = status if status in {"running", "completed", "error"} else existing.tool.status  # type: ignore[assignment]
            input_payload = _first_present(data, ("tool_args", "arguments", "args"))
            if _is_meaningful_payload(input_payload) and not _is_meaningful_payload(existing.tool.input_payload):
                existing.tool.input_payload = input_payload
            existing.tool.output_payload = data.get("result") if "result" in data else data.get("output", existing.tool.output_payload)
            if data.get("message") or event.content:
                existing.tool.message = str(data.get("message") or event.content or "")
        return existing

    def _append_message_timeline_entry(
        self,
        timeline_entries: list[tuple[tuple[int, int, int, str, str], AgentTimelineItem]],
        *,
        run_order: dict[str, int],
        message: AiAgentMessage,
        kind: str,
        role: str | None,
        content: str,
        phase: int,
    ) -> None:
        """把消息表记录加入待排序 timeline；主要用于用户消息和事件缺失兜底。"""

        item = AgentTimelineItem(
            id=f"message-{message.id}" if kind == "message" else f"message-{message.id}-{kind}",
            session_id=message.session_id,
            run_id=message.run_id or "",
            kind=kind,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            event_index=None,
            order_index=0,
            content=content,
            status=None,
            tool=None,
            attachments=[
                AgentMessageAttachmentItem.model_validate(item)
                for item in (message.attachments_json or [])
                if isinstance(item, dict)
            ] if kind == "message" else [],
            source="message",
            created_at=_iso(message.created_at),
        )
        timeline_entries.append((
            _timeline_sort_key(
                run_order,
                run_id=item.run_id,
                event_index=item.event_index,
                phase=phase,
                created_at=item.created_at,
                fallback_id=item.id,
            ),
            item,
        ))

    async def build_member_runs(
        self,
        *,
        session_id: str,
        parent_timeline_items: list[AgentTimelineItem],
    ) -> list[AgentMemberRunItem]:
        """构建成员运行快照；parent_timeline_items 当前仅用于接口对齐。"""

        _ = parent_timeline_items
        result = await self._session.execute(
            select(AiAgentMemberRun)
            .where(AiAgentMemberRun.session_id == session_id)
            .order_by(AiAgentMemberRun.created_at.asc())
        )
        event_result = await self._session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.session_id == session_id, AiAgentRunEvent.event.like("member.%"))
            .order_by(AiAgentRunEvent.event_index.asc(), AiAgentRunEvent.id.asc())
        )
        member_event_rows = event_result.scalars().all()
        member_runs: list[AgentMemberRunItem] = []
        for member_run in result.scalars().all():
            timeline = self._member_timeline_items_from_event_rows(member_run, member_event_rows)
            member_runs.append(
                AgentMemberRunItem(
                    parent_run_id=member_run.parent_run_id,
                    run_id=member_run.member_run_id,
                    agent_id=member_run.agent_id,
                    agent_name=member_run.agent_name,
                    status=_map_run_status(member_run.status),
                    created_at=_iso(member_run.created_at),
                    updated_at=_iso(member_run.updated_at),
                    delegate_tool_call_id=member_run.delegate_tool_call_id,
                    input_prompt=_member_input_prompt(member_run),
                    output_prompt=_member_output_prompt(member_run),
                    timeline_items=timeline,
                )
            )
        return member_runs

    def _member_timeline_items_from_event_rows(
        self,
        member_run: AiAgentMemberRun,
        event_rows: list[AiAgentRunEvent],
    ) -> list[AgentTimelineItem]:
        """按 member.* 事件重建成员运行内部时间线。"""

        items: list[AgentTimelineItem] = []
        current_text: AgentTimelineItem | None = None
        model_request_item: AgentTimelineItem | None = None
        tool_items: dict[str, AgentTimelineItem] = {}

        def clear_model_request_item() -> None:
            """成员已有实际输出或终态时，移除过期的等待输出提示。"""

            nonlocal model_request_item
            if model_request_item is not None and model_request_item in items:
                items.remove(model_request_item)
            model_request_item = None

        for event_row in event_rows:
            event = AgentRunEvent.model_validate(event_row.payload_json)
            data = event.data if isinstance(event.data, dict) else {}
            if _optional_str(data.get("member_run_id")) != member_run.member_run_id:
                continue
            if event.event in {"member.message.delta", "member.reasoning.delta"}:
                clear_model_request_item()
                kind = "message" if event.event == "member.message.delta" else "reasoning"
                role = "assistant" if kind == "message" else None
                if current_text is None or current_text.kind != kind:
                    current_text = AgentTimelineItem(
                        id=f"member-event-{event_row.id}-{kind}",
                        session_id=event_row.session_id,
                        run_id=member_run.member_run_id,
                        kind=kind,  # type: ignore[arg-type]
                        role=role,  # type: ignore[arg-type]
                        event_index=event_row.event_index,
                        order_index=len(items),
                        content="",
                        status=None,
                        tool=None,
                        source="event",
                        created_at=_iso(event_row.created_at),
                    )
                    items.append(current_text)
                if event.content:
                    current_text.content = f"{current_text.content or ''}{event.content}"
                continue
            if event.event in {"member.tool.started", "member.tool.completed", "member.tool.error"}:
                clear_model_request_item()
                current_text = None
                status = {
                    "member.tool.started": "running",
                    "member.tool.completed": "completed",
                    "member.tool.error": "error",
                }[event.event]
                tool_call_id = _optional_str(data.get("tool_call_id")) or f"member-event-{event_row.id}"
                existing = tool_items.get(tool_call_id)
                if existing is None:
                    existing = AgentTimelineItem(
                        id=f"member-tool-{member_run.member_run_id}-{tool_call_id}",
                        session_id=event_row.session_id,
                        run_id=member_run.member_run_id,
                        kind="tool",
                        role=None,
                        event_index=event_row.event_index,
                        order_index=len(items),
                        content=None,
                        status=status,
                        tool=AgentTimelineToolItem(
                            tool_call_id=_optional_str(data.get("tool_call_id")),
                            tool_name=str(data.get("tool_name") or "工具调用"),
                            member_agent_id=member_run.agent_id,
                            member_agent_name=member_run.agent_name,
                            member_run_id=member_run.member_run_id,
                            status=status,  # type: ignore[arg-type]
                            input_payload=_first_present(data, ("tool_args", "arguments", "args")),
                            output_payload=_first_present(data, ("result", "output")),
                            message=str(data.get("message") or event.content or ""),
                        ),
                        source="event",
                        created_at=_iso(event_row.created_at),
                    )
                    tool_items[tool_call_id] = existing
                    items.append(existing)
                elif existing.tool is not None:
                    existing.status = status
                    existing.tool.status = status  # type: ignore[assignment]
                    input_payload = _first_present(data, ("tool_args", "arguments", "args"))
                    if _is_meaningful_payload(input_payload) and not _is_meaningful_payload(existing.tool.input_payload):
                        existing.tool.input_payload = input_payload
                    output_payload = _first_present(data, ("result", "output"))
                    if output_payload is not None:
                        existing.tool.output_payload = output_payload
                    if data.get("message") or event.content:
                        existing.tool.message = str(data.get("message") or event.content or "")
                continue
            if event.event == "member.model.request.completed":
                clear_model_request_item()
                current_text = None
                continue
            if event.event in {"member.model.request.started", "member.run.paused", "member.run.completed", "member.run.cancelled", "member.run.error"}:
                if event.event != "member.model.request.started":
                    clear_model_request_item()
                current_text = None
                status = {
                    "member.model.request.started": "model_request",
                    "member.run.paused": "paused",
                    "member.run.completed": "completed",
                    "member.run.cancelled": "cancelled",
                    "member.run.error": "failed",
                }[event.event]
                content = {
                    "member.model.request.started": "等待智能体输出中",
                    "member.run.paused": "等待用户处理。",
                    "member.run.completed": "运行已完成。",
                    "member.run.cancelled": "运行已停止。",
                    "member.run.error": str(data.get("message") or "运行失败。"),
                }.get(event.event, "")
                items.append(
                    AgentTimelineItem(
                        id=f"member-status-{event_row.id}",
                        session_id=event_row.session_id,
                        run_id=member_run.member_run_id,
                        kind="run_status",
                        role=None,
                        event_index=event_row.event_index,
                        order_index=len(items),
                        content=content,
                        status=status,
                        tool=None,
                        source="event",
                        created_at=_iso(event_row.created_at),
                    )
                )
                if event.event == "member.model.request.started":
                    model_request_item = items[-1]
        for index, item in enumerate(items):
            item.order_index = index
        return items

    def map_session_item(self, model: AiAgentSession) -> AgentSessionItem:
        """把会话 ORM 映射为接口模型。"""

        return AgentSessionItem(
            session_id=model.session_id,
            agent_id=model.agent_id,
            session_name=model.session_name,
            created_at=_iso(model.created_at),
            updated_at=_iso(model.updated_at),
            metadata=dict(model.metadata_json or {}),
        )

    def map_message_item(self, model: AiAgentMessage) -> AgentMessageItem:
        """把消息 ORM 映射为接口模型。"""

        return AgentMessageItem(
            id=str(model.id),
            run_id=model.run_id,
            role=model.role,  # type: ignore[arg-type]
            content=model.content,
            reasoning_content=model.reasoning_content,
            created_at=_iso(model.created_at),
            attachments=[
                AgentMessageAttachmentItem.model_validate(item)
                for item in (model.attachments_json or [])
                if isinstance(item, dict)
            ],
        )

    def map_active_run(self, model: AiAgentRun | None) -> AgentActiveRunItem | None:
        """把 run ORM 映射为 active/last run 接口模型。"""

        if model is None:
            return None
        pending_requirement = None
        if model.status == "paused" and isinstance(model.pending_requirement_json, dict):
            pending_requirement = AgentPendingRequirement.model_validate(model.pending_requirement_json)
        return AgentActiveRunItem(
            run_id=model.run_id,
            session_id=model.session_id,
            agent_id=model.agent_id,
            status=_map_run_status(model.status),
            pending_requirement=pending_requirement,
            content=model.content,
            created_at=_iso(model.created_at),
            updated_at=_iso(model.updated_at),
            cancel_requested_at=_iso(model.cancel_requested_at),
            event_index=model.event_index,
        )

    def build_context_status(
        self,
        *,
        session_id: str,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
    ) -> AgentContextStatusItem:
        """构建无模型配置时的上下文状态兜底；真实 usage 缺失按 0 返回。"""

        _ = runtime_context
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=agent_id,
            compression_enabled=False,
            compression_required=False,
            compression_status="idle",
            compression_method="none",
            compression_error_message=None,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=0,
            max_output_tokens=0,
            history_token_ratio=0,
            compression_target_ratio=0,
            safety_margin_tokens=0,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=0,
            compression_target_tokens=0,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=0,
            context_input_budget_tokens=0,
            context_used_tokens=0,
            context_remaining_tokens=0,
            last_input_tokens=0,
            last_output_tokens=0,
            last_total_tokens=0,
            last_reasoning_tokens=0,
        )

    def _scope_query(self, query: Select[tuple[AiAgentSession]], *, agent_id: str, scope: AgentScopeContext) -> Select[tuple[AiAgentSession]]:
        """给会话查询追加当前用户、Agent 与 scope 过滤条件。"""

        return query.where(
            AiAgentSession.user_id == self._user_id,
            AiAgentSession.agent_id == agent_id,
            AiAgentSession.workspace_id == scope.workspace_id,
            AiAgentSession.scope_type == scope.scope_type,
            AiAgentSession.project_id.is_(scope.project_id) if scope.project_id is None else AiAgentSession.project_id == scope.project_id,
            AiAgentSession.page_id.is_(scope.page_id) if scope.page_id is None else AiAgentSession.page_id == scope.page_id,
            AiAgentSession.component_id.is_(scope.component_id) if scope.component_id is None else AiAgentSession.component_id == scope.component_id,
            AiAgentSession.source == scope.source,
        )

    def _workspace_scope_query(
        self,
        query: Select[tuple[AiAgentSession]],
        *,
        agent_id: str,
        workspace_id: int,
    ) -> Select[tuple[AiAgentSession]]:
        """给会话查询追加当前用户、Agent 与工作空间过滤条件。"""

        return query.where(
            AiAgentSession.user_id == self._user_id,
            AiAgentSession.agent_id == agent_id,
            AiAgentSession.workspace_id == workspace_id,
        )

    async def _append_message(
        self,
        *,
        session_id: str,
        run_id: str | None,
        role: str,
        content: str,
        reasoning_content: str | None = None,
        message_json: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> AiAgentMessage:
        """追加会话消息并分配顺序号。"""

        max_order = await self._session.scalar(
            select(func.max(AiAgentMessage.order_index)).where(AiAgentMessage.session_id == session_id)
        )
        model = AiAgentMessage(
            session_id=session_id,
            run_id=run_id,
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            message_json=message_json,
            attachments_json=attachments or [],
            order_index=int(max_order or -1) + 1,
        )
        self._session.add(model)
        return model

    async def _attachment_summaries(self, *, session_id: str, attachment_ids: list[int]) -> list[dict[str, Any]]:
        """读取已上传图片附件摘要，供消息展示。"""

        if not attachment_ids:
            return []
        result = await self._session.execute(
            select(AiAgentImageAttachment).where(
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.user_id == self._user_id,
                AiAgentImageAttachment.id.in_(attachment_ids),
                AiAgentImageAttachment.status == RecordStatus.ACTIVE.value,
            )
        )
        service = AgentImageAttachmentService(self._session, user_id=self._user_id)
        return [service._to_message_item(item).model_dump(mode="json") for item in result.scalars().all()]

    async def _tool_attachment_summaries(self, *, session_id: str) -> dict[tuple[str, str], list[AgentMessageAttachmentItem]]:
        """按 run/tool_call_id 返回工具输出图片附件摘要，用于 timeline 缩略图展示。"""

        result = await self._session.execute(
            select(AiAgentImageAttachment)
            .where(
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.user_id == self._user_id,
                AiAgentImageAttachment.source_kind == "tool_output",
                AiAgentImageAttachment.run_id.is_not(None),
                AiAgentImageAttachment.status == RecordStatus.ACTIVE.value,
            )
            .order_by(AiAgentImageAttachment.id.asc())
        )
        service = AgentImageAttachmentService(self._session, user_id=self._user_id)
        summaries: dict[tuple[str, str], list[AgentMessageAttachmentItem]] = {}
        for attachment in result.scalars().all():
            run_id = str(attachment.run_id or "")
            if not run_id:
                continue
            item = service._to_message_item(attachment)
            summaries.setdefault((run_id, str(attachment.tool_call_id or "")), []).append(item)
            if attachment.tool_name:
                summaries.setdefault((run_id, attachment.tool_name), []).append(item)
        return summaries

    def _tool_timeline_item(self, tool_call: AiAgentToolCall, *, order_index: int) -> AgentTimelineItem:
        """把工具调用映射为 timeline item。"""

        return AgentTimelineItem(
            id=f"tool-{tool_call.id}",
            session_id=tool_call.session_id,
            run_id=tool_call.run_id,
            kind="tool",
            role=None,
            event_index=None,
            order_index=order_index,
            content=None,
            status=tool_call.status,
            tool=AgentTimelineToolItem(
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.tool_name,
                member_run_id=tool_call.member_run_id,
                status=tool_call.status if tool_call.status in {"running", "completed", "error"} else "running",  # type: ignore[arg-type]
                input_payload=tool_call.input_payload_json,
                output_payload=tool_call.output_payload_json,
                message=tool_call.message or "",
            ),
            source="event",
            created_at=_iso(tool_call.created_at),
        )

    def _apply_event_to_run(self, run_model: AiAgentRun, event: AgentRunEvent) -> None:
        """根据平台事件更新 run 聚合字段。"""

        if event.event == "message.delta" and event.content:
            run_model.content = f"{run_model.content or ''}{event.content}"
        elif event.event == "reasoning.delta" and event.content:
            run_model.reasoning_content = f"{run_model.reasoning_content or ''}{event.content}"
        elif event.event == "run.paused":
            run_model.status = "paused"
            requirement = event.data.get("requirement") if isinstance(event.data, dict) else None
            run_model.pending_requirement_json = requirement if isinstance(requirement, dict) else None
        elif event.event == "run.completed":
            run_model.status = "completed"
            run_model.finished_at = _utc_now()
        elif event.event == "run.cancelled":
            run_model.status = "cancelled"
            run_model.finished_at = _utc_now()
        elif event.event == "run.error":
            run_model.status = "failed"
            run_model.finished_at = _utc_now()
        elif event.event == "run.cancelling":
            run_model.status = "cancelling"

    async def _sync_tool_event(self, run_model: AiAgentRun, event: AgentRunEvent) -> None:
        """把平台工具事件同步为工具调用详情。"""

        if event.event not in {
            "tool.started",
            "tool.completed",
            "tool.error",
            "member.tool.started",
            "member.tool.completed",
            "member.tool.error",
        }:
            return
        tool_name = str(event.data.get("tool_name") or "").strip()
        tool_call_id = str(event.data.get("tool_call_id") or "").strip() or None
        if not tool_name:
            return
        normalized_event = event.event.removeprefix("member.")
        member_run_id = _optional_str(event.data.get("member_run_id"))
        status = {
            "tool.started": "running",
            "tool.completed": "completed",
            "tool.error": "error",
        }[normalized_event]
        existing = None
        if tool_call_id:
            result = await self._session.execute(
                select(AiAgentToolCall).where(
                    AiAgentToolCall.run_id == run_model.run_id,
                    AiAgentToolCall.tool_call_id == tool_call_id,
                )
            )
            existing = result.scalar_one_or_none()
        if existing is None:
            existing = AiAgentToolCall(
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                member_run_id=member_run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status=status,
                input_payload_json=event.data.get("tool_args") or event.data.get("args"),
                output_payload_json=event.data.get("result"),
                message=str(event.data.get("message") or ""),
            )
            self._session.add(existing)
            return
        existing.status = status
        if member_run_id:
            existing.member_run_id = member_run_id
        input_payload = event.data.get("tool_args") or event.data.get("args")
        if _is_meaningful_payload(input_payload) and not _is_meaningful_payload(existing.input_payload_json):
            existing.input_payload_json = input_payload
        if event.data.get("result") is not None:
            existing.output_payload_json = event.data.get("result")
        if event.data.get("message") is not None:
            existing.message = str(event.data.get("message") or "")


def encode_sse_event(event: AgentRunEvent) -> bytes:
    """把平台事件编码为 SSE 数据块。"""

    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n".encode("utf-8")


async def stream_replay_then_subscribe(
    *,
    store: PlatformAgentRuntimeStore,
    run_id: str,
    event_index: int,
) -> AsyncGenerator[bytes, None]:
    """先从数据库回放事件，再订阅本进程实时事件，并用数据库轮询兜底跨进程恢复。"""

    last_index = event_index
    for event in await store.replay_events(run_id=run_id, event_index=last_index):
        yield encode_sse_event(event)
        last_index = event.event_index if event.event_index is not None else last_index
        if event.event in STREAM_END_EVENTS:
            return

    queue = _subscribe(run_id)
    last_keepalive_at = monotonic()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_EVENT_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                replayed = False
                for replayed_event in await store.replay_events(run_id=run_id, event_index=last_index):
                    replayed = True
                    yield encode_sse_event(replayed_event)
                    last_index = replayed_event.event_index if replayed_event.event_index is not None else last_index
                    if replayed_event.event in STREAM_END_EVENTS:
                        return
                if replayed:
                    last_keepalive_at = monotonic()
                    continue
                run_status = await store.get_run_status(run_id=run_id)
                if run_status in TERMINAL_RUN_STATUSES or run_status == "paused":
                    return
                now = monotonic()
                if now - last_keepalive_at >= _SSE_KEEPALIVE_INTERVAL_SECONDS:
                    yield b": keepalive\n\n"
                    last_keepalive_at = now
                continue
            if event is None:
                return
            if event.event_index is not None and event.event_index <= last_index:
                continue
            yield encode_sse_event(event)
            last_index = event.event_index if event.event_index is not None else last_index
            last_keepalive_at = monotonic()
            if event.event in STREAM_END_EVENTS:
                return
    finally:
        _unsubscribe(run_id, queue)


def subscribe_live_run_events(*, run_id: str) -> asyncio.Queue[AgentRunEvent | None]:
    """提前订阅指定 run 的本进程实时事件。"""

    return _subscribe(run_id)


async def stream_live_subscribe(
    *,
    run_id: str,
    queue: asyncio.Queue[AgentRunEvent | None] | None = None,
) -> AsyncGenerator[bytes, None]:
    """只订阅本进程实时事件；queue 可由调用方提前创建以避免启动竞态。"""

    live_queue = queue or _subscribe(run_id)
    try:
        while True:
            event = await live_queue.get()
            if event is None:
                return
            if event.event == "run.cancelling":
                continue
            yield encode_sse_event(event)
            if event.event in STREAM_END_EVENTS:
                return
    finally:
        _unsubscribe(run_id, live_queue)


def new_session_id() -> str:
    """生成平台会话 ID。"""

    return f"session-{uuid4().hex}"


def _scope_metadata(scope: AgentScopeContext) -> dict[str, Any]:
    """把 scope 转成会话 metadata。"""

    return scope.model_dump(mode="json")


def _timeline_sort_key(
    run_order: dict[str, int],
    *,
    run_id: str,
    event_index: int | None,
    phase: int,
    created_at: str | None,
    fallback_id: str,
) -> tuple[int, int, int, str, str]:
    """生成前端 timeline 的全局排序 key；phase 负责把用户消息放到 run 事件前。"""

    max_event_index = 1_000_000_000
    run_position = run_order.get(run_id, max_event_index)
    if event_index is None:
        event_position = -1 if phase < 0 else max_event_index
    else:
        event_position = event_index
    return (run_position, event_position, phase, created_at or "", fallback_id)


def _optional_str(value: Any) -> str | None:
    """把可选事件字段规整为字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _member_input_prompt(member_run: AiAgentMemberRun) -> str | None:
    """读取成员 run 的传入提示词，兼容旧数据中仅保存委派参数的情况。"""

    payload = member_run.input_payload_json if isinstance(member_run.input_payload_json, dict) else {}
    prompt = build_member_prompt_from_payload(payload)
    if prompt:
        return prompt
    return _message_history_text(
        member_run.message_history_json,
        message_kind="request",
        part_kinds={"user-prompt"},
    )


def _member_output_prompt(member_run: AiAgentMemberRun) -> str | None:
    """读取成员 run 返回给内容助手整合的输出提示词。"""

    return (
        _optional_str(member_run.content)
        or _message_history_text(
            member_run.message_history_json,
            message_kind="response",
            part_kinds={"text"},
            reverse=True,
        )
        or _optional_str(member_run.error_message)
    )


def _message_history_text(
    history: list[dict[str, Any]] | None,
    *,
    message_kind: str,
    part_kinds: set[str],
    reverse: bool = False,
) -> str | None:
    """从 Pydantic AI 消息历史中提取指定消息和 part 类型的文本。"""

    messages = [item for item in (history or []) if isinstance(item, dict)]
    iterable = reversed(messages) if reverse else iter(messages)
    for message in iterable:
        if message.get("kind") != message_kind:
            continue
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        texts = [
            str(part.get("content")).strip()
            for part in parts
            if isinstance(part, dict)
            and part.get("part_kind") in part_kinds
            and _optional_str(part.get("content"))
        ]
        if texts:
            return "\n\n".join(texts)
    return None


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """按顺序读取第一个存在的 key，保留空 dict、0、False 等合法值。"""

    for key in keys:
        if key in data:
            return data[key]
    return None


def _is_meaningful_payload(value: Any) -> bool:
    """判断工具 payload 是否携带真实参数，避免空串覆盖后续完整参数。"""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _mark_open_tool_items_failed(
    tool_items: dict[tuple[str, str], AgentTimelineItem],
    *,
    run_id: str,
    message: str,
) -> None:
    """回放到 run.error 时收敛同 run 中仍处于 running 的工具展示项。"""

    for (item_run_id, _), item in tool_items.items():
        if item_run_id != run_id or item.kind != "tool" or item.tool is None:
            continue
        if item.tool.status != "running":
            continue
        item.status = "error"
        item.tool.status = "error"
        item.tool.message = item.tool.message or message


def _map_run_status(status: str) -> str:
    """把数据库状态映射为接口状态枚举。"""

    if status == "failed":
        return "failed"
    if status in {"pending", "running", "paused", "cancelling", "completed", "cancelled"}:
        return status
    return "failed"


def _utc_now() -> datetime:
    """返回 UTC 当前时间。"""

    return datetime.now(tz=UTC)


def _iso(value: datetime | None) -> str | None:
    """把 datetime 转为接口字符串。"""

    return value.isoformat() if value is not None else None


def _subscribe(run_id: str) -> asyncio.Queue[AgentRunEvent | None]:
    """订阅指定 run 的实时平台事件。"""

    queue: asyncio.Queue[AgentRunEvent | None] = asyncio.Queue()
    _SUBSCRIBERS.setdefault(run_id, set()).add(queue)
    return queue


def _unsubscribe(run_id: str, queue: asyncio.Queue[AgentRunEvent | None]) -> None:
    """取消订阅指定 run。"""

    queues = _SUBSCRIBERS.get(run_id)
    if not queues:
        return
    queues.discard(queue)
    if not queues:
        _SUBSCRIBERS.pop(run_id, None)


def _notify_subscribers(run_id: str, event: AgentRunEvent) -> None:
    """向本进程订阅者推送平台事件。"""

    for queue in list(_SUBSCRIBERS.get(run_id, ())):
        queue.put_nowait(event)
    if event.event in STREAM_END_EVENTS:
        for queue in list(_SUBSCRIBERS.get(run_id, ())):
            queue.put_nowait(None)
