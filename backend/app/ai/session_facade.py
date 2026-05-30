"""文件功能：直接调用 Agno Agent/Team 与会话数据库，为 Editor 输出统一会话、消息与命名协议。"""

from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable
from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from agno.agent import Agent as AgnoAgent
from agno.models.message import Message
from agno.models.response import ToolExecution
from agno.db.base import SessionType
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunOutput
from agno.team import Team as AgnoTeam
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
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
from app.ai.session_timeline import build_timeline_items_from_agno_runs
from app.ai.tools.disclosure import (
    build_tool_disclosure_context,
    resolve_unified_tool_scopes,
)
from app.ai.tools.shared import apply_source_edits
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
    AgentSuggestedPatch,
    AgentMemberRunItem,
    AgentTimelineItem,
)
from app.schemas.page import PageItem
from app.services.ai_llm_service import AiLlmService
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.auth_service import AuthContext
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService
from app.repositories.workspace_repository import WorkspaceRepository

_REASONING_BLOCK_PATTERN = re.compile(r"<reasoning>(.*?)</reasoning>", re.IGNORECASE | re.DOTALL)
_THINK_BLOCK_PATTERN = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_OPEN_REASONING_TAG_PATTERN = re.compile(r"<(?:reasoning|think)>", re.IGNORECASE)
_REASONING_TAG_PATTERN = re.compile(r"</?(?:reasoning|think)>", re.IGNORECASE)
_AGNO_CONTEXT_NOTE_PREFIX = "Take note of the following content"


@dataclass(slots=True)
class _ActiveAgentStream:
    """保存一次运行对应的 Agent 实例与事件流，便于后续注册取消句柄。"""

    agent: Any
    stream: AsyncIterator[Any]
    run_id: str | None = None


@dataclass(slots=True)
class _SessionMessageRecord:
    """记录 Agno 消息及其所属 run，用于 Editor 恢复附件与工具锚点。"""

    run_id: str | None
    message: Any


@dataclass(slots=True)
class _TempHistoryMessage:
    """保存当前 run 中尚未写入 Agno session 的临时历史消息。"""

    role: str
    content: Any
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: Any | None = None
    tool_call_error: str | None = None


class _StreamingHistoryTracker:
    """累计当前 run 内已稳定完成的消息，用于中途刷新上下文统计。"""

    def __init__(self, initial_messages: list[Any] | None = None) -> None:
        self._messages: list[Any] = list(initial_messages or [])
        self._assistant_parts: list[str] = []
        self._last_assistant_content = ""
        self._tool_args_by_call_id: dict[str, Any] = {}

    def snapshot(self) -> list[Any]:
        """返回临时历史消息副本，避免估算过程修改内部缓冲。"""

        return [*self._messages]

    def append_assistant_delta(self, content: str | None) -> None:
        """累计流式 assistant 文本片段，等内容完成检查点再落入临时历史。"""

        if content:
            self._assistant_parts.append(content)

    def flush_assistant_content(self, fallback_content: str | None = None) -> bool:
        """把当前 assistant 文本缓冲固化为一条临时历史消息。"""

        content = "".join(self._assistant_parts)
        self._assistant_parts = []
        if not content and fallback_content:
            content = fallback_content
        if not content or content == self._last_assistant_content:
            return False
        self._messages.append(_TempHistoryMessage(role="assistant", content=content))
        self._last_assistant_content = content
        return True

    def remember_tool_started(self, event: AgentRunEvent) -> None:
        """记录工具入参，供完成或失败检查点估算工具消息。"""

        tool_call_id = _coerce_str(event.data.get("tool_call_id"))
        if not tool_call_id:
            return
        self._tool_args_by_call_id[tool_call_id] = event.data.get("tool_args")

    def append_tool_event(self, event: AgentRunEvent) -> bool:
        """把工具完成或失败结果固化为一条临时工具消息。"""

        tool_name = _coerce_str(event.data.get("tool_name"))
        tool_call_id = _coerce_str(event.data.get("tool_call_id"))
        result = event.data.get("result")
        message = event.data.get("message")
        content = result if result is not None else message
        if content is None:
            content = ""
        self._messages.append(
            _TempHistoryMessage(
                role="tool",
                content=content,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_args=self._tool_args_by_call_id.get(tool_call_id or ""),
                tool_call_error=_coerce_str(message) if event.event == "tool.error" else None,
            )
        )
        return True


@dataclass(slots=True)
class _RawSseRunMessageTracker:
    """跟踪 Agno raw SSE 中已展示给用户的当前 run 内容。"""

    fallback_user_message: str | None = None
    run_id: str | None = None
    cancelled: bool = False
    assistant_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)

    def observe(self, raw_event: Any, *, fallback_run_id: str | None = None) -> None:
        """读取 raw Agno 事件中的 run、正文、reasoning 和取消终态。"""

        payload = _normalize_raw_event_payload(raw_event)
        event_name = _raw_event_name(raw_event, payload)
        event_run_id = _coerce_str(payload.get("run_id")) or fallback_run_id
        if event_run_id:
            self.run_id = event_run_id
        if event_name in {
            "RunContent",
            "RunContentEvent",
            "IntermediateRunContent",
            "IntermediateRunContentEvent",
            "RunIntermediateContent",
            "TeamRunContent",
            "TeamRunIntermediateContent",
        }:
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if content:
                self.assistant_parts.append(content)
            if reasoning_content:
                self.reasoning_parts.append(reasoning_content)
        elif event_name == "ReasoningContentDelta":
            reasoning_content = _resolve_reasoning_content(payload, preserve_stream_boundary=True)
            if reasoning_content:
                self.reasoning_parts.append(reasoning_content)
        elif event_name in {"RunCompleted", "RunCompletedEvent", "TeamRunCompleted"}:
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if content and not "".join(self.assistant_parts):
                self.assistant_parts.append(content)
            if reasoning_content and not "".join(self.reasoning_parts):
                self.reasoning_parts.append(reasoning_content)
        elif event_name in {"RunCancelled", "RunCancelledEvent", "TeamRunCancelled"}:
            self.cancelled = True

    @property
    def assistant_content(self) -> str | None:
        """返回当前 run 已流出的 assistant 正文。"""

        content = "".join(self.assistant_parts or [])
        return content or None

    @property
    def reasoning_content(self) -> str | None:
        """返回当前 run 已流出的 reasoning 内容。"""

        content = "".join(self.reasoning_parts or [])
        return content or None


_ACTIVE_RUN_STATUSES = {RunStatus.pending, RunStatus.running, RunStatus.paused}
_TERMINAL_RUN_EVENTS = {"run.completed", "run.cancelled", "run.error", "run.paused"}
AgnoSessionDetail = AgentSession | TeamSession


