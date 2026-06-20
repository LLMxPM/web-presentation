"""文件功能：执行内容助手委派的组件助手与资源助手成员运行。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import build_effective_description, build_effective_instructions
from app.ai.message_history import build_context_limit_processor, build_history_budget, rebuild_agent_message_history
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_event_projection import PydanticEventProjector
from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.ai.pydantic_tools import build_pydantic_tools
from app.ai.run_errors import normalize_agent_run_exception
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent, AgentScopeContext
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.ai_llm_service import AiLlmService
from app.services.auth_service import AuthContext

logger = logging.getLogger(__name__)

_MEMBER_AGENT_IDS = {"component-manager", "resource-manager"}


class MemberDelegationPaused(Exception):
    """成员助手暂停后通知父 run 进入同一个 HITL 等待态。"""

    def __init__(self, requirement: AgentPendingRequirement) -> None:
        """保存需要交给父 run 暂停的 requirement。"""

        super().__init__("member delegation paused")
        self.requirement = requirement


@dataclass(slots=True, frozen=True)
class MemberDelegationResult:
    """描述一次成员委派完成后的稳定返回。"""

    member_run_id: str
    member_id: str
    member_name: str | None
    status: str
    result: str

    def to_payload(self) -> dict[str, Any]:
        """转换成可作为委派工具返回值的 JSON 对象。"""

        return {
            "member_run_id": self.member_run_id,
            "member_id": self.member_id,
            "member_name": self.member_name,
            "status": self.status,
            "result": self.result,
        }


class MemberDelegationExecutor:
    """封装内容助手委派成员助手的创建、执行和恢复。"""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        current: AuthContext,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        parent_session_id: str,
        parent_run_id: str,
    ) -> None:
        """保存父 run 与当前用户上下文，供委派工具运行时使用。"""

        self._session_factory = session_factory
        self._current = current
        self._scope = scope
        self._runtime_context = runtime_context
        self._parent_session_id = parent_session_id
        self._parent_run_id = parent_run_id

    async def delegate_task_to_member(
        self,
        *,
        member_id: str,
        task: str,
        handoff_context: str | None,
        expected_output: str | None,
        delegate_tool_call_id: str | None,
        delegate_tool_name: str,
        completed_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """创建单个成员 run，执行完成后返回成员结果。"""

        result = await self._delegate_one(
            member_id=member_id,
            task=task,
            handoff_context=handoff_context,
            expected_output=expected_output,
            delegate_tool_call_id=delegate_tool_call_id,
            delegate_tool_name=delegate_tool_name,
            parent_delegate_tool_args={
                "member_id": member_id,
                "task": task,
                "handoff_context": handoff_context,
                "expected_output": expected_output,
            },
            completed_results=completed_results or [],
        )
        return result.to_payload()

    async def delegate_task_to_members(
        self,
        *,
        tasks: list[Any],
        delegate_tool_call_id: str | None,
        delegate_tool_name: str,
        completed_results: list[dict[str, Any]] | None = None,
        start_index: int = 0,
    ) -> dict[str, Any]:
        """按顺序执行多个成员任务；任一成员暂停时保留批处理进度。"""

        dumped_tasks = [_dump_task(item) for item in tasks]
        results = list(completed_results or [])
        for index, task_item in enumerate(dumped_tasks[start_index:], start=start_index):
            try:
                result = await self._delegate_one(
                    member_id=str(task_item["member_id"]),
                    task=str(task_item["task"]),
                    handoff_context=_optional_text(task_item.get("handoff_context")),
                    expected_output=_optional_text(task_item.get("expected_output")),
                    delegate_tool_call_id=delegate_tool_call_id,
                    delegate_tool_name=delegate_tool_name,
                    parent_delegate_tool_args={"tasks": dumped_tasks},
                    completed_results=results,
                )
            except MemberDelegationPaused as exc:
                exc.requirement.tool_execution["delegate_batch_state"] = {
                    "tasks": dumped_tasks,
                    "current_index": index,
                    "completed_results": results,
                }
                raise
            results.append(result.to_payload())
        return {"status": "completed", "items": results}

    async def continue_after_member_requirement(
        self,
        *,
        requirement_payload: dict[str, Any],
        deferred_tool_results: DeferredToolResults,
    ) -> dict[str, Any]:
        """恢复暂停的成员 run，并在批量委派时继续执行剩余成员任务。"""

        tool_execution = requirement_payload.get("tool_execution")
        if not isinstance(tool_execution, dict):
            raise AppException(status_code=409, code="AI_MEMBER_REQUIREMENT_INVALID", detail="成员待处理动作缺少工具执行上下文。")
        member_result = await self._continue_member_run(
            requirement_payload=requirement_payload,
            deferred_tool_results=deferred_tool_results,
        )
        batch_state = tool_execution.get("delegate_batch_state")
        if not isinstance(batch_state, dict):
            return member_result.to_payload()
        tasks = batch_state.get("tasks")
        if not isinstance(tasks, list):
            return member_result.to_payload()
        completed_results = [
            item for item in (batch_state.get("completed_results") or [])
            if isinstance(item, dict)
        ]
        completed_results.append(member_result.to_payload())
        return await self.delegate_task_to_members(
            tasks=tasks,
            delegate_tool_call_id=_optional_text(tool_execution.get("parent_delegate_tool_call_id")),
            delegate_tool_name=_optional_text(tool_execution.get("parent_delegate_tool_name")) or "delegate_task_to_members",
            completed_results=completed_results,
            start_index=int(batch_state.get("current_index") or 0) + 1,
        )

    async def _delegate_one(
        self,
        *,
        member_id: str,
        task: str,
        handoff_context: str | None,
        expected_output: str | None,
        delegate_tool_call_id: str | None,
        delegate_tool_name: str,
        parent_delegate_tool_args: dict[str, Any],
        completed_results: list[dict[str, Any]],
    ) -> MemberDelegationResult:
        """执行一个具体成员任务，并把成员运行事件写入父 run。"""

        member_id = member_id.strip()
        if member_id not in _MEMBER_AGENT_IDS:
            raise AppException(status_code=422, code="AI_MEMBER_AGENT_UNSUPPORTED", detail="只能委派组件助手或资源助手。")
        task = task.strip()
        if not task:
            raise AppException(status_code=422, code="AI_MEMBER_TASK_REQUIRED", detail="委派任务不能为空。")
        async with self._session_factory() as session:
            parent_run = await self._require_parent_run(session)
            member_run = await self._create_member_run(
                session,
                parent_run=parent_run,
                member_id=member_id,
                task=task,
                handoff_context=handoff_context,
                expected_output=expected_output,
                delegate_tool_call_id=delegate_tool_call_id,
                delegate_tool_name=delegate_tool_name,
                parent_delegate_tool_args=parent_delegate_tool_args,
                completed_results=completed_results,
            )
            runner = _MemberAgentRunner(
                session=session,
                session_factory=self._session_factory,
                current=self._current,
                scope=self._scope,
                runtime_context=self._runtime_context,
                parent_run=parent_run,
                member_run=member_run,
            )
            return await runner.run(
                message=_build_member_prompt(
                    task=task,
                    handoff_context=handoff_context,
                    expected_output=expected_output,
                    completed_results=completed_results,
                )
            )

    async def _continue_member_run(
        self,
        *,
        requirement_payload: dict[str, Any],
        deferred_tool_results: DeferredToolResults,
    ) -> MemberDelegationResult:
        """恢复一个已暂停的成员 run。"""

        member_run_id = _optional_text(requirement_payload.get("member_run_id"))
        if not member_run_id:
            raise AppException(status_code=409, code="AI_MEMBER_RUN_REQUIRED", detail="成员待处理动作缺少成员运行 ID。")
        async with self._session_factory() as session:
            parent_run = await self._require_parent_run(session)
            member_run = await session.get(AiAgentMemberRun, member_run_id)
            if member_run is None or member_run.parent_run_id != parent_run.run_id:
                raise AppException(status_code=404, code="AI_MEMBER_RUN_NOT_FOUND", detail="成员运行不存在。")
            member_run.status = "running"
            member_run.pending_requirement_json = None
            member_run.updated_at = _utc_now()
            await session.flush()
            runner = _MemberAgentRunner(
                session=session,
                session_factory=self._session_factory,
                current=self._current,
                scope=self._scope,
                runtime_context=self._runtime_context,
                parent_run=parent_run,
                member_run=member_run,
            )
            await runner.append_member_event("run.continued")
            return await runner.run(
                message="",
                message_history=_member_continue_message_history(member_run, requirement_payload),
                deferred_tool_results=deferred_tool_results,
            )

    async def _require_parent_run(self, session: AsyncSession) -> AiAgentRun:
        """读取父 run 并校验它仍属于当前会话。"""

        parent_run = await session.get(AiAgentRun, self._parent_run_id)
        if parent_run is None or parent_run.session_id != self._parent_session_id or parent_run.user_id != self._current.user.id:
            raise AppException(status_code=404, code="AI_RUN_NOT_FOUND", detail="父级智能体运行不存在。")
        return parent_run

    async def _create_member_run(
        self,
        session: AsyncSession,
        *,
        parent_run: AiAgentRun,
        member_id: str,
        task: str,
        handoff_context: str | None,
        expected_output: str | None,
        delegate_tool_call_id: str | None,
        delegate_tool_name: str,
        parent_delegate_tool_args: dict[str, Any],
        completed_results: list[dict[str, Any]],
    ) -> AiAgentMemberRun:
        """创建成员运行记录并发送 member.run.started 事件。"""

        catalog = get_agent_catalog_entry(member_id)
        now = _utc_now()
        member_run = AiAgentMemberRun(
            member_run_id=f"member-run-{uuid4().hex}",
            parent_run_id=parent_run.run_id,
            session_id=parent_run.session_id,
            agent_id=member_id,
            agent_name=catalog.name if catalog else member_id,
            status="running",
            delegate_tool_call_id=delegate_tool_call_id,
            input_payload_json={
                "task": task,
                "handoff_context": handoff_context,
                "expected_output": expected_output,
                "delegate_tool_name": delegate_tool_name,
                "delegate_tool_call_id": delegate_tool_call_id,
                "parent_delegate_tool_args": parent_delegate_tool_args,
                "completed_results": completed_results,
            },
            message_history_json=[],
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(member_run)
        await session.flush([member_run])
        await _MemberAgentRunner(
            session=session,
            session_factory=self._session_factory,
            current=self._current,
            scope=self._scope,
            runtime_context=self._runtime_context,
            parent_run=parent_run,
            member_run=member_run,
        ).append_member_event("run.started")
        return member_run


class _MemberAgentRunner:
    """执行成员 Pydantic Agent，并把原始事件映射为父 run 的 member.* 事件。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        current: AuthContext,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        parent_run: AiAgentRun,
        member_run: AiAgentMemberRun,
    ) -> None:
        """保存成员运行需要的数据库、用户和业务范围。"""

        self._session = session
        self._session_factory = session_factory
        self._current = current
        self._scope = scope
        self._runtime_context = runtime_context
        self._parent_run = parent_run
        self._member_run = member_run
        self._store = PlatformAgentRuntimeStore(session, user_id=current.user.id)
        self._model_resolver = PydanticLlmModelResolver()

    async def run(
        self,
        *,
        message: str,
        message_history: list[Any] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
    ) -> MemberDelegationResult:
        """执行成员 run，返回完成结果；暂停时抛出 MemberDelegationPaused。"""

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        final_messages: list[dict[str, Any]] = []
        projector: PydanticEventProjector | None = None
        try:
            catalog = get_agent_catalog_entry(self._member_run.agent_id)
            if catalog is None:
                raise AppException(status_code=404, code="AI_AGENT_NOT_FOUND", detail="成员助手不存在。")
            llm_config = await AiLlmService(
                self._session,
                user_id=self._current.user.id,
                user_role=self._current.user.role,
            ).get_bound_config_or_raise(catalog.llm_slot)
            agent_config = await AiAgentConfigService(self._session, user_id=self._current.user.id).get_effective_runtime_config(
                self._member_run.agent_id
            )
            rebuilt_history = await rebuild_agent_message_history(
                session=self._session,
                user_id=self._current.user.id,
                session_id=self._parent_run.session_id,
                agent_id=self._parent_run.agent_id,
            )
            history_budget = build_history_budget(llm_config, runtime_context=self._runtime_context)
            context_processor = build_context_limit_processor(
                session=self._session,
                user_id=self._current.user.id,
                session_id=self._parent_run.session_id,
                agent_id=self._member_run.agent_id,
                budget=history_budget,
                rebuilt_history=rebuilt_history,
            )
            tools, deps = build_pydantic_tools(
                agent_id=self._member_run.agent_id,
                session_factory=self._session_factory,
                runtime_config=agent_config,
                current=self._current,
                scope=self._scope,
                session_id=self._parent_run.session_id,
                run_id=self._parent_run.run_id,
                supports_image_input=bool(llm_config.supports_image_input),
            )
            agent = Agent(
                self._model_resolver.resolve_model(llm_config),
                name=self._member_run.agent_id,
                output_type=[str, DeferredToolRequests],
                instructions=[
                    *build_effective_instructions(catalog, agent_config),
                    build_scope_context_text(self._runtime_context),
                ],
                system_prompt=build_effective_description(catalog, agent_config),
                deps_type=type(deps),
                tools=tools,
                history_processors=[context_processor] if context_processor is not None else None,
            )
            projector = PydanticEventProjector(
                run_id=self._parent_run.run_id,
                session_id=self._parent_run.session_id,
                append_event=self._append_projected_member_event,
                deferred_tool_results=deferred_tool_results,
                event_prefix="member.",
                base_event_data=self._member_event_data,
                map_tool_call_id=lambda raw_tool_call_id: _member_tool_call_id(
                    self._member_run.member_run_id,
                    raw_tool_call_id,
                ),
                extra_tool_data=lambda raw_tool_call_id: {"raw_tool_call_id": raw_tool_call_id},
                final_messages=final_messages,
                on_message_delta=lambda content: self._append_member_delta(
                    content_parts,
                    field="content",
                    content=content,
                ),
                on_reasoning_delta=lambda content: self._append_member_delta(
                    reasoning_parts,
                    field="reasoning_content",
                    content=content,
                ),
                on_deferred=self._pause_for_deferred_tools,
            )
            await self.append_member_event("model.request.started")
            async for raw_event in agent.run_stream_events(
                message if message else None,
                model_settings=self._model_resolver.resolve_model_settings(llm_config) or None,
                deps=deps,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                infer_name=False,
            ):
                await self._raise_if_parent_cancelled(projector)
                await projector.handle_raw_event(raw_event)
            await self._raise_if_parent_cancelled(projector)
            await projector.flush_delta_buffer()
            await self.append_member_event("model.request.completed")
            result_text = "".join(content_parts)
            self._member_run.status = "completed"
            self._member_run.content = result_text or self._member_run.content
            self._member_run.reasoning_content = "".join(reasoning_parts) or self._member_run.reasoning_content
            self._member_run.message_history_json = [
                *(self._member_run.message_history_json or []),
                *final_messages,
            ]
            self._member_run.finished_at = _utc_now()
            self._member_run.updated_at = _utc_now()
            await self.append_member_event("run.completed", content=result_text)
            return MemberDelegationResult(
                member_run_id=self._member_run.member_run_id,
                member_id=self._member_run.agent_id,
                member_name=self._member_run.agent_name,
                status="completed",
                result=result_text,
            )
        except MemberDelegationPaused:
            raise
        except AppException as exc:
            if exc.code == "AI_RUN_CANCELLED":
                raise
            if projector is not None:
                await projector.flush_delta_buffer(best_effort=True)
            return await self._mark_failed_result(code=exc.code, message=exc.detail)
        except Exception as exc:  # noqa: BLE001
            if projector is not None:
                await projector.flush_delta_buffer(best_effort=True)
            failure = normalize_agent_run_exception(exc, fallback_code="AI_MEMBER_RUN_FAILED")
            logger.exception(
                "Member agent run failed",
                extra={
                    "parent_run_id": self._parent_run.run_id,
                    "member_run_id": self._member_run.member_run_id,
                    "member_agent_id": self._member_run.agent_id,
                    "error_code": failure.code,
                    "raw_error_message": failure.raw_message,
                },
            )
            return await self._mark_failed_result(code=failure.code, message=failure.message)

    async def append_member_event(
        self,
        event_suffix: str,
        *,
        content: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> AgentRunEvent:
        """向父 run 追加 member.* 事件，并补齐成员身份字段。"""

        event_data = {
            "member_run_id": self._member_run.member_run_id,
            "member_agent_id": self._member_run.agent_id,
            "member_agent_name": self._member_run.agent_name,
            "delegate_tool_call_id": self._member_run.delegate_tool_call_id,
            **(data or {}),
        }
        event = await self._store.append_event(
            self._parent_run,
            AgentRunEvent(
                event=f"member.{event_suffix}",
                run_id=self._parent_run.run_id,
                session_id=self._parent_run.session_id,
                content=content,
                data=event_data,
            ),
        )
        await self._session.refresh(self._member_run)
        return event

    async def _append_projected_member_event(self, event: AgentRunEvent) -> AgentRunEvent:
        """写入共享投影器生成的 member.* 事件，并刷新成员运行字段。"""

        stored = await self._store.append_event(self._parent_run, event)
        await self._session.refresh(self._member_run)
        return stored

    def _member_event_data(self) -> dict[str, Any]:
        """生成每条 member.* 事件必须携带的成员身份字段。"""

        return {
            "member_run_id": self._member_run.member_run_id,
            "member_agent_id": self._member_run.agent_id,
            "member_agent_name": self._member_run.agent_name,
            "delegate_tool_call_id": self._member_run.delegate_tool_call_id,
        }

    def _append_member_delta(self, parts: list[str], *, field: str, content: str) -> None:
        """同步累计成员输出字段；真正落库节奏由共享投影器控制。"""

        parts.append(content)
        current = getattr(self._member_run, field) or ""
        setattr(self._member_run, field, f"{current}{content}")

    async def _pause_for_deferred_tools(
        self,
        requests: DeferredToolRequests,
        final_messages: list[dict[str, Any]],
    ) -> AgentRunEvent:
        """成员助手触发 HITL 时暂停成员 run，并把 requirement 抛回父 run。"""

        self._member_run.message_history_json = [
            *(self._member_run.message_history_json or []),
            *final_messages,
        ]
        requirement = _member_requirement_from_deferred(
            requests,
            parent_run=self._parent_run,
            member_run=self._member_run,
        )
        self._member_run.status = "paused"
        self._member_run.pending_requirement_json = requirement.model_dump(mode="json")
        self._member_run.updated_at = _utc_now()
        await self.append_member_event("run.paused", data={"requirement": requirement.model_dump(mode="json")})
        raise MemberDelegationPaused(requirement)

    async def _mark_failed_result(self, *, code: str, message: str) -> MemberDelegationResult:
        """把成员运行收敛为失败，并返回可交给内容助手整合的成员结果。"""

        self._member_run.status = "failed"
        self._member_run.error_message = message
        self._member_run.finished_at = _utc_now()
        self._member_run.updated_at = _utc_now()
        await self.append_member_event("run.error", data={"code": code, "message": message})
        return MemberDelegationResult(
            member_run_id=self._member_run.member_run_id,
            member_id=self._member_run.agent_id,
            member_name=self._member_run.agent_name,
            status="failed",
            result=f"成员助手运行失败：{message}",
        )

    async def _raise_if_parent_cancelled(self, projector: PydanticEventProjector | None = None) -> None:
        """成员执行期间感知父 run 取消标记，并收敛成员状态。"""

        await self._session.refresh(self._parent_run, attribute_names=["status", "cancel_requested_at"])
        if self._parent_run.cancel_requested_at is None and self._parent_run.status != "cancelling":
            return
        if projector is not None:
            await projector.flush_delta_buffer(best_effort=True)
        self._member_run.status = "cancelled"
        self._member_run.finished_at = _utc_now()
        self._member_run.updated_at = _utc_now()
        await self.append_member_event("run.cancelled", content="父级运行已停止，成员运行同步取消。")
        raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="当前智能体运行已被取消。")


