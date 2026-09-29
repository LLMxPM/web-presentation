"""文件功能：提供平台自有智能体运行态的读写、事件追加与快照构建能力（持久化门面）。

职责边界：
- 本模块只保留 PlatformAgentRuntimeStore 持久化/状态机与兼容再导出。
- 事件追加锁见 `app.ai.run_event_locks`；SSE 订阅与编码见 `app.ai.run_sse_stream`；
  timeline 事件投影见 `app.ai.run_timeline_build`；ORM→Schema 映射见 `app.ai.run_value_maps`。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.retry import WriteConflictContext, exponential_backoff_delays, run_with_write_retry
from app.ai.image_refs import sanitize_message_history_image_refs
from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.run_event_locks import get_run_event_lock
from app.ai.run_event_writer import allocate_run_event_index
from app.ai.run_sse_stream import (
    STREAM_END_EVENTS,
    encode_sse_event,
    get_live_run_activity_version,
    notify_subscribers,
    stream_live_subscribe,
    stream_replay_then_subscribe,
    subscribe_live_run_events,
    update_live_run_activity,
)
from app.ai.run_timeline_build import (
    ACTIVE_RUN_STATUSES,
    RunTimelineProjector,
    as_utc,
    first_present,
    is_meaningful_payload,
    iso,
    tool_input_attachment_ids,
    utc_now,
)
from app.ai.run_value_maps import (
    build_context_status as _build_context_status_impl,
    map_active_run,
    map_message_item,
    map_run_status,
    map_session_item,
    scope_metadata,
    tool_timeline_item,
)
from app.ai.run_write_fence import AgentRunWriteFence
from app.ai.external_task_control import seal_external_batch_for_requirement
from app.ai.tool_arguments import parse_tool_arguments
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.ai_agent_runtime import (
    AiAgentMessage,
    AiAgentRequirement,
    AiAgentRun,
    AiAgentRunEvent,
    AiAgentSession,
    AiAgentToolCall,
)
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentContextStatusItem,
    AgentMessageAttachmentItem,
    AgentMessageItem,
    AgentPendingRequirement,
    AgentRunEvent,
    AgentRunContextSummary,
    AgentRunProjectSummary,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
    AgentTimelineItem,
    AgentTimelineToolItem,
)
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.durable_job_lease_service import build_durable_worker_id

TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}
STALE_ACTIVE_RUN_ERROR_CODE = "AI_AGENT_STREAM_IDLE_TIMEOUT"
STALE_ACTIVE_RUN_ERROR_MESSAGE = "模型或工具流长时间没有返回新事件，本次运行已停止。"
_EVENT_WRITE_MAX_ATTEMPTS = 4
_EVENT_WRITE_RETRY_BASE_SECONDS = 0.025

# 兼容既有 monkeypatch 与同模块调用名（测试仍从 platform_runtime 改写）。
_get_run_event_lock = get_run_event_lock
_update_live_run_activity = update_live_run_activity
_notify_subscribers = notify_subscribers
_iso = iso
_as_utc = as_utc
_utc_now = utc_now


@dataclass(slots=True)
class PlatformRunStart:
    """描述一次平台 run 启动后的核心对象。"""

    session_model: AiAgentSession
    run_model: AiAgentRun


class PlatformAgentRuntimeStore:
    """封装平台自有 AI 运行态表的读写和事件协议。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        write_fence: AgentRunWriteFence | None = None,
    ) -> None:
        """保存数据库会话、用户和可选后台续跑写入围栏。"""

        self._session = session
        self._user_id = user_id
        self._write_fence = write_fence

    def map_session_item(self, model: AiAgentSession) -> AgentSessionItem:
        """把会话 ORM 映射为接口模型。"""

        return map_session_item(model)

    def map_message_item(self, model: AiAgentMessage) -> AgentMessageItem:
        """把消息 ORM 映射为接口模型。"""

        return map_message_item(model)

    def map_active_run(self, model: AiAgentRun | None) -> AgentActiveRunItem | None:
        """把 run ORM 映射为 active/last run 接口模型。"""

        return map_active_run(model)

    def build_context_status(
        self,
        *,
        session_id: str,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
    ) -> AgentContextStatusItem:
        """构建无模型配置时的上下文状态兜底。"""

        return _build_context_status_impl(
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
        )

    def _tool_timeline_item(self, tool_call: AiAgentToolCall, *, order_index: int) -> AgentTimelineItem:
        """把工具调用映射为 timeline item。"""

        return tool_timeline_item(tool_call, order_index=order_index)

    async def build_timeline_items(self, *, session_id: str) -> list[AgentTimelineItem]:
        """基于平台消息、工具调用、requirement 与事件生成会话 timeline。"""

        return await RunTimelineProjector(self._session, user_id=self._user_id).build_timeline_items(
            session_id=session_id
        )

    async def _tool_attachment_summaries(self, *, session_id: str) -> dict[tuple[str, str], list[AgentMessageAttachmentItem]]:
        """按 run/tool_call_id 返回工具输出图片附件摘要。"""

        return await RunTimelineProjector(self._session, user_id=self._user_id)._tool_attachment_summaries(
            session_id=session_id
        )

    async def _attachment_summary_lookup(self, *, session_id: str) -> dict[int, AgentMessageAttachmentItem]:
        """返回会话 active 图片附件摘要映射。"""

        return await RunTimelineProjector(self._session, user_id=self._user_id)._attachment_summary_lookup(
            session_id=session_id
        )


    async def list_sessions(
        self,
        *,
        agent_id: str,
        workspace_id: int,
    ) -> list[AgentSessionItem]:
        """按当前用户、Agent 与工作空间返回未归档会话列表。"""

        query = self._workspace_scope_query(select(AiAgentSession), agent_id=agent_id, workspace_id=workspace_id)

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
        workspace_id: int,
        focus_mode: str,
        pinned_project_id: int | None,
        work_scope_mode: str,
        allowed_project_ids: list[int],
        llm_metadata: dict[str, Any] | None = None,
    ) -> AgentSessionItem:
        """创建平台 Agent 会话。"""

        now = _utc_now()
        metadata: dict[str, Any] = {}
        if llm_metadata is not None:
            metadata["llm"] = dict(llm_metadata)
        model = AiAgentSession(
            session_id=session_id,
            agent_id=agent_id,
            user_id=self._user_id,
            session_name=session_name,
            workspace_id=workspace_id,
            focus_mode=focus_mode,
            pinned_project_id=pinned_project_id,
            work_scope_mode=work_scope_mode,
            allowed_project_ids_json=list(allowed_project_ids),
            focus_version=0,
            metadata_json=metadata,
            created_by=self._user_id,
            updated_by=self._user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self.map_session_item(model)

    async def update_session_preferences(
        self,
        *,
        session_id: str,
        agent_id: str,
        focus_mode: str,
        pinned_project_id: int | None,
        work_scope_mode: str,
        allowed_project_ids: list[int],
    ) -> AgentSessionItem:
        """更新会话偏好并递增版本；已创建 Run 的快照不会被修改。"""

        model = await self.require_session(session_id=session_id, agent_id=agent_id)
        model.focus_mode = focus_mode
        model.pinned_project_id = pinned_project_id
        model.work_scope_mode = work_scope_mode
        model.allowed_project_ids_json = list(allowed_project_ids)
        model.focus_version += 1
        model.updated_by = self._user_id
        model.updated_at = _utc_now()
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
        llm_config_id: int | None = None,
        llm_metadata: dict[str, Any] | None = None,
        session_llm_metadata: dict[str, Any] | None = None,
        runtime_context: AgentRuntimeContext | None = None,
    ) -> PlatformRunStart:
        """创建平台 run、用户消息与首个 run.started 事件。"""

        session_model = await self.require_session(session_id=session_id, agent_id=agent_id)
        await self.ensure_no_active_run(session_id=session_id, agent_id=agent_id)
        now = _utc_now()
        focus_snapshot = scope.model_copy(update={
            "workspace_name": runtime_context.workspace_name if runtime_context else scope.workspace_name,
            "project_name": runtime_context.project_name if runtime_context else scope.project_name,
            "page_title": runtime_context.page_title if runtime_context else scope.page_title,
            "component_name": runtime_context.component_name if runtime_context else scope.component_name,
        })
        allowed_projects = [
            {"id": project_id, "name": project_name}
            for project_id, project_name in (runtime_context.allowed_projects if runtime_context else ())
        ]
        if not allowed_projects:
            allowed_projects = [
                {"id": int(project_id), "name": None}
                for project_id in (session_model.allowed_project_ids_json or [])
            ]
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
            llm_config_id=llm_config_id,
            llm_config_snapshot_json=dict(llm_metadata) if llm_metadata is not None else None,
            process_owner=build_durable_worker_id(),
            input_payload_json={
                "message": message,
                "image_attachment_ids": list(image_attachment_ids or []),
                "llm_config_id": llm_config_id,
                "focus": focus_snapshot.model_dump(mode="json"),
                "work_scope_mode": session_model.work_scope_mode,
                "allowed_project_ids": list(session_model.allowed_project_ids_json or []),
                "allowed_projects": allowed_projects,
                "focus_version": session_model.focus_version,
            },
            message_history_json=[],
            event_index=-1,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        if session_llm_metadata is not None:
            session_metadata = dict(session_model.metadata_json or {})
            session_metadata["llm"] = dict(session_llm_metadata)
            session_model.metadata_json = session_metadata
        self._session.add(run_model)
        # PostgreSQL 会立即校验消息表 run_id 外键；先刷入父 run，避免同批 flush 时子表先插入。
        try:
            await self._session.flush([run_model])
        except IntegrityError as exc:
            if not _is_active_run_unique_conflict(exc):
                raise
            await self._session.rollback()
            raise ValueError("AI_SESSION_RUN_ACTIVE") from exc
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
        await self.append_event(
            run_model,
            AgentRunEvent(
                event="run.focus.snapshot",
                run_id=run_id,
                session_id=session_id,
                data={
                    "focus": focus_snapshot.model_dump(mode="json"),
                    "work_scope_mode": session_model.work_scope_mode,
                    "allowed_project_ids": list(session_model.allowed_project_ids_json or []),
                    "allowed_projects": allowed_projects,
                    "focus_version": session_model.focus_version,
                },
            ),
            commit=False,
        )
        session_model.updated_at = now
        await self._session.commit()
        await self._session.refresh(session_model)
        await self._session.refresh(run_model)
        return PlatformRunStart(session_model=session_model, run_model=run_model)

    async def append_event(self, run_model: AiAgentRun, event: AgentRunEvent, *, commit: bool = True) -> AgentRunEvent:
        """为 run 追加平台事件，分配单调 event_index 并通知订阅者。"""

        run_id = run_model.run_id
        has_sqlite_write_transaction = await self._has_sqlite_write_transaction()
        retry_after_rollback = (
            commit
            and not has_sqlite_write_transaction
            and not self._session_has_pending_changes()
        )
        if has_sqlite_write_transaction:
            return await self._append_event_once(run_model, event, commit=commit)
        async with _get_run_event_lock(run_id):
            if retry_after_rollback:
                return await self._append_event_with_retry(run_model, event)
            return await self._append_event_once(run_model, event, commit=commit)

    async def _append_event_with_retry(
        self,
        run_model: AiAgentRun,
        event: AgentRunEvent,
    ) -> AgentRunEvent:
        """为无额外 pending 状态的纯追加执行写冲突 rollback 与有限退避重试。"""

        current = run_model
        # rollback 会 expire 会话内全部实体，重试钩子只能使用此处预先取出的标量，
        # 不能在 rollback 之后读取 ORM 属性（会触发同步懒加载并抛 MissingGreenlet）。
        run_id = run_model.run_id

        async def _append_once(_: AsyncSession) -> AgentRunEvent:
            """在当前会话内追加一次事件；run 引用由重试钩子刷新后经闭包读取。"""

            return await self._append_event_once(current, event, commit=True)

        async def _reload_run(context: WriteConflictContext) -> None:
            """重试前重读 run，使聚合字段基于最新已提交内容继续追加。"""

            nonlocal current
            refreshed_run = await context.session.get(AiAgentRun, run_id, populate_existing=True)
            if refreshed_run is None:
                raise ValueError("AI_RUN_NOT_FOUND") from context.error
            current = refreshed_run

        return await run_with_write_retry(
            _append_once,
            session=self._session,
            backoff_delays=exponential_backoff_delays(
                _EVENT_WRITE_MAX_ATTEMPTS, _EVENT_WRITE_RETRY_BASE_SECONDS
            ),
            on_conflict=_reload_run,
        )

    async def _append_event_once(
        self,
        run_model: AiAgentRun,
        event: AgentRunEvent,
        *,
        commit: bool,
    ) -> AgentRunEvent:
        """在当前事务内原子分配游标、保存事件并同步运行态投影。"""

        _normalize_tool_event_arguments(event)
        await self._enrich_visual_tool_event_attachments(run_model, event)
        now = _utc_now()
        next_index = await allocate_run_event_index(
            self._session,
            run_id=run_model.run_id,
            updated_at=now,
            require_active=False,
            write_fence=self._write_fence,
        )
        await self._refresh_event_projection_source(run_model, event)
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
        run_model.updated_at = now
        self._apply_event_to_run(run_model, event)
        await self._sync_tool_event(run_model, event)
        if commit:
            await self._session.commit()
        update_live_run_activity(run_model.run_id, event)
        notify_subscribers(run_model.run_id, event)
        return event

    async def _enrich_visual_tool_event_attachments(self, run_model: AiAgentRun, event: AgentRunEvent) -> None:
        """为视觉工具实时事件补齐认证附件摘要，使 SSE 与刷新快照呈现一致。"""

        if event.event not in {"tool.started", "tool.completed", "tool.error"}:
            return
        tool_name = str(event.data.get("tool_name") or "").strip()
        if tool_name not in {"analyze_visuals", "generate_image"}:
            return
        raw_input = event.data.get("tool_args") if "tool_args" in event.data else event.data.get("args")
        input_payload = parse_tool_arguments(raw_input)
        input_ids = tool_input_attachment_ids(input_payload)
        if input_ids:
            event.data["input_attachments"] = await self._attachment_summaries(
                session_id=run_model.session_id,
                attachment_ids=input_ids,
            )
        if event.event != "tool.completed":
            return
        tool_call_id = str(event.data.get("tool_call_id") or "").strip()
        summaries = await self._tool_attachment_summaries(session_id=run_model.session_id)
        output_attachments = (
            summaries.get((run_model.run_id, tool_call_id), [])
            if tool_call_id
            else summaries.get((run_model.run_id, tool_name), [])
        )
        event.data["output_attachments"] = [
            item.model_dump(mode="json")
            for item in output_attachments
        ]

    async def _refresh_event_projection_source(self, run_model: AiAgentRun, event: AgentRunEvent) -> None:
        """持有原子游标写锁后刷新增量聚合字段，避免并发 delta 覆盖已提交内容。"""

        attribute_name = {
            "message.delta": "content",
            "reasoning.delta": "reasoning_content",
        }.get(event.event)
        if attribute_name is not None:
            await self._session.refresh(run_model, attribute_names=[attribute_name])

    def _session_has_pending_changes(self) -> bool:
        """判断当前事务是否含调用方尚未提交的状态，防止锁重试 rollback 丢失业务变更。"""

        if self._session.new or self._session.deleted:
            return True
        return any(
            self._session.is_modified(model, include_collections=False)
            for model in self._session.dirty
        )

    async def _has_sqlite_write_transaction(self) -> bool:
        """判断 SQLite 连接是否已执行未提交 DML，避免进程锁与数据库写锁发生锁序反转。"""

        from app.db.locks import holds_write_lock

        await self._session.connection()
        return holds_write_lock(self._session)

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
            await self.ensure_write_fence()
            await self._session.commit()

    async def ensure_write_fence(self) -> None:
        """在非事件型提交前验证后台续跑租约，普通交互式 run 不附加任何开销。"""

        if self._write_fence is None:
            return
        await self._write_fence.ensure_owned(self._session, now=_utc_now())

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
            # 原始 Pydantic 检查点保留用于审计；后续模型历史在重建时派生安全副本。
            run_model.pending_requirement_json = None
        run_model.status = status
        run_model.finished_at = _utc_now() if status in TERMINAL_RUN_STATUSES else None
        run_model.error_code = error_code
        run_model.error_message = error_message
        if status == "failed":
            await self._close_pending_requirements(
                run_model,
                status="failed",
                message=error_message or content or "运行失败，待处理动作已终止。",
            )
            await self._append_running_tool_error_events(
                run_model,
                message=error_message or content or "运行中断，工具调用未完成。",
            )
        elif status == "cancelled":
            await self._close_pending_requirements(
                run_model,
                status="cancelled",
                message=content or "运行已取消，待处理动作已终止。",
            )
            await self._append_running_tool_error_events(
                run_model,
                message=content or "运行已取消，工具调用未完成。",
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
            tool_call.status = "interrupted"
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
                        "code": "AI_TOOL_INTERRUPTED",
                        "outcome": "unknown",
                    },
                ),
                commit=False,
            )
            await self._session.flush()

    async def _close_pending_requirements(
        self,
        run_model: AiAgentRun,
        *,
        status: str,
        message: str,
    ) -> None:
        """终止 run 时同步收敛尚未处理的 requirement，避免前端残留可提交动作。"""

        result = await self._session.execute(
            select(AiAgentRequirement).where(
                AiAgentRequirement.run_id == run_model.run_id,
                AiAgentRequirement.status.in_(("pending", "resolving")),
            )
        )
        now = _utc_now()
        for requirement in result.scalars().all():
            requirement.status = status
            requirement.resolved_at = now
            requirement.resolved_payload_json = {"reason": message, "terminal_status": status}
        await self._session.flush()

    async def pause_for_requirement(
        self,
        run_model: AiAgentRun,
        *,
        requirement: AgentPendingRequirement,
    ) -> AgentRunEvent:
        """保存 pending requirement；外部任务进入等待态，其余动作进入用户暂停态。"""

        payload = requirement.model_dump(mode="json")
        is_external_job = requirement.kind == "external_job"
        run_model.status = "waiting_external" if is_external_job else "paused"
        run_model.pending_requirement_json = payload
        requirement_model = AiAgentRequirement(
                requirement_id=requirement.id or f"req-{uuid4().hex}",
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                kind=requirement.kind,
                status="pending",
                tool_call_id=str(requirement.tool_execution.get("tool_call_id") or "") or None,
                tool_name=requirement.tool_name,
                payload_json=payload,
            )
        self._session.add(requirement_model)
        await self._session.flush([requirement_model])
        if is_external_job and _requirement_uses_unified_external_batch(payload):
            await seal_external_batch_for_requirement(
                self._session,
                run=run_model,
                requirement=requirement_model,
            )
        return await self.append_event(
            run_model,
            AgentRunEvent(
                event="run.waiting" if is_external_job else "run.paused",
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
        """幂等标记Requirement已解决，禁止覆盖失败或取消终态。"""

        if requirement.status == "resolved":
            return
        if requirement.status not in {"pending", "resolving"}:
            raise ValueError("AI_RUN_REQUIREMENT_STALE")
        requirement.status = "resolved"
        requirement.resolved_payload_json = payload
        requirement.resolved_at = _utc_now()
        await self._session.flush()

    async def begin_requirement_resolution(
        self,
        requirement: AiAgentRequirement,
        *,
        payload: dict[str, Any],
    ) -> None:
        """把Requirement置为resolving；只有结果进入模型历史后才能最终resolved。"""

        if requirement.status not in {"pending", "resolving"}:
            raise ValueError("AI_RUN_REQUIREMENT_STALE")
        requirement.status = "resolving"
        requirement.resolved_payload_json = payload
        requirement.resolved_at = None
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

    async def recover_stale_active_run(
        self,
        *,
        run_model: AiAgentRun | None = None,
        run_id: str | None = None,
        idle_timeout_seconds: float | None = None,
    ) -> AgentRunEvent | None:
        """发现 active run 长时间没有事件时写入终态，避免会话永久残留 running。"""

        target = run_model
        if target is None:
            normalized_run_id = str(run_id or "").strip()
            if not normalized_run_id:
                return None
            result = await self._session.execute(
                select(AiAgentRun).where(
                    AiAgentRun.run_id == normalized_run_id,
                    AiAgentRun.user_id == self._user_id,
                    AiAgentRun.status.in_(ACTIVE_RUN_STATUSES),
                )
            )
            target = result.scalar_one_or_none()
        if target is None:
            return None
        if target.user_id != self._user_id or target.status not in ACTIVE_RUN_STATUSES or target.status in {"paused", "waiting_external"}:
            return None

        timeout_seconds = (
            float(idle_timeout_seconds)
            if idle_timeout_seconds is not None
            else float(get_settings().ai_agent_stream_idle_timeout_seconds)
        )
        if timeout_seconds <= 0:
            return None
        last_event_at = await self._last_run_event_created_at(target.run_id)
        anchor = _as_utc(last_event_at or target.updated_at or target.started_at or target.created_at)
        if (_utc_now() - anchor).total_seconds() < timeout_seconds:
            return None

        if target.status == "cancelling" or target.cancel_requested_at is not None:
            return await self.mark_terminal(target, status="cancelled", content="用户停止了当前运行。")
        return await self.mark_terminal(
            target,
            status="failed",
            error_code=STALE_ACTIVE_RUN_ERROR_CODE,
            error_message=STALE_ACTIVE_RUN_ERROR_MESSAGE,
        )

    async def _last_run_event_created_at(self, run_id: str) -> datetime | None:
        """读取 run 最近事件时间，用于判断运行态是否已经空闲过久。"""

        result = await self._session.execute(
            select(func.max(AiAgentRunEvent.created_at)).where(AiAgentRunEvent.run_id == run_id)
        )
        return result.scalar_one_or_none()

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
        elif event.event == "run.waiting":
            run_model.status = "waiting_external"
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
        }:
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
        if event.event == "tool.error" and event.data.get("outcome") == "unknown":
            status = "interrupted"
        raw_input_payload = (
            event.data.get("tool_args")
            if "tool_args" in event.data
            else event.data.get("args")
        )
        input_payload = parse_tool_arguments(raw_input_payload)
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
                input_payload_json=input_payload,
                output_payload_json=event.data.get("result"),
                message=str(event.data.get("message") or ""),
            )
            self._session.add(existing)
            return
        existing.status = status
        if is_meaningful_payload(input_payload) and not is_meaningful_payload(existing.input_payload_json):
            existing.input_payload_json = input_payload
        if event.data.get("result") is not None:
            existing.output_payload_json = event.data.get("result")
        if event.data.get("message") is not None:
            existing.message = str(event.data.get("message") or "")


