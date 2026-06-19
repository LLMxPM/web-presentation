"""文件功能：承载 AgentSessionFacade 的 Agent 构建、历史预算、run 状态持久化和 scope 映射逻辑。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.requirement import RunRequirement
from agno.run.team import TeamRunOutput
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
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.session_facade_common import (
    AgnoSessionDetail,
    _active_run_payload,
    _coerce_int,
    _coerce_run_status,
    _coerce_str,
    _find_latest_session_run,
    _normalize_run_status_value,
    _normalize_timestamp,
    _resolve_reasoning_content,
    _resolve_run_input_text,
    _resolve_run_owner_id,
    _resolve_session_owner_id,
    _run_latest_event_index,
    _stringify_content,
)
from app.ai.session_facade_models import _ACTIVE_RUN_STATUSES
from app.ai.session_facade_requirements import (
    _apply_resolved_requirement_to_agno_run,
    _extract_pending_requirement,
    _normalize_agno_terminal_run_payload,
)
from app.ai.session_facade_session import (
    _dedupe_scopes,
    _get_session_messages,
    _is_displayable_session_message,
    _merge_history_messages_for_policy,
    _message_attr,
    _scope_from_metadata,
    _session_metadata,
)
from app.ai.tools.disclosure import build_tool_disclosure_context, resolve_unified_tool_scopes
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.agent import AgentActiveRunItem, AgentPendingRequirement, AgentScopeContext, AgentSessionItem
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService


class _SessionFacadeRuntimeMixin:
    """提供运行期构建与持久化方法，依赖主 Facade 的数据库和配置服务。"""

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
        resolved_tool_execution: dict[str, Any] | None = None,
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
        _normalize_agno_terminal_run_payload(
            run,
            status=status,
            resolved_tool_execution=resolved_tool_execution,
        )
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
        resolved_tool_execution: dict[str, Any] | None = None,
    ) -> None:
        """在异常或断线时把运行中占位推进到终态，避免后续会话被永久占用。"""

        await self._set_existing_run_status(
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            status=status,
            content=content,
            resolved_tool_execution=resolved_tool_execution,
        )


    async def _ensure_cancelled_session_messages_preserved(
        self,
        detail: AgnoSessionDetail,
        *,
        agent_id: str,
        run_id: str | None = None,
        fallback_user_message: str | None = None,
        assistant_content: str | None = None,
        reasoning_content: str | None = None,
    ) -> AgnoSessionDetail:
        """懒补偿 cancelled run 的最小可展示消息，确保下一轮能读到已中断上下文。"""

        if not isinstance(detail, (AgentSession, TeamSession)):
            return detail
        changed = False
        for run in list(detail.runs or []):
            current_run_id = _coerce_str(getattr(run, "run_id", None))
            if run_id is not None and current_run_id != run_id:
                continue
            owner_id = _resolve_run_owner_id(run)
            if owner_id is not None and str(owner_id) != agent_id:
                continue
            if getattr(run, "parent_run_id", None) is not None:
                continue
            if not self._preserve_cancelled_run_messages(
                run,
                fallback_user_message=fallback_user_message,
                assistant_content=assistant_content,
                reasoning_content=reasoning_content,
            ):
                continue
            detail.upsert_run(run)
            changed = True
        if changed:
            await asyncio.to_thread(self._ai_db.upsert_session, detail)
        return detail

    @staticmethod

    def _preserve_cancelled_run_messages(
        run: RunOutput | TeamRunOutput,
        *,
        fallback_user_message: str | None,
        assistant_content: str | None,
        reasoning_content: str | None,
    ) -> bool:
        """从 cancelled run 的输入和输出字段补齐 messages，返回是否修改。"""

        if _coerce_run_status(getattr(run, "status", None)) != RunStatus.cancelled:
            return False

        original_messages = list(getattr(run, "messages", None) or [])
        displayable_messages = [
            message
            for message in original_messages
            if _is_displayable_session_message(message)
        ]
        has_user_message = any(str(_message_attr(message, "role", "") or "") == "user" for message in displayable_messages)
        has_assistant_message = any(
            str(_message_attr(message, "role", "") or "") == "assistant"
            and (_stringify_content(_message_attr(message, "content", None)) or _resolve_reasoning_content(message))
            for message in displayable_messages
        )
        if has_user_message and has_assistant_message:
            return False

        user_content = _resolve_run_input_text(run) or (fallback_user_message or "").strip() or None
        assistant_text = (assistant_content or "").strip() or _stringify_content(getattr(run, "content", None)).strip() or None
        reasoning_text = (reasoning_content or "").strip() or (_resolve_reasoning_content(run) or "").strip() or None
        next_messages: list[Any] = []
        added_message = False
        if user_content and not has_user_message:
            next_messages.append(
                Message(
                    role="user",
                    content=user_content,
                    created_at=_coerce_int(getattr(run, "created_at", None)) or int(datetime.now(tz=UTC).timestamp()),
                )
            )
            added_message = True
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
            added_message = True
        if not added_message:
            return False

        run.messages = next_messages
        run.status = RunStatus.cancelled
        if assistant_text is not None:
            run.content = assistant_text
        metadata = dict(getattr(run, "metadata", None) or {})
        metadata["user_cancel_preserved"] = True
        run.metadata = metadata
        _normalize_agno_terminal_run_payload(run, status=RunStatus.cancelled)
        return True


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
            return
        if not self._preserve_cancelled_run_messages(
            run,
            fallback_user_message=fallback_user_message,
            assistant_content=assistant_content,
            reasoning_content=reasoning_content,
        ):
            return
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