def _build_member_prompt(
    *,
    task: str,
    handoff_context: str | None,
    expected_output: str | None,
    completed_results: list[dict[str, Any]],
) -> str:
    """构造成员助手可直接执行的委派任务提示。"""

    parts = [
        "内容助手委派给你的成员任务如下，请只处理你负责的工作空间组件库或资源库范围。",
        f"任务：{task}",
    ]
    if handoff_context:
        parts.append(f"上下文：{handoff_context}")
    if completed_results:
        parts.append(f"前置成员结果：{json.dumps(completed_results, ensure_ascii=False)}")
    if expected_output:
        parts.append(f"期望返回：{expected_output}")
    parts.append("完成后用中文简要返回已执行动作、关键对象 ID/名称、后续内容助手需要整合的事实。")
    return "\n\n".join(parts)


def _member_requirement_from_deferred(
    requests: DeferredToolRequests,
    *,
    parent_run: AiAgentRun,
    member_run: AiAgentMemberRun,
) -> AgentPendingRequirement:
    """把成员 DeferredToolRequests 转成父 run 可展示和可恢复的 requirement。"""

    call = (requests.approvals or requests.calls)[0] if (requests.approvals or requests.calls) else None
    tool_name = getattr(call, "tool_name", None) if call is not None else None
    tool_call_id = str(getattr(call, "tool_call_id", "") or "") if call is not None else ""
    args = _tool_args_as_dict(getattr(call, "args", None) if call is not None else None)
    feedback_schema = _feedback_schema_from_args(args) if tool_name == "ask_user" else []
    kind = "user_feedback" if tool_name == "ask_user" else "confirmation"
    if kind == "user_feedback" and not feedback_schema:
        raise AppException(
            status_code=422,
            code="AI_ASK_USER_SCHEMA_INVALID",
            detail="ask_user 工具调用缺少可展示的问题，请使用 questions[].question 提供问题文案。",
        )
    parent_input = member_run.input_payload_json if isinstance(member_run.input_payload_json, dict) else {}
    tool_execution = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_args": args,
        "member_tool_call_id": tool_call_id,
        "member_tool_name": tool_name,
        "member_run_id": member_run.member_run_id,
        "parent_delegate_tool_call_id": parent_input.get("delegate_tool_call_id"),
        "parent_delegate_tool_name": parent_input.get("delegate_tool_name"),
        "parent_delegate_tool_args": parent_input.get("parent_delegate_tool_args") or {},
        "deferred_metadata": requests.metadata,
    }
    if feedback_schema:
        tool_execution.update({"requires_user_input": True, "user_feedback_schema": feedback_schema})
    return AgentPendingRequirement(
        id=f"req-{uuid4().hex}",
        kind=kind,  # type: ignore[arg-type]
        run_id=parent_run.run_id,
        session_id=parent_run.session_id,
        member_agent_id=member_run.agent_id,
        member_agent_name=member_run.agent_name,
        member_run_id=member_run.member_run_id,
        tool_name=str(tool_name or "") or None,
        tool_execution=tool_execution,
        user_feedback_schema=feedback_schema,
        note="需要用户回答后继续。" if kind == "user_feedback" else f"成员工具 {tool_name or 'unknown'} 需要确认后执行。",
    )


