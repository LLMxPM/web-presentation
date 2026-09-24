"""文件功能：统一渲染协调器，负责公平调度、配额占用、派发、重试与结果落库。"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.db import metrics as write_path_metrics
from app.db.session import get_session_factory
from app.services.rendering.client import RendererClient
from app.services.rendering.credentials import RenderCredentialService
from app.services.rendering.repository import RenderRepository
from app.services.rendering.snapshot_service import RenderSnapshotService
from app.services.rendering.target_resolver import RenderTargetResolver
from render_contracts.constants import (
    PROTOCOL_VERSION,
    RUNTIME_RENDER_PROTOCOL_VERSION,
    SCHEDULE_CATEGORY_BACKGROUND,
    SCHEDULE_CATEGORY_INTERACTIVE,
)
from render_contracts.errors import (
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_PROFILE_MISMATCH,
    ERROR_CODE_RESULT_LOST,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    ERROR_CODE_WORKER_BUSY,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import ExecutionRequest, SnapshotRef, ViewportSpec
from render_contracts.tokens import AdmissionTicket, sha256_hex

logger = logging.getLogger(__name__)


class RenderCoordinator:
    """唯一渲染调度入口；事务内不做 HTTP，HTTP 失败不重复释放额度。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        client: RendererClient | None = None,
        target_resolver: RenderTargetResolver | None = None,
        credential_service: RenderCredentialService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.client = client or RendererClient(credential_service=credential_service)
        self.targets = target_resolver or RenderTargetResolver(self.settings)
        self.credentials = credential_service or RenderCredentialService(self.settings)
        self._prefer_category = SCHEDULE_CATEGORY_INTERACTIVE
        self._category_counter = 0
        self._last_progress_at = 0.0
        self._progress_lock = asyncio.Lock()

    async def ensure_progress(self, *, min_interval: float | None = None) -> int:
        """节流驱动一轮调度，避免大量等待方同时打满 tick。"""

        interval = float(
            min_interval
            if min_interval is not None
            else self.settings.render_scheduler_poll_interval_seconds
        )
        now = time.monotonic()
        if now - self._last_progress_at < interval:
            return 0
        async with self._progress_lock:
            now = time.monotonic()
            if now - self._last_progress_at < interval:
                return 0
            processed = await self.tick()
            self._last_progress_at = time.monotonic()
            return processed

    async def tick(self) -> int:
        """推进一轮调度：注册 Worker、派发、核对在途 attempt、回收过期租约。"""

        processed = 0
        try:
            async with self.session_factory() as session:
                repository = RenderRepository(session)
                await repository.expire_requests()
                await repository.release_expired_attempt_leases()
                await session.commit()
                await self._sync_workers(session, repository)
                await session.commit()
                processed += await self._cancel_active_attempts(session, repository)
                await session.commit()
                processed += await self._dispatch_once(session, repository)
                processed += await self._reconcile_running(session, repository)
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "渲染协调器调度轮次失败。",
                extra={"event": "render.coordinator.tick.failed"},
            )
        return processed

    async def run_forever(self, *, poll_interval: float | None = None) -> None:
        """后台持续调度，直到任务被取消。"""

        interval = float(poll_interval or self.settings.render_scheduler_poll_interval_seconds)
        logger.info(
            "渲染协调器后台任务已启动。",
            extra={"event": "render.coordinator.started", "poll_interval": interval},
        )
        while True:
            loop_token = write_path_metrics.bind_loop_name("render-coordinator")
            tick_started = time.perf_counter()
            try:
                await self.tick()
            finally:
                write_path_metrics.record_tick((time.perf_counter() - tick_started) * 1000.0)
                write_path_metrics.reset_loop_name(loop_token)
            await asyncio.sleep(max(0.05, interval))

    async def wait_for_terminal(
        self,
        request_id: int,
        *,
        timeout_seconds: float | None = None,
        drive_dispatch: bool = True,
    ) -> dict[str, Any]:
        """等待请求进入终态；可选在等待路径内驱动调度。"""

        deadline = utc_now() + timedelta(
            seconds=float(timeout_seconds or self.settings.render_request_timeout_seconds)
        )
        while utc_now() < deadline:
            if drive_dispatch:
                await self.ensure_progress()
            async with self.session_factory() as session:
                repository = RenderRepository(session)
                request = await repository.get_request(request_id)
                if request is None:
                    raise RenderExecutionError(
                        RenderError.from_code(
                            ERROR_CODE_RESULT_LOST,
                            message="渲染请求不存在。",
                            stage="wait",
                        )
                    )
                if request.status == "succeeded":
                    result = await repository.get_result_for_request(request_id)
                    if result is None:
                        raise RenderExecutionError(
                            RenderError.from_code(
                                ERROR_CODE_RESULT_LOST,
                                message="渲染请求成功但结果缺失。",
                                stage="wait",
                            )
                        )
                    payload = dict(result.payload or {})
                    payload["_object_refs"] = dict(result.object_refs or {})
                    return payload
                if request.status in {"failed", "cancelled", "expired"}:
                    error = RenderError.from_code(
                        request.error_code or ERROR_CODE_INTERNAL_ERROR,
                        message=request.error_message or "渲染请求失败。",
                        stage="wait",
                    )
                    raise RenderExecutionError(error)
            await asyncio.sleep(max(0.05, self.settings.render_wait_poll_interval_seconds))
        raise RenderExecutionError(
            RenderError.from_code(
                ERROR_CODE_DEADLINE_EXCEEDED,
                message="等待渲染结果超过总预算。",
                stage="wait",
            )
        )

    async def _sync_workers(self, session: AsyncSession, repository: RenderRepository) -> None:
        """把受信 Worker 配置与能力探测结果同步进数据库。"""

        endpoints = self.targets.worker_endpoints()
        profile_digest = str(self.settings.render_profile_digest or "")
        try:
            await repository.ensure_workers_from_config(
                [{"worker_id": item.worker_id, "base_url": item.base_url} for item in endpoints],
                profile_digest=profile_digest,
            )
        except Exception:  # noqa: BLE001
            logger.exception("登记 Renderer Worker 配置失败。", extra={"event": "render.worker.config.failed"})
            return
        # 能力探测是外部 HTTP；先提交配置登记，避免网络等待持有数据库事务。
        await session.commit()
        for endpoint in endpoints:
            try:
                capabilities = await self.client.fetch_capabilities(endpoint)
                if profile_digest:
                    self.client.validate_profile(capabilities, profile_digest)
                # 槽位状态未知时不得当作 idle，避免双派。
                slot_state = capabilities.slot_state
                if slot_state not in {"idle", "busy"}:
                    slot_state = "unknown"
                await repository.upsert_worker_heartbeat(
                    worker_id=capabilities.worker_id or endpoint.worker_id,
                    worker_epoch=capabilities.worker_epoch,
                    service_base_url=endpoint.base_url,
                    render_profile_digest=capabilities.render_profile_digest or profile_digest,
                    environment_summary=capabilities.environment_summary,
                    slot_state=slot_state,
                    slot_generation=capabilities.slot_generation,
                )
                await session.commit()
            except RenderExecutionError as exc:
                logger.warning(
                    "Renderer Worker 能力探测失败。",
                    extra={
                        "event": "render.worker.capabilities.failed",
                        "worker_id": endpoint.worker_id,
                        "error_code": exc.error.code,
                    },
                )

    async def _cancel_active_attempts(self, session: AsyncSession, repository: RenderRepository) -> int:
        """把 cancel_requested 下发到已占用 attempt 的 Renderer。"""

        attempts = await repository.list_cancelled_active_attempts()
        # 取消请求的查询完成后再调用外部 HTTP，避免长时间占用读事务。
        await session.commit()
        processed = 0
        for attempt in attempts:
            endpoint = self._endpoint_for_worker(attempt.worker_id)
            if endpoint is None:
                continue
            try:
                await self.client.cancel_execution(endpoint, attempt.attempt_uid)
                processed += 1
            except Exception:  # noqa: BLE001
                logger.warning(
                    "向 Renderer 下发取消失败。",
                    extra={"event": "render.cancel.dispatch.failed", "attempt_id": attempt.id},
                )
        return processed

    async def _dispatch_once(self, session: AsyncSession, repository: RenderRepository) -> int:
        """原子完成一次派发意图，并在事务外发送 HTTP。"""

        global_limit = int(self.settings.render_global_concurrency)
        workspace_limit = int(self.settings.render_workspace_concurrency)
        active = await repository.count_active_attempts()
        if active >= global_limit:
            return 0
        prefer_category = await repository.get_scheduler_state()
        # 工作空间额度已满时排除候选继续挑，避免单空间堵住全局派发。
        excluded: set[int] = set()
        request = None
        for _ in range(8):
            request = await repository.select_dispatch_candidate(
                prefer_category=str(prefer_category.cursor_category or self._prefer_category),
                exclude_request_ids=excluded or None,
            )
            if request is None:
                return 0
            ws_active = await repository.count_active_attempts(workspace_id=request.workspace_id)
            if ws_active < workspace_limit and not await repository.request_has_unreleased_attempt(request.id):
                break
            excluded.add(request.id)
            request = None
        if request is None:
            return 0
        workers = await repository.list_idle_workers()
        idle_worker = None
        for worker in workers:
            occupied = await self._worker_has_active_attempt(repository, worker.worker_id, worker.worker_epoch)
            if not occupied:
                idle_worker = worker
                break
        if idle_worker is None:
            return 0
        try:
            attempt = await repository.reserve_attempt(
                request=request,
                worker=idle_worker,
                request_digest=request.request_digest,
            )
            await repository.advance_scheduler_cursor(
                workspace_id=request.workspace_id,
                request_id=request.id,
            )
            await repository.flip_scheduler_category()
            await session.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "渲染 attempt 保留冲突，跳过本轮派发。",
                extra={"event": "render.reserve.conflict", "request_id": request.id},
            )
            await session.rollback()
            return 0
        return await self._dispatch_attempt(attempt.id)

    async def _dispatch_attempt(self, attempt_id: int) -> int:
        """条件更新为 dispatched 后发送请求；未接管则释放并重排。"""

        async with self.session_factory() as session:
            repository = RenderRepository(session)
            attempt = await repository.get_attempt(attempt_id)
            request = await repository.get_request(attempt.request_id) if attempt else None
            if attempt is None or request is None:
                return 0
            endpoint = self._endpoint_for_worker(attempt.worker_id)
            if endpoint is None:
                await repository.fail_attempt(
                    request=request,
                    attempt=attempt,
                    error_code=ERROR_CODE_SERVICE_UNAVAILABLE,
                    error_message="找不到受信 Renderer Worker 地址。",
                    retryable=True,
                    retry_after=utc_now() + timedelta(seconds=2),
                    release_slot=True,
                    terminal=False,
                )
                await session.commit()
                return 0
            try:
                # 能力探测发生在 attempt 状态写入前，先结束读取事务再访问 Worker。
                await session.commit()
                capabilities = await self.client.fetch_capabilities(endpoint)
                self.client.validate_profile(capabilities, request.render_profile_digest)
                execution_request = self._build_execution_request(request=request, attempt=attempt)
                dispatched = await repository.mark_attempt_dispatched(
                    attempt.id,
                    worker_id=attempt.worker_id or "",
                    worker_epoch=attempt.worker_epoch or "",
                )
                if not dispatched:
                    await session.commit()
                    return 0
                await session.commit()
                receipt = await self.client.dispatch_execution(endpoint, execution_request)
                async with self.session_factory() as update_session:
                    update_repo = RenderRepository(update_session)
                    # 条件更新 dispatched→accepted，禁止复活已被收敛的终态 attempt。
                    accepted = await update_repo.mark_attempt_accepted(
                        attempt.id,
                        request_digest=receipt.request_digest,
                    )
                    if accepted:
                        await update_repo.extend_attempt_lease(attempt.id)
                    await update_session.commit()
                return 1
            except RenderExecutionError as exc:
                # 仅在明确未接管时释放占用；响应超时等未知结果必须保留占用，避免双派。
                release = _is_definitely_not_taken(exc)
                await repository.fail_attempt(
                    request=request,
                    attempt=attempt,
                    error_code=exc.error.code,
                    error_message=exc.error.message,
                    retryable=exc.error.retryable,
                    retry_after=utc_now() + timedelta(seconds=2 * max(1, attempt.attempt_no)),
                    release_slot=release,
                    terminal=not exc.error.retryable,
                )
                await session.commit()
                return 1
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "渲染 attempt 派发出现未预期异常。",
                    extra={"event": "render.dispatch.unexpected", "attempt_id": attempt.id},
                )
                await repository.fail_attempt(
                    request=request,
                    attempt=attempt,
                    error_code=ERROR_CODE_INTERNAL_ERROR,
                    error_message=str(exc),
                    retryable=True,
                    retry_after=utc_now() + timedelta(seconds=2 * max(1, attempt.attempt_no)),
                    release_slot=False,
                    terminal=False,
                )
                await session.commit()
                return 1

    async def _reconcile_running(self, session: AsyncSession, repository: RenderRepository) -> int:
        """查询已派发/运行中的 attempt，完成结果落库或隔离。"""

        from sqlalchemy import select

        from app.models.render_attempt import RenderAttempt

        rows = list(
            (
                await session.execute(
                    select(RenderAttempt.id, RenderAttempt.worker_id, RenderAttempt.worker_epoch, RenderAttempt.attempt_uid)
                    .where(RenderAttempt.status.in_(("dispatched", "accepted", "running", "cleaning", "unknown")))
                    .where(RenderAttempt.active_occupancy == 1)
                    .limit(20)
                )
            ).all()
        )
        # 后续状态查询与产物下载走独立会话；这里先释放行查询事务。
        await session.commit()
        processed = 0
        for attempt_id, worker_id, worker_epoch, attempt_uid in rows:
            endpoint = self._endpoint_for_worker(worker_id)
            if endpoint is None:
                continue
            try:
                receipt = await self.client.fetch_execution(endpoint, attempt_uid)
            except RenderExecutionError as exc:
                if exc.error.code == ERROR_CODE_RESULT_LOST:
                    await self._fail_unknown_attempt(
                        attempt_id=attempt_id,
                        error_code=ERROR_CODE_RESULT_LOST,
                        error_message="Renderer 不认识该 attempt（可能已重启），释放占用。",
                        retryable=True,
                        release_slot=True,
                    )
                    processed += 1
                else:
                    # 网络/服务不可用时延长租约，等待下一轮核对；租约超时由
                    # release_expired_attempt_leases 兜底收敛，避免容量永久泄漏。
                    async with self.session_factory() as lease_session:
                        lease_repo = RenderRepository(lease_session)
                        await lease_repo.extend_attempt_lease(attempt_id)
                        await lease_session.commit()
                continue
            if receipt.status in {"accepted", "running", "cleaning"}:
                async with self.session_factory() as lease_session:
                    lease_repo = RenderRepository(lease_session)
                    await lease_repo.extend_attempt_lease(attempt_id)
                    await lease_session.commit()
                continue
            async with self.session_factory() as result_session:
                # materialize 前会 commit 结束读事务；关闭 expire_on_commit，
                # 避免访问已加载实体时重新开事务，导致 HTTP 仍占用数据库事务。
                result_session.expire_on_commit = False
                result_repo = RenderRepository(result_session)
                attempt = await result_repo.get_attempt(attempt_id)
                request = await result_repo.get_request(attempt.request_id) if attempt else None
                if attempt is None or request is None:
                    continue
                # 失败/取消必须优先于成功分支：Renderer 历史回执可能把失败也标成 terminal。
                if receipt.error:
                    error = receipt.error
                    await result_repo.fail_attempt(
                        request=request,
                        attempt=attempt,
                        error_code=str(error.get("code") or ERROR_CODE_INTERNAL_ERROR),
                        error_message=str(error.get("message") or "渲染执行失败。"),
                        retryable=bool(error.get("retryable", True)),
                        retry_after=utc_now() + timedelta(seconds=2 * max(1, attempt.attempt_no)),
                        release_slot=receipt.resource_state == "released",
                        terminal=not bool(error.get("retryable", True)),
                    )
                    await result_session.commit()
                    processed += 1
                    continue
                is_success_status = receipt.status in {"succeeded", "success"} or (
                    receipt.status == "terminal" and bool(receipt.result_descriptor)
                )
                if is_success_status:
                    if not receipt.result_descriptor:
                        await result_repo.fail_attempt(
                            request=request,
                            attempt=attempt,
                            error_code=ERROR_CODE_RESULT_LOST,
                            error_message="Renderer 返回成功但缺少结果描述。",
                            retryable=True,
                            retry_after=utc_now() + timedelta(seconds=1),
                            release_slot=receipt.resource_state == "released",
                            terminal=False,
                        )
                        await result_session.commit()
                        continue
                    # 先结束读取事务：materialize 含 HTTP/对象存储写入，禁止占用数据库事务。
                    await result_session.commit()
                    try:
                        result_payload = await self._materialize_result(
                            endpoint=endpoint,
                            request=request,
                            attempt=attempt,
                            receipt=receipt,
                        )
                    except RenderExecutionError as exc:
                        await result_repo.fail_attempt(
                            request=request,
                            attempt=attempt,
                            error_code=exc.error.code,
                            error_message=exc.error.message,
                            retryable=True,
                            retry_after=utc_now() + timedelta(seconds=1),
                            release_slot=receipt.resource_state == "released",
                            terminal=False,
                        )
                        await result_session.commit()
                        continue
                    saved = await result_repo.save_result(
                        request=request,
                        attempt=attempt,
                        payload=result_payload["payload"],
                        object_refs=result_payload["object_refs"],
                        environment_summary=result_payload["environment_summary"],
                        input_digest=str(request.input_digest),
                        render_profile_digest=str(request.render_profile_digest),
                        request_digest=str(request.request_digest),
                    )
                    if saved is None:
                        # 条件更新失败说明 attempt 已被其它路径收敛，不得确认消费。
                        logger.warning(
                            "渲染结果落库条件更新失败，跳过消费确认。",
                            extra={"event": "render.result.save.conflict", "attempt_id": attempt_id},
                        )
                        continue
                    await result_session.commit()
                    await self.client.confirm_result_consumption(endpoint, attempt_uid)
                    processed += 1
                else:
                    error = receipt.error or {"code": ERROR_CODE_INTERNAL_ERROR, "message": "渲染执行失败。"}
                    await result_repo.fail_attempt(
                        request=request,
                        attempt=attempt,
                        error_code=str(error.get("code") or ERROR_CODE_INTERNAL_ERROR),
                        error_message=str(error.get("message") or "渲染执行失败。"),
                        retryable=bool(error.get("retryable", True)),
                        retry_after=utc_now() + timedelta(seconds=2 * max(1, attempt.attempt_no)),
                        release_slot=receipt.resource_state == "released",
                        terminal=not bool(error.get("retryable", True)),
                    )
                    await result_session.commit()
                    processed += 1
        return processed

    async def _materialize_result(
        self,
        *,
        endpoint: Any,
        request: Any,
        attempt: Any,
        receipt: Any,
    ) -> dict[str, Any]:
        """校验 digest 并把产物写入对象存储，形成有界结果 payload（不含原始字节）。"""

        from app.services.object_storage_service import ObjectStorageService

        descriptor = dict(receipt.result_descriptor or {})
        result_payload = dict(descriptor.get("result") or descriptor)
        if result_payload.get("request_digest") and result_payload["request_digest"] != request.request_digest:
            raise RenderExecutionError(
                RenderError.from_code(
                    ERROR_CODE_RESULT_LOST,
                    message="Renderer 结果 request_digest 与请求不一致。",
                    stage="commit",
                )
            )
        object_storage = ObjectStorageService()
        object_refs: dict[str, Any] = {}
        artifacts = list(result_payload.get("artifacts") or [])
        workspace_id = request.workspace_id
        max_bytes = int(self.settings.render_artifact_max_bytes)
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_CONTRACT_MISMATCH,
                        message="Renderer 返回了非法产物描述。",
                        stage="commit",
                    )
                )
            name = str(artifact.get("name") or "")
            if not name or "/" in name or "\\" in name or name in {".", ".."}:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_CONTRACT_MISMATCH,
                        message="Renderer 返回了非法产物名称。",
                        stage="commit",
                    )
                )
            expected_len = int(artifact.get("byte_length") or 0)
            if expected_len > max_bytes:
                raise RenderExecutionError(
                    RenderError.from_code(
                        "RENDER_OUTPUT_LIMIT_EXCEEDED",
                        message=f"产物 {name} 超过大小上限。",
                        stage="commit",
                    )
                )
            content = await self.client.fetch_artifact(endpoint, attempt.attempt_uid, name)
            if len(content) > max_bytes:
                raise RenderExecutionError(
                    RenderError.from_code(
                        "RENDER_OUTPUT_LIMIT_EXCEEDED",
                        message=f"产物 {name} 实际大小超过上限。",
                        stage="commit",
                    )
                )
            sha = sha256_hex(content)
            expected = str(artifact.get("sha256") or "")
            if expected and sha != expected:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_RESULT_LOST,
                        message=f"产物 {name} 摘要校验失败。",
                        stage="commit",
                    )
                )
            storage_key = await object_storage.put_object(
                f"render-results/{workspace_id}/{request.id}/{attempt.id}/{name}",
                content=content,
                content_type=str(artifact.get("content_type") or "application/octet-stream"),
            )
            object_refs[name] = {
                "workspace_id": workspace_id,
                "request_id": request.id,
                "attempt_id": attempt.id,
                "sha256": sha,
                "byte_length": len(content),
                "content_type": str(artifact.get("content_type") or "application/octet-stream"),
                "storage_key": storage_key,
            }
        return {
            "payload": result_payload,
            "object_refs": object_refs,
            "environment_summary": dict(result_payload.get("environment_summary") or {}),
        }

    async def _fail_unknown_attempt(
        self,
        *,
        attempt_id: int,
        error_code: str,
        error_message: str,
        retryable: bool,
        release_slot: bool,
    ) -> None:
        """收敛结果未知的 attempt，必要时释放占用并重排请求。"""

        async with self.session_factory() as session:
            repository = RenderRepository(session)
            attempt = await repository.get_attempt(attempt_id)
            request = await repository.get_request(attempt.request_id) if attempt else None
            if attempt is None or request is None:
                return
            await repository.fail_attempt(
                request=request,
                attempt=attempt,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                retry_after=utc_now() + timedelta(seconds=1),
                release_slot=release_slot,
                terminal=False,
            )
            await session.commit()

    def _build_execution_request(self, *, request: Any, attempt: Any) -> ExecutionRequest:
        """把持久化请求与 attempt 转为契约执行请求。"""

        snapshot_ref = SnapshotRef.from_dict(dict(request.snapshot_ref or {}))
        viewport = ViewportSpec.from_dict(dict(request.viewport or {}))
        secret = self.credentials.load_secret()
        now = utc_now()
        deadline_at = request.deadline_at if request.deadline_at.tzinfo else request.deadline_at.replace(tzinfo=UTC)
        remaining_ms = max(1, int((deadline_at - now).total_seconds() * 1000))
        stop_by = deadline_at
        accept_before = now + timedelta(seconds=min(30, remaining_ms / 1000))
        ticket = AdmissionTicket.issue(
            secret=secret,
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            worker_id=attempt.worker_id or "",
            worker_epoch=attempt.worker_epoch or "",
            slot_generation=attempt.slot_generation,
            accept_before=accept_before,
            stop_by=stop_by,
            attempt_id=attempt.attempt_uid,
            ticket_id=secrets.token_urlsafe(12),
        )
        from render_contracts.tokens import PreviewAccess as PreviewAccessType

        snap = dict(request.snapshot_ref or {})
        # 基于快照密文解出预览访问授权，避免明文 token 依赖会话再次读取。
        credentials = self.credentials.decrypt_sensitive_payload(str(snap.get("preview_credentials") or ""))
        preview_token = str(credentials.get("preview_token") or "")
        preview_url = str(credentials.get("preview_url") or "").strip()
        extra_http_headers = (
            {str(k): str(v) for k, v in dict(credentials["extra_http_headers"]).items()}
            if isinstance(credentials.get("extra_http_headers"), dict)
            else None
        )
        if preview_url:
            navigation_url = _ensure_render_identity_query(
                preview_url,
                input_digest=request.input_digest,
                artifact_id=str(snap.get("artifact_id") or ""),
            )
        else:
            navigation_url = RenderSnapshotService.build_preview_navigation_url(
                navigation_base_url=self.targets.navigation_base_url(),
                artifact_id=str(snap.get("artifact_id") or ""),
                preview_token=preview_token,
                input_digest=request.input_digest,
            )
        preview_access = PreviewAccessType(
            navigation_base_url=navigation_url,
            preview_token=preview_token,
            artifact_id=str(snap.get("artifact_id") or ""),
            expires_at=str(snap.get("expires_at") or ""),
            runtime_protocol_version=RUNTIME_RENDER_PROTOCOL_VERSION,
            asset_base_url=self.targets.asset_base_url(),
            platform_asset_base_url=self.targets.platform_asset_base_url(),
            extra_http_headers=extra_http_headers,
        )
        return ExecutionRequest(
            contract_version=PROTOCOL_VERSION,
            operation=request.operation,
            request_id=str(request.id),
            attempt_id=attempt.attempt_uid,
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            trace_id=request.trace_id or str(uuid.uuid4()),
            snapshot_ref=snapshot_ref,
            input_digest=request.input_digest,
            render_profile_digest=request.render_profile_digest,
            viewport=viewport,
            operation_options=dict(request.operation_options or {}),
            deadline_at=deadline_at.isoformat().replace("+00:00", "Z"),
            remaining_budget_ms=remaining_ms,
            admission_ticket=ticket,
            preview_access=preview_access,
            render_category=request.schedule_category or SCHEDULE_CATEGORY_BACKGROUND,
        )

    def _endpoint_for_worker(self, worker_id: str | None):
        """按受信配置解析 Worker 地址。"""

        if not worker_id:
            return None
        for endpoint in self.targets.worker_endpoints():
            if endpoint.worker_id == worker_id:
                return endpoint
        return None

    def _advance_category_cursor(self) -> None:
        """按交互 3 : 后台 1 推进类别轮转。"""

        self._category_counter += 1
        if self._category_counter >= 4:
            self._category_counter = 0
            self._prefer_category = SCHEDULE_CATEGORY_BACKGROUND
        else:
            self._prefer_category = SCHEDULE_CATEGORY_INTERACTIVE

    async def _worker_has_active_attempt(
        self,
        repository: RenderRepository,
        worker_id: str,
        worker_epoch: str,
    ) -> bool:
        """判断 Worker/epoch 是否仍有未释放占用。"""

        from sqlalchemy import select

        from app.models.render_attempt import RenderAttempt
        from render_contracts.constants import ATTEMPT_OCCUPYING_STATUSES

        stmt = select(RenderAttempt.id).where(
            RenderAttempt.worker_id == worker_id,
            RenderAttempt.worker_epoch == worker_epoch,
            RenderAttempt.active_occupancy == 1,
            RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
        ).limit(1)
        return await repository.session.scalar(stmt) is not None


