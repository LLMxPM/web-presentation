"""文件功能：创建与查询不可变渲染请求，保证业务阶段幂等。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.render_request import RenderRequest
from app.services.rendering.repository import RenderRepository
from render_contracts.constants import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    OPERATION_PAGE_CAPTURE,
    OPERATION_PAGE_DIAGNOSE,
    REQUEST_TERMINAL_STATUSES,
    SCHEDULE_CATEGORY_BACKGROUND,
    SCHEDULE_CATEGORY_INTERACTIVE,
)
from render_contracts.tokens import compute_render_digest, compute_request_key

logger = logging.getLogger(__name__)

_CATEGORY_BY_OPERATION = {
    OPERATION_PAGE_CAPTURE: SCHEDULE_CATEGORY_BACKGROUND,
    OPERATION_PAGE_DIAGNOSE: SCHEDULE_CATEGORY_INTERACTIVE,
}


class RenderRequestService:
    """渲染请求服务：输入快照、幂等键、取消与查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RenderRepository(session)
        self.settings = get_settings()

    async def get_or_create_request(
        self,
        *,
        logical_owner_key: str,
        business_stage: str,
        operation: str,
        workspace_id: int,
        project_id: int | None,
        page_id: int | None,
        component_id: str | None,
        owner_kind: str,
        owner_ref: str | None,
        snapshot_ref: dict[str, Any],
        input_digest: str,
        operation_options: dict[str, Any],
        viewport: dict[str, Any],
        render_profile_digest: str,
        trace_id: str,
        created_by: int | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
    ) -> tuple[Any, bool]:
        """按逻辑 owner 取回同一请求，或创建新请求。

        成功结果与未终态请求直接复用；failed/expired/cancelled 允许以递增
        generation 创建新请求，避免幂等键把业务重试永久粘在旧失败上。
        """

        render_digest = compute_render_digest(
            render_profile_digest=render_profile_digest,
            viewport=viewport,
            operation_options=operation_options,
        )
        generation = 0
        while True:
            owner_key_for_digest = (
                logical_owner_key if generation == 0 else f"{logical_owner_key}#{generation}"
            )
            request_key = compute_request_key(
                owner_key=owner_key_for_digest,
                business_stage=business_stage,
                operation=operation,
                input_digest=input_digest,
                render_digest=render_digest,
            )
            existing = await self.repository.get_request_by_key(
                logical_owner_key=logical_owner_key,
                business_stage=business_stage,
                operation=operation,
                request_key=request_key,
            )
            if existing is None:
                break
            if existing.status == "succeeded":
                result = await self.repository.get_result_for_request(existing.id)
                if result is not None:
                    return existing, False
                # succeeded 但结果缺失视为坏数据，允许 generation 重建，避免幂等粘死。
                generation += 1
                if generation > 64:
                    raise AppException(
                        status_code=500,
                        code="RENDER_INTERNAL_ERROR",
                        detail="渲染请求重试代次异常，请检查历史渲染请求状态。",
                    )
                continue
            if existing.status not in REQUEST_TERMINAL_STATUSES:
                return existing, False
            generation += 1
            if generation > 64:
                raise AppException(
                    status_code=500,
                    code="RENDER_INTERNAL_ERROR",
                    detail="渲染请求重试代次异常，请检查历史渲染请求状态。",
                )

        # 先锁定全局调度状态，保证容量检查与后续 INSERT 在同一写事务内串行化。
        await self.repository.lock_scheduler_state_for_queue_admission()
        queue_size = await self.repository.count_queued_requests()
        workspace_queue = await self.repository.count_queued_requests(workspace_id=workspace_id)
        if queue_size >= self.settings.render_queue_size:
            raise AppException(
                status_code=429,
                code="RENDER_QUEUE_FULL",
                detail="渲染队列已满，请稍后重试。",
            )
        if workspace_queue >= self.settings.render_workspace_queue_size:
            raise AppException(
                status_code=429,
                code="RENDER_QUEUE_FULL",
                detail="当前工作空间渲染队列已满，请稍后重试。",
            )

        timeout = float(timeout_seconds or self.settings.render_request_timeout_seconds or DEFAULT_REQUEST_TIMEOUT_SECONDS)
        request = RenderRequest(
            logical_owner_key=logical_owner_key,
            business_stage=business_stage,
            operation=operation,
            schedule_category=_CATEGORY_BY_OPERATION.get(operation, SCHEDULE_CATEGORY_BACKGROUND),
            workspace_id=workspace_id,
            project_id=project_id,
            page_id=page_id,
            component_id=component_id,
            owner_kind=owner_kind,
            owner_ref=owner_ref,
            request_key=request_key,
            status="queued",
            input_digest=input_digest,
            render_digest=render_digest,
            request_digest=request_key,
            snapshot_ref=snapshot_ref,
            operation_options=dict(operation_options or {}),
            viewport=viewport,
            render_profile_digest=render_profile_digest,
            deadline_at=utc_now() + timedelta(seconds=timeout),
            max_attempts=int(max_attempts or self.settings.render_max_attempts or DEFAULT_MAX_ATTEMPTS),
            attempt_count=0,
            cancel_version=0,
            cancel_requested=False,
            trace_id=trace_id,
            claim_generation=generation,
            created_by=created_by,
        )
        # 使用 SAVEPOINT，避免并发冲突时回滚调用方整笔未提交事务。
        try:
            async with self.session.begin_nested():
                self.session.add(request)
                await self.session.flush()
        except IntegrityError:
            existing = await self.repository.get_request_by_key(
                logical_owner_key=logical_owner_key,
                business_stage=business_stage,
                operation=operation,
                request_key=request_key,
            )
            if existing is not None:
                return existing, False
            raise
        logger.info(
            "已创建渲染请求。",
            extra={
                "event": "render.request.created",
                "request_id": request.id,
                "operation": operation,
                "workspace_id": workspace_id,
                "trace_id": trace_id,
            },
        )
        return request, True

    async def cancel_request(self, request_id: int) -> Any:
        """取消渲染请求并返回更新后的记录。"""

        request = await self.repository.cancel_request(request_id)
        if request is None:
            raise AppException(status_code=404, code="RENDER_REQUEST_NOT_FOUND", detail="渲染请求不存在。")
        return request

    async def get_request(self, request_id: int) -> Any:
        """读取渲染请求。"""

        request = await self.repository.get_request(request_id)
        if request is None:
            raise AppException(status_code=404, code="RENDER_REQUEST_NOT_FOUND", detail="渲染请求不存在。")
        return request

    async def get_result_payload(self, request_id: int) -> dict[str, Any] | None:
        """读取请求结果 payload。"""

        result = await self.repository.get_result_for_request(request_id)
        if result is None:
            return None
        return dict(result.payload or {})

    async def mark_result_consumed(self, request_id: int) -> None:
        """业务消费后标记结果。"""

        result = await self.repository.get_result_for_request(request_id)
        if result is not None:
            await self.repository.mark_result_consumed(result.id)