def _member_continue_message_history(member_run: AiAgentMemberRun, requirement_payload: dict[str, Any]) -> list[Any]:
    """读取成员恢复执行所需的 Pydantic AI 历史；缺失时重建最小上下文。"""

    if member_run.message_history_json:
        return ModelMessagesTypeAdapter.validate_python(member_run.message_history_json)
    tool_execution = requirement_payload.get("tool_execution") if isinstance(requirement_payload, dict) else {}
    if not isinstance(tool_execution, dict):
        return []
    tool_name = str(tool_execution.get("member_tool_name") or tool_execution.get("tool_name") or "").strip()
    tool_call_id = str(tool_execution.get("member_tool_call_id") or tool_execution.get("tool_call_id") or "").strip()
    if not tool_name or not tool_call_id:
        return []
    input_payload = member_run.input_payload_json if isinstance(member_run.input_payload_json, dict) else {}
    message = _build_member_prompt(
        task=str(input_payload.get("task") or "继续成员任务。"),
        handoff_context=_optional_text(input_payload.get("handoff_context")),
        expected_output=_optional_text(input_payload.get("expected_output")),
        completed_results=[
            item for item in (input_payload.get("completed_results") or [])
            if isinstance(item, dict)
        ],
    )
    return [
        ModelRequest(parts=[UserPromptPart(content=message)], run_id=member_run.member_run_id),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool_name,
                    args=tool_execution.get("tool_args") if isinstance(tool_execution.get("tool_args"), (dict, str)) else None,
                    tool_call_id=tool_call_id,
                )
            ],
            run_id=member_run.member_run_id,
        ),
    ]

