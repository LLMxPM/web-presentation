"""文件功能：单槽执行控制：接管、取消标记、回执、幂等与临时产物。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wp_renderer.config import get_renderer_settings
from render_contracts.constants import (
    ATTEMPT_STATUS_ACCEPTED,
    ATTEMPT_STATUS_CLEANING,
    ATTEMPT_STATUS_RUNNING,
    ATTEMPT_STATUS_TERMINAL,
    RESOURCE_STATE_RELEASED,
    RESOURCE_STATE_RETAINED,
)
from render_contracts.errors import (
    ERROR_CODE_BROWSER_LOST,
    ERROR_CODE_CANCELLED,
    ERROR_CODE_DEADLINE_EXCEEDED,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import ExecutionReceipt, ExecutionRequest, ExecutionResult

logger = logging.getLogger(__name__)

# 回执/取消标记历史上限，防止内存无界增长。
_MAX_HISTORY_ENTRIES = 512


@dataclass
class SlotExecution:
    """当前槽位上的一次 attempt 执行状态。"""

    request: ExecutionRequest
    accepted_at: datetime
    stage: str = ATTEMPT_STATUS_ACCEPTED
    resource_state: str = RESOURCE_STATE_RETAINED
    cancel_requested: bool = False
    result: ExecutionResult | None = None
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cleaned_at: datetime | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)
    consumed: bool = False
    # 接管时快照的 slot generation，回执不得读取运行中的 live generation。
    slot_generation: int = 0


class SlotController:
    """一个 Renderer 实例一个活动槽位；忙时明确拒绝且不接管。"""

    def __init__(self, *, worker_id: str, worker_epoch: str) -> None:
        self.settings = get_renderer_settings()
        self.worker_id = worker_id
        self.worker_epoch = worker_epoch
        self.slot_generation = 0
        self._lock = asyncio.Lock()
        self._current: SlotExecution | None = None
        self._receipts: dict[str, SlotExecution] = {}
        self._cancellations: dict[str, datetime] = {}
        self._recycled: dict[str, datetime] = {}
        self._task: asyncio.Task[None] | None = None
        self._executor: Any | None = None
        self._ttl_task: asyncio.Task[None] | None = None

    @property
    def busy(self) -> bool:
        """槽位是否占用中。"""

        return self._current is not None

    def capabilities(self) -> dict[str, Any]:
        """返回能力与槽位状态。"""

        return {
            "worker_id": self.worker_id,
            "worker_epoch": self.worker_epoch,
            "protocol_version": self.settings.protocol_version,
            "runtime_render_protocol_version": self.settings.runtime_protocol_version,
            "result_schema_version": self.settings.result_schema_version,
            "render_profile_digest": self.settings.render_profile_digest,
            "environment_summary": {
                "platform": "linux-container",
                "playwright_mode": "async",
                "chromium": "launched-per-attempt",
            },
            "limits": {
                "max_png_bytes": self.settings.max_png_bytes,
                "max_diagnostics_json_bytes": self.settings.max_diagnostics_json_bytes,
                "max_component_scenarios": self.settings.max_component_scenarios,
                "max_canvas_pixels": self.settings.max_canvas_pixels,
                "max_canvas_edge": self.settings.max_canvas_edge,
            },
            "slot_state": "busy" if self.busy else "idle",
            "slot_generation": self.slot_generation,
        }

    async def accept(self, request: ExecutionRequest) -> tuple[int, ExecutionReceipt | None]:
        """接管 attempt；返回 (status_code, receipt)。"""

        self.sweep_expired_artifacts()
        existing = self._receipts.get(request.attempt_id)
        if existing is not None:
            # 已接管的重复 POST 必须先走幂等回执，不应因原票据过期而变成 403。
            if existing.request.request_digest != request.request_digest:
                return 409, None
            return 202, self._build_receipt(existing)
        request.validate()
        # Backend 发票绑定「接管后」generation = worker.slot_generation + 1；严格相等校验。
        expected_generation = self.slot_generation + 1
        ticket_error = self._validate_admission_ticket(request, expected_generation=expected_generation)
        if ticket_error is not None:
            return 403, ticket_error
        if request.attempt_id in self._cancellations:
            # 取消先于 POST 到达：记录标记，不启动浏览器。
            receipt = self._mark_precancel(request, slot_generation=expected_generation)
            return 202, receipt
        async with self._lock:
            if self.busy or self._task is not None:
                return 429, None
            # 校验通过且真正接管后再提交 generation，写入执行快照。
            self.slot_generation = expected_generation
            execution = SlotExecution(
                request=request,
                accepted_at=datetime.now(UTC),
                slot_generation=expected_generation,
            )
            self._current = execution
            self._receipts[request.attempt_id] = execution
            self._ensure_ttl_sweep()
            self._task = asyncio.create_task(
                self._run_execution(execution),
                name=f"render-attempt-{request.attempt_id}",
            )
        return 202, self._build_receipt(execution)

    def _validate_admission_ticket(self, request: ExecutionRequest, *, expected_generation: int):
        """校验接入票据签名与绑定；失败时返回错误回执，不接管执行。"""

        from render_contracts.errors import RenderContractError

        try:
            # 票据绑定「本次接管后」的 slot generation；与 Backend 侧
            # attempt.slot_generation = worker.slot_generation + 1 严格相等对齐。
            request.admission_ticket.validate(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                attempt_id=request.attempt_id,
                secret=self.settings.credential_secret,
                worker_id=self.worker_id,
                worker_epoch=self.worker_epoch,
                slot_generation=expected_generation,
            )
        except RenderContractError as exc:
            return ExecutionReceipt(
                attempt_id=request.attempt_id,
                request_id=request.request_id,
                worker_id=self.worker_id,
                worker_epoch=self.worker_epoch,
                slot_generation=self.slot_generation,
                request_digest=request.request_digest,
                status=ATTEMPT_STATUS_TERMINAL,
                resource_state=RESOURCE_STATE_RELEASED,
                accepted_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                stage=ATTEMPT_STATUS_TERMINAL,
                error=RenderError.from_code(
                    "RENDER_CONTRACT_MISMATCH",
                    message=str(exc),
                    stage="admission",
                ).to_dict(),
            )
        return None

    def get_execution(self, attempt_id: str) -> SlotExecution | None:
        """读取回执状态。"""

        return self._receipts.get(attempt_id)

    def was_recycled(self, attempt_id: str) -> bool:
        """判断 attempt 是否曾存在但已被 TTL/消费回收（用于 410）。"""

        self._prune_recycled()
        return attempt_id in self._recycled

    def request_cancel(self, attempt_id: str) -> bool:
        """记录幂等取消标记，并尝试关闭执行器以打断 Playwright 等待。"""

        self._cancellations[attempt_id] = datetime.now(UTC)
        self._prune_cancellations()
        execution = self._receipts.get(attempt_id)
        if execution is not None:
            execution.cancel_requested = True
            self._interrupt_execution(execution)
            return True
        return False

    def _interrupt_execution(self, execution: SlotExecution) -> None:
        """触发 executor.shutdown() 关闭 context/browser，解除进行中的等待。"""

        executor = self._executor
        if executor is None or self._current is not execution:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._shutdown_executor(executor), name=f"cancel-shutdown-{execution.request.attempt_id}")

    async def _shutdown_executor(self, executor: Any) -> None:
        """安全调用执行器关闭；异常只记日志。"""

        try:
            await executor.shutdown()
        except Exception:  # noqa: BLE001
            logger.warning("取消路径关闭执行器失败。", exc_info=True)

    def mark_consumed(self, attempt_id: str) -> bool:
        """Backend 确认结果持久化后提前释放临时产物。"""

        execution = self._receipts.get(attempt_id)
        if execution is None:
            return False
        execution.consumed = True
        self._cleanup_artifacts(execution)
        execution.resource_state = RESOURCE_STATE_RELEASED
        self._remember_recycled(attempt_id)
        return True

    def artifact_path(self, attempt_id: str, name: str) -> Path | None:
        """返回有界产物路径；name 仅允许安全文件名，且来自结果描述符允许集合。"""

        if not _is_safe_artifact_name(name):
            return None
        execution = self._receipts.get(attempt_id)
        if execution is None:
            return None
        self._maybe_expire_artifacts(execution)
        return execution.artifacts.get(name)

    def build_receipt(self, execution: SlotExecution) -> ExecutionReceipt:
        """构建稳定回执。"""

        return self._build_receipt(execution)

    def sweep_expired_artifacts(self) -> None:
        """扫描并回收过期未消费产物，同时裁剪历史回执。"""

        # 必须先清理产物，再裁剪回执；否则回执被移除后将失去 artifact 路径，
        # 过期的成功结果会永久遗留在 Renderer 工作目录中。
        for execution in list(self._receipts.values()):
            self._maybe_expire_artifacts(execution)
        self._prune_history()

    def _mark_precancel(self, request: ExecutionRequest, *, slot_generation: int) -> ExecutionReceipt:
        """在 POST 之前收到取消时创建取消终态回执；使用已校验的目标 generation。"""

        now = datetime.now(UTC)
        self.slot_generation = slot_generation
        execution = SlotExecution(
            request=request,
            accepted_at=now,
            stage=ATTEMPT_STATUS_TERMINAL,
            resource_state=RESOURCE_STATE_RELEASED,
            cancel_requested=True,
            finished_at=now,
            cleaned_at=now,
            slot_generation=slot_generation,
            error=RenderError.from_code(
                ERROR_CODE_CANCELLED,
                message="执行在启动前已被取消。",
                stage="admission",
            ).to_dict(),
        )
        self._receipts[request.attempt_id] = execution
        return self._build_receipt(execution)

    def _build_receipt(self, execution: SlotExecution) -> ExecutionReceipt:
        """把槽位执行状态转换为契约回执；generation 使用接管时快照。

        status 表达业务终态（succeeded/failed/cancelled），stage 保留生命周期阶段。
        禁止把失败/取消也标成 terminal-success，避免 Backend 误落库为成功。
        """

        result_descriptor = None
        if execution.result is not None:
            result_descriptor = {
                "result": execution.result.to_dict(),
                "artifacts": [item.to_dict() for item in execution.result.artifacts],
            }
        status = self._resolve_receipt_status(execution)
        return ExecutionReceipt(
            attempt_id=execution.request.attempt_id,
            request_id=execution.request.request_id,
            worker_id=self.worker_id,
            worker_epoch=self.worker_epoch,
            slot_generation=execution.slot_generation,
            request_digest=execution.request.request_digest,
            status=status,
            resource_state=execution.resource_state,
            accepted_at=_iso(execution.accepted_at),
            stage=execution.stage,
            started_at=_iso(execution.started_at) if execution.started_at else None,
            finished_at=_iso(execution.finished_at) if execution.finished_at else None,
            cleaned_at=_iso(execution.cleaned_at) if execution.cleaned_at else None,
            error=execution.error,
            result_descriptor=result_descriptor,
        )

    @staticmethod
    def _resolve_receipt_status(execution: SlotExecution) -> str:
        """按错误/结果推导回执业务状态，失败与取消不得伪装成成功。"""

        if execution.error is not None:
            code = str(execution.error.get("code") or "")
            if code == ERROR_CODE_CANCELLED or execution.cancel_requested:
                return "cancelled"
            return "failed"
        if execution.result is not None:
            return "succeeded"
        if execution.stage == ATTEMPT_STATUS_TERMINAL:
            return "failed"
        return execution.stage

    async def _run_execution(self, execution: SlotExecution) -> None:
        """在受保护任务中执行引擎，完成清理后再发布终态。"""

        from wp_renderer.engine.executor import RenderExecutor

        request = execution.request
        artifact_dir = self._artifact_dir(request.attempt_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        execution.started_at = datetime.now(UTC)
        execution.stage = ATTEMPT_STATUS_RUNNING
        executor = RenderExecutor(settings=self.settings, slot=self, execution=execution)
        self._executor = executor
        try:
            remaining_ms = request.remaining_budget_ms
            if remaining_ms <= 0:
                raise RenderExecutionError(
                    RenderError.from_code(
                        ERROR_CODE_DEADLINE_EXCEEDED,
                        message="remaining_budget_ms 必须为正。",
                        stage="admission",
                    )
                )
            result = await executor.execute(artifact_dir=artifact_dir)
            execution.result = result
            execution.stage = ATTEMPT_STATUS_CLEANING
        except asyncio.CancelledError:
            # 取消/事件循环收尾时仍写入终态错误，避免任务悬空无状态。
            if execution.error is None:
                code = ERROR_CODE_CANCELLED if execution.cancel_requested else ERROR_CODE_BROWSER_LOST
                execution.error = RenderError.from_code(
                    code,
                    message="执行任务被取消或进程收尾中断。",
                    stage="execution",
                ).to_dict()
            raise
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, RenderExecutionError):
                execution.error = exc.error.to_dict()
            else:
                code = ERROR_CODE_DEADLINE_EXCEEDED if _is_deadline(exc) else "RENDER_INTERNAL_ERROR"
                if execution.cancel_requested:
                    code = ERROR_CODE_CANCELLED
                execution.error = RenderError.from_code(
                    code,
                    message=str(exc)[:300],
                    stage="execution",
                ).to_dict()
        finally:
            # 独立监督流程关闭资源：不依赖对 Playwright Task 的 cancel()。
            await self._shutdown_executor(executor)
            if self._executor is executor:
                self._executor = None
            now = datetime.now(UTC)
            execution.finished_at = execution.finished_at or now
            if execution.error is not None:
                # 失败结果没有可消费产物，立即释放磁盘。
                self._cleanup_artifacts(execution)
                execution.cleaned_at = now
                execution.stage = ATTEMPT_STATUS_TERMINAL
                execution.resource_state = RESOURCE_STATE_RELEASED
                self._remember_recycled(request.attempt_id)
            elif execution.result is not None:
                # 成功产物保留到 Backend 确认消费或 TTL 过期；已消费则不得回写 retained。
                execution.stage = ATTEMPT_STATUS_TERMINAL
                if execution.consumed or execution.resource_state == RESOURCE_STATE_RELEASED:
                    execution.resource_state = RESOURCE_STATE_RELEASED
                else:
                    execution.resource_state = RESOURCE_STATE_RETAINED
            else:
                self._cleanup_artifacts(execution)
                execution.cleaned_at = now
                execution.stage = ATTEMPT_STATUS_TERMINAL
                execution.resource_state = RESOURCE_STATE_RELEASED
                self._remember_recycled(request.attempt_id)
            async with self._lock:
                if self._current is execution:
                    self._current = None
                self._task = None
                self._executor = None

    def _artifact_dir(self, attempt_id: str) -> Path:
        """构造 attempt 产物目录；拒绝路径穿越。"""

        safe_name = Path(attempt_id).name
        if not safe_name or safe_name in {".", ".."} or safe_name != attempt_id or "/" in attempt_id or "\\" in attempt_id:
            raise RenderExecutionError(
                RenderError.from_code(
                    "RENDER_CONTRACT_MISMATCH",
                    message="attempt_id 含非法路径字符。",
                    stage="admission",
                )
            )
        return self.settings.workspace_path / safe_name

    def _cleanup_artifacts(self, execution: SlotExecution) -> None:
        """删除临时产物目录；幂等标记继续保留。"""

        for path in list(execution.artifacts.values()):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                logger.warning("临时产物清理失败：%s", path, exc_info=True)
        execution.artifacts.clear()
        try:
            parent = self._artifact_dir(execution.request.attempt_id)
        except RenderExecutionError:
            parent = None
        if parent is not None and parent.exists():
            try:
                for child in parent.iterdir():
                    child.unlink(missing_ok=True)
                parent.rmdir()
            except OSError:
                pass
        execution.cleaned_at = execution.cleaned_at or datetime.now(UTC)

    def _maybe_expire_artifacts(self, execution: SlotExecution) -> None:
        """终态产物超过 TTL 仍未消费时回收。"""

        if execution.consumed or execution.result is None:
            return
        if execution.stage != ATTEMPT_STATUS_TERMINAL or execution.finished_at is None:
            return
        age = (datetime.now(UTC) - execution.finished_at).total_seconds()
        if age >= float(self.settings.render_result_ttl_seconds):
            self._cleanup_artifacts(execution)
            execution.resource_state = RESOURCE_STATE_RELEASED
            self._remember_recycled(execution.request.attempt_id)

    def _ensure_ttl_sweep(self) -> None:
        """惰性启动 TTL 后台扫描任务。"""

        if self._ttl_task is not None and not self._ttl_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._ttl_task = loop.create_task(self._ttl_sweep_loop(), name="renderer-ttl-sweep")

    async def _ttl_sweep_loop(self) -> None:
        """周期性回收未消费过期产物与历史回执。"""

        interval = max(1.0, float(self.settings.render_result_ttl_seconds) / 4.0)
        while True:
            try:
                await asyncio.sleep(interval)
                self.sweep_expired_artifacts()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning("TTL 后台扫描失败。", exc_info=True)

    def _prune_history(self) -> None:
        """裁剪超龄终态回执与取消标记，保持有界。"""

        ttl = float(self.settings.render_result_ttl_seconds)
        now = datetime.now(UTC)
        drop: list[str] = []
        for attempt_id, execution in self._receipts.items():
            if execution.stage != ATTEMPT_STATUS_TERMINAL:
                continue
            finished = execution.finished_at or execution.accepted_at
            if (now - finished).total_seconds() >= ttl:
                drop.append(attempt_id)
        for attempt_id in drop:
            execution = self._receipts.pop(attempt_id, None)
            if execution is not None and execution.artifacts:
                # 容量裁剪也不能遗留无法再消费的临时产物。
                self._cleanup_artifacts(execution)
            self._cancellations.pop(attempt_id, None)
            self._remember_recycled(attempt_id)
        self._prune_cancellations()
        self._prune_recycled()
        while len(self._receipts) > _MAX_HISTORY_ENTRIES:
            oldest = next(iter(self._receipts))
            execution = self._receipts.pop(oldest, None)
            if execution is not None and execution.artifacts:
                self._cleanup_artifacts(execution)
            self._remember_recycled(oldest)

    def _prune_cancellations(self) -> None:
        """取消标记按 TTL 与容量裁剪。"""

        ttl = float(self.settings.render_result_ttl_seconds)
        now = datetime.now(UTC)
        expired = [
            attempt_id
            for attempt_id, marked_at in self._cancellations.items()
            if (now - marked_at).total_seconds() >= ttl
        ]
        for attempt_id in expired:
            self._cancellations.pop(attempt_id, None)
        while len(self._cancellations) > _MAX_HISTORY_ENTRIES:
            self._cancellations.pop(next(iter(self._cancellations)), None)

    def _prune_recycled(self) -> None:
        """回收记录按容量裁剪。"""

        while len(self._recycled) > _MAX_HISTORY_ENTRIES:
            self._recycled.pop(next(iter(self._recycled)), None)

    def _remember_recycled(self, attempt_id: str) -> None:
        """记录已回收 attempt，供 410 语义查询。"""

        self._recycled[attempt_id] = datetime.now(UTC)
        self._prune_recycled()

    async def shutdown(self, *, grace_seconds: float | None = None) -> None:
        """停止接管并限时回收当前执行；不 cancel Playwright 任务，靠 closer 解除阻塞。"""

        grace = float(grace_seconds if grace_seconds is not None else self.settings.render_cleanup_grace_seconds)
        task = self._task
        execution = self._current
        executor = self._executor
        # 先尝试关闭执行器资源，使卡住的 Playwright 调用解除等待。
        if executor is not None:
            await self._shutdown_executor(executor)
        if task is not None and not task.done():
            # asyncio.wait 宽限等待，不 cancel 底层任务；超时后由 closer 解除阻塞并标记失败。
            _done, pending = await asyncio.wait({task}, timeout=grace)
            if pending:
                logger.warning("执行任务在宽限期内未结束，标记失败并回收槽位。")
                if execution is not None:
                    self._finalize_stuck_execution(execution)
            elif task.cancelled():
                logger.warning("执行任务已被事件循环收尾取消。")
        async with self._lock:
            if self._current is execution:
                self._current = None
            self._task = None
            self._executor = None
        if self._ttl_task is not None:
            self._ttl_task.cancel()
            try:
                await asyncio.wait({self._ttl_task}, timeout=1.0)
            except Exception:  # noqa: BLE001
                logger.warning("TTL 扫描任务收尾异常。", exc_info=True)
            self._ttl_task = None
        self.sweep_expired_artifacts()

    def _finalize_stuck_execution(self, execution: SlotExecution) -> None:
        """关停时仍卡住的执行标记为 BROWSER_LOST/DEADLINE，并在 closer 后清理。"""

        if execution.stage == ATTEMPT_STATUS_TERMINAL:
            return
        if execution.error is None:
            code = ERROR_CODE_BROWSER_LOST
            if execution.cancel_requested:
                code = ERROR_CODE_CANCELLED
            elif _deadline_elapsed(execution):
                code = ERROR_CODE_DEADLINE_EXCEEDED
            execution.error = RenderError.from_code(
                code,
                message="执行在关停时未能结束，已标记失败。",
                stage="shutdown",
            ).to_dict()
        now = datetime.now(UTC)
        execution.finished_at = execution.finished_at or now
        self._cleanup_artifacts(execution)
        execution.cleaned_at = now
        execution.stage = ATTEMPT_STATUS_TERMINAL
        execution.resource_state = RESOURCE_STATE_RELEASED
        self._remember_recycled(execution.request.attempt_id)


def _iso(value: datetime | None) -> str | None:
    """格式化 UTC 时间。"""

    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _is_deadline(exc: Exception) -> bool:
    """判断异常是否属于超时。"""

    return isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "deadline" in str(exc).lower()


def _deadline_elapsed(execution: SlotExecution) -> bool:
    """按 accepted_at + remaining_budget_ms 判断硬期限是否已过。"""

    budget_s = float(execution.request.remaining_budget_ms or 0) / 1000.0
    return (datetime.now(UTC) - execution.accepted_at).total_seconds() >= budget_s


def _is_safe_artifact_name(name: str) -> bool:
    """产物名仅允许单层文件名，拒绝路径穿越与空名。"""

    if not name or len(name) > 128:
        return False
    if name in {".", ".."}:
        return False
    if "/" in name or "\\" in name or "\x00" in name:
        return False
    return Path(name).name == name
