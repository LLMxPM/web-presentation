"""文件功能：执行持久化 AI 页面创建与修改任务，并把页面写入和任务结果原子提交。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.run_event_writer import is_sqlite_lock_error
from app.ai.platform_tools import recoverable_tool_error_result
from app.ai.tools.page.apply_page_edits import (
    _ensure_page_base_version,
    _ensure_page_in_context,
    _with_apply_validation_metadata,
)
from app.ai.tools.project.project_pages import (
    _has_warning_diagnostics,
    _is_validation_passed,
    _with_create_validation_failure_message,
)
from app.ai.tools.shared import apply_source_edits
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRun, AiAgentToolCall
from app.models.ai_page_mutation import AiPageMutationJob
from app.models.enums import PageFileType, RecordStatus
from app.models.page import Page
from app.models.user import User
from app.schemas.page import PageCreateRequest, PageUpdateRequest
from app.services.code_check_service import CodeCheckService, build_code_check_failed_result
from app.services.durable_job_lease_service import transition_owned_running_job
from app.services.page_service import PageService

ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PageMutationExecutionContext:
    """保存任务执行所需的稳定引用和原始工具参数。"""

    database_id: int
    job_id: str
    operation: str
    run_id: str
    user_id: int
    workspace_id: int
    project_id: int | None
    page_id: int | None
    base_version_no: int | None
    arguments: dict[str, Any]


class AiPageMutationExecutor:
    """使用短数据库会话准备候选源码，并在最终事务中完成页面写入。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """保存异步会话工厂，所有慢诊断前后都重新建立短会话。"""

        self._session_factory = session_factory

    async def execute(
        self,
        *,
        database_id: int,
        worker_id: str,
        progress: ProgressCallback,
        lease_lost: asyncio.Event | None = None,
    ) -> None:
        """执行一个已认领任务；失去租约或取消时不产生页面副作用。"""

        self._raise_if_lease_lost(lease_lost)
        context = await self._load_context(database_id=database_id, worker_id=worker_id)
        await progress("validating")
        self._raise_if_lease_lost(lease_lost)
        if context.operation == "create_page":
            await self._execute_create(
                context=context,
                worker_id=worker_id,
                progress=progress,
                lease_lost=lease_lost,
            )
            return
        if context.operation == "apply_page_edits":
            await self._execute_apply(
                context=context,
                worker_id=worker_id,
                progress=progress,
                lease_lost=lease_lost,
            )
            return
        raise AppException(
            status_code=422,
            code="AI_PAGE_MUTATION_OPERATION_INVALID",
            detail=f"不支持的页面变更操作：{context.operation}",
        )

    async def complete_business_error(
        self,
        *,
        database_id: int,
        worker_id: str,
        error: AppException,
    ) -> bool:
        """把可恢复业务异常保存为正常 deferred tool result，让模型决定下一步。"""

        result = recoverable_tool_error_result(
            code=error.code,
            message=error.detail,
            status_code=error.status_code,
            hint="请重新读取最新页面状态或修正参数后再调用。",
        )
        return await self._finish_without_page_write(
            database_id=database_id,
            worker_id=worker_id,
            result=result,
        )

    async def _load_context(self, *, database_id: int, worker_id: str) -> PageMutationExecutionContext:
        """读取任务、run 与工具参数，并在执行前检查租约和取消状态。"""

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(AiPageMutationJob, AiAgentRun, AiAgentToolCall)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationJob.run_id)
                    .join(
                        AiAgentToolCall,
                        (AiAgentToolCall.run_id == AiPageMutationJob.run_id)
                        & (AiAgentToolCall.tool_call_id == AiPageMutationJob.tool_call_id),
                    )
                    .where(
                        AiPageMutationJob.id == database_id,
                        AiPageMutationJob.status == "running",
                        AiPageMutationJob.worker_id == worker_id,
                        AiPageMutationJob.lease_expires_at.is_not(None),
                        AiPageMutationJob.lease_expires_at > utc_now(),
                    )
                )
            ).first()
            if row is None:
                raise AppException(status_code=409, code="AI_PAGE_MUTATION_LEASE_LOST", detail="页面变更任务租约已失效。")
            job, run, tool_call = row
            if job.cancel_requested_at is not None or run.cancel_requested_at is not None or run.status in {"cancelled", "failed"}:
                raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已取消。")
            user = await session.get(User, run.user_id)
            if user is None or user.status != RecordStatus.ACTIVE.value:
                raise AppException(status_code=403, code="AUTH_DISABLED", detail="执行页面变更的用户已被禁用或删除。")
            arguments = tool_call.input_payload_json
            if not isinstance(arguments, dict):
                raise AppException(
                    status_code=422,
                    code="AI_PAGE_MUTATION_ARGUMENTS_MISSING",
                    detail="页面变更任务缺少原始工具参数。",
                )
            return PageMutationExecutionContext(
                database_id=job.id,
                job_id=job.job_id,
                operation=job.operation,
                run_id=job.run_id,
                user_id=run.user_id,
                workspace_id=job.workspace_id,
                project_id=job.project_id,
                page_id=job.page_id,
                base_version_no=job.base_version_no,
                arguments=dict(arguments),
            )

    async def _execute_create(
        self,
        *,
        context: PageMutationExecutionContext,
        worker_id: str,
        progress: ProgressCallback,
        lease_lost: asyncio.Event | None,
    ) -> None:
        """检查未落库页面源码，并在新事务中创建页面和完成 Job。"""

        title = str(context.arguments.get("title") or "").strip()
        page_content = str(context.arguments.get("page_content") or "")
        if not title:
            raise AppException(status_code=400, code="AI_PAGE_TITLE_REQUIRED", detail="页面标题不能为空。")
        if not page_content.strip():
            raise AppException(status_code=400, code="AI_PAGE_CONTENT_REQUIRED", detail="创建页面时必须提供非空 page_content。")
        if context.project_id is None:
            raise AppException(status_code=409, code="AI_PROJECT_CONTEXT_REQUIRED", detail="创建页面缺少项目上下文。")

        async with self._session_factory() as session:
            validation_result = await CodeCheckService(session).check_page_code(
                page_id=None,
                project_id=context.project_id,
                workspace_id=context.workspace_id,
                user_id=context.user_id,
                content=page_content,
            )
        self._raise_if_lease_lost(lease_lost)
        if not _is_validation_passed(validation_result):
            await self._finish_without_page_write(
                database_id=context.database_id,
                worker_id=worker_id,
                result=_with_create_validation_failure_message(validation_result),
            )
            return

        await progress("saving")
        self._raise_if_lease_lost(lease_lost)

        async def save(session: AsyncSession) -> None:
            """在单个短事务内创建页面并同步收敛 Job。"""

            await self._lock_owned_job(session, context=context, worker_id=worker_id)
            created = await PageService(session).create(
                PageCreateRequest(
                    workspace_id=context.workspace_id,
                    project_id=context.project_id,
                    title=title,
                    summary=_optional_string(context.arguments.get("summary")),
                    speaker_notes=_optional_string(context.arguments.get("speaker_notes")),
                    page_content=page_content,
                    file_type=PageFileType.VUE,
                    status=RecordStatus.ACTIVE,
                ),
                context.user_id,
                commit=False,
            )
            response: dict[str, Any] = {
                "success": True,
                "message": "页面已创建。",
                "page_id": created.id,
                "page_code": created.code,
                "title": created.title,
                "summary": created.summary,
                "speaker_notes": created.speaker_notes,
                "project_id": created.project_id,
                "version_no": created.current_version_no,
                "diagnostics": _extract_diagnostics(validation_result),
                "code_check_summary": validation_result.get("summary"),
            }
            if _has_warning_diagnostics(response):
                response["message"] = "页面已创建，但发现布局警告。"
            if not await self._mark_succeeded(
                session,
                database_id=context.database_id,
                worker_id=worker_id,
                result=response,
            ):
                await session.rollback()
                raise AppException(
                    status_code=409,
                    code="AI_PAGE_MUTATION_LEASE_LOST",
                    detail="页面变更任务租约已失效。",
                )
            await session.commit()
        await self._run_final_write(save)

    async def _execute_apply(
        self,
        *,
        context: PageMutationExecutionContext,
        worker_id: str,
        progress: ProgressCallback,
        lease_lost: asyncio.Event | None,
    ) -> None:
        """准备候选源码并诊断，保存前重新检查页面版本和任务租约。"""

        if context.page_id is None or context.base_version_no is None:
            raise AppException(status_code=422, code="AI_PAGE_MUTATION_TARGET_REQUIRED", detail="页面修改缺少 page_id 或 base_version_no。")
        raw_edits = context.arguments.get("edits")
        if not isinstance(raw_edits, list):
            raise AppException(status_code=400, code="AI_SOURCE_EDITS_EMPTY", detail="edits 不能为空。")
        dependencies = {
            "workspace_id": context.workspace_id,
            "project_id": context.project_id,
        }
        edit_error: AppException | None = None
        async with self._session_factory() as session:
            current_page = await PageService(session).get(context.page_id, user_id=context.user_id)
            _ensure_page_in_context(current_page, dependencies)
            _ensure_page_base_version(current_page.current_version_no, context.base_version_no)
            try:
                edit_result = apply_source_edits(current_page.page_content, raw_edits)
            except AppException as exc:
                # 先退出读取 Session，再用独立短事务写 Job 结果；SQLite 不能在
                # 同一 Worker 保持旧读事务时升级为另一连接的写事务。
                edit_error = exc
                edit_result = None

        if edit_error is not None:
            await self._finish_without_page_write(
                database_id=context.database_id,
                worker_id=worker_id,
                result=build_code_check_failed_result(
                    code=edit_error.code,
                    message=edit_error.detail,
                    source="edits",
                ),
            )
            return
        if edit_result is None:  # pragma: no cover - 为类型与异常分支提供显式防线
            raise AppException(status_code=500, code="AI_SOURCE_EDITS_FAILED", detail="页面编辑结果生成失败。")

        async with self._session_factory() as session:
            validation_result = await CodeCheckService(session).check_page_code(
                page_id=context.page_id,
                workspace_id=context.workspace_id,
                user_id=context.user_id,
                content=edit_result.next_content,
            )
        self._raise_if_lease_lost(lease_lost)
        validation_result = _with_apply_validation_metadata(
            validation_result,
            canonical_diff=edit_result.canonical_diff,
            edits_applied=edit_result.applied_edit_count,
            message="页面代码校验失败，未保存页面版本。",
        )
        if not _is_validation_passed(validation_result):
            await self._finish_without_page_write(
                database_id=context.database_id,
                worker_id=worker_id,
                result=validation_result,
            )
            return

        await progress("saving")
        self._raise_if_lease_lost(lease_lost)

        async def save(session: AsyncSession) -> None:
            """在单个短事务内复核版本、写入新版本并同步收敛 Job。"""

            await self._lock_owned_job(session, context=context, worker_id=worker_id)
            await session.scalar(select(Page).where(Page.id == context.page_id).with_for_update())
            current_page = await PageService(session).get(context.page_id, user_id=context.user_id)
            _ensure_page_in_context(current_page, dependencies)
            _ensure_page_base_version(current_page.current_version_no, context.base_version_no)
            current_edit_result = apply_source_edits(current_page.page_content, raw_edits)
            updated_page = await PageService(session).update(
                context.page_id,
                PageUpdateRequest(
                    page_content=current_edit_result.next_content,
                    change_note=_optional_string(context.arguments.get("change_note")) or "AI 助手页面更新",
                ),
                context.user_id,
                commit=False,
            )
            response: dict[str, Any] = {
                "success": True,
                "message": "页面代码已更新并生成新版本。",
                "page_id": updated_page.id,
                "page_code": updated_page.code,
                "version_no": updated_page.current_version_no,
                "edits_applied": current_edit_result.applied_edit_count,
                "canonical_diff": current_edit_result.canonical_diff,
                "diagnostics": _extract_diagnostics(validation_result),
                "code_check_summary": validation_result.get("summary"),
            }
            if _has_warning_diagnostics(response):
                response["message"] = "页面代码已更新并生成新版本，但发现布局警告。"
            if not await self._mark_succeeded(
                session,
                database_id=context.database_id,
                worker_id=worker_id,
                result=response,
            ):
                await session.rollback()
                raise AppException(
                    status_code=409,
                    code="AI_PAGE_MUTATION_LEASE_LOST",
                    detail="页面变更任务租约已失效。",
                )
            await session.commit()
        await self._run_final_write(save)

    async def _run_final_write(self, operation: Callable[[AsyncSession], Awaitable[None]]) -> None:
        """对 SQLite 最终写入执行有限退避重试，其他数据库错误原样上抛。"""

        max_attempts = 3
        for attempt in range(max_attempts):
            session = self._session_factory()
            try:
                await operation(session)
                return
            except OperationalError as exc:
                await session.rollback()
                if not is_sqlite_lock_error(session, exc) or attempt + 1 >= max_attempts:
                    raise
                await asyncio.sleep(0.05 * (2**attempt))
            finally:
                await session.close()

    async def _lock_owned_job(
        self,
        session: AsyncSession,
        *,
        context: PageMutationExecutionContext,
        worker_id: str,
    ) -> tuple[AiPageMutationJob, AiAgentRun]:
        """锁定任务并复查 run 取消状态，作为最终页面写入的安全边界。"""

        row = (
            await session.execute(
                select(AiPageMutationJob, AiAgentRun)
                .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationJob.run_id)
                .where(
                    AiPageMutationJob.id == context.database_id,
                    AiPageMutationJob.status == "running",
                    AiPageMutationJob.worker_id == worker_id,
                    AiPageMutationJob.lease_expires_at.is_not(None),
                    AiPageMutationJob.lease_expires_at > utc_now(),
                )
                .with_for_update()
            )
        ).first()
        if row is None:
            raise AppException(status_code=409, code="AI_PAGE_MUTATION_LEASE_LOST", detail="页面变更任务租约已失效。")
        job, run = row
        if job.cancel_requested_at is not None or run.cancel_requested_at is not None or run.status in {"cancelled", "failed"}:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已取消。")
        user = await session.get(User, run.user_id)
        if user is None or user.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=403, code="AUTH_DISABLED", detail="执行页面变更的用户已被禁用或删除。")
        return job, run

    async def _finish_without_page_write(
        self,
        *,
        database_id: int,
        worker_id: str,
        result: Any,
    ) -> bool:
        """完成无需写页面的业务结果，并用拥有者条件防止旧 Worker 覆盖。"""

        async with self._session_factory() as session:
            return await self._mark_succeeded(
                session,
                database_id=database_id,
                worker_id=worker_id,
                result=result,
                commit=True,
            )

    @staticmethod
    async def _mark_succeeded(
        session: AsyncSession,
        *,
        database_id: int,
        worker_id: str,
        result: Any,
        commit: bool = False,
    ) -> bool:
        """仅由未过期租约所有者把 Job 收敛成功，防止迟到 Worker 写入页面。"""

        now = utc_now()
        return await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            require_not_cancelled=True,
            require_active_lease=True,
            commit=commit,
            values={
                "status": "succeeded",
                "result_json": result,
                "error_code": None,
                "error_message": None,
                "worker_id": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "finished_at": now,
                "updated_at": now,
            },
        )

    @staticmethod
    def _raise_if_lease_lost(lease_lost: asyncio.Event | None) -> None:
        """在慢诊断前后快速放弃已经失效的租约，避免无谓占用 Runtime/Chromium。"""

        if lease_lost is not None and lease_lost.is_set():
            raise AppException(
                status_code=409,
                code="AI_PAGE_MUTATION_LEASE_LOST",
                detail="页面变更任务租约已失效。",
            )


def _extract_diagnostics(result: dict[str, Any]) -> list[Any]:
    """读取代码检查诊断列表并过滤异常形态。"""

    diagnostics = result.get("diagnostics")
    return list(diagnostics) if isinstance(diagnostics, list) else []


def _optional_string(value: Any) -> str | None:
    """把可选工具参数转换为字符串，同时保留显式空字符串语义。"""

    return None if value is None else str(value)