def _ensure_render_identity_query(preview_url: str, *, input_digest: str, artifact_id: str) -> str:
    """在已有预览 URL 上补齐 input_digest 与 artifact 查询参数，供 render-ready.v1 硬核对。

    Runtime 从 location.search 读取 artifact/input_digest 写入协议桥；仅放请求头
    会导致 bridge.artifactId 为空，Renderer 校验失败。
    """

    if not input_digest and not artifact_id:
        return preview_url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(preview_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        changed = False
        if input_digest and query.get("input_digest") != input_digest:
            query["input_digest"] = input_digest
            changed = True
        if artifact_id and query.get("artifact") != artifact_id:
            query["artifact"] = artifact_id
            changed = True
        if not changed:
            return preview_url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:  # noqa: BLE001
        return preview_url


def _ensure_input_digest_query(preview_url: str, input_digest: str) -> str:
    """兼容入口：仅补齐 input_digest。"""

    return _ensure_render_identity_query(preview_url, input_digest=input_digest, artifact_id="")


def _is_definitely_not_taken(exc: RenderExecutionError) -> bool:
    """判断错误是否明确表示 Renderer 未接管该 attempt。

    4xx（忙、契约/票据拒绝、digest 冲突）发生在 accept 之前，必须释放占用；
    连接建立失败说明请求未到达 Worker，也可安全释放。读超时等已发出的失败不得释放。
    """

    import httpx

    not_taken_codes = {
        ERROR_CODE_WORKER_BUSY,
        ERROR_CODE_CONTRACT_MISMATCH,
        ERROR_CODE_PROFILE_MISMATCH,
    }
    if exc.error.code in not_taken_codes:
        return True
    http_status = getattr(exc, "http_status", None)
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return True
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, (httpx.ConnectError, httpx.ConnectTimeout)):
        return True
    if isinstance(cause, httpx.HTTPStatusError):
        status = cause.response.status_code
        return 400 <= status < 500
    return False


_DEFAULT_COORDINATOR: RenderCoordinator | None = None


def get_render_coordinator() -> RenderCoordinator:
    """获取进程内默认协调器实例。"""

    global _DEFAULT_COORDINATOR
    if _DEFAULT_COORDINATOR is None:
        _DEFAULT_COORDINATOR = RenderCoordinator()
    return _DEFAULT_COORDINATOR
