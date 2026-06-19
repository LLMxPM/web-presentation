"""文件功能：提供平台自有智能体运行态的读写、事件追加、快照构建与 SSE 编码能力。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.runtime_context import AgentRuntimeContext
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

ACTIVE_RUN_STATUSES = {"pending", "running", "paused", "cancelling"}
TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}
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

    async def list_sessions(self, *, agent_id: str, scope: AgentScopeContext) -> list[AgentSessionItem]:
        """按当前用户、Agent 与 scope 返回未删除会话列表。"""

        result = await self._session.execute(
            self._scope_query(select(AiAgentSession), agent_id=agent_id, scope=scope)
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

    async def append_assistant_message(
        self,
        run_model: AiAgentRun,
        *,
        content: str,
        reasoning_content: str | None = None,
        message_history: list[dict[str, Any]] | None = None,
    ) -> None:
        """保存一次运行完成后的助手消息和 Pydantic AI 历史。"""

        if content:
            await self._append_message(
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                role="assistant",
                content=content,
                reasoning_content=reasoning_content,
                message_json={"message_history": message_history or []},
            )
        if message_history is not None:
            run_model.message_history_json = message_history

    async def save_run_message_history(self, run_model: AiAgentRun, message_history: list[dict[str, Any]]) -> None:
        """保存 Pydantic AI 历史消息并提交。"""

        run_model.message_history_json = message_history
        run_model.updated_at = _utc_now()
        await self._session.commit()

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
        run_model.status = status
        run_model.finished_at = _utc_now() if status in TERMINAL_RUN_STATUSES else None
        run_model.error_code = error_code
        run_model.error_message = error_message
        event_name = {
            "completed": "run.completed",
            "cancelled": "run.cancelled",
            "failed": "run.error",
            "paused": "run.paused",
        }[status]
        return await self.append_event(
            run_model,
            AgentRunEvent(
                event=event_name,
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                content=content,
                data={"message": error_message or content} if error_message or content else {},
            ),
        )

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
        return AgentSessionRuntimeSnapshot(
            session=self.map_session_item(session_model),
            timeline_items=timeline_items,
            member_runs=member_runs,
            context_status=self.build_context_status(session_id=session_id, agent_id=agent_id, runtime_context=runtime_context),
            active_run=active_run,
            last_run=last_run,
            pending_requirement=pending_requirement,
            event_index=active_run.event_index if active_run is not None else (last_run.event_index if last_run else -1),
            pending_attachments=[],
        )

    async def replay_events(self, *, run_id: str, event_index: int) -> list[AgentRunEvent]:
        """读取指定 event_index 之后的事件。"""

        result = await self._session.execute(
            select(AiAgentRunEvent)
            .where(AiAgentRunEvent.run_id == run_id, AiAgentRunEvent.event_index > event_index)
            .order_by(AiAgentRunEvent.event_index.asc())
        )
        return [AgentRunEvent.model_validate(row.payload_json) for row in result.scalars().all()]

    async def build_timeline_items(self, *, session_id: str) -> list[AgentTimelineItem]:
        """基于平台消息、工具调用、requirement 与事件生成会话 timeline。"""

        items: list[AgentTimelineItem] = []
        order = 0
        message_result = await self._session.execute(
            select(AiAgentMessage)
            .where(AiAgentMessage.session_id == session_id)
            .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        )
        messages = message_result.scalars().all()
        assistant_message_run_ids = {item.run_id for item in messages if item.role == "assistant" and item.run_id}
        for message in messages:
            if message.role == "assistant" and message.reasoning_content:
                items.append(
                    AgentTimelineItem(
                        id=f"message-{message.id}-reasoning",
                        session_id=message.session_id,
                        run_id=message.run_id or "",
                        kind="reasoning",
                        role=None,
                        event_index=None,
                        order_index=order,
                        content=message.reasoning_content,
                        status=None,
                        tool=None,
                        source="message",
                        created_at=_iso(message.created_at),
                    )
                )
                order += 1
            items.append(
                AgentTimelineItem(
                    id=f"message-{message.id}",
                    session_id=message.session_id,
                    run_id=message.run_id or "",
                    kind="message",
                    role=message.role if message.role in {"user", "assistant"} else None,  # type: ignore[arg-type]
                    event_index=None,
                    order_index=order,
                    content=message.content,
                    status=None,
                    tool=None,
                    source="message",
                    created_at=_iso(message.created_at),
                )
            )
            order += 1

        run_result = await self._session.execute(
            select(AiAgentRun)
            .where(AiAgentRun.session_id == session_id, AiAgentRun.run_id.not_in(assistant_message_run_ids))
            .order_by(AiAgentRun.created_at.asc())
        )
        for run in run_result.scalars().all():
            if run.reasoning_content:
                items.append(
                    AgentTimelineItem(
                        id=f"run-{run.run_id}-reasoning",
                        session_id=run.session_id,
                        run_id=run.run_id,
                        kind="reasoning",
                        role=None,
                        event_index=run.event_index,
                        order_index=order,
                        content=run.reasoning_content,
                        status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                        tool=None,
                        source="event",
                        created_at=_iso(run.created_at),
                    )
                )
                order += 1
            if run.content:
                items.append(
                    AgentTimelineItem(
                        id=f"run-{run.run_id}-message",
                        session_id=run.session_id,
                        run_id=run.run_id,
                        kind="message",
                        role="assistant",
                        event_index=run.event_index,
                        order_index=order,
                        content=run.content,
                        status="running" if run.status in ACTIVE_RUN_STATUSES else None,
                        tool=None,
                        source="event",
                        created_at=_iso(run.created_at),
                    )
                )
                order += 1

        tool_result = await self._session.execute(
            select(AiAgentToolCall)
            .where(AiAgentToolCall.session_id == session_id, AiAgentToolCall.member_run_id.is_(None))
            .order_by(AiAgentToolCall.created_at.asc(), AiAgentToolCall.id.asc())
        )
        for tool_call in tool_result.scalars().all():
            items.append(self._tool_timeline_item(tool_call, order_index=order))
            order += 1

        req_result = await self._session.execute(
            select(AiAgentRequirement)
            .where(AiAgentRequirement.session_id == session_id, AiAgentRequirement.status == "pending")
            .order_by(AiAgentRequirement.created_at.asc())
        )
        for requirement in req_result.scalars().all():
            items.append(
                AgentTimelineItem(
                    id=f"requirement-{requirement.requirement_id}",
                    session_id=requirement.session_id,
                    run_id=requirement.run_id,
                    kind="requirement",
                    role=None,
                    event_index=None,
                    order_index=order,
                    content=requirement.payload_json.get("note"),
                    status="paused",
                    tool=None,
                    source="event",
                    created_at=_iso(requirement.created_at),
                )
            )
            order += 1
        return sorted(items, key=lambda item: (item.order_index, item.created_at or ""))

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
        member_runs: list[AgentMemberRunItem] = []
        for member_run in result.scalars().all():
            tool_result = await self._session.execute(
                select(AiAgentToolCall)
                .where(AiAgentToolCall.member_run_id == member_run.member_run_id)
                .order_by(AiAgentToolCall.created_at.asc(), AiAgentToolCall.id.asc())
            )
            timeline = [
                self._tool_timeline_item(tool_call, order_index=index)
                for index, tool_call in enumerate(tool_result.scalars().all())
            ]
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
                    timeline_items=timeline,
                )
            )
        return member_runs

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
        """构建轻量上下文预算状态；精确 token 压缩后续由 history policy 接管。"""

        fixed_context = len(str(runtime_context.page_content or "") + str(runtime_context.component_code or ""))
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=agent_id,
            compression_enabled=False,
            compression_required=False,
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
            fixed_context_tokens=fixed_context,
            history_budget_tokens=0,
            compression_target_tokens=0,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=0,
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
        return [
            {
                "id": item.id,
                "original_name": item.original_name,
                "content_type": item.content_type,
                "file_size": item.file_size,
                "url": "",
                "promoted_asset_id": item.promoted_asset_id,
            }
            for item in result.scalars().all()
        ]

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

        if event.event not in {"tool.started", "tool.completed", "tool.error"}:
            return
        tool_name = str(event.data.get("tool_name") or "").strip()
        tool_call_id = str(event.data.get("tool_call_id") or "").strip() or None
        if not tool_name:
            return
        status = {
            "tool.started": "running",
            "tool.completed": "completed",
            "tool.error": "error",
        }[event.event]
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
    """先从数据库回放事件，再订阅本进程实时事件。"""

    last_index = event_index
    for event in await store.replay_events(run_id=run_id, event_index=last_index):
        yield encode_sse_event(event)
        last_index = event.event_index if event.event_index is not None else last_index

    queue = _subscribe(run_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
                continue
            if event is None:
                return
            if event.event_index is not None and event.event_index <= last_index:
                continue
            yield encode_sse_event(event)
            last_index = event.event_index if event.event_index is not None else last_index
            if event.event in {"run.completed", "run.cancelled", "run.error", "run.paused"}:
                return
    finally:
        _unsubscribe(run_id, queue)


def new_session_id() -> str:
    """生成平台会话 ID。"""

    return f"session-{uuid4().hex}"


def _scope_metadata(scope: AgentScopeContext) -> dict[str, Any]:
    """把 scope 转成会话 metadata。"""

    return scope.model_dump(mode="json")


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
    if event.event in {"run.completed", "run.cancelled", "run.error", "run.paused"}:
        for queue in list(_SUBSCRIBERS.get(run_id, ())):
            queue.put_nowait(None)