class AgentSessionFacade:
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
            await self._mark_run_terminal(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                status=RunStatus.cancelled,
                content="用户取消了待确认动作。",
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

    def _stream_agno_events(
        self,
        *,
        agent_id: str,
        session_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        stream_builder,
        reserved_lock: asyncio.Lock | None = None,
        initial_history_messages: list[Any] | None = None,
        resolved_tool_execution: dict[str, Any] | None = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """把 Agno 事件流重写为前端稳定消费的统一事件。"""

        async def generator() -> AsyncGenerator[AgentRunEvent, None]:
            active_run_id: str | None = None
            active_stream: _ActiveAgentStream | None = None
            terminal_seen = False
            history_tracker = _StreamingHistoryTracker(initial_history_messages)
            lock = reserved_lock or self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
            lock_acquired = reserved_lock is not None
            if not lock_acquired:
                if lock.locked():
                    yield AgentRunEvent(
                        event="run.error",
                        session_id=session_id,
                        data={"message": "当前会话已有运行中的智能体任务。", "code": "AI_SESSION_RUN_ACTIVE"},
                    )
                    return
                await lock.acquire()
                lock_acquired = True
            try:
                await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
                active_stream = await stream_builder()
                active_run_id = active_stream.run_id
                yield await self._build_context_status_event(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    runtime_context=runtime_context,
                    run_id=active_run_id,
                    extra_history_messages=history_tracker.snapshot(),
                )
                async for raw_event in active_stream.stream:
                    raw_payload = _normalize_raw_event_payload(raw_event)
                    raw_event_name = _raw_event_name(raw_event, raw_payload)
                    normalized_event = self._normalize_event(
                        raw_event=raw_event,
                        runtime_context=runtime_context,
                        session_id=session_id,
                    )
                    if raw_event_name in {"RunContentCompleted", "RunContentCompletedEvent", "TeamRunContentCompleted"}:
                        if history_tracker.flush_assistant_content(_raw_event_text_content(raw_payload)):
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
                    if normalized_event is not None:
                        if normalized_event.event in {"run.started", "run.continued"} and normalized_event.run_id:
                            active_run_id = normalized_event.run_id
                        if normalized_event.event in _TERMINAL_RUN_EVENTS:
                            terminal_seen = True
                            history_tracker.flush_assistant_content(normalized_event.content)
                            if (
                                normalized_event.event == "run.completed"
                                and active_run_id
                                and resolved_tool_execution is not None
                            ):
                                await self._normalize_agno_completed_run_after_continue(
                                    session_id=session_id,
                                    agent_id=agent_id,
                                    run_id=active_run_id,
                                    content=normalized_event.content,
                                    resolved_tool_execution=resolved_tool_execution,
                                )
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
                            yield normalized_event
                            if normalized_event.event == "run.paused":
                                break
                            continue
                        if normalized_event.event == "message.delta":
                            history_tracker.append_assistant_delta(normalized_event.content)
                        elif normalized_event.event == "tool.started":
                            history_tracker.remember_tool_started(normalized_event)
                        elif normalized_event.event in {"tool.completed", "tool.error"}:
                            history_tracker.append_tool_event(normalized_event)
                        yield normalized_event
                        if normalized_event.event in {"tool.completed", "tool.error"}:
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
            except asyncio.CancelledError:
                raise
            except AppException as exc:
                terminal_seen = True
                if active_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=active_run_id,
                        status=RunStatus.error,
                        content=exc.detail,
                    )
                yield AgentRunEvent(
                    event="run.error",
                    session_id=session_id,
                    data={"message": exc.detail, "code": exc.code},
                )
            except Exception:  # noqa: BLE001
                terminal_seen = True
                if active_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=active_run_id,
                        status=RunStatus.error,
                        content="智能体执行失败，请稍后重试。",
                    )
                yield AgentRunEvent(
                    event="run.error",
                    session_id=session_id,
                    data={"message": "智能体执行失败，请稍后重试。"},
                )
            finally:
                cleanup_cancelled = False
                try:
                    if active_stream is not None:
                        try:
                            cleanup_cancelled = await _finish_shielded_cleanup(
                                _close_async_iterator(active_stream.stream)
                            ) or cleanup_cancelled
                        except Exception:  # noqa: BLE001
                            pass
                    if active_run_id and not terminal_seen:
                        cleanup_cancelled = await _finish_shielded_cleanup(
                            self._mark_run_terminal(
                                session_id=session_id,
                                agent_id=agent_id,
                                run_id=active_run_id,
                                status=RunStatus.cancelled,
                                content="流式连接已断开，本次运行已停止。",
                            )
                        ) or cleanup_cancelled
                finally:
                    if lock_acquired and lock.locked():
                        lock.release()
                if cleanup_cancelled:
                    raise asyncio.CancelledError

        return generator()

    def _stream_agno_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        stream_builder,
        reserved_lock: asyncio.Lock | None = None,
        fallback_user_message: str | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行 Agno background stream，并直接透传 Agno 生成的 SSE 文本。"""

        async def generator() -> AsyncGenerator[bytes, None]:
            tracker = _RawSseRunMessageTracker(fallback_user_message=fallback_user_message)
            active_run_id: str | None = None
            lock = reserved_lock or self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
            lock_acquired = reserved_lock is not None
            if not lock_acquired:
                if lock.locked():
                    yield _format_raw_sse_error(
                        run_id=None,
                        session_id=session_id,
                        message="当前会话已有运行中的智能体任务。",
                        code="AI_SESSION_RUN_ACTIVE",
                    )
                    return
                await lock.acquire()
                lock_acquired = True
            try:
                session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
                active_stream = await stream_builder()
                active_run_id = active_stream.run_id
                tracker.run_id = active_run_id
                local_event_index = _run_latest_event_index_from_detail(session_detail, active_run_id)
                async for sse_data in active_stream.stream:
                    if isinstance(sse_data, (str, bytes)):
                        yield _ensure_sse_bytes(sse_data)
                    else:
                        from agno.os.utils import format_sse_event_with_index

                        local_event_index += 1
                        tracker.observe(sse_data, fallback_run_id=active_stream.run_id)
                        active_run_id = tracker.run_id or active_run_id
                        yield _ensure_sse_bytes(
                            format_sse_event_with_index(
                                sse_data,
                                event_index=local_event_index,
                                run_id=active_stream.run_id,
                            )
                        )
                if tracker.cancelled and (tracker.run_id or active_run_id):
                    await self._preserve_cancelled_raw_run_messages(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=str(tracker.run_id or active_run_id),
                        fallback_user_message=tracker.fallback_user_message,
                        assistant_content=tracker.assistant_content,
                        reasoning_content=tracker.reasoning_content,
                    )
            except asyncio.CancelledError:
                raise
            except AppException as exc:
                yield _format_raw_sse_error(
                    run_id=None,
                    session_id=session_id,
                    message=exc.detail,
                    code=exc.code,
                )
            except Exception:  # noqa: BLE001
                yield _format_raw_sse_error(
                    run_id=None,
                    session_id=session_id,
                    message="智能体执行失败，请稍后重试。",
                    code="AI_RUN_FAILED",
                )
            finally:
                if lock_acquired and lock.locked():
                    lock.release()

        return generator()

    async def _build_context_status_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        run_id: str | None,
        extra_history_messages: list[Any] | None = None,
    ) -> AgentRunEvent:
        """把上下文预算状态包装成前端可消费的 SSE 事件。"""

        status = await self.get_context_status(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
            extra_history_messages=extra_history_messages,
        )
        return AgentRunEvent(
            event="context.status",
            run_id=run_id,
            session_id=session_id,
            data=status.model_dump(mode="json"),
        )

    def _normalize_event(
        self,
        *,
        raw_event: Any,
        runtime_context: AgentRuntimeContext,
        session_id: str,
    ) -> AgentRunEvent | None:
        """把 Agno 原始事件翻译成 Editor 约定的事件协议。"""

        payload = _event_payload(raw_event)
        if not isinstance(payload, dict):
            return None

        event_name = str(payload.get("event") or type(raw_event).__name__)
        run_id = payload.get("run_id")
        resolved_session_id = payload.get("session_id") or session_id
        member_event_data = _extract_member_event_data(payload)
        is_member_event = bool(member_event_data.get("parent_run_id") and member_event_data.get("member_run_id"))
        event_run_id = member_event_data.get("parent_run_id") if is_member_event else run_id

        if isinstance(raw_event, (RunOutput, TeamRunOutput)):
            pending_requirement = _extract_pending_requirement(
                payload={**payload, "run_id": event_run_id} if event_run_id else payload,
                runtime_context=runtime_context,
            )
            if pending_requirement is not None:
                return AgentRunEvent(
                    event="run.paused",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={
                        "requirement": pending_requirement.model_dump(mode="json"),
                        **member_event_data,
                    },
                )
            if is_member_event and not isinstance(raw_event, TeamRunOutput):
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload),
            )
            return AgentRunEvent(
                event="run.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=content,
                data={
                    "metadata": payload.get("metadata") or {},
                    "reasoning_content": reasoning_content,
                    **member_event_data,
                },
            )

        if event_name in {"RunStarted", "RunStartedEvent", "TeamRunStarted"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.started",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"agent_id": payload.get("agent_id") or payload.get("team_id"), **member_event_data},
            )

        if event_name in {
            "RunContent",
            "RunContentEvent",
            "IntermediateRunContent",
            "IntermediateRunContentEvent",
            "RunIntermediateContent",
            "TeamRunContent",
            "TeamRunIntermediateContent",
        }:
            if is_member_event:
                return None
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if not content and not reasoning_content:
                return None
            return AgentRunEvent(
                event="message.delta",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=content,
                data={"reasoning_content": reasoning_content, **member_event_data},
            )

        if event_name in {"ToolCallStarted", "ToolCallStartedEvent", "TeamToolCallStarted"}:
            tool_execution = payload.get("tool") or {}
            return AgentRunEvent(
                event="tool.started",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "tool_args": tool_execution.get("tool_args") or {},
                    **member_event_data,
                },
            )

        if event_name in {"ToolCallCompleted", "ToolCallCompletedEvent", "TeamToolCallCompleted"}:
            tool_execution = payload.get("tool") or {}
            tool_result = tool_execution.get("result")
            if tool_result is None:
                tool_result = payload.get("content")
            return AgentRunEvent(
                event="tool.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "result": tool_result,
                    "message": payload.get("content"),
                    **member_event_data,
                },
            )

        if event_name in {"ToolCallError", "ToolCallErrorEvent", "TeamToolCallError"}:
            tool_execution = payload.get("tool") or {}
            error_message, error_code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
                payload=payload,
                tool_execution=tool_execution,
            )
            return AgentRunEvent(
                event="tool.error",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "message": error_message,
                    "code": error_code,
                    "repair_attempted": repair_attempted,
                    "repair_succeeded": repair_succeeded,
                    "repair_reason": repair_reason,
                    **member_event_data,
                },
            )

        if event_name in {"RunPaused", "RunPausedEvent", "TeamRunPaused"}:
            pending_requirement = _extract_pending_requirement(
                payload={**payload, "run_id": event_run_id} if event_run_id else payload,
                runtime_context=runtime_context,
            )
            return AgentRunEvent(
                event="run.paused",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "requirement": pending_requirement.model_dump(mode="json") if pending_requirement else None,
                    **member_event_data,
                },
            )

        if event_name in {"RunContinued", "RunContinuedEvent", "TeamRunContinued"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.continued",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data=member_event_data,
            )

        if event_name in {"RunContentCompleted", "RunContentCompletedEvent", "TeamRunContentCompleted"}:
            return None

        if event_name in {"RunCompleted", "RunCompletedEvent", "TeamRunCompleted"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            completed_content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload),
            )
            return AgentRunEvent(
                event="run.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=completed_content,
                data={
                    "metadata": payload.get("metadata") or {},
                    "reasoning_content": reasoning_content,
                    **member_event_data,
                },
            )

        if event_name in {"RunCancelled", "RunCancelledEvent", "TeamRunCancelled"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.cancelled",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"message": _stringify_content(payload.get("content") or payload.get("message") or payload.get("reason")), **member_event_data},
            )

        if event_name in {"RunError", "RunErrorEvent", "TeamRunError"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={
                        "source_event": event_name,
                        "member_event": True,
                        "message": _stringify_content(payload.get("content") or payload.get("error")),
                        **member_event_data,
                    },
                )
            return AgentRunEvent(
                event="run.error",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"message": _stringify_content(payload.get("content") or payload.get("error")), **member_event_data},
            )

        return AgentRunEvent(
            event="trace.event",
            run_id=event_run_id,
            session_id=resolved_session_id,
            data={"source_event": event_name, "payload": payload, **member_event_data},
        )

    def _resolve_run_session_metadata(
        self,
        *,
        metadata: dict[str, Any],
        scope: AgentScopeContext,
        agent_config: EffectiveAgentRuntimeConfig,
        supports_image_input: bool | None = None,
    ) -> dict[str, Any]:
        """补齐本轮模型能力元数据；工具不再按业务 scope 分组裁剪。"""

        _ = scope, agent_config
        model_supports_image_input = bool(supports_image_input)
        return {
            **metadata,
            "model_supports_image_input": model_supports_image_input,
        }

    def _build_tool_dependencies(
        self,
        *,
        scope: AgentScopeContext,
        session_id: str,
        run_id: str,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
        session_metadata: dict[str, Any],
        agent_config: EffectiveAgentRuntimeConfig,
    ) -> dict[str, Any]:
        """构造供 Agno tools 使用的泛化依赖上下文。"""

        tool_scopes = self._resolve_tool_scopes(
            agent_id=agent_id,
            agent_config=agent_config,
            supports_image_input=bool(session_metadata.get("model_supports_image_input", False)),
        )
        tool_token = build_agent_tool_token(
            self._current,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            workspace_id=scope.workspace_id,
            project_id=scope.project_id,
            page_id=scope.page_id,
            component_id=scope.component_id,
            source=scope.source,
            scopes=tool_scopes,
        )
        dependencies = {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": str(self._current.user.id),
            "agent_id": agent_id,
            "scope_type": scope.scope_type,
            "workspace_id": scope.workspace_id,
            "project_id": scope.project_id,
            "page_id": scope.page_id,
            "component_id": scope.component_id,
            "page_width": runtime_context.page_width,
            "page_height": runtime_context.page_height,
            "base_font_size": runtime_context.base_font_size,
            "style_spec_markdown": runtime_context.style_spec_markdown,
            "page_code": runtime_context.page_code,
            "model_supports_image_input": bool(session_metadata.get("model_supports_image_input", False)),
            "role": "admin",
            "backend_session_id": self._current.backend_session_id,
            "source": scope.source,
            "tool_auth_token": tool_token,
            "tool_scopes": list(tool_scopes),
        }
        if agent_id == AGENT_COORDINATOR_AGENT_ID:
            # Agno Team 委派成员时复用 leader dependencies，因此成员工具需要独立授权 token。
            member_tokens: dict[str, str] = {}
            member_scopes: dict[str, list[str]] = {}
            for member_agent_id in (COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
                scopes = self._resolve_tool_scopes(agent_id=member_agent_id)
                member_tokens[member_agent_id] = build_agent_tool_token(
                    self._current,
                    run_id=run_id,
                    session_id=session_id,
                    agent_id=member_agent_id,
                    workspace_id=scope.workspace_id,
                    project_id=scope.project_id,
                    page_id=scope.page_id,
                    component_id=scope.component_id,
                    source=scope.source,
                    scopes=scopes,
                )
                member_scopes[member_agent_id] = list(scopes)
            dependencies["member_tool_auth_tokens"] = member_tokens
            dependencies["member_tool_scopes"] = member_scopes
        return dependencies

    @staticmethod
    def _resolve_tool_scopes(
        *,
        agent_id: str,
        enabled_tool_groups: tuple[str, ...] = (),
        agent_config: EffectiveAgentRuntimeConfig | None = None,
        supports_image_input: bool | None = None,
    ) -> tuple[str, ...]:
        """按 Agent 类型返回 run task 工具授权 scope。"""

        _ = enabled_tool_groups
        if agent_id == COMPONENT_MANAGER_AGENT_ID:
            return _dedupe_scopes(
                (
                    *COMPONENT_TOOL_READ_SCOPES,
                    *COMPONENT_TOOL_WRITE_SCOPES,
                    *COMPONENT_TOOL_DELETE_SCOPES,
                    *RESOURCE_TOOL_READ_SCOPES,
                    *CODE_CHECK_TOOL_SCOPES,
                )
            )
        if agent_id == RESOURCE_MANAGER_AGENT_ID:
            return _dedupe_scopes((*RESOURCE_TOOL_READ_SCOPES, *RESOURCE_TOOL_WRITE_SCOPES))
        direct_scopes = resolve_unified_tool_scopes(
            session_factory=get_session_factory(),
            agent_config=agent_config,
            supports_image_input=supports_image_input,
        )
        if agent_id == AGENT_COORDINATOR_AGENT_ID:
            return _dedupe_scopes(direct_scopes)
        return direct_scopes

    async def _build_agent_for_descriptor(
        self,
        descriptor,
        runtime_context: AgentRuntimeContext,
        session_detail: AgnoSessionDetail,
        session_metadata: dict[str, Any],
        agent_config: EffectiveAgentRuntimeConfig,
        current_input: str | None = None,
        model_config=None,
    ) -> tuple[Any, dict[str, Any]]:
        """按描述符解析模型配置并构建 Agent 或 Team。"""

        if model_config is None:
            model_config = await self._llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
        history_policy = self._build_history_policy_for_session(
            model_config=model_config,
            agent_id=descriptor.id,
            runtime_context=runtime_context,
            session_metadata=session_metadata,
            agent_config=agent_config,
            session_detail=session_detail,
            current_input=current_input,
        )
        metadata = {
            "llm_slot": descriptor.llm_slot,
            "llm_config_id": model_config.id,
            "llm_config_name": model_config.name,
            "provider_key": model_config.provider_key,
            "model_id": model_config.model_id,
            "model_supports_image_input": bool(model_config.supports_image_input),
            "history_policy": {
                "num_history_messages": history_policy.num_history_messages,
                "max_tool_calls_from_history": history_policy.max_tool_calls_from_history,
                "history_budget_tokens": history_policy.history_budget_tokens,
                "compression_target_tokens": history_policy.compression_target_tokens,
                "estimated_history_tokens": history_policy.estimated_history_tokens,
                "compression_required": history_policy.compression_required,
                "compression_target_ratio": history_policy.compression_target_ratio,
                "history_token_ratio": history_policy.history_token_ratio,
            },
            "agent_prompt_customized": agent_config.prompt_customized,
            "enabled_tool_keys": list(agent_config.enabled_tool_keys),
            "disabled_tool_keys": list(agent_config.disabled_tool_keys),
        }
        model = self._model_resolver.resolve_model(model_config)
        component_model = None
        component_agent_config = None
        resource_model = None
        resource_agent_config = None
        if descriptor.id == AGENT_COORDINATOR_AGENT_ID:
            component_descriptor = self._registry.get_descriptor(COMPONENT_MANAGER_AGENT_ID)
            resource_descriptor = self._registry.get_descriptor(RESOURCE_MANAGER_AGENT_ID)
            component_agent_config = await self._agent_config_service.get_effective_runtime_config(COMPONENT_MANAGER_AGENT_ID)
            resource_agent_config = await self._agent_config_service.get_effective_runtime_config(RESOURCE_MANAGER_AGENT_ID)
            component_model_config = await self._llm_service.get_bound_config_or_raise(component_descriptor.llm_slot or "")
            resource_model_config = await self._llm_service.get_bound_config_or_raise(resource_descriptor.llm_slot or "")
            component_model = self._model_resolver.resolve_model(component_model_config)
            resource_model = self._model_resolver.resolve_model(resource_model_config)
            metadata["member_llm_configs"] = {
                COMPONENT_MANAGER_AGENT_ID: {
                    "llm_slot": component_descriptor.llm_slot,
                    "llm_config_id": component_model_config.id,
                    "llm_config_name": component_model_config.name,
                    "provider_key": component_model_config.provider_key,
                    "model_id": component_model_config.model_id,
                },
                RESOURCE_MANAGER_AGENT_ID: {
                    "llm_slot": resource_descriptor.llm_slot,
                    "llm_config_id": resource_model_config.id,
                    "llm_config_name": resource_model_config.name,
                    "provider_key": resource_model_config.provider_key,
                    "model_id": resource_model_config.model_id,
                },
            }
            metadata["member_tool_keys"] = {
                COMPONENT_MANAGER_AGENT_ID: {
                    "enabled_tool_keys": list(component_agent_config.enabled_tool_keys),
                    "disabled_tool_keys": list(component_agent_config.disabled_tool_keys),
                },
                RESOURCE_MANAGER_AGENT_ID: {
                    "enabled_tool_keys": list(resource_agent_config.enabled_tool_keys),
                    "disabled_tool_keys": list(resource_agent_config.disabled_tool_keys),
                },
            }
        return self._registry.build_agent(
            agent_id=descriptor.id,
            model=model,
            runtime_context=runtime_context,
            session_metadata=session_metadata,
            agent_config=agent_config,
            component_model=component_model,
            component_agent_config=component_agent_config,
            resource_model=resource_model,
            resource_agent_config=resource_agent_config,
            num_history_messages=history_policy.num_history_messages,
            max_tool_calls_from_history=history_policy.max_tool_calls_from_history,
            enable_session_summaries=history_policy.compression_required,
            add_session_summary_to_context=history_policy.summary_available or history_policy.compression_required,
        ), metadata

    def _build_history_policy_for_session(
        self,
        *,
        model_config,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
        session_metadata: dict[str, Any],
        agent_config: EffectiveAgentRuntimeConfig,
        session_detail: AgnoSessionDetail,
        current_input: str | None = None,
        extra_history_messages: list[Any] | None = None,
    ):
        """读取当前会话历史和摘要，并按 token 预算生成上下文策略。"""

        fixed_context_tokens = self._estimate_fixed_context_tokens(
            agent_id=agent_id,
            runtime_context=runtime_context,
            session_metadata=session_metadata,
            agent_config=agent_config,
        )
        return build_history_policy(
            model_config,
            current_input=current_input,
            fixed_context_tokens=fixed_context_tokens,
            history_messages=_merge_history_messages_for_policy(
                self._get_policy_history_messages(session_detail, agent_id=agent_id),
                extra_history_messages or [],
            ),
            session_summary=getattr(session_detail, "summary", None),
        )

    def _estimate_fixed_context_tokens(
        self,
        *,
        agent_id: str,
        runtime_context: AgentRuntimeContext,
        session_metadata: dict[str, Any],
        agent_config: EffectiveAgentRuntimeConfig,
    ) -> int:
        """估算系统指令之外的固定业务上下文，给历史预算预留空间。"""

        parts = [build_scope_context_text(runtime_context)]
        if agent_id == AGENT_COORDINATOR_AGENT_ID:
            parts.append(
                build_tool_disclosure_context(
                    metadata=session_metadata,
                    scope=runtime_context,
                    session_factory=get_session_factory(),
                    agent_config=agent_config,
                    supports_image_input=bool(session_metadata.get("model_supports_image_input", False)),
                )
            )
        return estimate_text_tokens("\n\n".join(part for part in parts if part))

    @staticmethod
    def _get_policy_history_messages(session_detail: AgnoSessionDetail, *, agent_id: str) -> list[Any]:
        """读取用于上下文预算估算的历史消息，包含暂停 run 中已稳定持久化的消息。"""

        try:
            return list(
                _get_session_messages(
                    session_detail,
                    agent_id=agent_id,
                    skip_history_messages=False,
                    skip_statuses=[],
                )
            )
        except TypeError:
            return list(session_detail.get_messages(skip_history_messages=False, skip_statuses=[]))

    @staticmethod
    def _build_model_history_messages(agent: Any, *, session_detail: AgnoSessionDetail, agent_id: str) -> list[Message]:
        """按平台策略构造模型历史，保留已补偿的 cancelled run，仍跳过 paused/error。"""

        if not bool(getattr(agent, "add_history_to_context", False)):
            return []
        system_message_role = str(getattr(agent, "system_message_role", "system"))
        skip_role = system_message_role if system_message_role not in {"user", "assistant", "tool"} else None
        try:
            history = _get_session_messages(
                session_detail,
                agent_id=agent_id,
                last_n_runs=getattr(agent, "num_history_runs", None),
                limit=getattr(agent, "num_history_messages", None),
                skip_roles=[skip_role] if skip_role else None,
                skip_statuses=[RunStatus.paused, RunStatus.error],
            )
        except TypeError:
            history = list(
                session_detail.get_messages(
                    last_n_runs=getattr(agent, "num_history_runs", None),
                    limit=getattr(agent, "num_history_messages", None),
                    skip_roles=[skip_role] if skip_role else None,
                    skip_statuses=[RunStatus.paused, RunStatus.error],
                )
            )
        history_copy = [deepcopy(message) for message in history]
        for message in history_copy:
            message.from_history = True
        max_tool_calls = getattr(agent, "max_tool_calls_from_history", None)
        if max_tool_calls is not None:
            filter_tool_calls(history_copy, max_tool_calls)
        return history_copy

    def _map_active_run_item(
        self,
        run: RunOutput | TeamRunOutput,
        *,
        session_id: str,
        agent_id: str,
        runtime_context: AgentRuntimeContext | None,
    ) -> AgentActiveRunItem:
        """把 Agno RunOutput 映射成前端 session 级 active-run 状态。"""

        payload = _active_run_payload(run)
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("session_id", session_id)
        payload.setdefault("run_id", getattr(run, "run_id", None))
        status = _normalize_run_status_value(getattr(run, "status", None))
        pending_requirement = _extract_pending_requirement(payload=payload, runtime_context=runtime_context)
        if pending_requirement is not None:
            status = "paused"
        return AgentActiveRunItem(
            run_id=str(getattr(run, "run_id", "") or ""),
            session_id=session_id,
            agent_id=str(_resolve_run_owner_id(run) or agent_id),
            status=status,
            pending_requirement=pending_requirement,
            content=_stringify_content(payload.get("content")),
            created_at=_normalize_timestamp(getattr(run, "created_at", None)),
            updated_at=_normalize_timestamp(getattr(run, "updated_at", None)),
            event_index=_run_latest_event_index(run),
        )

    async def _get_continuable_pending_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
    ) -> tuple[RunOutput | TeamRunOutput | None, AgentPendingRequirement | None]:
        """读取可继续的 HITL run，兼容 Agno 状态被误写为 completed/error 的历史数据。"""

        session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        if not isinstance(session_detail, (AgentSession, TeamSession)):
            return None, None
        candidates = [
            _find_latest_session_run(session_detail, agent_id=agent_id, statuses=_ACTIVE_RUN_STATUSES),
            _find_latest_session_run(session_detail, agent_id=agent_id),
        ]
        for run in candidates:
            if run is None:
                continue
            run_scope = self._resolve_run_scope(run, fallback_metadata=_session_metadata(session_detail))
            run_runtime_context = runtime_context
            if run_scope is not None:
                run_runtime_context = await build_agent_runtime_context(session=self._session, scope=run_scope)
            run_item = self._map_active_run_item(
                run,
                session_id=session_id,
                agent_id=agent_id,
                runtime_context=run_runtime_context,
            )
            if run_item.status == "paused" and run_item.pending_requirement is not None:
                return run, run_item.pending_requirement
        return None, None

    def _get_session_run_lock(self, *, session_id: str, agent_id: str) -> asyncio.Lock:
        """返回当前用户、Agent、Session 维度的进程内互斥锁。"""

        lock_key = f"{self._current.user.id}:{agent_id}:{session_id}"
        lock = self._session_run_locks.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_run_locks[lock_key] = lock
        return lock

    async def _upsert_run_marker(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        status: RunStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """在 Agno session.runs 中写入运行中占位，作为 session-first 并发状态源。"""

        detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
        if not isinstance(detail, (AgentSession, TeamSession)):
            return
        if isinstance(detail, TeamSession):
            run_output: RunOutput | TeamRunOutput = TeamRunOutput(
                run_id=run_id,
                session_id=session_id,
                team_id=agent_id,
                user_id=str(self._current.user.id),
                status=status,
                metadata=metadata or {},
            )
        else:
            run_output = RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                user_id=str(self._current.user.id),
                status=status,
                metadata=metadata or {},
            )
        detail.upsert_run(run_output)
        await asyncio.to_thread(self._ai_db.upsert_session, detail)

    async def _set_existing_run_status(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        status: RunStatus,
        content: str | None,
    ) -> None:
        """更新已存在 run 的状态，保留原始消息与工具信息。"""

        detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
        if not isinstance(detail, (AgentSession, TeamSession)):
            return
        run = detail.get_run(run_id)
        if run is None:
            await self._upsert_run_marker(session_id=session_id, agent_id=agent_id, run_id=run_id, status=status)
            return
        run.status = status
        if content is not None:
            run.content = content
        _normalize_agno_terminal_run_payload(run, status=status)
        detail.upsert_run(run)
        await asyncio.to_thread(self._ai_db.upsert_session, detail)

    async def _sync_agno_requirement_decision_before_continue(
        self,
        *,
        session_detail: AgnoSessionDetail,
        run_id: str,
        requirement: RunRequirement,
    ) -> None:
        """继续前先把用户决策写回 Agno session，避免刷新读到旧暂停态。"""

        run = session_detail.get_run(run_id)
        if run is None:
            return
        run.status = RunStatus.running
        run.content = None
        _apply_resolved_requirement_to_agno_run(run, requirement=requirement)
        session_detail.upsert_run(run)
        await asyncio.to_thread(self._ai_db.upsert_session, session_detail)

    async def _normalize_agno_completed_run_after_continue(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        content: str | None,
        resolved_tool_execution: dict[str, Any] | None,
    ) -> None:
        """continue 完成后规范化 Agno run，确保终态不残留未解决 HITL。"""

        detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
        if not isinstance(detail, (AgentSession, TeamSession)):
            return
        run = detail.get_run(run_id)
        if run is None:
            return
        run.status = RunStatus.completed
        if content is not None:
            run.content = content
        _normalize_agno_terminal_run_payload(
            run,
            status=RunStatus.completed,
            resolved_tool_execution=resolved_tool_execution,
        )
        detail.upsert_run(run)
        await asyncio.to_thread(self._ai_db.upsert_session, detail)

    async def _mark_run_terminal(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        status: RunStatus,
        content: str,
    ) -> None:
        """在异常或断线时把运行中占位推进到终态，避免后续会话被永久占用。"""

        await self._set_existing_run_status(
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            status=status,
            content=content,
        )

    async def _preserve_cancelled_raw_run_messages(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str,
        fallback_user_message: str | None,
        assistant_content: str | None,
        reasoning_content: str | None,
    ) -> None:
        """Agno 取消 run 未写 messages 时，补回 Editor 已展示的最小对话历史。"""

        detail = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
        if not isinstance(detail, (AgentSession, TeamSession)):
            return
        run = detail.get_run(run_id)
        if run is None:
            if isinstance(detail, TeamSession):
                run = TeamRunOutput(
                    run_id=run_id,
                    session_id=session_id,
                    team_id=agent_id,
                    user_id=str(self._current.user.id),
                    status=RunStatus.cancelled,
                )
            else:
                run = RunOutput(
                    run_id=run_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=str(self._current.user.id),
                    status=RunStatus.cancelled,
                )
        displayable_messages = [
            message
            for message in list(getattr(run, "messages", None) or [])
            if _is_displayable_session_message(message)
        ]
        has_user_message = any(str(getattr(message, "role", "") or "") == "user" for message in displayable_messages)
        has_assistant_message = any(
            str(getattr(message, "role", "") or "") == "assistant"
            and (_stringify_content(getattr(message, "content", None)) or _resolve_reasoning_content(message))
            for message in displayable_messages
        )
        user_content = _resolve_run_input_text(run) or (fallback_user_message or "").strip() or None
        assistant_text = (assistant_content or "").strip() or None
        reasoning_text = (reasoning_content or "").strip() or None
        next_messages: list[Any] = []
        if user_content and not has_user_message:
            next_messages.append(
                Message(
                    role="user",
                    content=user_content,
                    created_at=_coerce_int(getattr(run, "created_at", None)) or int(datetime.now(tz=UTC).timestamp()),
                )
            )
        next_messages.extend(displayable_messages)
        if (assistant_text or reasoning_text) and not has_assistant_message:
            next_messages.append(
                Message(
                    role="assistant",
                    content=assistant_text or "",
                    reasoning_content=reasoning_text,
                    created_at=_coerce_int(getattr(run, "updated_at", None))
                    or _coerce_int(getattr(run, "created_at", None))
                    or int(datetime.now(tz=UTC).timestamp()),
                )
            )
        if not next_messages:
            return
        run.messages = next_messages
        run.status = RunStatus.cancelled
        if assistant_text is not None:
            run.content = assistant_text
        metadata = dict(getattr(run, "metadata", None) or {})
        metadata["user_cancel_preserved"] = True
        run.metadata = metadata
        _normalize_agno_terminal_run_payload(run, status=RunStatus.cancelled)
        detail.upsert_run(run)
        await asyncio.to_thread(self._ai_db.upsert_session, detail)

    async def _cancel_stale_running_run_if_needed(
        self,
        *,
        run: RunOutput | TeamRunOutput,
        session_id: str,
        agent_id: str,
    ) -> RunOutput | TeamRunOutput:
        """后台重启后 Agno buffer 丢失时，把陈旧 running run 收敛为 cancelled。"""

        if _coerce_run_status(getattr(run, "status", None)) not in {RunStatus.pending, RunStatus.running}:
            return run
        run_id = str(getattr(run, "run_id", "") or "")
        if not run_id:
            return run
        from agno.os.managers import event_buffer

        if event_buffer.get_run_status(run_id) is not None:
            return run
        timestamp = getattr(run, "updated_at", None) or getattr(run, "created_at", None)
        try:
            run_age_seconds = int(datetime.now(tz=UTC).timestamp()) - int(timestamp)
        except (TypeError, ValueError):
            return run
        if run_age_seconds < 30:
            return run
        await self._mark_run_terminal(
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            status=RunStatus.cancelled,
            content="后台服务已重启，运行事件缓冲丢失，本次运行已停止。",
        )
        refreshed = await self._read_session_detail(session_id=session_id, agent_id=agent_id)
        if isinstance(refreshed, (AgentSession, TeamSession)):
            return refreshed.get_run(run_id) or run
        return run

    def _map_session_item(self, payload: AgnoSessionDetail, *, metadata: dict[str, Any] | None = None) -> AgentSessionItem:
        """把 Agno session 映射成前端会话项结构。"""

        session_data = payload.session_data or {}
        return AgentSessionItem(
            session_id=payload.session_id,
            agent_id=_resolve_session_owner_id(payload) or AGENT_COORDINATOR_AGENT_ID,
            session_name=session_data.get("session_name"),
            created_at=_normalize_timestamp(payload.created_at),
            updated_at=_normalize_timestamp(payload.updated_at),
            metadata=metadata if metadata is not None else payload.metadata or {},
        )

    @staticmethod
    def _session_matches_workspace(metadata: dict[str, Any], workspace_id: int) -> bool:
        """判断会话 metadata 是否属于当前工作空间。"""

        return str(metadata.get("workspace_id")) == str(workspace_id)

    @staticmethod
    def _route_scope_within_session_scope(session_metadata: dict[str, Any], route_scope: AgentScopeContext) -> bool:
        """判断当前路由 scope 是否落在会话工作范围内。"""

        session_scope = _scope_from_metadata(session_metadata)
        if session_scope is None or str(session_scope.workspace_id) != str(route_scope.workspace_id):
            return False
        if session_scope.scope_type == "workspace":
            return True
        if session_scope.scope_type == "project":
            return route_scope.project_id is not None and str(route_scope.project_id) == str(session_scope.project_id)
        if session_scope.scope_type == "page":
            return route_scope.page_id is not None and str(route_scope.page_id) == str(session_scope.page_id)
        if session_scope.scope_type == "component":
            return route_scope.component_id is not None and str(route_scope.component_id) == str(session_scope.component_id)
        return False

    @classmethod
    def _ensure_route_scope_in_session_scope(cls, session_metadata: dict[str, Any], route_scope: AgentScopeContext) -> None:
        """运行前确保当前路由在会话工作范围内。"""

        if cls._route_scope_within_session_scope(session_metadata, route_scope):
            return
        raise AppException(
            status_code=409,
            code="AI_SESSION_ROUTE_OUT_OF_SCOPE",
            detail="当前页面不在此会话工作范围。",
        )

    async def _enrich_session_scope_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """为旧会话 metadata 动态补齐上下文名称，避免前端展示空标题。"""

        scope = _scope_from_metadata(metadata)
        if scope is None:
            return dict(metadata)
        next_metadata = dict(metadata)
        try:
            workspace = await WorkspaceRepository(self._session).get_by_id(scope.workspace_id)
            if workspace is not None:
                next_metadata["workspace_name"] = workspace.name
        except AppException:
            pass

        if scope.project_id is not None:
            try:
                project = await ProjectService(self._session).get(scope.project_id)
                next_metadata["project_name"] = project.name
                next_metadata["workspace_name"] = project.workspace_name or next_metadata.get("workspace_name")
            except AppException:
                pass

        if scope.page_id is not None:
            try:
                page = await PageService(self._session).get(scope.page_id)
                next_metadata["page_title"] = page.title
                next_metadata["project_name"] = page.project_name or next_metadata.get("project_name")
                next_metadata["workspace_name"] = page.workspace_name or next_metadata.get("workspace_name")
            except AppException:
                pass

        if scope.component_id is not None:
            try:
                component = await WorkspaceComponentService(self._session).get(scope.component_id)
                next_metadata["component_name"] = component.name
                next_metadata["workspace_name"] = component.workspace_name or next_metadata.get("workspace_name")
            except AppException:
                pass
        return next_metadata

    @staticmethod
    def _resolve_run_scope(run: RunOutput | TeamRunOutput, *, fallback_metadata: dict[str, Any]) -> AgentScopeContext | None:
        """优先从 run metadata 读取创建 run 时的业务 scope，旧数据回退到 session scope。"""

        run_metadata = getattr(run, "metadata", None)
        run_scope_payload = run_metadata.get("run_scope") if isinstance(run_metadata, dict) else None
        if isinstance(run_scope_payload, dict):
            parsed = _scope_from_metadata(run_scope_payload)
            if parsed is not None:
                return parsed
        return _scope_from_metadata(fallback_metadata)

    def _get_registry(self):
        """从应用状态中读取 Agent 注册表。"""

        registry = getattr(self._app.state, "ai_registry", None)
        if registry is None:
            raise RuntimeError("AI registry is not initialized.")
        return registry

    def _get_ai_db(self):
        """从应用状态中读取 Agno 会话库。"""

        ai_db = getattr(self._app.state, "ai_db", None)
        if ai_db is None:
            raise RuntimeError("AI db is not initialized.")
        return ai_db


def _scope_from_metadata(metadata: dict[str, Any]) -> AgentScopeContext | None:
    """从会话或 run metadata 中恢复业务 scope，兼容旧会话缺少 scope_type 的数据。"""

    workspace_id = _coerce_int(metadata.get("workspace_id"))
    if workspace_id is None:
        return None
    project_id = _coerce_int(metadata.get("project_id"))
    page_id = _coerce_int(metadata.get("page_id"))
    component_id = _coerce_int(metadata.get("component_id"))
    raw_scope_type = str(metadata.get("scope_type") or "").strip()
    scope_type = raw_scope_type if raw_scope_type in {"workspace", "project", "page", "component"} else ""
    if not scope_type:
        if page_id is not None:
            scope_type = "page"
        elif component_id is not None:
            scope_type = "component"
        elif project_id is not None:
            scope_type = "project"
        else:
            scope_type = "workspace"
    return AgentScopeContext(
        scope_type=scope_type,  # type: ignore[arg-type]
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        workspace_name=_coerce_str(metadata.get("workspace_name")),
        project_name=_coerce_str(metadata.get("project_name")),
        page_title=_coerce_str(metadata.get("page_title")),
        component_name=_coerce_str(metadata.get("component_name")),
        source=str(metadata.get("source") or "editor-agent-sidebar"),
    )


def _session_type_for_descriptor(descriptor: Any) -> SessionType:
    """根据目录 entry_kind 选择 Agno 会话类型。"""

    return SessionType.TEAM if getattr(descriptor, "entry_kind", None) == "team" else SessionType.AGENT


def _session_type_for_detail(detail: AgnoSessionDetail) -> SessionType:
    """根据 Agno session 实例选择写回类型。"""

    return SessionType.TEAM if isinstance(detail, TeamSession) else SessionType.AGENT


def _session_type_candidates(primary: SessionType) -> tuple[SessionType, ...]:
    """返回读取会话时的主类型和兼容类型。"""

    if primary == SessionType.TEAM:
        return (SessionType.TEAM, SessionType.AGENT)
    return (primary,)


def _get_session_messages(session_detail: AgnoSessionDetail, *, agent_id: str, **kwargs: Any) -> list[Any]:
    """按 Agno session 类型读取消息，Team 默认隐藏成员内部消息。"""

    if isinstance(session_detail, TeamSession):
        return list(session_detail.get_messages(team_id=agent_id, skip_member_messages=True, **kwargs))
    return list(session_detail.get_messages(agent_id=agent_id, **kwargs))


def _merge_history_messages_for_policy(persisted_messages: list[Any], extra_messages: list[Any]) -> list[Any]:
    """合并已持久化历史和当前 run 临时历史，避免同一消息重复计入预算。"""

    result = [*persisted_messages]
    seen = {_history_message_identity(message) for message in persisted_messages}
    for message in extra_messages:
        identity = _history_message_identity(message)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(message)
    return result


def _history_message_identity(message: Any) -> tuple[str, str, str | None, str | None]:
    """提取消息去重标识；内容会序列化以兼容工具 JSON 结果。"""

    return (
        str(getattr(message, "role", "") or "").lower(),
        _stringify_content(getattr(message, "content", None)),
        _coerce_str(getattr(message, "tool_name", None)),
        _coerce_str(getattr(message, "tool_call_id", None)),
    )


def _get_session_message_records(session_detail: AgnoSessionDetail, *, agent_id: str, **kwargs: Any) -> list[_SessionMessageRecord]:
    """按 run 展开消息并保留 run_id，弥补 Agno get_messages 丢失外层 run 信息的问题。"""

    skip_statuses = kwargs.get("skip_statuses")
    if skip_statuses is None:
        skip_statuses = [RunStatus.paused, RunStatus.cancelled, RunStatus.error]
    skip_history_messages = bool(kwargs.get("skip_history_messages", True))
    records: list[_SessionMessageRecord] = []
    for run in session_detail.runs or []:
        owner_id = _resolve_run_owner_id(run)
        if owner_id is not None and str(owner_id) != agent_id:
            continue
        if getattr(run, "parent_run_id", None) is not None:
            continue
        if _coerce_run_status(getattr(run, "status", None)) in skip_statuses:
            continue
        run_id = _coerce_str(getattr(run, "run_id", None))
        for message in getattr(run, "messages", None) or []:
            if skip_history_messages and getattr(message, "from_history", False):
                continue
            records.append(_SessionMessageRecord(run_id=run_id, message=message))
    return records


def _message_attr(message: Any, field_name: str, default: Any = None) -> Any:
    """兼容 Agno Message 对象和 dict 测试替身读取字段。"""

    if isinstance(message, dict):
        return message.get(field_name, default)
    return getattr(message, field_name, default)


def _is_displayable_session_message(message: Any, *, role: str | None = None) -> bool:
    """判断消息是否属于用户可见对话，过滤 Agno 历史和框架上下文注入。"""

    resolved_role = role or str(_message_attr(message, "role", "") or "")
    if resolved_role == "system":
        return False
    if resolved_role not in {"user", "assistant", "tool"}:
        return False
    if bool(_message_attr(message, "from_history", False)):
        return False
    if _is_agno_context_note_message(message, role=resolved_role):
        return False
    return True


def _is_agno_context_note_message(message: Any, *, role: str) -> bool:
    """识别 Agno 为图片或上下文附加的非用户输入提示消息。"""

    if role != "user":
        return False
    content = _stringify_content(_message_attr(message, "content", None)).strip()
    if not content.startswith(_AGNO_CONTEXT_NOTE_PREFIX):
        return False
    for field_name in ("images", "videos", "audio", "files"):
        if _message_attr(message, field_name, None):
            return True
    return False


def _session_metadata(payload: Any) -> dict[str, Any]:
    """从 Agno session 或测试替身中读取 metadata。"""

    if isinstance(payload, dict):
        metadata = payload.get("metadata")
    else:
        metadata = getattr(payload, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _coerce_int(value: Any) -> int | None:
    """把 metadata 中的数字字段安全转为 int。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    """把 metadata 中的展示字段安全转为非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_continue_temp_history_messages(tool_execution: dict[str, Any]) -> list[_TempHistoryMessage]:
    """把继续 paused run 的用户决策临时视作工具结果参与上下文估算。"""

    if not tool_execution:
        return []
    content = {
        key: value
        for key, value in tool_execution.items()
        if key not in {"tool_args", "tool_call_id"}
    }
    if not content:
        content = tool_execution
    return [
        _TempHistoryMessage(
            role="tool",
            content=content,
            tool_name=_coerce_str(tool_execution.get("tool_name")),
            tool_call_id=_coerce_str(tool_execution.get("tool_call_id")),
            tool_args=tool_execution.get("tool_args"),
        )
    ]


def _dedupe_scopes(scopes: tuple[str, ...]) -> tuple[str, ...]:
    """保持原有顺序去重工具授权 scope。"""

    result: list[str] = []
    for scope in scopes:
        if scope not in result:
            result.append(scope)
    return tuple(result)


def _normalize_user_feedback_schema(raw_schema: Any) -> list[dict[str, Any]]:
    """把 Agno 的结构化提问 schema 归一成前端可直接渲染的单选列表。"""

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


def _apply_user_feedback_selections(
    tool_execution: dict[str, Any],
    feedback_selections: list[dict[str, Any]],
) -> dict[str, Any]:
    """把前端单选或自定义回答写回 Agno ask_user 的 ToolExecution。"""

    selection_map: dict[str, dict[str, Any]] = {}
    for raw_selection in feedback_selections:
        if not isinstance(raw_selection, dict):
            continue
        question = _coerce_str(raw_selection.get("question"))
        if question:
            selection_map[question] = raw_selection

    schema = _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    for question in schema:
        selection = selection_map.get(str(question.get("question") or ""))
        if not selection:
            continue
        custom_text = _coerce_str(selection.get("custom_text"))
        selected_label = _coerce_str(selection.get("selected_label"))
        selected_options = [f"用户补充：{custom_text}"] if custom_text else ([selected_label] if selected_label else [])
        question["selected_options"] = selected_options
        for option in question.get("options") or []:
            if isinstance(option, dict):
                option["selected"] = option.get("label") in selected_options

    updated_tool_execution = dict(tool_execution)
    updated_tool_execution["requires_user_input"] = True
    updated_tool_execution["user_feedback_schema"] = schema
    if schema and all(question.get("selected_options") for question in schema):
        updated_tool_execution["answered"] = True
    return updated_tool_execution


def _apply_resolved_requirement_to_agno_run(run: RunOutput | TeamRunOutput, *, requirement: RunRequirement) -> None:
    """把本次 HITL 决策同步到 Agno run 的 requirement 与 tool 列表。"""

    tool_execution = requirement.tool_execution
    tool_call_id = _tool_call_id(tool_execution)
    if not tool_call_id:
        return
    updated_requirements: list[Any] = []
    replaced = False
    for item in list(getattr(run, "requirements", None) or []):
        if _requirement_tool_call_id(item) == tool_call_id:
            updated_requirements.append(requirement)
            replaced = True
        else:
            updated_requirements.append(item)
    if not replaced:
        updated_requirements.append(requirement)
    run.requirements = updated_requirements

    updated_tools: list[Any] = []
    tool_replaced = False
    for item in list(getattr(run, "tools", None) or []):
        if _tool_call_id(item) == tool_call_id:
            _copy_tool_execution_state(item, tool_execution)
            updated_tools.append(item)
            tool_replaced = True
        else:
            updated_tools.append(item)
    if not tool_replaced and tool_execution is not None:
        updated_tools.append(tool_execution)
    run.tools = updated_tools


def _normalize_agno_terminal_run_payload(
    run: RunOutput | TeamRunOutput,
    *,
    status: RunStatus,
    resolved_tool_execution: dict[str, Any] | None = None,
    fallback_tool_result: Any = None,
) -> None:
    """终态 run 不再携带未解决 HITL，避免后续刷新把旧动作恢复为 paused。"""

    if status not in {RunStatus.completed, RunStatus.cancelled}:
        return
    tool_call_id = _coerce_str((resolved_tool_execution or {}).get("tool_call_id"))
    run.requirements = []
    for item in list(getattr(run, "tools", None) or []):
        item_call_id = _tool_call_id(item)
        is_target_tool = bool(tool_call_id and item_call_id == tool_call_id)
        if is_target_tool and resolved_tool_execution is not None:
            _copy_tool_execution_payload_state(item, resolved_tool_execution)
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
        if is_target_tool and fallback_tool_result is not None and getattr(item, "result", None) is None:
            item.result = fallback_tool_result


def _copy_tool_execution_state(target: Any, source: Any) -> None:
    """把 Agno ToolExecution 对象中的决策字段复制到旧对象。"""

    if target is None or source is None:
        return
    for field_name in (
        "confirmed",
        "confirmation_note",
        "requires_user_input",
        "user_input_schema",
        "user_feedback_schema",
        "answered",
        "external_execution_required",
        "external_execution_silent",
        "result",
    ):
        value = getattr(source, field_name, None)
        if value is not None:
            setattr(target, field_name, value)


def _copy_tool_execution_payload_state(target: Any, source: dict[str, Any]) -> None:
    """把前端 ToolExecution payload 中的决策字段复制到 Agno ToolExecution。"""

    for field_name in (
        "confirmed",
        "confirmation_note",
        "requires_user_input",
        "user_input_schema",
        "user_feedback_schema",
        "answered",
        "external_execution_required",
        "external_execution_silent",
        "result",
    ):
        if field_name in source and source[field_name] is not None:
            setattr(target, field_name, source[field_name])


def _requirement_tool_call_id(requirement: Any) -> str:
    """提取 Agno RunRequirement 中的 tool_call_id。"""

    return _tool_call_id(getattr(requirement, "tool_execution", None))


def _tool_call_id(tool_execution: Any) -> str:
    """兼容对象与 dict，提取 ToolExecution 的稳定调用 ID。"""

    if isinstance(tool_execution, dict):
        return _coerce_str(tool_execution.get("tool_call_id"))
    return _coerce_str(getattr(tool_execution, "tool_call_id", None))


def _build_run_requirement_from_tool_execution_payload(tool_execution: dict[str, Any]) -> RunRequirement:
    """从前端提交的 ToolExecution payload 构造 Agno requirement，并补齐 Agno 反序列化遗漏字段。"""

    execution = ToolExecution.from_dict(tool_execution)
    confirmed = tool_execution.get("confirmed")
    confirmation_note = _coerce_str(tool_execution.get("confirmation_note"))
    answered = tool_execution.get("answered")
    if answered is True or _tool_execution_payload_has_complete_user_answers(tool_execution):
        execution.answered = True
    if execution.tool_name == "ask_user" and execution.answered is True:
        # Agno 2.5.x 的 Team continue 路径没有 ask_user 专用处理，会把已答复的问题再次执行成工具。
        # 这里将用户选择转为普通工具结果消息，让 Team/Agent 两条路径都能继续同一个 tool_call_id。
        execution.requires_user_input = False
        execution.external_execution_required = True
        execution.result = _build_user_feedback_tool_result(tool_execution)
        requirement = RunRequirement(tool_execution=execution)
        requirement.external_execution_result = execution.result
        return requirement
    requirement = RunRequirement(tool_execution=execution)
    if confirmed is True:
        requirement.confirmation = True
        execution.confirmed = True
    elif confirmed is False:
        requirement.confirmation = False
        requirement.confirmation_note = confirmation_note
        execution.confirmed = False
        execution.confirmation_note = confirmation_note
    return requirement


def _build_user_feedback_tool_result(tool_execution: dict[str, Any]) -> str:
    """把 ask_user 结构化选择编码为 Agno 工具结果消息内容。"""

    feedback_result = [
        {
            "question": question.get("question"),
            "selected": question.get("selected_options") or [],
        }
        for question in _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    ]
    return f"User feedback received: {json.dumps(feedback_result, ensure_ascii=False)}"


def _tool_execution_payload_has_complete_user_answers(tool_execution: dict[str, Any]) -> bool:
    """判断已序列化的用户输入/反馈是否已经完整回答。"""

    feedback_schema = _normalize_user_feedback_schema(tool_execution.get("user_feedback_schema"))
    if feedback_schema:
        return all(question.get("selected_options") for question in feedback_schema)

    input_schema = tool_execution.get("user_input_schema")
    if isinstance(input_schema, list) and input_schema:
        values: list[Any] = []
        for raw_field in input_schema:
            field = jsonable_encoder(raw_field)
            if isinstance(field, dict):
                values.append(field.get("value"))
        return len(values) == len(input_schema) and all(value is not None for value in values)

    return False


def _extract_pending_requirement(
    *,
    payload: dict[str, Any],
    runtime_context: AgentRuntimeContext | None = None,
    current_page: PageItem | None = None,
    ) -> AgentPendingRequirement | None:
    """从 RunPaused 事件中提取第一个待确认需求，并补齐页面 patch 信息。"""

    if runtime_context is None and current_page is not None:
        runtime_context = AgentRuntimeContext(
            scope_type="page",
            workspace_id=int(current_page.workspace_id or 0),
            project_id=current_page.project_id,
            page_id=current_page.id,
            page_title=current_page.title,
            page_summary=current_page.summary,
            page_code=current_page.code,
            page_content=current_page.page_content,
            file_type=current_page.file_type.value,
            source="editor-page-detail",
        )
    requirement_payload = _resolve_requirement_payload(payload)
    if requirement_payload is None:
        return None
    member_event_data = _extract_member_event_data(payload)

    tool_execution = requirement_payload.get("tool_execution") or {}
    tool_name = tool_execution.get("tool_name")
    tool_args = tool_execution.get("tool_args") or {}
    user_feedback_schema = _normalize_user_feedback_schema(
        requirement_payload.get("user_feedback_schema")
        or tool_execution.get("user_feedback_schema")
        or tool_args.get("questions")
    )
    requirement_kind = "user_feedback" if (tool_name == "ask_user" or user_feedback_schema) else "confirmation"
    suggested_patch, preview_note = (None, None)
    if runtime_context is not None and runtime_context.page_id is not None and runtime_context.page_content is not None:
        suggested_patch, preview_note = _build_suggested_patch(
            current_page=PageItem(
                id=runtime_context.page_id,
                code=runtime_context.page_code or "",
                page_content=runtime_context.page_content,
                current_version_no=1,
                file_type=runtime_context.file_type or "vue",
                title=runtime_context.page_title or "",
                summary=runtime_context.page_summary,
                status="active",
                workspace_id=runtime_context.workspace_id,
                project_id=runtime_context.project_id,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
                created_by=None,
                updated_by=None,
            ),
            tool_name=tool_name,
            tool_args=tool_args,
        )
    normalized_tool_execution = tool_execution
    if user_feedback_schema:
        normalized_tool_execution = {
            **normalized_tool_execution,
            "requires_user_input": True,
            "user_feedback_schema": user_feedback_schema,
        }

    return AgentPendingRequirement(
        id=requirement_payload.get("id"),
        kind=requirement_kind,
        run_id=str(payload.get("run_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        member_agent_id=_coerce_str(member_event_data.get("member_agent_id")),
        member_agent_name=_coerce_str(member_event_data.get("member_agent_name")),
        member_run_id=_coerce_str(member_event_data.get("member_run_id")),
        tool_name=tool_name,
        tool_execution=normalized_tool_execution,
        suggested_patch=suggested_patch,
        user_feedback_schema=user_feedback_schema,
        note=normalized_tool_execution.get("confirmation_note") or preview_note,
    )


def _pending_requirement_timeline_content(requirement: AgentPendingRequirement) -> str:
    """生成 requirement 时间线文案，ask_user 优先展示真实问题而不是内部工具名。"""

    if requirement.kind == "user_feedback" or requirement.tool_name == "ask_user":
        for item in requirement.user_feedback_schema or []:
            if not isinstance(item, dict):
                continue
            question = _coerce_str(item.get("question"))
            if question:
                return question
        return requirement.note or "等待用户回复。"
    return requirement.note or requirement.tool_name or "等待用户处理。"


def _find_latest_session_run(
    session: AgnoSessionDetail,
    *,
    agent_id: str,
    statuses: set[RunStatus] | None = None,
) -> RunOutput | TeamRunOutput | None:
    """按创建时间倒序查找当前 Agent/Team 的最近 run，可选限制状态集合。"""

    candidates: list[tuple[int, int, RunOutput | TeamRunOutput]] = []
    for index, run in enumerate(session.runs or []):
        owner_id = _resolve_run_owner_id(run)
        if owner_id is not None and str(owner_id) != agent_id:
            continue
        run_status = _coerce_run_status(getattr(run, "status", None))
        if statuses is not None and run_status not in statuses:
            continue
        created_at = getattr(run, "created_at", None)
        try:
            created_order = int(created_at)
        except (TypeError, ValueError):
            created_order = index
        candidates.append((created_order, index, run))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _coerce_run_status(status: Any) -> RunStatus:
    """把 Agno 或 JSON 化后的状态值统一为 RunStatus。"""

    if isinstance(status, RunStatus):
        return status
    if status is None:
        return RunStatus.running
    raw_status = str(status).lower()
    for candidate in RunStatus:
        if raw_status in {candidate.name.lower(), candidate.value.lower()}:
            return candidate
    return RunStatus.error


def _normalize_run_status_value(status: Any) -> str:
    """把 Agno RunStatus 映射为前端稳定状态字符串。"""

    normalized = _coerce_run_status(status)
    if normalized == RunStatus.error:
        return "failed"
    return normalized.name


def _run_latest_event_index(run: RunOutput | TeamRunOutput) -> int:
    """按 Agno run.events 计算当前可回放的最后事件下标。"""

    events = getattr(run, "events", None) or []
    return len(events) - 1


def _run_latest_event_index_from_detail(detail: AgnoSessionDetail | Any, run_id: str | None) -> int:
    """从会话详情读取指定 run 已持久化的最后事件下标。"""

    if not run_id or not isinstance(detail, (AgentSession, TeamSession)):
        return -1
    run = detail.get_run(run_id)
    return _run_latest_event_index(run) if run is not None else -1


def _resolve_requirement_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """优先从 requirements 提取待确认项；若缺失，则从暂停 tools 中兜底合成。"""

    requirements = payload.get("requirements") or []
    if requirements:
        for requirement_payload in reversed(requirements):
            if isinstance(requirement_payload, dict) and _is_requirement_payload_active(requirement_payload):
                return requirement_payload

    tools = payload.get("tools") or []
    for tool_payload in reversed(tools):
        if not isinstance(tool_payload, dict):
            continue
        if _is_tool_execution_payload_active(tool_payload):
            return {
                "id": None,
                "tool_execution": tool_payload,
            }
    return None


def _is_requirement_payload_active(requirement_payload: dict[str, Any]) -> bool:
    """判断 JSON 化后的 Agno RunRequirement 是否仍需要人工处理。"""

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
    """判断 JSON 化后的 Agno ToolExecution 是否仍处于暂停等待态。"""

    if tool_execution.get("requires_confirmation") and tool_execution.get("confirmed") is None:
        return True
    if tool_execution.get("requires_user_input") and tool_execution.get("answered") is not True:
        return True
    if tool_execution.get("external_execution_required") and tool_execution.get("result") is None:
        return True
    return False


def _extract_member_event_data(payload: dict[str, Any]) -> dict[str, Any]:
    """从 Team 或成员事件中提取成员智能体标识，供前端工具详情展示。"""

    result: dict[str, Any] = {}
    parent_run_id = payload.get("parent_run_id")
    if parent_run_id is not None:
        result["parent_run_id"] = parent_run_id
        if payload.get("run_id") is not None:
            result["member_run_id"] = payload.get("run_id")
        if payload.get("agent_id") is not None:
            result["member_agent_id"] = payload.get("agent_id")
        if payload.get("agent_name") is not None:
            result["member_agent_name"] = payload.get("agent_name")
    for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
        if payload.get(field_name) is not None:
            result[field_name] = payload.get(field_name)
    tool_payload = payload.get("tool")
    if isinstance(tool_payload, dict):
        for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
            if field_name not in result and tool_payload.get(field_name) is not None:
                result[field_name] = tool_payload.get(field_name)
        field_aliases = {
            "member_agent_id": ("agent_id", "child_agent_id", "target_agent_id"),
            "member_agent_name": ("agent_name", "child_agent_name", "target_agent_name", "member_name"),
            "member_run_id": ("child_run_id", "target_run_id"),
        }
        for field_name, aliases in field_aliases.items():
            if field_name in result:
                continue
            for alias in aliases:
                if tool_payload.get(alias) is not None:
                    result[field_name] = tool_payload.get(alias)
                    break
    requirements = payload.get("requirements") or []
    if isinstance(requirements, list) and requirements:
        first_requirement = requirements[0]
        if isinstance(first_requirement, dict):
            for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                if field_name not in result and first_requirement.get(field_name) is not None:
                    result[field_name] = first_requirement.get(field_name)
            nested_tool = first_requirement.get("tool_execution")
            if isinstance(nested_tool, dict):
                for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                    if field_name not in result and nested_tool.get(field_name) is not None:
                        result[field_name] = nested_tool.get(field_name)
    return result


def _resolve_session_owner_id(payload: AgnoSessionDetail) -> str | None:
    """提取 Agno session 所属的 Agent/Team ID。"""

    owner_id = getattr(payload, "agent_id", None) or getattr(payload, "team_id", None)
    if not owner_id:
        agent_data = getattr(payload, "agent_data", None)
        team_data = getattr(payload, "team_data", None)
        if isinstance(agent_data, dict):
            owner_id = agent_data.get("agent_id")
        if not owner_id and isinstance(team_data, dict):
            owner_id = team_data.get("agent_id") or team_data.get("team_id")
    return str(owner_id) if owner_id else None


def _resolve_run_owner_id(payload: RunOutput | TeamRunOutput | Any) -> str | None:
    """提取 Agno run 所属的 Agent/Team ID。"""

    owner_id = getattr(payload, "agent_id", None) or getattr(payload, "team_id", None)
    return str(owner_id) if owner_id else None


def _prepare_team_run_output_for_agno_continue(
    run: RunOutput | TeamRunOutput | None,
    *,
    agent_id: str,
    agent_name: str | None,
) -> TeamRunOutput | None:
    """补齐 Agno Team continue 复用 Agent 工具事件 helper 所需的兼容字段。"""

    if not isinstance(run, TeamRunOutput):
        return None

    if not run.team_id:
        run.team_id = agent_id
    if not run.team_name:
        run.team_name = agent_name or agent_id
    setattr(run, "agent_id", str(run.team_id or agent_id))
    setattr(run, "agent_name", str(run.team_name or agent_name or agent_id))

    for member_run in run.member_responses or []:
        if isinstance(member_run, TeamRunOutput):
            _prepare_team_run_output_for_agno_continue(
                member_run,
                agent_id=str(member_run.team_id or agent_id),
                agent_name=str(member_run.team_name or agent_name or agent_id),
            )
    return run


def _resolve_message_run_id(payload: Any) -> str:
    """从 Agno 消息中尽量提取所属 run_id，用于把图片附件挂回用户消息。"""

    for field_name in ("run_id", "runId"):
        value = getattr(payload, field_name, None)
        if value:
            return str(value)
    metadata = getattr(payload, "metadata", None)
    if isinstance(metadata, dict):
        for field_name in ("run_id", "runId"):
            value = metadata.get(field_name)
            if value:
                return str(value)
    return ""


def _normalize_message_tool_calls(payload: Any) -> list[dict[str, Any]]:
    """把 Agno assistant.tool_calls 透传为 Editor 可消费的 JSON 列表。"""

    encoded = jsonable_encoder(getattr(payload, "tool_calls", None) or [])
    if not isinstance(encoded, list):
        return []
    return [item for item in encoded if isinstance(item, dict)]


def _build_suggested_patch(
    *,
    current_page: PageItem,
    tool_name: Any,
    tool_args: dict[str, Any],
) -> tuple[AgentSuggestedPatch | None, str | None]:
    """尽量为页面写回工具构造预览 patch；若预生成失败，不中断整个暂停事件。"""

    if tool_name != "apply_page_edits" or not isinstance(tool_args.get("edits"), list):
        return None, None

    try:
        edit_result = apply_source_edits(current_page.page_content, tool_args["edits"])
    except AppException as exc:
        return None, f"页面改写已进入待确认状态，但当前无法预生成 edits 预览：{exc.detail}"

    return AgentSuggestedPatch(
        tool_name=tool_name,
        target_page_id=current_page.id,
        change_note=tool_args.get("change_note"),
        proposed_content=edit_result.next_content,
        unified_diff=edit_result.canonical_diff,
    ), None


def _extract_tool_error_info(
    *,
    payload: dict[str, Any],
    tool_execution: dict[str, Any],
) -> tuple[str | None, str | None, bool, bool, str | None]:
    """从 ToolCallError 事件中提取可稳定下发给前端的错误文案与错误码。"""

    candidates = [
        payload.get("error"),
        tool_execution.get("error"),
        payload.get("content"),
        tool_execution.get("result"),
    ]

    resolved_message: str | None = None
    resolved_code: str | None = None
    repair_attempted = False
    repair_succeeded = False
    repair_reason: str | None = None
    for candidate in candidates:
        candidate = _normalize_error_payload(candidate)
        candidate_message = _extract_error_message(candidate)
        candidate_code = _extract_error_code(candidate)
        candidate_repair_attempted = _extract_error_flag(candidate, "repair_attempted")
        candidate_repair_succeeded = _extract_error_flag(candidate, "repair_succeeded")
        candidate_repair_reason = _extract_error_text_field(candidate, "repair_reason")
        if resolved_message is None and candidate_message:
            resolved_message = candidate_message
        if resolved_code is None and candidate_code:
            resolved_code = candidate_code
        if candidate_repair_attempted is not None:
            repair_attempted = candidate_repair_attempted
        if candidate_repair_succeeded is not None:
            repair_succeeded = candidate_repair_succeeded
        if repair_reason is None and candidate_repair_reason:
            repair_reason = candidate_repair_reason
        if resolved_message and resolved_code and repair_reason is not None:
            break

    return resolved_message, resolved_code, repair_attempted, repair_succeeded, repair_reason


def _normalize_error_payload(value: Any) -> Any:
    """将 JSON 字符串错误体反序列化为字典，便于统一提取结构化字段。"""

    if not isinstance(value, str):
        return value

    stripped_value = value.strip()
    if not stripped_value.startswith("{"):
        return value

    try:
        parsed_value = json.loads(stripped_value)
    except json.JSONDecodeError:
        return value

    return parsed_value if isinstance(parsed_value, dict) else value


def _extract_error_message(value: Any) -> str | None:
    """把多种错误载荷统一折叠为用户可读的字符串。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("detail", "message", "error", "content"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return _stringify_content(value)


def _extract_error_code(value: Any) -> str | None:
    """尽量从错误载荷中提取结构化错误码。"""

    if not isinstance(value, dict):
        return None
    for key in ("code", "error_code"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _extract_error_flag(value: Any, field_name: str) -> bool | None:
    """提取错误载荷中的布尔标记字段。"""

    if not isinstance(value, dict):
        return None
    candidate = value.get(field_name)
    return candidate if isinstance(candidate, bool) else None


def _extract_error_text_field(value: Any, field_name: str) -> str | None:
    """提取错误载荷中的文本字段。"""

    if not isinstance(value, dict):
        return None
    candidate = value.get(field_name)
    if isinstance(candidate, str) and candidate.strip():
        return candidate
    return None


def _resolve_reasoning_content(value: Any, *, preserve_stream_boundary: bool = False) -> str | None:
    """从 Agno 消息或事件中提取 reasoning 字段。"""

    if isinstance(value, dict):
        for field_name in ("reasoning_content", "redacted_reasoning_content"):
            resolved = _normalize_reasoning_content(
                _stringify_content(value.get(field_name)),
                preserve_boundary=preserve_stream_boundary,
            )
            if resolved is not None:
                return resolved
        return None

    for field_name in ("reasoning_content", "redacted_reasoning_content"):
        resolved = _normalize_reasoning_content(
            _stringify_content(getattr(value, field_name, None)),
            preserve_boundary=preserve_stream_boundary,
        )
        if resolved is not None:
            return resolved
    return None


def _split_reasoning_content(
    content: str | None,
    reasoning_content: str | None = None,
    *,
    preserve_reasoning_boundary: bool = False,
) -> tuple[str | None, str | None]:
    """把正文中内嵌的 think/reasoning 标签拆成独立字段。"""

    resolved_reasoning = _normalize_reasoning_content(
        reasoning_content,
        preserve_boundary=preserve_reasoning_boundary,
    )
    if content is None:
        return None, resolved_reasoning

    stripped_content = content
    collected_reasoning: list[str] = []
    for pattern in (_REASONING_BLOCK_PATTERN, _THINK_BLOCK_PATTERN):
        matches = [match.strip() for match in pattern.findall(stripped_content) if match.strip()]
        if matches:
            collected_reasoning.extend(matches)
        stripped_content = pattern.sub("", stripped_content)
    open_tag_match = _OPEN_REASONING_TAG_PATTERN.search(stripped_content)
    if open_tag_match is not None:
        before_reasoning = stripped_content[: open_tag_match.start()]
        after_reasoning = stripped_content[open_tag_match.end() :].strip()
        if after_reasoning:
            collected_reasoning.append(after_reasoning)
        stripped_content = before_reasoning
    stripped_content = _REASONING_TAG_PATTERN.sub("", stripped_content)

    if collected_reasoning:
        reasoning_parts = [resolved_reasoning] if resolved_reasoning else []
        reasoning_parts.extend(collected_reasoning)
        resolved_reasoning = "\n\n".join(reasoning_parts)

    return stripped_content, resolved_reasoning


def _normalize_reasoning_content(value: str | None, *, preserve_boundary: bool = False) -> str | None:
    """规范化 reasoning 文本；流式片段需保留换行边界以便前端即时排版。"""

    if not isinstance(value, str):
        return None
    if preserve_boundary:
        return value if value else None
    stripped_value = value.strip()
    return stripped_value or None


def _normalize_timestamp(value: Any) -> str | None:
    """把 Agno 时间字段统一转换为 ISO 字符串。"""

    if value is None or value == "":
        return None
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    if isinstance(value, float):
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _stringify_content(value: Any) -> str:
    """把 Agno 内容字段统一序列化为文本。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _safe_json_payload(value: Any) -> Any:
    """把 Agno/Pydantic 对象转为 JSON 兼容结构，并用轻量占位替换二进制内容。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "binary", "size": len(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _safe_json_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_payload(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _safe_json_payload(value.model_dump(mode="python", exclude_none=True))
        except TypeError:
            return _safe_json_payload(value.model_dump())
    if is_dataclass(value):
        return {
            field.name: _safe_json_payload(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "__dict__"):
        return {
            key: _safe_json_payload(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    if hasattr(value, "to_dict"):
        return _safe_json_payload(value.to_dict())
    try:
        return _safe_json_payload(jsonable_encoder(value))
    except Exception:
        return str(value)


def _event_payload(raw_event: Any) -> Any:
    """优先沿用 FastAPI 编码，遇到图片 bytes 等异常时降级为安全结构。"""

    try:
        return jsonable_encoder(raw_event)
    except Exception:
        return _safe_json_payload(raw_event)


def _active_run_payload(run: RunOutput | TeamRunOutput) -> dict[str, Any]:
    """仅抽取 runtime/active-run 恢复所需字段，避免序列化历史图片 bytes。"""

    payload = {
        "run_id": getattr(run, "run_id", None),
        "session_id": getattr(run, "session_id", None),
        "agent_id": getattr(run, "agent_id", None),
        "agent_name": getattr(run, "agent_name", None),
        "team_id": getattr(run, "team_id", None),
        "team_name": getattr(run, "team_name", None),
        "parent_run_id": getattr(run, "parent_run_id", None),
        "content": getattr(run, "content", None),
        "requirements": getattr(run, "requirements", None) or [],
        "tools": getattr(run, "tools", None) or [],
    }
    return _safe_json_payload(payload)


def _resolve_run_input_text(run: Any) -> str | None:
    """从 Agno run.input 中提取真实用户输入文本，避免使用 additional_input 历史。"""

    raw_input = getattr(run, "input", None)
    if raw_input is None:
        return None
    payload = _safe_json_payload(raw_input)
    if isinstance(payload, dict):
        for field_name in ("input_content", "content", "message", "input"):
            candidate = payload.get(field_name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        nested_input = payload.get("input")
        if isinstance(nested_input, dict):
            for field_name in ("input_content", "content", "message"):
                candidate = nested_input.get(field_name)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return None


def _extract_text_content(value: Any) -> str | None:
    """仅提取适合直接渲染为助手正文的文本内容，避免把工具结构化结果误当成回答。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _normalize_raw_event_payload(raw_event: Any) -> dict[str, Any]:
    """把 Agno 原始事件归一成字典，供检查点识别和临时历史估算使用。"""

    payload = _event_payload(raw_event)
    return payload if isinstance(payload, dict) else {}


def _raw_event_name(raw_event: Any, payload: dict[str, Any]) -> str:
    """读取 Agno 原始事件名，兼容 dict 与事件对象两种形态。"""

    return str(payload.get("event") or type(raw_event).__name__)


def _raw_event_text_content(payload: dict[str, Any]) -> str | None:
    """从内容完成事件中提取最终文本，作为缺失 delta 时的兜底。"""

    member_event_data = _extract_member_event_data(payload)
    if member_event_data.get("parent_run_id") and member_event_data.get("member_run_id"):
        return None
    content, _ = _split_reasoning_content(
        _extract_text_content(payload.get("content")),
        _resolve_reasoning_content(payload),
    )
    return content


def _build_timeline_items_from_agno_runs(
    detail: AgnoSessionDetail,
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext | None = None,
    target_run_ids: set[str] | None = None,
    include_child_runs: bool = False,
    hide_member_events: bool = True,
) -> list[AgentTimelineItem]:
    """从 Agno runs/messages/events 派生 session-first 时间线。"""

    return build_timeline_items_from_agno_runs(
        detail,
        session_id=session_id,
        agent_id=agent_id,
        runtime_context=runtime_context,
        target_run_ids=target_run_ids,
        include_child_runs=include_child_runs,
        hide_member_events=hide_member_events,
        extract_pending_requirement=_extract_pending_requirement,
        pending_requirement_timeline_content=_pending_requirement_timeline_content,
    )


def _build_member_runs_from_agno_runs(
    detail: AgnoSessionDetail,
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext | None,
    parent_timeline_items: list[AgentTimelineItem],
) -> list[AgentMemberRunItem]:
    """从 Team 父 run 的成员响应中提取可单独展示的子 run。"""

    member_runs: list[AgentMemberRunItem] = []
    seen_run_ids: set[str] = set()
    all_runs = list(getattr(detail, "runs", None) or [])
    for parent_index, parent_run in enumerate(all_runs):
        parent_owner_id = _resolve_run_owner_id(parent_run)
        if parent_owner_id is not None and str(parent_owner_id) != agent_id:
            continue
        if getattr(parent_run, "parent_run_id", None) is not None:
            continue
        parent_run_id = _coerce_str(getattr(parent_run, "run_id", None)) or f"run-{parent_index}"
        for member_run in _iter_member_runs_for_parent(parent_run, all_runs=all_runs):
            member_run_id = _coerce_str(getattr(member_run, "run_id", None))
            if not member_run_id or member_run_id in seen_run_ids:
                continue
            seen_run_ids.add(member_run_id)
            member_agent_id = _resolve_run_owner_id(member_run) or ""
            member_runs.append(
                AgentMemberRunItem(
                    parent_run_id=parent_run_id,
                    run_id=member_run_id,
                    agent_id=str(member_agent_id),
                    agent_name=_resolve_run_owner_name(member_run),
                    status=_normalize_run_status_value(getattr(member_run, "status", None)),  # type: ignore[arg-type]
                    created_at=_normalize_timestamp(getattr(member_run, "created_at", None)),
                    updated_at=_normalize_timestamp(getattr(member_run, "updated_at", None)),
                    delegate_tool_call_id=None,
                    timeline_items=_build_timeline_items_from_agno_runs(
                        SimpleNamespace(runs=[member_run]),
                        session_id=session_id,
                        agent_id=str(member_agent_id),
                        runtime_context=runtime_context,
                        target_run_ids={member_run_id},
                        include_child_runs=True,
                        hide_member_events=False,
                    ),
                )
            )

    _assign_delegate_tool_call_ids(member_runs, parent_timeline_items)
    return sorted(member_runs, key=_member_run_sort_key)


def _iter_member_runs_for_parent(parent_run: RunOutput | TeamRunOutput, *, all_runs: list[Any]) -> list[Any]:
    """读取某个父 run 直接产生的成员 run，兼容 member_responses 与 session.runs 两种存储形态。"""

    parent_run_id = _coerce_str(getattr(parent_run, "run_id", None))
    result: list[Any] = []
    seen_ids: set[str] = set()

    def append_member_run(candidate: Any) -> None:
        candidate_run_id = _coerce_str(getattr(candidate, "run_id", None))
        if not candidate_run_id or candidate_run_id in seen_ids:
            return
        seen_ids.add(candidate_run_id)
        result.append(candidate)

    for member_run in getattr(parent_run, "member_responses", None) or []:
        append_member_run(member_run)
    if parent_run_id:
        for run in all_runs:
            if _coerce_str(getattr(run, "parent_run_id", None)) == parent_run_id:
                append_member_run(run)
    return result


def _assign_delegate_tool_call_ids(member_runs: list[AgentMemberRunItem], parent_timeline_items: list[AgentTimelineItem]) -> None:
    """按成员 id 和时间顺序，把子 run 关联到父时间线中的 delegate 工具调用。"""

    used_member_runs: set[str] = set()
    delegate_items = [
        item
        for item in parent_timeline_items
        if item.kind == "tool"
        and item.tool is not None
        and item.tool.tool_name in {"delegate_task_to_member", "delegate_task_to_members"}
    ]
    delegate_items.sort(key=lambda item: (item.order_index, item.event_index if item.event_index is not None else 10**9, item.id))

    for delegate_item in delegate_items:
        if delegate_item.tool is None:
            continue
        delegate_key = delegate_item.tool.tool_call_id or delegate_item.id
        requested_member_id = _delegate_requested_member_id(delegate_item.tool.input_payload)
        candidates = [
            member_run
            for member_run in member_runs
            if member_run.parent_run_id == delegate_item.run_id
            and member_run.run_id not in used_member_runs
            and (requested_member_id is None or member_run.agent_id == requested_member_id)
        ]
        candidates.sort(key=_member_run_sort_key)
        if not candidates:
            continue
        if delegate_item.tool.tool_name == "delegate_task_to_member":
            candidates = candidates[:1]
        for member_run in candidates:
            member_run.delegate_tool_call_id = delegate_key
            used_member_runs.add(member_run.run_id)


def _delegate_requested_member_id(input_payload: Any) -> str | None:
    """从 delegate_task_to_member 参数中提取目标成员 id。"""

    if not isinstance(input_payload, dict):
        return None
    return _coerce_str(input_payload.get("member_id"))


def _member_run_sort_key(member_run: AgentMemberRunItem) -> tuple[bool, str, int, str]:
    """按创建时间排序子 run；缺失时间时用首个事件序号和 run_id 兜底。"""

    first_event_index = min(
        [item.event_index for item in member_run.timeline_items if item.event_index is not None],
        default=10**9,
    )
    return (member_run.created_at is None, member_run.created_at or "", first_event_index, member_run.run_id)


def _resolve_run_owner_name(payload: RunOutput | TeamRunOutput | Any) -> str | None:
    """提取 Agno run 所属 Agent/Team 展示名。"""

    owner_name = getattr(payload, "agent_name", None) or getattr(payload, "team_name", None)
    return str(owner_name) if owner_name else None


async def _close_async_iterator(stream: AsyncIterator[Any]) -> None:
    """关闭上游 Agno 流，确保客户端断线后不继续消费模型输出。"""

    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        await aclose()


async def _finish_shielded_cleanup(awaitable: Awaitable[Any]) -> bool:
    """保护断线清理任务；返回清理期间是否收到新的取消信号。"""

    task = asyncio.create_task(awaitable)
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        try:
            await task
        except BaseException:  # noqa: BLE001
            pass
        return True


def _format_sse(event: AgentRunEvent) -> bytes:
    """把统一事件模型编码为标准 SSE 文本块。"""

    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n".encode("utf-8")


def _ensure_sse_bytes(value: Any) -> bytes:
    """把 Agno background stream 返回的 SSE 字符串统一成字节。"""

    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _format_raw_sse_error(*, run_id: str | None, session_id: str | None, message: str, code: str) -> bytes:
    """构造 Agno raw SSE 兼容的错误事件。"""

    payload = {
        "event": "RunError",
        "run_id": run_id,
        "session_id": session_id,
        "content": message,
        "error": message,
        "error_type": code,
    }
    return f"event: RunError\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


def _stream_sse_events(events: AsyncGenerator[AgentRunEvent, None]) -> AsyncGenerator[bytes, None]:
    """把统一事件生成器转为兼容旧接口的 SSE 字节流。"""

    async def generator() -> AsyncGenerator[bytes, None]:
        async for event in events:
            yield _format_sse(event)

    return generator()
