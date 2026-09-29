"""文件功能：Agent 会话门面的 SSE 流式启动、续跑确认与外部任务回写协作方法。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic_ai import DeferredToolResults
from sqlalchemy import select, update

from app.ai.image_refs import build_agent_image_ref
from app.ai.message_history import (
    build_context_limit_processor,
    build_history_budget,
    rebuild_agent_message_history,
)
from app.ai.platform_runtime import (
    PlatformAgentRuntimeStore,
    stream_replay_then_subscribe,
)
from app.ai.pydantic_runner import PydanticAgentRunner
from app.ai.pydantic_tools import build_pydantic_tools
from app.ai.run_errors import build_agent_error_log_extra, normalize_agent_run_exception
from app.ai.run_write_fence import AgentRunWriteFence
from app.ai.runtime_context_builder import build_agent_runtime_context
from app.ai.session_facade_helpers import (
    _build_continue_message_history,
    _build_deferred_results,
    _build_user_prompt,
    _error_event,
    _hydrate_continue_message_history_json,
    _map_store_error,
    _scope_from_run,
)
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentToolCall
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_image_generation import AiImageGenerationJob
from app.schemas.agent import AgentCancelRunResponse, AgentRunEvent, AgentScopeContext
from app.schemas.model_config import ReasoningPolicy

logger = logging.getLogger(__name__)


class AgentRunStreamMixin:
    """承载会话门面的 SSE 生成、取消与外部任务续跑；假定宿主提供 _store/_app/_current/_session。"""

    def run_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        message: str,
        runtime_context: Any,
        reserved_lock: asyncio.Lock | None = None,
        image_attachment_ids: list[int] | None = None,
        run_id: str | None = None,
        llm_config_id: int | None = None,
        reasoning: ReasoningPolicy | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """启动 Pydantic AI run 并输出平台 SSE；函数名保留以兼容路由。"""

        async def generator() -> AsyncGenerator[bytes, None]:
            lock = reserved_lock or self._get_lock(session_id=session_id, agent_id=agent_id)
            acquired = reserved_lock is not None
            run_model = None
            if not acquired:
                if lock.locked():
                    yield _error_event(session_id=session_id, run_id=run_id, code="AI_SESSION_RUN_ACTIVE", message="当前会话已有运行中的智能体任务。")
                    return
                await lock.acquire()
                acquired = True
            try:
                effective_run_id = run_id or f"run-{asyncio.get_running_loop().time():.0f}"
                descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
                llm_config = await self.resolve_new_run_llm_config(
                    session_id=session_id,
                    agent_id=agent_id,
                    slot=descriptor.llm_slot or "",
                    requested_llm_config_id=llm_config_id,
                )
                selection_kind: Literal["explicit_config", "run_override"] = (
                    "run_override" if llm_config_id is not None else "explicit_config"
                )
                llm_service = self._llm_service()
                llm_service.apply_run_reasoning_policy(
                    llm_config,
                    slot=descriptor.llm_slot or "",
                    reasoning=reasoning or ReasoningPolicy(),
                )
                llm_metadata = llm_service.build_run_llm_snapshot(
                    llm_config,
                    selection_kind=selection_kind,
                )
                session_llm_metadata = llm_service.build_session_llm_metadata(
                    llm_config,
                    selection_kind=selection_kind,
                )
                rebuilt_history = await rebuild_agent_message_history(
                    session=self._session,
                    user_id=self._current.user.id,
                    session_id=session_id,
                    agent_id=agent_id,
                    hydrate_images=False,
                )
                history_budget = build_history_budget(llm_config, runtime_context=runtime_context)
                context_processor = build_context_limit_processor(
                    session=self._session,
                    user_id=self._current.user.id,
                    session_id=session_id,
                    agent_id=agent_id,
                    budget=history_budget,
                    rebuilt_history=rebuilt_history,
                )
                image_attachments = await self._resolve_run_images(
                    session_id=session_id,
                    scope=scope,
                    image_attachment_ids=image_attachment_ids or [],
                )
                run_start = await self._store.start_run(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    run_id=effective_run_id,
                    message=message,
                    image_attachment_ids=image_attachment_ids or [],
                    llm_config_id=llm_config.id,
                    llm_metadata=llm_metadata,
                    session_llm_metadata=session_llm_metadata,
                    runtime_context=runtime_context,
                )
                run_model = run_start.run_model
                await self._mark_images_used(
                    session_id=session_id,
                    scope=scope,
                    image_attachment_ids=image_attachment_ids or [],
                    run_id=run_start.run_model.run_id,
                )
                model = self._model_resolver.resolve_model(llm_config)
                model_settings = self._model_resolver.resolve_model_settings(llm_config)
                agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
                visual_unavailable, image_generation_model, image_generation_config_id = (
                    await self._resolve_visual_tool_runtime(agent_id)
                )
                tools, deps = build_pydantic_tools(
                    agent_id=agent_id,
                    session_factory=get_session_factory(),
                    runtime_config=agent_config,
                    current=self._current,
                    scope=scope,
                    session_id=session_id,
                    run_id=run_start.run_model.run_id,
                    supports_image_input=bool(llm_config.supports_image_input),
                    work_scope_mode=runtime_context.work_scope_mode,
                    allowed_project_ids=runtime_context.allowed_project_ids,
                    focus_version=runtime_context.focus_version,
                    unavailable_group_keys=visual_unavailable,
                    image_generation_model=image_generation_model,
                    image_generation_config_id=image_generation_config_id,
                )
                runner = PydanticAgentRunner(self._store)
                async for chunk in runner.stream_run(
                    run_model=run_start.run_model,
                    agent_id=agent_id,
                    model=model,
                    model_settings=model_settings,
                    runtime_context=runtime_context,
                    message=_build_user_prompt(message, image_attachments),
                    include_runtime_context=True,
                    agent_config=agent_config,
                    tools=tools,
                    deps=deps,
                    message_history=rebuilt_history.messages or None,
                    message_image_refs=[build_agent_image_ref(item) for item in image_attachments],
                    context_budget=history_budget,
                    context_processor=context_processor,
                ):
                    yield chunk
            except asyncio.CancelledError:
                await self._mark_interrupted_run_terminal(
                    run_model,
                    fallback_code="AI_RUN_STREAM_INTERRUPTED",
                    fallback_message="智能体连接中断，运行已停止。",
                )
                raise
            except AppException as exc:
                logger.warning(
                    "Agent run setup stopped by application error",
                    extra=build_agent_error_log_extra(
                        exc,
                        event="ai.agent_run.setup_app_error",
                        run_id=run_model.run_id if run_model is not None else run_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        error_code=exc.code,
                        user_error_message=exc.detail,
                    ),
                )
                if run_model is not None:
                    from app.ai.platform_runtime import encode_sse_event

                    event = await self._store.mark_terminal(
                        run_model,
                        status="failed",
                        error_code=exc.code,
                        error_message=exc.detail,
                    )
                    yield encode_sse_event(event)
                else:
                    yield _error_event(session_id=session_id, run_id=run_id, code=exc.code, message=exc.detail)
            except Exception as exc:  # noqa: BLE001
                failure = normalize_agent_run_exception(
                    exc,
                    fallback_code="AI_RUN_SETUP_FAILED",
                    fallback_message="智能体运行初始化失败，请检查模型配置后重试。",
                )
                logger.exception(
                    "Agent run setup failed",
                    extra=build_agent_error_log_extra(
                        exc,
                        event="ai.agent_run.setup_exception",
                        run_id=run_model.run_id if run_model is not None else run_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        error_code=failure.code,
                        user_error_message=failure.message,
                        raw_error_message=failure.raw_message,
                    ),
                )
                if run_model is not None:
                    from app.ai.platform_runtime import encode_sse_event

                    event = await self._store.mark_terminal(
                        run_model,
                        status="failed",
                        error_code=failure.code,
                        error_message=failure.message,
                    )
                    yield encode_sse_event(event)
                else:
                    yield _error_event(session_id=session_id, run_id=run_id, code=failure.code, message=failure.message)
            finally:
                if acquired and lock.locked():
                    lock.release()

        return generator()

    async def resume_raw_sse(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        event_index: int | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """从平台事件表按 event_index 回放并订阅实时事件。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        async for chunk in stream_replay_then_subscribe(
            store=self._store,
            run_id=run_id,
            event_index=event_index if event_index is not None else -1,
        ):
            yield chunk

    async def cancel_active_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        force: bool = False,
        tool_call_id: str | None = None,
    ) -> AgentCancelRunResponse:
        """标记当前运行为取消中；工具侧会读取平台取消标记。"""

        _ = tool_call_id
        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        try:
            if force:
                run_model = await self._store.force_cancel(session_id=session_id, agent_id=agent_id)
            else:
                run_model = await self._store.request_cancel(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            raise _map_store_error(exc) from exc
        cancelled_at = utc_now()
        await self._session.execute(
            update(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.run_id == run_model.run_id,
                AiImageGenerationJob.status == "pending",
            )
            .values(
                status="cancelled",
                cancel_requested_at=cancelled_at,
                finished_at=cancelled_at,
                progress_json={"phase": "error", "message": "图片任务已取消。"},
            )
        )
        await self._session.execute(
            update(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.run_id == run_model.run_id,
                AiImageGenerationJob.status.in_(("running", "waiting_provider")),
            )
            .values(cancel_requested_at=cancelled_at)
        )
        await self._session.execute(
            update(AiAgentExternalTask)
            .where(
                AiAgentExternalTask.run_id == run_model.run_id,
                AiAgentExternalTask.status == "pending",
            )
            .values(
                status="cancelled",
                cancel_requested_at=cancelled_at,
                finished_at=cancelled_at,
            )
        )
        await self._session.execute(
            update(AiAgentExternalTask)
            .where(
                AiAgentExternalTask.run_id == run_model.run_id,
                AiAgentExternalTask.status.in_(("running", "waiting_provider")),
            )
            .values(cancel_requested_at=cancelled_at)
        )
        await self._session.execute(
            update(AiAgentExternalBatch)
            .where(
                AiAgentExternalBatch.run_id == run_model.run_id,
                AiAgentExternalBatch.status.in_(("collecting", "waiting_tasks", "ready")),
            )
            .values(status="cancelled", finished_at=cancelled_at)
        )
        await self._session.execute(
            update(AiAgentRequirement)
            .where(
                AiAgentRequirement.run_id == run_model.run_id,
                AiAgentRequirement.status.in_(("pending", "resolving")),
            )
            .values(status="cancelled", resolved_at=cancelled_at)
        )
        await self._session.execute(
            update(AiAgentToolCall)
            .where(
                AiAgentToolCall.run_id == run_model.run_id,
                AiAgentToolCall.status.in_(("running", "waiting_external")),
            )
            .values(status="cancelled", message="父级运行已取消。")
        )
        await self._session.commit()
        if force:
            manager = getattr(self._app.state, "agent_background_run_manager", None)
            cancel_task = getattr(manager, "cancel", None)
            if callable(cancel_task):
                await cancel_task(run_model.run_id)
        return AgentCancelRunResponse(run_id=run_model.run_id, session_id=session_id, cancel_requested=True)

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
        runtime_context: Any,
        interruption_code: str = "AI_RUN_CONTINUE_INTERRUPTED",
        interruption_message: str = "智能体继续运行连接中断，运行已停止。",
        reserved_lock: asyncio.Lock | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """继续 paused run，并提交 Pydantic AI deferred tool 结果。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
        run_model = await self._store.get_active_run_model(session_id=session_id, agent_id=agent_id)
        if run_model is None or run_model.status != "paused":
            raise AppException(status_code=409, code="AI_SESSION_RUN_NOT_PAUSED", detail="当前会话没有待继续的智能体运行。")
        requirement = await self._store.get_pending_requirement(run_id=run_model.run_id)
        if requirement is None:
            raise AppException(status_code=409, code="AI_RUN_NOT_PAUSED", detail="当前暂停运行缺少待处理动作。")
        expected_tool_call_id = str(requirement.tool_call_id or "")
        received_tool_call_id = str((tool_execution or {}).get("tool_call_id") or "")
        if received_tool_call_id and expected_tool_call_id and received_tool_call_id != expected_tool_call_id:
            raise AppException(status_code=409, code="AI_RUN_REQUIREMENT_STALE", detail="待确认动作已变化，请刷新会话后重试。")
        stored_tool_execution = {}
        if isinstance(requirement.payload_json, dict) and isinstance(requirement.payload_json.get("tool_execution"), dict):
            stored_tool_execution = dict(requirement.payload_json["tool_execution"])
        merged_tool_execution = {**stored_tool_execution, **(tool_execution or {})}
        async def generator() -> AsyncGenerator[bytes, None]:
            lock = reserved_lock or self._get_lock(session_id=session_id, agent_id=agent_id)
            acquired = reserved_lock is not None
            if not acquired and lock.locked():
                yield _error_event(session_id=session_id, run_id=run_model.run_id, code="AI_SESSION_RUN_ACTIVE", message="当前会话已有运行中的智能体任务。")
                return
            if not acquired:
                await lock.acquire()
                acquired = True
            try:
                descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
                llm_config = await self.resolve_run_llm_config(
                    run_model=run_model,
                    slot=descriptor.llm_slot or "",
                )
                previous_history = await rebuild_agent_message_history(
                    session=self._session,
                    user_id=self._current.user.id,
                    session_id=session_id,
                    agent_id=agent_id,
                    exclude_run_id=run_model.run_id,
                    hydrate_images=False,
                )
                history_budget = build_history_budget(llm_config, runtime_context=runtime_context)
                context_processor = build_context_limit_processor(
                    session=self._session,
                    user_id=self._current.user.id,
                    session_id=session_id,
                    agent_id=agent_id,
                    budget=history_budget,
                    rebuilt_history=previous_history,
                )
                agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
                visual_unavailable, image_generation_model, image_generation_config_id = (
                    await self._resolve_visual_tool_runtime(agent_id)
                )
                tools, deps = build_pydantic_tools(
                    agent_id=agent_id,
                    session_factory=get_session_factory(),
                    runtime_config=agent_config,
                    current=self._current,
                    scope=scope,
                    session_id=session_id,
                    run_id=run_model.run_id,
                    supports_image_input=bool(llm_config.supports_image_input),
                    work_scope_mode=runtime_context.work_scope_mode,
                    allowed_project_ids=runtime_context.allowed_project_ids,
                    focus_version=runtime_context.focus_version,
                    unavailable_group_keys=visual_unavailable,
                    image_generation_model=image_generation_model,
                    image_generation_config_id=image_generation_config_id,
                )
                deferred_results = _build_deferred_results(
                    requirement_tool_call_id=expected_tool_call_id,
                    decision=decision,
                    note=note,
                    tool_execution=merged_tool_execution,
                    feedback_selections=feedback_selections or [],
                )
                resolution_payload = {
                    "decision": decision,
                    "note": note,
                    "tool_execution": merged_tool_execution,
                    "feedback_selections": feedback_selections or [],
                }
                await self._store.begin_requirement_resolution(requirement, payload=resolution_payload)
                run_model.status = "running"
                run_model.pending_requirement_json = None
                continued = await self._store.append_event(
                    run_model,
                    AgentRunEvent(event="run.continued", run_id=run_model.run_id, session_id=session_id),
                )
                from app.ai.platform_runtime import encode_sse_event

                yield encode_sse_event(continued)
                current_message_history_json = await _hydrate_continue_message_history_json(
                    session=self._session,
                    user_id=self._current.user.id,
                    session_id=session_id,
                    message_history=run_model.message_history_json,
                )
                current_run_history = _build_continue_message_history(
                    run_model_message_history=current_message_history_json,
                    run_input_payload=run_model.input_payload_json,
                    run_id=run_model.run_id,
                    tool_execution=merged_tool_execution,
                    runtime_context=runtime_context,
                )
                message_history = [
                    *previous_history.messages,
                    *current_run_history,
                ]
                runner = PydanticAgentRunner(self._store)
                async for chunk in runner.stream_run(
                    run_model=run_model,
                    agent_id=agent_id,
                    model=self._model_resolver.resolve_model(llm_config),
                    model_settings=self._model_resolver.resolve_model_settings(llm_config),
                    runtime_context=runtime_context,
                    message=note or "",
                    include_runtime_context=False,
                    agent_config=agent_config,
                    tools=tools,
                    deps=deps,
                    message_history=message_history,
                    deferred_tool_results=deferred_results,
                    context_budget=history_budget,
                    context_processor=context_processor,
                    consuming_requirement=requirement,
                    requirement_resolution_payload=resolution_payload,
                ):
                    yield chunk
            except asyncio.CancelledError:
                await self._mark_interrupted_run_terminal(
                    run_model,
                    fallback_code=interruption_code,
                    fallback_message=interruption_message,
                )
                raise
            except AppException as exc:
                from app.ai.platform_runtime import encode_sse_event

                logger.warning(
                    "Agent run continue stopped by application error",
                    extra=build_agent_error_log_extra(
                        exc,
                        event="ai.agent_run.continue_app_error",
                        run_id=run_model.run_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        error_code=exc.code,
                        user_error_message=exc.detail,
                    ),
                )
                event = await self._store.mark_terminal(
                    run_model,
                    status="failed",
                    error_code=exc.code,
                    error_message=exc.detail,
                )
                yield encode_sse_event(event)
            except Exception as exc:  # noqa: BLE001
                from app.ai.platform_runtime import encode_sse_event

                failure = normalize_agent_run_exception(
                    exc,
                    fallback_code="AI_RUN_CONTINUE_FAILED",
                    fallback_message="智能体继续运行失败，请稍后重试。",
                )
                logger.exception(
                    "Agent run continue failed",
                    extra=build_agent_error_log_extra(
                        exc,
                        event="ai.agent_run.continue_exception",
                        run_id=run_model.run_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        error_code=failure.code,
                        user_error_message=failure.message,
                        raw_error_message=failure.raw_message,
                    ),
                )
                event = await self._store.mark_terminal(
                    run_model,
                    status="failed",
                    error_code=failure.code,
                    error_message=failure.message,
                )
                yield encode_sse_event(event)
            finally:
                if acquired and lock.locked():
                    lock.release()

        return generator()

    async def continue_external_job_to_store(
        self,
        *,
        run_id: str,
        deferred_results: DeferredToolResults,
        requirement_id: str | None = None,
        continuation_fence: AgentRunWriteFence | None = None,
        source: str = "external_job_queue",
    ) -> str:
        """恢复通用 external_job run；页面任务可额外提供租约写围栏。"""

        store = PlatformAgentRuntimeStore(
            self._session,
            user_id=self._current.user.id,
            write_fence=continuation_fence,
        )

        run_model = await self._session.get(AiAgentRun, run_id)
        if run_model is None or run_model.user_id != self._current.user.id:
            raise AppException(status_code=404, code="AI_RUN_NOT_FOUND", detail="待恢复的智能体运行不存在。")
        if run_model.status != "waiting_external" or run_model.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_NOT_WAITING_EXTERNAL", detail="智能体运行已不再等待外部任务。")
        requirement_query = select(AiAgentRequirement).where(
            AiAgentRequirement.run_id == run_model.run_id,
            AiAgentRequirement.kind == "external_job",
            AiAgentRequirement.status.in_(("pending", "resolving", "resolved")),
        )
        if requirement_id:
            requirement_query = requirement_query.where(AiAgentRequirement.requirement_id == requirement_id)
        requirement = await self._session.scalar(requirement_query.order_by(AiAgentRequirement.created_at.desc()))
        if requirement is None:
            raise AppException(status_code=409, code="AI_EXTERNAL_REQUIREMENT_MISSING", detail="外部任务缺少待恢复 requirement。")

        scope = AgentScopeContext(
            scope_type=run_model.scope_type,  # type: ignore[arg-type]
            workspace_id=run_model.workspace_id,
            project_id=run_model.project_id,
            page_id=run_model.page_id,
            component_id=run_model.component_id,
            source=run_model.source,
        )
        run_input = run_model.input_payload_json or {}
        runtime_context = await build_agent_runtime_context(
            session=self._session,
            scope=scope,
            work_scope_mode=str(run_input.get("work_scope_mode") or "workspace"),
            allowed_project_ids=list(run_input.get("allowed_project_ids") or []),
            focus_version=int(run_input.get("focus_version") or 0),
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
        agent_config = await self._agent_config_service.get_effective_runtime_config(run_model.agent_id)
        visual_unavailable, image_generation_model, image_generation_config_id = (
            await self._resolve_visual_tool_runtime(
                run_model.agent_id,
                retained_tool_names=frozenset({str(requirement.tool_name or "")}),
            )
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
            write_fence=continuation_fence,
        )
        await store.ensure_write_fence()
        resolution_payload = {"source": source, "tool_call_ids": sorted(deferred_results.calls)}
        if requirement.status in {"pending", "resolving"}:
            await store.begin_requirement_resolution(
                requirement,
                payload=resolution_payload,
            )
        run_model.status = "running"
        run_model.pending_requirement_json = None
        await store.append_event(
            run_model,
            AgentRunEvent(event="run.continued", run_id=run_model.run_id, session_id=run_model.session_id),
        )
        current_message_history_json = await _hydrate_continue_message_history_json(
            session=self._session,
            user_id=self._current.user.id,
            session_id=run_model.session_id,
            message_history=run_model.message_history_json,
        )
        tool_execution = (
            dict(requirement.payload_json.get("tool_execution") or {})
            if isinstance(requirement.payload_json, dict)
            else {}
        )
        current_run_history = _build_continue_message_history(
            run_model_message_history=current_message_history_json,
            run_input_payload=run_model.input_payload_json,
            run_id=run_model.run_id,
            tool_execution=tool_execution,
            runtime_context=runtime_context,
        )
        await PydanticAgentRunner(store).run_to_store(
            run_model=run_model,
            agent_id=run_model.agent_id,
            model=self._model_resolver.resolve_model(llm_config),
            model_settings=self._model_resolver.resolve_model_settings(llm_config),
            runtime_context=runtime_context,
            message="",
            include_runtime_context=False,
            agent_config=agent_config,
            tools=tools,
            deps=deps,
            message_history=[*previous_history.messages, *current_run_history],
            deferred_tool_results=deferred_results,
            context_budget=history_budget,
            context_processor=context_processor,
            consuming_requirement=requirement,
            requirement_resolution_payload=resolution_payload,
        )
        await self._session.refresh(run_model, attribute_names=["status"])
        return run_model.status
