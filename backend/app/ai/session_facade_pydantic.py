"""文件功能：基于平台运行态与 Pydantic AI 的 Agent 会话 BFF Facade。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI
from pydantic_ai import DeferredToolResults, ToolDenied
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, ToolCallPart, UserContent, UserPromptPart
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.platform_runtime import ACTIVE_RUN_STATUSES, PlatformAgentRuntimeStore, new_session_id, stream_replay_then_subscribe
from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.ai.pydantic_runner import PydanticAgentRunner
from app.ai.pydantic_tools import build_pydantic_tools
from app.ai.run_errors import normalize_agent_run_exception
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.schemas.agent import (
    AgentActiveRunItem,
    AgentCancelRunResponse,
    AgentContextStatusItem,
    AgentMessageItem,
    AgentRunEvent,
    AgentScopeContext,
    AgentSessionItem,
    AgentSessionRuntimeSnapshot,
)
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.ai_llm_service import AiLlmService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.agent_image_transport_resolver import ResolvedAgentImage
from app.services.auth_service import AuthContext

logger = logging.getLogger(__name__)


class AgentSessionFacade:
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

    async def list_sessions(self, *, agent_id: str, scope: AgentScopeContext) -> list[AgentSessionItem]:
        """列出当前用户在指定 scope 下的智能体会话。"""

        return await self._store.list_sessions(agent_id=agent_id, scope=scope)

    async def create_session(
        self,
        *,
        agent_id: str,
        scope: AgentScopeContext,
        session_name: str | None = None,
    ) -> AgentSessionItem:
        """创建平台智能体会话。"""

        return await self._store.create_session(
            session_id=new_session_id(),
            agent_id=agent_id,
            session_name=session_name,
            scope=scope,
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
        scope: AgentScopeContext,
    ) -> AgentSessionItem:
        """校验当前用户可以访问会话，并返回会话项。"""

        try:
            model = await self._store.require_session(session_id=session_id, agent_id=agent_id)
        except ValueError as exc:
            raise _map_store_error(exc) from exc
        if model.workspace_id != scope.workspace_id or model.scope_type != scope.scope_type:
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
        return await self._store.get_runtime_snapshot(
            session_id=session_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
        )

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
        """读取当前会话上下文状态。"""

        await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
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
                llm_config = await AiLlmService(
                    self._session,
                    user_id=self._current.user.id,
                    user_role=self._current.user.role,
                ).get_bound_config_or_raise(descriptor.llm_slot or "")
                resolved_images = await self._resolve_run_images(
                    session_id=session_id,
                    scope=scope,
                    image_attachment_ids=image_attachment_ids or [],
                    supports_image_input=bool(llm_config.supports_image_input),
                )
                run_start = await self._store.start_run(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    run_id=effective_run_id,
                    message=message,
                    image_attachment_ids=image_attachment_ids or [],
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
                tools, deps = build_pydantic_tools(
                    agent_id=agent_id,
                    session_factory=get_session_factory(),
                    runtime_config=agent_config,
                    current=self._current,
                    scope=scope,
                    session_id=session_id,
                    run_id=run_start.run_model.run_id,
                    supports_image_input=bool(llm_config.supports_image_input),
                )
                runner = PydanticAgentRunner(self._store)
                async for chunk in runner.stream_run(
                    run_model=run_start.run_model,
                    agent_id=agent_id,
                    model=model,
                    model_settings=model_settings,
                    runtime_context=runtime_context,
                    message=_build_user_prompt(message, resolved_images),
                    agent_config=agent_config,
                    tools=tools,
                    deps=deps,
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
                    extra={
                        "run_id": run_model.run_id if run_model is not None else run_id,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "error_code": failure.code,
                        "raw_error_message": failure.raw_message,
                    },
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
            lock = self._get_lock(session_id=session_id, agent_id=agent_id)
            if lock.locked():
                yield _error_event(session_id=session_id, run_id=run_model.run_id, code="AI_SESSION_RUN_ACTIVE", message="当前会话已有运行中的智能体任务。")
                return
            await lock.acquire()
            try:
                descriptor = self._app.state.ai_registry.get_descriptor(agent_id)
                llm_config = await AiLlmService(
                    self._session,
                    user_id=self._current.user.id,
                    user_role=self._current.user.role,
                ).get_bound_config_or_raise(descriptor.llm_slot or "")
                agent_config = await self._agent_config_service.get_effective_runtime_config(agent_id)
                tools, deps = build_pydantic_tools(
                    agent_id=agent_id,
                    session_factory=get_session_factory(),
                    runtime_config=agent_config,
                    current=self._current,
                    scope=scope,
                    session_id=session_id,
                    run_id=run_model.run_id,
                    supports_image_input=bool(llm_config.supports_image_input),
                )
                deferred_results = _build_deferred_results(
                    requirement_tool_call_id=expected_tool_call_id,
                    decision=decision,
                    note=note,
                    tool_execution=merged_tool_execution,
                    feedback_selections=feedback_selections or [],
                )
                await self._store.resolve_requirement(
                    requirement,
                    payload={
                        "decision": decision,
                        "note": note,
                        "tool_execution": merged_tool_execution,
                        "feedback_selections": feedback_selections or [],
                    },
                )
                run_model.status = "running"
                run_model.pending_requirement_json = None
                continued = await self._store.append_event(
                    run_model,
                    AgentRunEvent(event="run.continued", run_id=run_model.run_id, session_id=session_id),
                )
                from app.ai.platform_runtime import encode_sse_event

                yield encode_sse_event(continued)
                message_history = _build_continue_message_history(
                    run_model_message_history=run_model.message_history_json,
                    run_input_payload=run_model.input_payload_json,
                    run_id=run_model.run_id,
                    tool_execution=merged_tool_execution,
                )
                runner = PydanticAgentRunner(self._store)
                async for chunk in runner.stream_run(
                    run_model=run_model,
                    agent_id=agent_id,
                    model=self._model_resolver.resolve_model(llm_config),
                    model_settings=self._model_resolver.resolve_model_settings(llm_config),
                    runtime_context=runtime_context,
                    message=note or "",
                    agent_config=agent_config,
                    tools=tools,
                    deps=deps,
                    message_history=message_history,
                    deferred_tool_results=deferred_results,
                ):
                    yield chunk
            except asyncio.CancelledError:
                await self._mark_interrupted_run_terminal(
                    run_model,
                    fallback_code="AI_RUN_CONTINUE_INTERRUPTED",
                    fallback_message="智能体继续运行连接中断，运行已停止。",
                )
                raise
            except AppException as exc:
                from app.ai.platform_runtime import encode_sse_event

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
                    extra={
                        "run_id": run_model.run_id,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "error_code": failure.code,
                        "raw_error_message": failure.raw_message,
                    },
                )
                event = await self._store.mark_terminal(
                    run_model,
                    status="failed",
                    error_code=failure.code,
                    error_message=failure.message,
                )
                yield encode_sse_event(event)
            finally:
                if lock.locked():
                    lock.release()

        return generator()

    async def _mark_interrupted_run_terminal(
        self,
        run_model: Any | None,
        *,
        fallback_code: str,
        fallback_message: str,
    ) -> None:
        """流式响应被取消时收敛后端 run 状态，避免长期残留 running。"""

        if run_model is None:
            return
        try:
            current_status = await self._store.get_run_status(run_id=run_model.run_id)
            if current_status not in ACTIVE_RUN_STATUSES or current_status == "paused":
                return
            if current_status == "cancelling":
                await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                return
            await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code=fallback_code,
                error_message=fallback_message,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark interrupted agent run terminal",
                extra={
                    "run_id": getattr(run_model, "run_id", None),
                    "fallback_code": fallback_code,
                },
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
        supports_image_input: bool,
    ) -> list[ResolvedAgentImage]:
        """校验并解析本轮用户图片附件，返回可放入 Pydantic AI prompt 的图片内容。"""

        if not image_attachment_ids:
            return []
        if not supports_image_input:
            raise AppException(
                status_code=409,
                code="AI_LLM_IMAGE_INPUT_UNSUPPORTED",
                detail="当前绑定模型不支持图片输入，不能发送图片附件。",
            )
        service = AgentImageAttachmentService(self._session, user_id=self._current.user.id)
        attachments = await service.validate_attachments_for_run(
            workspace_id=scope.workspace_id,
            session_id=session_id,
            attachment_ids=image_attachment_ids,
        )
        return await service.build_images_for_run(attachments)

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


def _map_store_error(exc: ValueError) -> AppException:
    """把运行态 store 错误转换为 API 异常。"""

    code = str(exc)
    if code == "AI_SESSION_NOT_FOUND":
        return AppException(status_code=404, code=code, detail="指定智能体会话不存在。")
    if code == "AI_SESSION_RUN_ACTIVE":
        return AppException(status_code=409, code=code, detail="当前会话已有未结束的智能体运行，请等待完成或先处理待确认动作。")
    if code == "AI_RUN_NOT_ACTIVE":
        return AppException(status_code=409, code=code, detail="当前会话没有可取消的运行。")
    return AppException(status_code=500, code="AI_RUNTIME_STATE_ERROR", detail="智能体运行态异常。")


def _error_event(*, session_id: str, run_id: str | None, code: str, message: str) -> bytes:
    """构造平台错误 SSE。"""

    from app.ai.platform_runtime import encode_sse_event

    return encode_sse_event(
        AgentRunEvent(
            event="run.error",
            run_id=run_id,
            session_id=session_id,
            data={"code": code, "message": message},
        )
    )


def _build_deferred_results(
    *,
    requirement_tool_call_id: str,
    decision: str | None,
    note: str | None,
    tool_execution: dict[str, Any],
    feedback_selections: list[dict[str, Any]],
) -> DeferredToolResults:
    """把前端确认结果转换为 Pydantic AI DeferredToolResults。"""

    result = DeferredToolResults()
    if not requirement_tool_call_id:
        return result
    if _is_user_feedback_tool(tool_execution):
        if decision == "reject":
            result.calls[requirement_tool_call_id] = note or "用户未提供回答。"
        else:
            result.calls[requirement_tool_call_id] = _format_user_feedback_result(
                tool_execution=tool_execution,
                feedback_selections=feedback_selections,
                note=note,
            )
        return result
    if decision == "reject":
        result.approvals[requirement_tool_call_id] = ToolDenied(note or "用户拒绝执行该工具。")
    else:
        result.approvals[requirement_tool_call_id] = True
    if "external_result" in (tool_execution or {}):
        result.calls[requirement_tool_call_id] = tool_execution["external_result"]
    return result


def _build_continue_message_history(
    *,
    run_model_message_history: list[dict[str, Any]] | None,
    run_input_payload: dict[str, Any] | None,
    run_id: str,
    tool_execution: dict[str, Any],
) -> list[Any]:
    """读取继续运行所需的 Pydantic AI 历史；空历史时重建最小 deferred tool 上下文。"""

    if run_model_message_history:
        return ModelMessagesTypeAdapter.validate_python(run_model_message_history)
    tool_name = str(tool_execution.get("tool_name") or "").strip()
    tool_call_id = str(tool_execution.get("tool_call_id") or "").strip()
    if not tool_name or not tool_call_id:
        return []
    input_payload = run_input_payload if isinstance(run_input_payload, dict) else {}
    message = str(input_payload.get("message") or "").strip() or "继续当前智能体运行。"
    tool_args = tool_execution.get("tool_args")
    return [
        ModelRequest(parts=[UserPromptPart(content=message)], run_id=run_id),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool_name,
                    args=tool_args if isinstance(tool_args, (dict, str)) else None,
                    tool_call_id=tool_call_id,
                )
            ],
            run_id=run_id,
        ),
    ]


def _build_user_prompt(message: str, resolved_images: list[ResolvedAgentImage]) -> str | list[UserContent]:
    """把文本和图片附件组合成 Pydantic AI 用户输入。"""

    if not resolved_images:
        return message
    parts: list[UserContent] = []
    if message.strip():
        parts.append(message)
    else:
        parts.append("用户发送了图片附件，请结合图片内容理解需求。")
    parts.extend(resolved.image for resolved in resolved_images)
    return parts


def _is_user_feedback_tool(tool_execution: dict[str, Any]) -> bool:
    """判断当前 deferred tool 是否是平台结构化提问。"""

    return str(tool_execution.get("tool_name") or "").strip() == "ask_user"


def _format_user_feedback_result(
    *,
    tool_execution: dict[str, Any],
    feedback_selections: list[dict[str, Any]],
    note: str | None,
) -> str:
    """把用户对 ask_user 的回答整理为模型可读的工具返回文本。"""

    answers: list[dict[str, Any]] = []
    questions = _feedback_questions(tool_execution)
    by_question = {
        str(item.get("question") or "").strip(): item
        for item in feedback_selections
        if isinstance(item, dict)
    }
    for question in questions:
        question_text = str(question.get("question") or "").strip()
        selection = by_question.get(question_text, {})
        selected_label = str(selection.get("selected_label") or "").strip()
        custom_text = str(selection.get("custom_text") or "").strip()
        answer = f"用户补充：{custom_text}" if custom_text else selected_label
        if question_text and answer:
            answers.append({"question": question_text, "selected": [answer]})
    if not answers:
        fallback = str(note or "").strip()
        if fallback:
            answers.append({"question": "用户补充", "selected": [fallback]})
    if not answers:
        answers.append({"question": "用户补充", "selected": ["用户已继续，但未提供具体回答。"]})
    return f"User feedback received: {json.dumps(answers, ensure_ascii=False)}"


def _feedback_questions(tool_execution: dict[str, Any]) -> list[dict[str, Any]]:
    """从工具执行 payload 中读取 ask_user 问题结构。"""

    raw_questions = tool_execution.get("user_feedback_schema") or tool_execution.get("questions")
    tool_args = tool_execution.get("tool_args")
    if raw_questions is None and isinstance(tool_args, dict):
        raw_questions = tool_args.get("questions") or tool_args.get("user_feedback_schema")
    if not isinstance(raw_questions, list):
        return []
    return [item for item in raw_questions if isinstance(item, dict)]