def _tool_args_as_dict(value: Any) -> dict[str, Any]:
    """把 Pydantic AI 工具参数归一化为 dict，兼容 JSON 字符串。"""

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _feedback_schema_from_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    """从 ask_user 参数中提取前端可渲染的问题结构。"""

    questions = args.get("questions")
    if not isinstance(questions, list):
        return []
    result: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        normalized = dict(item)
        normalized["question"] = question
        normalized["multi_select"] = False
        options = normalized.get("options")
        normalized["options"] = options if isinstance(options, list) else []
        result.append(normalized)
    return result

def _member_tool_call_id(member_run_id: str, raw_tool_call_id: str | None) -> str | None:
    """生成父 run 内唯一的成员工具调用 ID。"""

    raw = str(raw_tool_call_id or "").strip()
    return f"{member_run_id}:{raw}" if raw else None


def _dump_task(item: Any) -> dict[str, Any]:
    """把 Pydantic task 模型或 dict 规整为普通 JSON 对象。"""

    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", exclude_none=True)
    if isinstance(item, dict):
        return {str(key): value for key, value in item.items()}
    return {}


def _optional_text(value: Any) -> str | None:
    """把可选文本字段规整为空值或非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now() -> datetime:
    """返回 UTC 当前时间。"""

    return datetime.now(tz=UTC)