def _normalize_tool_event_arguments(event: AgentRunEvent) -> None:
    """将工具事件中的 JSON 字符串参数原地归一化为对象，统一事件与工具调用投影格式。"""

    if event.event not in {
        "tool.started",
        "tool.completed",
        "tool.error",
    }:
        return
    for key in ("tool_args", "arguments", "args"):
        if key not in event.data:
            continue
        parsed = parse_tool_arguments(event.data.get(key))
        if parsed is not None:
            event.data[key] = parsed
        return


def _requirement_uses_unified_external_batch(payload: dict[str, Any]) -> bool:
    """判断Requirement是否携带统一Batch元数据，兼容迁移前历史deferred记录。"""

    tool_execution = payload.get("tool_execution")
    if not isinstance(tool_execution, dict):
        return False
    calls = tool_execution.get("tool_calls")
    if not isinstance(calls, list):
        return False
    return any(
        isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and bool(item["metadata"].get("external_batch_id"))
        for item in calls
    )


def _is_active_run_unique_conflict(error: IntegrityError) -> bool:
    """识别数据库最终仲裁产生的同会话活动Run唯一冲突。"""

    message = str(error).lower()
    return (
        "uq_ai_agent_runs_active_session_agent" in message
        or "ai_agent_runs.session_id, ai_agent_runs.agent_id" in message
    )


