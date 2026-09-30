"""文件功能：基于平台运行态与 Pydantic AI 的 Agent 会话 BFF Facade。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import FastAPI
from pydantic_ai import DeferredToolResults, ToolDenied
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.message_history import (
    build_context_limit_processor,
    build_context_status_item,
    build_history_budget,
    rebuild_agent_message_history,
    replace_agent_image_refs_with_placeholders,
)
from app.ai.image_refs import build_agent_image_ref
from app.ai.platform_runtime import (
    ACTIVE_RUN_STATUSES,
    PlatformAgentRuntimeStore,
    new_session_id,
    stream_replay_then_subscribe,
)
from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.ai.pydantic_runner import PydanticAgentRunner
from app.ai.pydantic_tools import build_pydantic_tools
from app.ai.run_write_fence import AgentRunWriteFence
from app.ai.run_write_fence import AgentRunWriteFenceLost
from app.ai.process_liveness import bind_ordinary_run_owner
from app.ai.agent.runtime_context import AgentRuntimeContext, prepend_runtime_context_to_user_message
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.visual_tool_runtime import resolve_visual_tool_runtime
from app.ai.run_errors import build_agent_error_log_extra, normalize_agent_run_exception
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentToolCall
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_llm import AiLlmConfig
from app.models.ai_image_generation import AiImageGenerationJob
from app.core.time_utils import utc_now
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentCancelRunResponse,
    AgentContextStatusItem,
    AgentMessageItem,
    AgentRunEvent,
    AgentRunStartResponse,
    AgentFocusRequest,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
)
from app.schemas.model_config import ReasoningPolicy
from app.services.agent_work_scope_service import AgentWorkScopeService
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.ai_llm_service import AiLlmService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.services.auth_service import AuthContext
from app.services.image_generation.contracts import ImageModelSpec

logger = logging.getLogger(__name__)

from app.ai.session_facade_helpers import (
    _apply_llm_snapshot,
    _build_continue_message_history,
    _build_deferred_results,
    _build_user_prompt,
    _consume_interrupted_cleanup_result,
    _error_event,
    _extract_session_llm_config_id,
    _feedback_questions,
    _format_user_feedback_result,
    _is_user_feedback_tool,
    _map_store_error,
    _matches_existing_run_request,
    _scope_from_run,
)
from app.ai.session_facade_stream import AgentRunStreamMixin


class AgentSessionFacade(AgentRunStreamMixin):
    """封装 Editor Agent 会话、运行、流式输出与恢复逻辑。"""

    _run_locks: dict[tuple[str, str], asyncio.Lock] = {}

    def __init__(self, *, app: FastAPI, current: AuthContext, session: AsyncSession) -> None:
        """保存 FastAPI app、当前用户与数据库会话。"""

        self._app = app
        self._current = current
        self._session = session
        self._store = PlatformAgentRuntimeStore(session, user_id=current.user.id)
        self._model_resolver = PydanticLlmModelResolver()
        self._agent_config_service = AiAgentConfigService(session, user_id=current.user.id)

    async def list_sessions(
        self,
        *,
        agent_id: str,
        workspace_id: int,
    ) -> list[AgentSessionItem]:
        """列出当前用户在指定工作空间下的智能体会话。"""

        await AgentWorkScopeService(self._session, user_id=self._current.user.id).require_workspace_access(workspace_id)
        return await self._store.list_sessions(agent_id=agent_id, workspace_id=workspace_id)

    async def create_session(
        self,
        *,
        agent_id: str,
        workspace_id: int,
        focus_mode: str = "follow_route",
        pinned_project_id: int | None = None,
        work_scope_mode: str = "workspace",
        allowed_project_ids: list[int] | None = None,
        session_name: str | None = None,
        llm_config_id: int | None = None,
    ) -> AgentSessionItem:
        """创建平台智能体会话。"""

        descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
        pinned_project_id, normalized_project_ids = await AgentWorkScopeService(
            self._session,
            user_id=self._current.user.id,
        ).validate_preferences(
            workspace_id=workspace_id,
            focus_mode=focus_mode,
            pinned_project_id=pinned_project_id,
            work_scope_mode=work_scope_mode,
            allowed_project_ids=list(allowed_project_ids or []),
        )
        llm_service = self._llm_service()
        selection_kind: Literal["explicit_config", "slot_binding"] = "explicit_config" if llm_config_id else "slot_binding"
        llm_config = (
            await llm_service.get_selectable_active_config_or_raise(llm_config_id)
            if llm_config_id is not None
            else await llm_service.get_bound_config_or_raise(descriptor.llm_slot or "")
        )
        llm_service._validate_slot_model_type(descriptor.llm_slot or "", llm_config)
        return await self._store.create_session(
            session_id=new_session_id(),
            agent_id=agent_id,
            session_name=session_name,
            workspace_id=workspace_id,
            focus_mode=focus_mode,
            pinned_project_id=pinned_project_id,
            work_scope_mode=work_scope_mode,
            allowed_project_ids=normalized_project_ids,
            llm_metadata=llm_service.build_session_llm_metadata(llm_config, selection_kind=selection_kind),
        )

    async def update_session_preferences(
        self,
        *,
        session_id: str,
        agent_id: str,
        workspace_id: int,
        focus_mode: str,
        pinned_project_id: int | None,
        work_scope_mode: str,
        allowed_project_ids: list[int],
    ) -> AgentSessionItem:
        """校验并更新下一轮 Run 使用的会话偏好。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, workspace_id=workspace_id)
        pinned_project_id, normalized_ids = await AgentWorkScopeService(
            self._session,
            user_id=self._current.user.id,
        ).validate_preferences(
            workspace_id=workspace_id,
            focus_mode=focus_mode,
            pinned_project_id=pinned_project_id,
            work_scope_mode=work_scope_mode,
            allowed_project_ids=allowed_project_ids,
        )
        return await self._store.update_session_preferences(
            session_id=session_id,
            agent_id=agent_id,
            focus_mode=focus_mode,
            pinned_project_id=pinned_project_id,
            work_scope_mode=work_scope_mode,
            allowed_project_ids=normalized_ids,
        )

    async def resolve_run_focus(
        self,
        *,
        session_id: str,
        agent_id: str,
        workspace_id: int,
        requested: AgentFocusRequest,
    ) -> AgentScopeContext:
        """读取会话最新偏好并解析一次不可变 Run 焦点。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, workspace_id=workspace_id)
        model = await self._store.require_session(session_id=session_id, agent_id=agent_id)
        return await AgentWorkScopeService(self._session, user_id=self._current.user.id).resolve_run_focus(
            session_model=model,
            requested=requested,
        )

    async def rename_session(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        session_name: str | None,
        autogenerate: bool,
        runtime_context: Any,
    ) -> AgentSessionItem:
        """重命名会话；自动命名时采用最近助手消息或页面标题兜底。"""

        _ = scope
        if autogenerate and not session_name:
            messages = await self._store.list_messages(session_id=session_id, agent_id=agent_id)
            latest_assistant = next((item for item in reversed(messages) if item.role == "assistant" and item.content.strip()), None)
            session_name = (latest_assistant.content.strip()[:32] if latest_assistant else None) or getattr(runtime_context, "page_title", None)
        if not session_name:
            raise AppException(status_code=400, code="AI_SESSION_NAME_REQUIRED", detail="会话名称不能为空。")
        try:
            return await self._store.rename_session(session_id=session_id, agent_id=agent_id, session_name=session_name)
        except ValueError as exc:
            raise _map_store_error(exc) from exc

    async def get_messages(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> list[AgentMessageItem]:
        """读取会话消息。"""

        _ = scope
        try:
            return await self._store.list_messages(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            raise _map_store_error(exc) from exc

    async def ensure_session_access(
        self,
        *,
        session_id: str,
        agent_id: str,
        workspace_id: int | None = None,
        scope: AgentScopeContext | None = None,
    ) -> AgentSessionItem:
        """校验当前用户可以访问会话，并返回会话项。"""

        resolved_workspace_id = workspace_id if workspace_id is not None else (scope.workspace_id if scope else None)
        if resolved_workspace_id is None:
            raise AppException(status_code=400, code="AI_SESSION_WORKSPACE_REQUIRED", detail="缺少会话工作空间。")
        try:
            model = await self._store.require_session(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            raise _map_store_error(exc) from exc
        if model.workspace_id != resolved_workspace_id:
            raise AppException(status_code=403, code="AI_SESSION_SCOPE_MISMATCH", detail="会话范围与当前请求不一致。")
        return self._store.map_session_item(model)

    async def get_runtime_snapshot(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: Any,
    ) -> AgentSessionRuntimeSnapshot:
        """返回平台运行态快照。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        snapshot = await self._store.get_runtime_snapshot(
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
        )
        snapshot.context_status = await self.get_context_status(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
        )
        return snapshot

    async def get_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: Any,
    ) -> AgentActiveRunItem | None:
        """读取当前会话非终态运行。"""

        _ = runtime_context
        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        run_model = await self._store.get_active_run_model(session_id=session_id, agent_id=agent_id)
        return self._store.map_active_run(run_model)

    async def get_context_status(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: Any,
    ) -> AgentContextStatusItem:
        """读取当前会话上下文状态；有活跃 run 时一并纳入其已落盘历史，避免运行中读数回退。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        try:
            descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
            llm_config = await self.resolve_session_llm_config(
                session_id=session_id,
                agent_id=agent_id,
                slot=descriptor.llm_slot or "",
            )
            active_run_model = await self._store.get_active_run_model(session_id=session_id, agent_id=agent_id)
            rebuilt_history = await rebuild_agent_message_history(
                session=self._session,
                user_id=self._current.user.id,
                session_id=session_id,
                agent_id=agent_id,
                include_run_id=active_run_model.run_id if active_run_model is not None else None,
                hydrate_images=False,
            )
            return build_context_status_item(
                session_id=session_id,
                agent_id=agent_id,
                budget=build_history_budget(llm_config, runtime_context=runtime_context),
                rebuilt_history=rebuilt_history,
            )
        except AppException:
            return self._store.build_context_status(session_id=session_id, agent_id=agent_id, runtime_context=runtime_context)

    async def reserve_run_slot(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
    ) -> asyncio.Lock:
        """为指定 session 预占运行锁。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        lock = self._get_lock(session_id=session_id, agent_id=agent_id)
        if lock.locked():
            raise AppException(status_code=409, code="AI_SESSION_RUN_ACTIVE", detail="当前会话已有运行中的智能体任务，请等待完成后再发送新消息。")
        await lock.acquire()
        try:
            await self._store.ensure_no_active_run(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            lock.release()
            raise _map_store_error(exc) from exc
        return lock

    async def reserve_continue_slot(self, *, session_id: str, agent_id: str) -> asyncio.Lock:
        """为 paused Run 的继续阶段预留进程内槽位，阻止重复 HITL 提交。"""

        lock = self._get_lock(session_id=session_id, agent_id=agent_id)
        if lock.locked():
            raise AppException(status_code=409, code="AI_SESSION_RUN_ACTIVE", detail="当前会话已有运行中的智能体任务。")
        await lock.acquire()
        return lock

    async def prepare_background_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: Any,
        image_attachment_ids: list[int] | None,
        run_id: str,
        llm_config_id: int | None,
        reasoning: ReasoningPolicy | None = None,
    ) -> tuple[AgentRunStartResponse, bool]:
        """串行化同一会话的 Run 创建，避免并发请求越过 active-run 校验。"""

        lock = self._get_lock(session_id=session_id, agent_id=agent_id)
        async with lock:
            return await self._prepare_background_run_unlocked(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                message=message,
                runtime_context=runtime_context,
                image_attachment_ids=image_attachment_ids,
                run_id=run_id,
                llm_config_id=llm_config_id,
                reasoning=reasoning,
            )

    async def _prepare_background_run_unlocked(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: Any,
        image_attachment_ids: list[int] | None,
        run_id: str,
        llm_config_id: int | None,
        reasoning: ReasoningPolicy | None = None,
    ) -> tuple[AgentRunStartResponse, bool]:
        """持久化新 Run；相同 run_id 的同请求按幂等成功返回。"""

        existing = await self._session.get(AiAgentRun, run_id)
        if existing is not None:
            if not _matches_existing_run_request(
                existing,
                user_id=self._current.user.id,
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                message=message,
                image_attachment_ids=image_attachment_ids or [],
                requested_llm_config_id=llm_config_id,
                requested_reasoning=reasoning or ReasoningPolicy(),
            ):
                raise AppException(status_code=409, code="AI_RUN_ID_CONFLICT", detail="run_id 已被其它请求使用。")
            return AgentRunStartResponse(
                run_id=existing.run_id,
                session_id=existing.session_id,
                status="running",
                event_index=-1,
            ), False

        descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
        llm_config = await self.resolve_new_run_llm_config(
            session_id=session_id,
            agent_id=agent_id,
            slot=descriptor.llm_slot or "",
            requested_llm_config_id=llm_config_id,
        )
        llm_service = self._llm_service()
        llm_service.apply_run_reasoning_policy(
            llm_config,
            slot=descriptor.llm_slot or "",
            reasoning=reasoning or ReasoningPolicy(),
        )
        selection_kind: Literal["explicit_config", "run_override"] = (
            "run_override" if llm_config_id is not None else "explicit_config"
        )
        image_ids = list(image_attachment_ids or [])
        await self._resolve_run_images(
            session_id=session_id,
            scope=scope,
            image_attachment_ids=image_ids,
        )
        run_start = await self._store.start_run(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            run_id=run_id,
            message=message,
            image_attachment_ids=image_ids,
            llm_config_id=llm_config.id,
            llm_metadata=llm_service.build_run_llm_snapshot(llm_config, selection_kind=selection_kind),
            session_llm_metadata=llm_service.build_session_llm_metadata(llm_config, selection_kind=selection_kind),
            runtime_context=runtime_context,
        )
        await self._mark_images_used(
            session_id=session_id,
            scope=scope,
            image_attachment_ids=image_ids,
            run_id=run_id,
        )
        return AgentRunStartResponse(
            run_id=run_start.run_model.run_id,
            session_id=session_id,
            status="running",
            event_index=-1,
        ), True

    async def execute_background_run(self, *, run_id: str, runtime_context: Any) -> None:
        """使用独立数据库会话执行已持久化的新 Run，所有产物只写平台事件表。"""

        run_model = await self._session.get(AiAgentRun, run_id)
        if run_model is None or run_model.user_id != self._current.user.id:
            return
        if run_model.status not in {"pending", "running", "cancelling"}:
            return
        try:
            execution_fence = await bind_ordinary_run_owner(self._session, run_model)
            self._store = PlatformAgentRuntimeStore(
                self._session, user_id=self._current.user.id, write_fence=execution_fence,
            )
            descriptor = self._app.state.ai_registry.get_descriptor(run_model.agent_id)
            llm_config = await self.resolve_run_llm_config(
                run_model=run_model,
                slot=descriptor.llm_slot or "",
            )
            previous_history = await rebuild_agent_message_history(
                session=self._session,
                user_id=self._current.user.id,
                session_id=run_model.session_id,
                agent_id=run_model.agent_id,
                exclude_run_id=run_model.run_id,
                hydrate_images=False,
            )
            history_budget = build_history_budget(llm_config, runtime_context=runtime_context)
            context_processor = build_context_limit_processor(
                session=self._session,
                user_id=self._current.user.id,
                session_id=run_model.session_id,
                agent_id=run_model.agent_id,
                budget=history_budget,
                rebuilt_history=previous_history,
            )
            run_input = dict(run_model.input_payload_json or {})
            image_attachments = await self._resolve_run_images(
                session_id=run_model.session_id,
                scope=_scope_from_run(run_model),
                image_attachment_ids=list(run_input.get("image_attachment_ids") or []),
            )
            agent_config = await self._agent_config_service.get_effective_runtime_config(run_model.agent_id)
            scope = _scope_from_run(run_model)
            visual_unavailable, image_generation_model, image_generation_config_id = (
                await self._resolve_visual_tool_runtime(run_model.agent_id)
            )
            tools, deps = build_pydantic_tools(
                agent_id=run_model.agent_id,
                session_factory=get_session_factory(),
                runtime_config=agent_config,
                current=self._current,
                scope=scope,
                session_id=run_model.session_id,
                run_id=run_model.run_id,
                supports_image_input=bool(llm_config.supports_image_input),
                work_scope_mode=runtime_context.work_scope_mode,
                allowed_project_ids=runtime_context.allowed_project_ids,
                focus_version=runtime_context.focus_version,
                unavailable_group_keys=visual_unavailable,
                image_generation_model=image_generation_model,
                image_generation_config_id=image_generation_config_id,
                write_fence=execution_fence,
            )
            await PydanticAgentRunner(self._store).run_to_store(
                run_model=run_model,
                agent_id=run_model.agent_id,
                model=self._model_resolver.resolve_model(llm_config),
                model_settings=self._model_resolver.resolve_model_settings(llm_config),
                runtime_context=runtime_context,
                message=_build_user_prompt(str(run_input.get("message") or ""), image_attachments),
                include_runtime_context=True,
                agent_config=agent_config,
                tools=tools,
                deps=deps,
                message_history=previous_history.messages or None,
                message_image_refs=[build_agent_image_ref(item) for item in image_attachments],
                context_budget=history_budget,
                context_processor=context_processor,
            )
        except asyncio.CancelledError:
            await self._mark_interrupted_run_terminal(
                run_model,
                fallback_code="AI_RUN_PROCESS_STOPPED",
                fallback_message="Backend 已停止，当前智能体运行未继续执行。",
            )
            raise
        except AgentRunWriteFenceLost:
            await self._session.rollback()
            return
        except AppException as exc:
            await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code=exc.code,
                error_message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            failure = normalize_agent_run_exception(exc, fallback_code="AI_RUN_SETUP_FAILED")
            logger.exception(
                "Agent background run setup failed",
                extra=build_agent_error_log_extra(
                    exc,
                    event="ai.agent_run.background_setup_exception",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    agent_id=run_model.agent_id,
                    error_code=failure.code,
                    user_error_message=failure.message,
                    raw_error_message=failure.raw_message,
                ),
            )
            await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code=failure.code,
                error_message=failure.message,
            )

    async def fail_background_run_start(self, *, run_id: str, code: str, message: str) -> None:
        """后台任务未能登记时立即释放已持久化的 active Run。"""

        run_model = await self._session.get(AiAgentRun, run_id)
        if run_model is None or run_model.user_id != self._current.user.id:
            return
        if run_model.status not in {"pending", "running", "cancelling"}:
            return
        await self._store.mark_terminal(
            run_model,
            status="failed",
            error_code=code,
            error_message=message,
        )

    async def resolve_session_llm_config(
        self,
        *,
        session_id: str,
        agent_id: str,
        slot: str,
    ) -> AiLlmConfig:
        """解析当前会话运行模型；新会话优先使用 metadata 固化配置，历史会话回退槽位绑定。"""

        try:
            session_model = await self._store.require_session(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            raise _map_store_error(exc) from exc

        llm_service = self._llm_service()
        config_id = _extract_session_llm_config_id(session_model.metadata_json)
        if config_id is not None:
            return await llm_service.get_selectable_active_config_or_raise(config_id)
        return await llm_service.get_bound_config_or_raise(slot)

    async def resolve_new_run_llm_config(
        self,
        *,
        session_id: str,
        agent_id: str,
        slot: str,
        requested_llm_config_id: int | None,
    ) -> AiLlmConfig:
        """解析新 run 的模型；显式选择优先，否则沿用会话默认。"""

        llm_service = self._llm_service()
        if requested_llm_config_id is not None:
            config = await llm_service.get_selectable_active_config_or_raise(requested_llm_config_id)
            llm_service._validate_slot_model_type(slot, config)
            return config
        config = await self.resolve_session_llm_config(
            session_id=session_id,
            agent_id=agent_id,
            slot=slot,
        )
        llm_service._validate_slot_model_type(slot, config)
        return config

    async def resolve_run_llm_config(
        self,
        *,
        run_model: AiAgentRun,
        slot: str,
    ) -> AiLlmConfig:
        """恢复既有 run 启动时选择的模型；历史 run 才回退会话默认。"""

        if run_model.llm_config_id is None:
            return await self.resolve_session_llm_config(
                session_id=run_model.session_id,
                agent_id=run_model.agent_id,
                slot=slot,
            )
        llm_service = self._llm_service()
        config = await llm_service.get_selectable_active_config_or_raise(run_model.llm_config_id)
        llm_service._validate_slot_model_type(slot, config)
        snapshot = run_model.llm_config_snapshot_json
        if not isinstance(snapshot, dict):
            return config
        return _apply_llm_snapshot(config, snapshot)

    def _llm_service(self) -> AiLlmService:
        """创建带当前用户身份的大模型服务实例。"""

        return AiLlmService(
            self._session,
            user_id=self._current.user.id,
            user_role=self._current.user.role,
        )

    async def _resolve_unavailable_visual_tool_groups(
        self,
        agent_id: str,
        *,
        retained_tool_names: frozenset[str] = frozenset(),
    ) -> frozenset[str]:
        """按视觉槽位独立裁剪工具；续跑时保留已有 deferred 调用所需定义。"""

        unavailable, _, _ = await self._resolve_visual_tool_runtime(
            agent_id,
            retained_tool_names=retained_tool_names,
        )
        return unavailable

    async def _resolve_visual_tool_runtime(
        self,
        agent_id: str,
        *,
        retained_tool_names: frozenset[str] = frozenset(),
    ) -> tuple[frozenset[str], ImageModelSpec | None, int | None]:
        """一次解析视觉工具可用性及图片模型能力，供本轮 Schema 与执行配置共用。"""

        return await resolve_visual_tool_runtime(
            llm_service=self._llm_service(),
            agent_id=agent_id,
            retained_tool_names=retained_tool_names,
        )

    async def _mark_interrupted_run_terminal(
        self,
        run_model: Any | None,
        *,
        fallback_code: str,
        fallback_message: str,
    ) -> None:
        """流式响应被取消时用独立会话收敛 run，避免复用已取消事务。"""

        if run_model is None:
            return
        run_id = str(getattr(run_model, "run_id", "") or "").strip()
        if not run_id:
            return
        cleanup_task = asyncio.create_task(
            self._mark_interrupted_run_terminal_in_new_session(
                run_id=run_id,
                fallback_code=fallback_code,
                fallback_message=fallback_message,
            )
        )
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            cleanup_task.add_done_callback(_consume_interrupted_cleanup_result)
            raise
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark interrupted agent run terminal",
                extra={
                    "run_id": run_id,
                    "fallback_code": fallback_code,
                },
            )

    async def _mark_interrupted_run_terminal_in_new_session(
        self,
        *,
        run_id: str,
        fallback_code: str,
        fallback_message: str,
    ) -> None:
        """在与请求生命周期隔离的新事务中读取并写入中断终态。"""

        async with get_session_factory()() as cleanup_session:
            result = await cleanup_session.execute(
                select(AiAgentRun).where(
                    AiAgentRun.run_id == run_id,
                    AiAgentRun.user_id == self._current.user.id,
                )
            )
            cleanup_run = result.scalar_one_or_none()
            if cleanup_run is None:
                return
            current_status = cleanup_run.status
            # external_job 已由持久化队列持有租约；浏览器断开 SSE 不能取消其页面写入。
            if current_status not in ACTIVE_RUN_STATUSES or current_status in {"paused", "waiting_external"}:
                return
            cleanup_store = PlatformAgentRuntimeStore(cleanup_session, user_id=self._current.user.id)
            if current_status == "cancelling":
                await cleanup_store.mark_terminal(cleanup_run, status="cancelled", content="用户停止了当前运行。")
                return
            await cleanup_store.mark_terminal(
                cleanup_run,
                status="failed",
                error_code=fallback_code,
                error_message=fallback_message,
            )

    def _get_lock(self, *, session_id: str, agent_id: str) -> asyncio.Lock:
        """读取或创建 session 级运行锁。"""

        key = (session_id, agent_id)
        if key not in self._run_locks:
            self._run_locks[key] = asyncio.Lock()
        return self._run_locks[key]

    async def _resolve_run_images(
        self,
        *,
        session_id: str,
        scope: AgentScopeContext,
        image_attachment_ids: list[int],
    ) -> list[AiAgentImageAttachment]:
        """只校验本轮附件并返回轻量元数据，内容模型永不读取图片字节。"""

        if not image_attachment_ids:
            return []
        service = AgentImageAttachmentService(self._session, user_id=self._current.user.id)
        return await service.validate_attachments_for_run(
            workspace_id=scope.workspace_id,
            session_id=session_id,
            attachment_ids=image_attachment_ids,
        )

    async def _mark_images_used(
        self,
        *,
        session_id: str,
        scope: AgentScopeContext,
        image_attachment_ids: list[int],
        run_id: str,
    ) -> None:
        """把本轮图片附件标记到 run，供消息历史和待发送列表展示。"""

        if not image_attachment_ids:
            return
        service = AgentImageAttachmentService(self._session, user_id=self._current.user.id)
        attachments = await service.validate_attachments_for_run(
            workspace_id=scope.workspace_id,
            session_id=session_id,
            attachment_ids=image_attachment_ids,
        )
        await service.mark_run_id(attachments=attachments, run_id=run_id, operator_id=self._current.user.id)


# ---------------------------------------------------------------------------
# 兼容再导出：既有测试/调用方继续 `from app.ai.session_facade_pydantic import ...`
# ---------------------------------------------------------------------------

from app.ai.session_facade_helpers import (  # noqa: E402
    _apply_llm_snapshot,
    _build_continue_message_history,
    _build_deferred_results,
    _build_user_prompt,
    _consume_interrupted_cleanup_result,
    _error_event,
    _extract_session_llm_config_id,
    _feedback_questions,
    _format_user_feedback_result,
    _is_user_feedback_tool,
    _map_store_error,
    _matches_existing_run_request,
    _scope_from_run,
)
