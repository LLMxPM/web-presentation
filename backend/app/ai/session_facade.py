"""文件功能：直接调用 Agno Agent/Team 与会话数据库，为 Editor 输出统一会话、消息与命名协议。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agno.agent import Agent as AgnoAgent
from agno.models.message import Message
from agno.db.base import SessionType
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunOutput
from agno.team import Team as AgnoTeam
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from agno.utils.message import filter_tool_calls

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID, AgentRuntimeContext
from app.ai.agent.runtime_context import build_scope_context_text
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig
from app.ai.auth_tokens import (
    CODE_CHECK_TOOL_SCOPES,
    COMPONENT_TOOL_DELETE_SCOPES,
    COMPONENT_TOOL_READ_SCOPES,
    COMPONENT_TOOL_WRITE_SCOPES,
    RESOURCE_TOOL_READ_SCOPES,
    RESOURCE_TOOL_WRITE_SCOPES,
    build_agent_tool_token,
)
from app.ai.history_policy import build_history_policy, estimate_text_tokens
from app.ai.model_resolver import LlmModelResolver
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.session_facade_common import (
    AgnoSessionDetail,
    _active_run_payload,
    _coerce_int,
    _coerce_run_status,
    _coerce_str,
    _event_payload,
    _extract_member_event_data,
    _extract_text_content,
    _extract_tool_error_info,
    _find_latest_session_run,
    _normalize_message_tool_calls,
    _normalize_raw_event_payload,
    _normalize_run_status_value,
    _normalize_timestamp,
    _prepare_team_run_output_for_agno_continue,
    _raw_event_name,
    _raw_event_text_content,
    _resolve_message_run_id,
    _resolve_reasoning_content,
    _resolve_run_input_text,
    _resolve_run_owner_id,
    _resolve_session_owner_id,
    _run_latest_event_index,
    _run_latest_event_index_from_detail,
    _split_reasoning_content,
    _stringify_content,
)
from app.ai.session_facade_models import (
    _ACTIVE_RUN_STATUSES,
    _TERMINAL_RUN_EVENTS,
    _ActiveAgentStream,
    _RawSseRunMessageTracker,
    _StreamingHistoryTracker,
    _TempHistoryMessage,
)
from app.ai.session_facade_requirements import (
    _apply_resolved_requirement_to_agno_run,
    _apply_user_feedback_selections,
    _build_run_requirement_from_tool_execution_payload,
    _extract_pending_requirement,
    _normalize_agno_terminal_run_payload,
    _resolve_requirement_payload,
)
from app.ai.session_facade_runtime_mixin import _SessionFacadeRuntimeMixin
from app.ai.session_facade_session import (
    _build_continue_temp_history_messages,
    _dedupe_scopes,
    _get_session_message_records,
    _get_session_messages,
    _is_displayable_session_message,
    _merge_history_messages_for_policy,
    _message_attr,
    _scope_from_metadata,
    _session_metadata,
    _session_type_candidates,
    _session_type_for_descriptor,
    _session_type_for_detail,
)
from app.ai.session_facade_sse import (
    _close_async_iterator,
    _ensure_sse_bytes,
    _finish_shielded_cleanup,
    _format_raw_sse_error,
    _iter_raw_sse_payloads,
    _raw_terminal_content,
    _stream_sse_events,
)
from app.ai.session_facade_stream_mixin import _SessionFacadeStreamMixin
from app.ai.session_facade_timeline import _build_member_runs_from_agno_runs, _build_timeline_items_from_agno_runs
from app.ai.tools.disclosure import (
    build_tool_disclosure_context,
    resolve_unified_tool_scopes,
)
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentCancelRunResponse,
    AgentContextStatusItem,
    AgentMessageItem,
    AgentPendingRequirement,
    AgentRunEvent,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
)
from app.services.ai_llm_service import AiLlmService
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.auth_service import AuthContext
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService
from app.repositories.workspace_repository import WorkspaceRepository



class AgentSessionFacade(_SessionFacadeStreamMixin, _SessionFacadeRuntimeMixin):
    """封装内容助手会话的读取、创建与流式执行。"""

    _session_run_locks: dict[str, asyncio.Lock] = {}

    def __init__(self, *, app: FastAPI, current: AuthContext, session: AsyncSession) -> None:
        self._app = app
        self._current = current
        self._session = session
        self._registry = self._get_registry()
        self._ai_db = self._get_ai_db()
        self._llm_service = AiLlmService(session, user_id=current.user.id)
        self._agent_config_service = AiAgentConfigService(session, user_id=current.user.id)
        self._model_resolver = LlmModelResolver()

    async def list_sessions(self, *, agent_id: str, scope: AgentScopeContext) -> list[AgentSessionItem]:
        """列出当前工作空间内指定 Agent 或 Team 的所有会话。"""

        descriptor = self._registry.get_descriptor(agent_id)
        session_types = _session_type_candidates(_session_type_for_descriptor(descriptor))
        result: list[AgentSessionItem] = []
        seen_session_ids: set[str] = set()
        for session_type in session_types:
            sessions = await asyncio.to_thread(
                self._ai_db.get_sessions,
                session_type,
                str(self._current.user.id),
                agent_id,
                None,
                None,
                None,
                100,
                1,
                "updated_at",
                "desc",
                True,
            )
            for item in sessions:
                if not isinstance(item, (AgentSession, TeamSession)):
                    continue
                if item.session_id in seen_session_ids:
                    continue
                if _resolve_session_owner_id(item) != agent_id:
                    continue
                if not self._session_matches_workspace(item.metadata or {}, scope.workspace_id):
                    continue
                seen_session_ids.add(item.session_id)
                result.append(self._map_session_item(item, metadata=await self._enrich_session_scope_metadata(item.metadata or {})))
        result.sort(key=lambda item: item.updated_at or "", reverse=True)
        return result

    async def create_session(
        self,
        *,
        agent_id: str,
        scope: AgentScopeContext,
        session_name: str,
    ) -> AgentSessionItem:
        """创建一个绑定当前页面范围的 Agent 或 Team 会话记录。"""

        descriptor = self._registry.get_descriptor(agent_id)
        now_timestamp = int(datetime.now(tz=UTC).timestamp())
        session_metadata = {
            **scope.model_dump(mode="json"),
            "llm_slot": descriptor.llm_slot,
        }
        session_id = str(uuid4())
        if _session_type_for_descriptor(descriptor) == SessionType.TEAM:
            session_model: AgnoSessionDetail = TeamSession(
                session_id=session_id,
                team_id=agent_id,
                user_id=str(self._current.user.id),
                session_data={"session_name": session_name},
                metadata=session_metadata,
                team_data={"agent_id": agent_id, "entry_kind": "team"},
                runs=[],
                created_at=now_timestamp,
                updated_at=now_timestamp,
            )
        else:
            session_model = AgentSession(
                session_id=session_id,
                agent_id=agent_id,
                user_id=str(self._current.user.id),
                session_data={"session_name": session_name},
                metadata=session_metadata,
                agent_data={"agent_id": agent_id, "entry_kind": "agent"},
                runs=[],
                created_at=now_timestamp,
                updated_at=now_timestamp,
            )
        created = await asyncio.to_thread(self._ai_db.upsert_session, session_model)
        if not isinstance(created, (AgentSession, TeamSession)):
            raise AppException(status_code=500, code="AI_SESSION_CREATE_FAILED", detail="智能体会话创建失败。")
        return self._map_session_item(created)

    async def rename_session(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        session_name: str | None,
        autogenerate: bool,
        runtime_context: AgentRuntimeContext,
    ) -> AgentSessionItem:
        """重命名当前页面范围内的会话，或使用 Agno 自动生成会话名。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        if autogenerate:
            descriptor = self._registry.get_descriptor(agent_id)
            agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
            model_config = await self._llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
            session_metadata = self._resolve_run_session_metadata(
                metadata=_session_metadata(detail),
                scope=scope,
                agent_config=agent_config,
                supports_image_input=bool(model_config.supports_image_input),
            )
            agent, _ = await self._build_agent_for_descriptor(
                descriptor,
                runtime_context,
                session_detail=detail,
                session_metadata=session_metadata,
                agent_config=agent_config,
                model_config=model_config,
            )
            renamed = await asyncio.to_thread(
                agent.set_session_name,
                session_id,
                True,
                None,
            )
        else:
            session_type = _session_type_for_detail(detail)
            renamed = await asyncio.to_thread(
                self._ai_db.rename_session,
                session_id,
                session_type,
                session_name,
                str(self._current.user.id),
                True,
            )
        if not isinstance(renamed, (AgentSession, TeamSession)):
            raise AppException(status_code=404, code="AI_SESSION_NOT_FOUND", detail="智能体会话不存在。")
        return self._map_session_item(renamed)

    async def get_messages(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> list[AgentMessageItem]:
        """读取当前会话消息历史。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        detail = await self._ensure_cancelled_session_messages_preserved(detail, agent_id=agent_id)
        attachments_by_run = await AgentImageAttachmentService(
            self._session,
            user_id=self._current.user.id,
        ).list_message_attachments(workspace_id=scope.workspace_id, session_id=session_id)
        message_kwargs = {
            "skip_history_messages": False,
            # 页面写回 run 会先进入 paused，若仍沿用 Agno 默认过滤则前端刷新后会误判为“消息丢失”。
            "skip_statuses": [],
        }
        message_items: list[AgentMessageItem] = []
        for index, record in enumerate(_get_session_message_records(detail, agent_id=agent_id, **message_kwargs)):
            item = record.message
            role = str(item.role or "assistant")
            if not _is_displayable_session_message(item, role=role):
                continue
            content, reasoning_content = _split_reasoning_content(
                _stringify_content(item.content),
                _resolve_reasoning_content(item),
            )
            message_items.append(
                AgentMessageItem(
                    id=str(item.id or f"{session_id}:{index}"),
                    run_id=record.run_id,
                    role=role,  # type: ignore[arg-type]
                    content=content,
                    reasoning_content=reasoning_content,
                    created_at=_normalize_timestamp(item.created_at),
                    tool_name=item.tool_name,
                    tool_call_id=item.tool_call_id,
                    tool_args=item.tool_args,
                    tool_call_error=item.tool_call_error,
                    tool_calls=_normalize_message_tool_calls(item) if role == "assistant" else [],
                    attachments=attachments_by_run.get(record.run_id or _resolve_message_run_id(item), []) if role == "user" else [],
                )
            )
        return message_items

    async def get_context_status(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        current_input: str | None = None,
        extra_history_messages: list[Any] | None = None,
    ) -> AgentContextStatusItem:
        """读取当前会话的上下文预算、摘要状态和最近原文保留策略。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        detail = await self._ensure_cancelled_session_messages_preserved(detail, agent_id=agent_id)
        descriptor = self._registry.get_descriptor(agent_id)
        agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
        model_config = await self._llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
        session_metadata = self._resolve_run_session_metadata(
            metadata=_session_metadata(detail),
            scope=scope,
            agent_config=agent_config,
            supports_image_input=bool(model_config.supports_image_input),
        )
        history_policy = self._build_history_policy_for_session(
            model_config=model_config,
            agent_id=agent_id,
            runtime_context=runtime_context,
            session_metadata=session_metadata,
            agent_config=agent_config,
            session_detail=detail,
            current_input=current_input,
            extra_history_messages=extra_history_messages,
        )
        session_summary = getattr(detail, "summary", None)
        return AgentContextStatusItem(
            session_id=session_id,
            agent_id=agent_id,
            compression_enabled=True,
            compression_required=history_policy.compression_required,
            summary_available=history_policy.summary_available,
            summary=_coerce_str(getattr(session_summary, "summary", None)),
            topics=list(getattr(session_summary, "topics", None) or []),
            summary_updated_at=_normalize_timestamp(getattr(session_summary, "updated_at", None)),
            context_window_tokens=history_policy.context_window_tokens,
            max_output_tokens=history_policy.max_output_tokens,
            history_token_ratio=history_policy.history_token_ratio,
            compression_target_ratio=history_policy.compression_target_ratio,
            safety_margin_tokens=history_policy.safety_margin_tokens,
            current_input_tokens=history_policy.current_input_tokens,
            fixed_context_tokens=history_policy.fixed_context_tokens,
            history_budget_tokens=history_policy.history_budget_tokens,
            compression_target_tokens=history_policy.compression_target_tokens,
            estimated_history_tokens=history_policy.estimated_history_tokens,
            retained_recent_history_tokens=history_policy.retained_recent_history_tokens,
            retained_recent_message_count=history_policy.num_history_messages,
        )

    async def get_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext | None = None,
    ) -> AgentActiveRunItem | None:
        """读取当前会话最近一次非终态 run，供前端刷新后恢复界面。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        latest_run = _find_latest_session_run(detail, agent_id=agent_id, statuses=_ACTIVE_RUN_STATUSES)
        if latest_run is None:
            return None
        latest_run = await self._cancel_stale_running_run_if_needed(
            run=latest_run,
            session_id=session_id,
            agent_id=agent_id,
        )
        if _coerce_run_status(getattr(latest_run, "status", None)) not in _ACTIVE_RUN_STATUSES:
            return None
        effective_runtime_context = runtime_context
        if _normalize_run_status_value(getattr(latest_run, "status", None)) == "paused":
            run_scope = self._resolve_run_scope(latest_run, fallback_metadata=_session_metadata(detail))
            if run_scope is not None:
                effective_runtime_context = await build_agent_runtime_context(session=self._session, scope=run_scope)
        return self._map_active_run_item(
            latest_run,
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=effective_runtime_context,
        )

    async def get_runtime_snapshot(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
    ) -> AgentSessionRuntimeSnapshot:
        """一次性返回 Editor 恢复会话 UI 需要的运行时快照。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        detail = await self._ensure_cancelled_session_messages_preserved(detail, agent_id=agent_id)
        active_run: AgentActiveRunItem | None = None
        last_run: AgentActiveRunItem | None = None
        latest_run = _find_latest_session_run(detail, agent_id=agent_id)
        if latest_run is not None:
            latest_run = await self._cancel_stale_running_run_if_needed(
                run=latest_run,
                session_id=session_id,
                agent_id=agent_id,
            )
            mapped_run = self._map_active_run_item(
                latest_run,
                session_id=session_id,
                agent_id=agent_id,
                runtime_context=runtime_context,
            )
            if mapped_run.status in {"pending", "running", "paused", "cancelling"}:
                active_run = mapped_run
            else:
                last_run = mapped_run

        attachment_service = AgentImageAttachmentService(self._session, user_id=self._current.user.id)
        timeline_items = _build_timeline_items_from_agno_runs(
            detail,
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
        )
        member_runs = _build_member_runs_from_agno_runs(
            detail,
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
            parent_timeline_items=timeline_items,
        )
        return AgentSessionRuntimeSnapshot(
            session=self._map_session_item(detail, metadata=await self._enrich_session_scope_metadata(detail.metadata or {})),
            timeline_items=timeline_items,
            member_runs=member_runs,
            context_status=await self.get_context_status(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                runtime_context=runtime_context,
            ),
            active_run=active_run,
            last_run=last_run,
            pending_requirement=active_run.pending_requirement if active_run is not None else None,
            event_index=active_run.event_index if active_run is not None else (last_run.event_index if last_run else -1),
            pending_attachments=await attachment_service.list_pending_attachments(
                workspace_id=scope.workspace_id,
                session_id=session_id,
            ),
        )

    async def ensure_no_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> None:
        """启动新 run 前校验同一 session 没有非终态 Agno run 或本进程流式锁。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        self._ensure_route_scope_in_session_scope(_session_metadata(detail), scope)
        lock = self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
        if lock.locked():
            raise AppException(
                status_code=409,
                code="AI_SESSION_RUN_ACTIVE",
                detail="当前会话已有运行中的智能体任务，请等待完成后再发送新消息。",
            )
        active_run = await self._get_non_terminal_run(session_id=session_id, agent_id=agent_id, scope=scope)
        if active_run is not None:
            raise AppException(
                status_code=409,
                code="AI_SESSION_RUN_ACTIVE",
                detail="当前会话已有未结束的智能体运行，请等待完成或先处理待确认动作。",
            )

    async def reserve_run_slot(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> asyncio.Lock:
        """为即将启动的新 run 预占 session 级执行锁，保证并发请求能返回 409。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        self._ensure_route_scope_in_session_scope(_session_metadata(detail), scope)
        lock = self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
        if lock.locked():
            raise AppException(
                status_code=409,
                code="AI_SESSION_RUN_ACTIVE",
                detail="当前会话已有运行中的智能体任务，请等待完成后再发送新消息。",
            )
        await lock.acquire()
        try:
            active_run = await self._get_non_terminal_run(session_id=session_id, agent_id=agent_id, scope=scope)
        except Exception:
            if lock.locked():
                lock.release()
            raise
        if active_run is not None:
            lock.release()
            raise AppException(
                status_code=409,
                code="AI_SESSION_RUN_ACTIVE",
                detail="当前会话已有未结束的智能体运行，请等待完成或先处理待确认动作。",
            )
        return lock

    async def cancel_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        force: bool = False,
        tool_call_id: str | None = None,
    ) -> AgentCancelRunResponse:
        """取消当前会话中仍未结束的 Agno run。"""

        active_run = await self._get_non_terminal_run(session_id=session_id, agent_id=agent_id, scope=scope)
        if active_run is None:
            raise AppException(
                status_code=409,
                code="AI_RUN_NOT_ACTIVE",
                detail="当前会话没有可取消的运行。",
            )
        run_id = str(active_run.run_id or "")
        if not run_id:
            raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="当前运行缺少 run_id，无法取消。")

        if _normalize_run_status_value(active_run.status) == "paused":
            resolved_tool_execution: dict[str, Any] | None = None
            if force:
                pending_requirement = _extract_pending_requirement(payload=_active_run_payload(active_run))
                active_tool_call_id = (
                    _coerce_str(pending_requirement.tool_execution.get("tool_call_id"))
                    if pending_requirement is not None
                    else ""
                )
                incoming_tool_call_id = _coerce_str(tool_call_id)
                if incoming_tool_call_id and active_tool_call_id and incoming_tool_call_id != active_tool_call_id:
                    raise AppException(
                        status_code=409,
                        code="AI_RUN_REQUIREMENT_STALE",
                        detail="待确认动作已变化，请刷新会话后重试。",
                    )
                resolved_tool_execution = pending_requirement.tool_execution if pending_requirement is not None else None
            await self._mark_run_terminal(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                status=RunStatus.cancelled,
                content="用户取消了待确认动作",
                resolved_tool_execution=resolved_tool_execution,
            )
        else:
            descriptor = self._registry.get_descriptor(agent_id)
            if _session_type_for_descriptor(descriptor) == SessionType.TEAM:
                AgnoTeam.cancel_run(run_id)
            else:
                AgnoAgent.cancel_run(run_id)
        return AgentCancelRunResponse(run_id=run_id, session_id=session_id, cancel_requested=True)

    def continue_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[bytes, None]:
        """继续当前会话中暂停的 run，并转为 Editor SSE。"""

        return _stream_sse_events(
            self.continue_active_events(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                tool_execution=tool_execution,
                decision=decision,
                note=note,
                feedback_selections=feedback_selections,
                runtime_context=runtime_context,
            )
        )

    async def _get_non_terminal_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> RunOutput | TeamRunOutput | None:
        """从 Agno session.runs 中找出最近的非终态 run。"""

        detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        if not isinstance(detail, (AgentSession, TeamSession)):
            return None
        return _find_latest_session_run(detail, agent_id=agent_id, statuses=_ACTIVE_RUN_STATUSES)

    async def ensure_session_access(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> AgnoSessionDetail:
        """确保会话属于当前登录用户和当前页面范围。"""

        detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)

        if detail is None:
            raise AppException(status_code=404, code="AI_SESSION_NOT_FOUND", detail="智能体会话不存在。")
        if _resolve_session_owner_id(detail) != agent_id:
            raise AppException(status_code=403, code="AI_SESSION_SCOPE_DENIED", detail="当前页面无权访问该会话。")
        metadata = detail.metadata or {}
        if not self._session_matches_workspace(metadata, scope.workspace_id):
            raise AppException(status_code=403, code="AI_SESSION_SCOPE_DENIED", detail="当前页面无权访问该会话。")
        return detail

    async def _read_session_detail(
        self,
        *,
        session_id: str,
        agent_id: str,
    ) -> AgnoSessionDetail | None:
        """按目录 entry_kind 读取会话，并兼容内容助手历史 AgentSession。"""

        descriptor = self._registry.get_descriptor(agent_id)
        for session_type in _session_type_candidates(_session_type_for_descriptor(descriptor)):
            candidate = await asyncio.to_thread(
                self._ai_db.get_session,
                session_id,
                session_type,
                str(self._current.user.id),
                True,
            )
            if not isinstance(candidate, (AgentSession, TeamSession)):
                continue
            if _resolve_session_owner_id(candidate) == agent_id:
                return candidate
        return None

    def stream_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: AgentRuntimeContext,
        reserved_lock: asyncio.Lock | None = None,
        image_attachment_ids: list[int] | None = None,
        run_id: str | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """发起一次新的 Agent run，并把 Agno 事件转为 Editor SSE。"""

        return _stream_sse_events(
            self.run_events(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                message=message,
                runtime_context=runtime_context,
                reserved_lock=reserved_lock,
                image_attachment_ids=image_attachment_ids,
                run_id=run_id,
            )
        )

    def run_events(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: AgentRuntimeContext,
        reserved_lock: asyncio.Lock | None = None,
        image_attachment_ids: list[int] | None = None,
        run_id: str | None = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """发起一次新的 Agent run，并逐条返回 Editor 统一事件。"""

        initial_history_messages = [
            _TempHistoryMessage(
                role="user",
                content=(message.strip() or "请查看随消息上传的图片。"),
            )
        ]
        return self._stream_agno_events(
            agent_id=agent_id,
            session_id=session_id,
            scope=scope,
            runtime_context=runtime_context,
            reserved_lock=reserved_lock,
            initial_history_messages=initial_history_messages,
            stream_builder=self._build_run_stream(
                agent_id=agent_id,
                session_id=session_id,
                scope=scope,
                message=message,
                runtime_context=runtime_context,
                image_attachment_ids=image_attachment_ids,
                run_id=run_id,
            ),
        )

    def continue_run(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[bytes, None]:
        """继续一个已暂停 run，并把继续执行结果转为 Editor SSE。"""

        return _stream_sse_events(
            self.continue_events(
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                tool_execution=tool_execution,
                decision=decision,
                note=note,
                feedback_selections=feedback_selections,
                runtime_context=runtime_context,
            )
        )

    def continue_events(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """继续一个已暂停 run，并逐条返回 Editor 统一事件。"""

        updated_tool_execution = dict(tool_execution or {})
        if decision is not None:
            updated_tool_execution["confirmed"] = decision == "confirm"
        if note:
            updated_tool_execution["confirmation_note"] = note
        if feedback_selections:
            updated_tool_execution = _apply_user_feedback_selections(
                updated_tool_execution,
                feedback_selections,
            )

        initial_history_messages = _build_continue_temp_history_messages(updated_tool_execution)
        return self._stream_agno_events(
            agent_id=agent_id,
            session_id=session_id,
            scope=scope,
            runtime_context=runtime_context,
            initial_history_messages=initial_history_messages,
            resolved_tool_execution=updated_tool_execution,
            stream_builder=self._build_continue_stream(
                agent_id=agent_id,
                session_id=session_id,
                scope=scope,
                run_id=run_id,
                updated_tool_execution=updated_tool_execution,
                runtime_context=runtime_context,
            ),
        )

    async def continue_active_events(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """查找当前 paused run，并复用 Agno continue_run 继续执行。"""

        active_run, active_requirement = await self._get_continuable_pending_run(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
        )
        if active_run is None or active_requirement is None:
            yield AgentRunEvent(
                event="run.error",
                session_id=session_id,
                data={"message": "当前会话没有待继续的暂停运行。", "code": "AI_RUN_NOT_PAUSED"},
            )
            return
        run_id = str(active_run.run_id or "")
        if not run_id:
            yield AgentRunEvent(
                event="run.error",
                session_id=session_id,
                data={"message": "当前暂停运行缺少 run_id。", "code": "AI_RUN_NOT_PAUSED"},
            )
            return
        session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        run_scope = self._resolve_run_scope(active_run, fallback_metadata=_session_metadata(session_detail)) or scope
        run_runtime_context = await build_agent_runtime_context(session=self._session, scope=run_scope)
        incoming_tool_call_id = _coerce_str((tool_execution or {}).get("tool_call_id"))
        active_tool_call_id = _coerce_str(active_requirement.tool_execution.get("tool_call_id"))
        if incoming_tool_call_id and active_tool_call_id and incoming_tool_call_id != active_tool_call_id:
            yield AgentRunEvent(
                event="run.error",
                run_id=run_id,
                session_id=session_id,
                data={
                    "message": "待确认动作已变化，请刷新会话后重试。",
                    "code": "AI_RUN_REQUIREMENT_STALE",
                    "expected_tool_call_id": active_tool_call_id,
                    "received_tool_call_id": incoming_tool_call_id,
                },
            )
            return
        merged_tool_execution = {
            **active_requirement.tool_execution,
            **(tool_execution or {}),
        }
        async for event in self.continue_events(
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            scope=run_scope,
            tool_execution=merged_tool_execution,
            decision=decision,
            note=note,
            feedback_selections=feedback_selections,
            runtime_context=run_runtime_context,
        ):
            yield event

    def run_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: AgentRuntimeContext,
        reserved_lock: asyncio.Lock | None = None,
        image_attachment_ids: list[int] | None = None,
        run_id: str | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """按 Agno 官方 background stream 输出原始 SSE，不再写平台 run 状态。"""

        return self._stream_agno_raw_sse(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            fallback_user_message=message,
            stream_builder=self._build_run_stream(
                agent_id=agent_id,
                session_id=session_id,
                scope=scope,
                message=message,
                runtime_context=runtime_context,
                image_attachment_ids=image_attachment_ids,
                run_id=run_id,
            ),
            reserved_lock=reserved_lock,
        )

    async def prepare_continue_active_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[bytes, None]:
        """读取并校验 Agno active requirement，返回继续执行的原始 SSE 流。"""

        active_run, active_requirement = await self._get_continuable_pending_run(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
        )
        if active_run is None or active_requirement is None:
            raise AppException(
                status_code=409,
                code="AI_RUN_NOT_PAUSED",
                detail="当前会话没有待继续的暂停运行。",
            )
        run_id = str(active_run.run_id or "")
        if not run_id:
            raise AppException(
                status_code=409,
                code="AI_RUN_NOT_PAUSED",
                detail="当前暂停运行缺少 run_id。",
            )

        incoming_tool_call_id = _coerce_str((tool_execution or {}).get("tool_call_id"))
        active_tool_call_id = _coerce_str(active_requirement.tool_execution.get("tool_call_id"))
        if incoming_tool_call_id and active_tool_call_id and incoming_tool_call_id != active_tool_call_id:
            raise AppException(
                status_code=409,
                code="AI_RUN_REQUIREMENT_STALE",
                detail="待确认动作已变化，请刷新会话后重试。",
            )

        session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        run_scope = self._resolve_run_scope(active_run, fallback_metadata=_session_metadata(session_detail)) or scope
        run_runtime_context = await build_agent_runtime_context(session=self._session, scope=run_scope)
        merged_tool_execution = {**active_requirement.tool_execution, **(tool_execution or {})}
        if decision is not None:
            merged_tool_execution["confirmed"] = decision == "confirm"
        if note:
            merged_tool_execution["confirmation_note"] = note
        if feedback_selections:
            merged_tool_execution = _apply_user_feedback_selections(merged_tool_execution, feedback_selections)

        return self._stream_agno_raw_sse(
            session_id=session_id,
            agent_id=agent_id,
            scope=run_scope,
            fallback_user_message=note,
            expected_run_id=run_id,
            resolved_tool_execution=merged_tool_execution,
            stream_builder=self._build_continue_stream(
                agent_id=agent_id,
                session_id=session_id,
                scope=run_scope,
                run_id=run_id,
                updated_tool_execution=merged_tool_execution,
                runtime_context=run_runtime_context,
            ),
        )

    async def continue_active_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        tool_execution: dict[str, Any],
        decision: str | None,
        note: str | None,
        feedback_selections: list[dict[str, Any]] | None,
        runtime_context: AgentRuntimeContext,
    ) -> AsyncGenerator[bytes, None]:
        """继续 paused run，并原样转发 Agno SSE。"""

        stream = await self.prepare_continue_active_raw_sse(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            tool_execution=tool_execution,
            decision=decision,
            note=note,
            feedback_selections=feedback_selections,
            runtime_context=runtime_context,
        )
        async for chunk in stream:
            yield chunk

    async def resume_raw_sse(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        event_index: int | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """按 Agno event_buffer 或 Agno DB events 回放原始 SSE。"""

        from agno.os.managers import event_buffer, sse_subscriber_manager
        from agno.os.utils import format_sse_event_with_index

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        last_index = event_index if event_index is not None else -1
        buffer_status = event_buffer.get_run_status(run_id)
        if buffer_status is None:
            detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
            run = detail.get_run(run_id) if isinstance(detail, (AgentSession, TeamSession)) else None
            events = list(getattr(run, "events", None) or []) if run is not None else []
            if not events:
                yield _format_raw_sse_error(
                    run_id=run_id,
                    session_id=session_id,
                    message="当前运行不在事件缓冲区，且数据库中没有可回放事件。",
                    code="AI_RUN_EVENTS_NOT_FOUND",
                )
                return
            for index, event in enumerate(events):
                if index <= last_index:
                    continue
                yield _ensure_sse_bytes(format_sse_event_with_index(event, event_index=index, run_id=run_id))
            return

        if buffer_status in (RunStatus.completed, RunStatus.error, RunStatus.cancelled, RunStatus.paused):
            for index, event in event_buffer.get_events(run_id, last_event_index=last_index):
                yield _ensure_sse_bytes(format_sse_event_with_index(event, event_index=index, run_id=run_id))
            return

        queue = sse_subscriber_manager.subscribe(run_id)
        last_replayed_index = last_index
        try:
            for index, event in event_buffer.get_events(run_id, last_event_index=last_index):
                yield _ensure_sse_bytes(format_sse_event_with_index(event, event_index=index, run_id=run_id))
                last_replayed_index = index
            if event_buffer.get_run_status(run_id) != RunStatus.running:
                for index, event in event_buffer.get_events(run_id, last_event_index=last_replayed_index):
                    yield _ensure_sse_bytes(format_sse_event_with_index(event, event_index=index, run_id=run_id))
                return
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    if event_buffer.get_run_status(run_id) != RunStatus.running:
                        for index, event in event_buffer.get_events(run_id, last_event_index=last_replayed_index):
                            yield _ensure_sse_bytes(format_sse_event_with_index(event, event_index=index, run_id=run_id))
                        return
                    yield b": keep-alive\n\n"
                    continue
                if item is None:
                    return
                index, sse_data = item
                if index <= last_replayed_index:
                    continue
                last_replayed_index = index
                yield _ensure_sse_bytes(sse_data)
        finally:
            sse_subscriber_manager.unsubscribe(run_id, queue)

    async def cancel_run(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> AgentCancelRunResponse:
        """中断指定 run；保留给内部兼容调用，实际状态仍来自 session active run。"""

        active_run = await self._get_non_terminal_run(session_id=session_id, agent_id=agent_id, scope=scope)
        if active_run is None or str(active_run.run_id or "") != run_id:
            raise AppException(
                status_code=409,
                code="AI_RUN_NOT_ACTIVE",
                detail="当前运行已结束或尚未进入可中断状态。",
            )
        return await self.cancel_active_run(session_id=session_id, agent_id=agent_id, scope=scope)

    def _build_run_stream(
        self,
        *,
        agent_id: str,
        session_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: AgentRuntimeContext,
        image_attachment_ids: list[int] | None = None,
        run_id: str | None = None,
    ):
        """构造新的 run 流生成器。"""

        async def builder() -> _ActiveAgentStream:
            descriptor = self._registry.get_descriptor(agent_id)
            session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
            session_detail = await self._ensure_cancelled_session_messages_preserved(session_detail, agent_id=agent_id)
            session_metadata = _session_metadata(session_detail)
            self._ensure_route_scope_in_session_scope(session_metadata, scope)
            agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
            model_config = await self._llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
            normalized_image_attachment_ids = list(image_attachment_ids or [])
            if normalized_image_attachment_ids and not bool(model_config.supports_image_input):
                raise AppException(
                    status_code=409,
                    code="AI_LLM_IMAGE_INPUT_UNSUPPORTED",
                    detail="当前绑定模型不支持图片输入，不能发送图片附件。",
                )
            attachment_service = AgentImageAttachmentService(
                self._session,
                user_id=self._current.user.id,
            )
            image_attachments = await attachment_service.validate_attachments_for_run(
                workspace_id=scope.workspace_id,
                session_id=session_id,
                attachment_ids=normalized_image_attachment_ids,
            )
            resolved_images = await attachment_service.build_images_for_run(image_attachments)
            session_metadata = self._resolve_run_session_metadata(
                metadata=session_metadata,
                scope=scope,
                agent_config=agent_config,
                supports_image_input=bool(model_config.supports_image_input),
            )
            agent, metadata = await self._build_agent_for_descriptor(
                descriptor,
                runtime_context,
                session_detail=session_detail,
                session_metadata=session_metadata,
                agent_config=agent_config,
                current_input=message,
                model_config=model_config,
            )
            metadata["run_scope"] = scope.model_dump(mode="json")
            metadata["image_attachment_ids"] = [attachment.id for attachment in image_attachments]
            metadata["image_transports"] = [resolved.transport for resolved in resolved_images]
            resolved_run_id = run_id or str(uuid4())
            await attachment_service.mark_run_id(
                attachments=image_attachments,
                run_id=resolved_run_id,
                operator_id=self._current.user.id,
            )
            await self._upsert_run_marker(
                session_id=session_id,
                agent_id=agent_id,
                run_id=resolved_run_id,
                status=RunStatus.running,
                metadata=metadata,
            )
            history_messages = self._build_model_history_messages(
                agent,
                session_detail=session_detail,
                agent_id=agent_id,
            )
            if history_messages:
                existing_additional_input = list(getattr(agent, "additional_input", None) or [])
                agent.additional_input = [*existing_additional_input, *history_messages]
                agent.add_history_to_context = False
            stream = agent.arun(
                message.strip() or "请查看随消息上传的图片。",
                session_id=session_id,
                user_id=str(self._current.user.id),
                run_id=resolved_run_id,
                stream=True,
                stream_events=True,
                background=True,
                add_history_to_context=False if history_messages else None,
                images=[resolved.image for resolved in resolved_images] or None,
                dependencies=self._build_tool_dependencies(
                    scope=scope,
                    session_id=session_id,
                    run_id=resolved_run_id,
                    agent_id=agent_id,
                    runtime_context=runtime_context,
                    session_metadata=session_metadata,
                    agent_config=agent_config,
                ),
                metadata=metadata,
            )
            return _ActiveAgentStream(agent=agent, stream=stream, run_id=resolved_run_id)

        return builder

    def _build_continue_stream(
        self,
        *,
        agent_id: str,
        session_id: str,
        scope: AgentScopeContext,
        run_id: str,
        updated_tool_execution: dict[str, Any],
        runtime_context: AgentRuntimeContext,
    ):
        """构造 continue_run 流生成器。"""

        async def builder() -> _ActiveAgentStream:
            descriptor = self._registry.get_descriptor(agent_id)
            session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
            agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
            model_config = await self._llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
            session_metadata = self._resolve_run_session_metadata(
                metadata=_session_metadata(session_detail),
                scope=scope,
                agent_config=agent_config,
                supports_image_input=bool(model_config.supports_image_input),
            )
            agent, metadata = await self._build_agent_for_descriptor(
                descriptor,
                runtime_context,
                session_detail=session_detail,
                session_metadata=session_metadata,
                agent_config=agent_config,
                current_input=_stringify_content(updated_tool_execution.get("confirmation_note")),
                model_config=model_config,
            )
            # 继续 paused run 时，run_response.messages 已经包含本次工具调用前的完整上下文。
            # 若此处再次注入 session history，当前 run 会被重复拼接，DeepSeek 会看到未紧跟 tool
            # 结果的重复 assistant.tool_calls，从而触发 400 协议校验错误。
            agent.add_history_to_context = False
            metadata["run_scope"] = scope.model_dump(mode="json")
            dependencies = self._build_tool_dependencies(
                scope=scope,
                session_id=session_id,
                run_id=run_id,
                agent_id=agent_id,
                runtime_context=runtime_context,
                session_metadata=session_metadata,
                agent_config=agent_config,
            )
            requirement = _build_run_requirement_from_tool_execution_payload(updated_tool_execution)
            await self._set_existing_run_status(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                status=RunStatus.running,
                content=None,
            )
            await self._sync_agno_requirement_decision_before_continue(
                session_detail=session_detail,
                run_id=run_id,
                requirement=requirement,
            )
            continue_run_response = _prepare_team_run_output_for_agno_continue(
                session_detail.get_run(run_id) if isinstance(session_detail, TeamSession) else None,
                agent_id=agent_id,
                agent_name=_coerce_str(getattr(descriptor, "name", None)) or agent_id,
            )
            if continue_run_response is not None:
                continue_run_response.status = RunStatus.running
                continue_run_response.content = None
            continue_run_kwargs = (
                {"run_response": continue_run_response} if continue_run_response is not None else {"run_id": run_id}
            )
            background_kwargs = {"background": True} if not isinstance(agent, AgnoTeam) else {}
            stream = agent.acontinue_run(
                **continue_run_kwargs,
                session_id=session_id,
                user_id=str(self._current.user.id),
                requirements=[requirement],
                stream=True,
                stream_events=True,
                dependencies=dependencies,
                metadata=metadata,
                **background_kwargs,
            )
            return _ActiveAgentStream(agent=agent, stream=stream, run_id=run_id)

        return builder