# ---------------------------------------------------------------------------
# 兼容再导出：既有调用方继续 `from app.ai.platform_runtime import ...`
# ---------------------------------------------------------------------------

from app.ai.run_sse_stream import (  # noqa: E402
    _subscribe,
    _unsubscribe,
)
from app.ai.run_timeline_build import (  # noqa: E402
    timeline_sort_key as _timeline_sort_key,
    remove_requirement_timeline_items as _remove_requirement_timeline_items,
    mark_open_tool_items_failed as _mark_open_tool_items_failed,
    mark_last_assistant_timeline_item_interrupted as _mark_last_assistant_timeline_item_interrupted,
)
from app.ai.run_value_maps import scope_metadata as _scope_metadata  # noqa: E402
from app.ai.run_event_locks import _get_run_event_lock as _get_run_event_lock_compat  # noqa: E402

__all__ = [
    "ACTIVE_RUN_STATUSES",
    "PlatformAgentRuntimeStore",
    "PlatformRunStart",
    "STREAM_END_EVENTS",
    "STALE_ACTIVE_RUN_ERROR_CODE",
    "STALE_ACTIVE_RUN_ERROR_MESSAGE",
    "TERMINAL_RUN_STATUSES",
    "encode_sse_event",
    "get_live_run_activity_version",
    "new_session_id",
    "stream_live_subscribe",
    "stream_replay_then_subscribe",
    "subscribe_live_run_events",
]


def new_session_id() -> str:
    """生成平台会话 ID。"""

    return f"session-{uuid4().hex}"
