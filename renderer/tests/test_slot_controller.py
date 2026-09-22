"""文件功能：Renderer 控制面契约与单槽互斥测试（不依赖真实浏览器）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages" / "render-contracts" / "src"))

# 测试使用固定服务凭证；未设置时 SlotController 校验会失败。
import os  # noqa: E402

os.environ.setdefault("RENDER_SERVICE_CREDENTIAL", "renderer-test-secret")
os.environ.setdefault("RENDER_WORKER_ID", "renderer-local")
os.environ.setdefault("RENDER_WORKER_EPOCH", "epoch-1")

from app.control.slot import SlotController, SlotExecution, _is_safe_artifact_name  # noqa: E402
from render_contracts.constants import (  # noqa: E402
    PROTOCOL_VERSION,
    RESOURCE_STATE_RELEASED,
    RESOURCE_STATE_RETAINED,
)
from render_contracts.errors import (  # noqa: E402
    ERROR_CODE_CANCELLED,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import (  # noqa: E402
    ExecutionRequest,
    SnapshotRef,
    ViewportSpec,
)
from render_contracts.tokens import AdmissionTicket, PreviewAccess  # noqa: E402

pytestmark = pytest.mark.unit


def _make_request(*, attempt_id: str = "a1", digest: str = "digest-1") -> ExecutionRequest:
    """构造合法执行请求；票据 generation 须与 SlotController 当前值一致。"""

    secret = b"renderer-test-secret"
    now = datetime.now(UTC)
    ticket = AdmissionTicket.issue(
        secret=secret,
        request_digest=digest,
        workspace_id=1,
        worker_id="renderer-local",
        worker_epoch="epoch-1",
        # Backend 发票使用 attempt.slot_generation = worker.slot_generation + 1；
        # 全新 SlotController 当前 generation 为 0，故票据应为 1。
        slot_generation=1,
        accept_before=now + timedelta(seconds=60),
        stop_by=now + timedelta(seconds=120),
        attempt_id=attempt_id,
    )
    return ExecutionRequest(
        contract_version=PROTOCOL_VERSION,
        operation="page.capture",
        request_id="r1",
        attempt_id=attempt_id,
        request_digest=digest,
        workspace_id=1,
        trace_id="t1",
        snapshot_ref=SnapshotRef(artifact_id="art", input_digest="in"),
        input_digest="in",
        render_profile_digest="profile.v1",
        viewport=ViewportSpec(width=320, height=240),
        operation_options={},
        deadline_at=(now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        remaining_budget_ms=60_000,
        admission_ticket=ticket,
        preview_access=PreviewAccess(
            navigation_base_url="http://127.0.0.1:7373/preview",
            preview_token="tok",
            artifact_id="art",
            expires_at=(now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
            runtime_protocol_version="render-ready.v1",
        ),
    )


def test_capabilities_reports_protocol_and_idle_slot() -> None:
    """能力接口应返回协议版本与空闲槽位。"""

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    capabilities = slot.capabilities()
    assert capabilities["protocol_version"] == PROTOCOL_VERSION
    assert capabilities["slot_state"] == "idle"


def test_slot_accept_rejects_second_attempt_when_busy() -> None:
    """忙时明确返回 429，不接管第二个 attempt。"""

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    slot._current = object()  # noqa: SLF001 模拟占用中
    status, receipt = asyncio.new_event_loop().run_until_complete(
        slot.accept(_make_request(attempt_id="busy-1"))
    )
    assert status == 429
    assert receipt is None


def test_same_attempt_digest_mismatch_is_conflict() -> None:
    """相同 attempt ID 不同 digest 返回 409。"""

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    first = _make_request(attempt_id="dup", digest="d1")
    slot._receipts["dup"] = SlotExecution(request=first, accepted_at=datetime.now(UTC))
    status, _ = asyncio.new_event_loop().run_until_complete(
        slot.accept(_make_request(attempt_id="dup", digest="d2"))
    )
    assert status == 409


def test_same_attempt_retry_returns_existing_receipt_before_ticket_validation() -> None:
    """重复 POST 即使原接入票据已过期，也必须返回已有回执而不是重新拒绝。"""

    async def _scenario() -> None:
        from dataclasses import replace

        slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        original = _make_request(attempt_id="idempotent-expired")
        execution = SlotExecution(
            request=original,
            accepted_at=datetime.now(UTC),
            slot_generation=1,
        )
        slot._receipts[original.attempt_id] = execution
        expired_ticket = AdmissionTicket.issue(
            secret=b"renderer-test-secret",
            request_digest=original.request_digest,
            workspace_id=original.workspace_id,
            worker_id="renderer-local",
            worker_epoch="epoch-1",
            slot_generation=1,
            accept_before=datetime.now(UTC) - timedelta(seconds=1),
            stop_by=datetime.now(UTC) - timedelta(seconds=1),
            attempt_id=original.attempt_id,
        )
        retry = replace(original, admission_ticket=expired_ticket)

        status, receipt = await slot.accept(retry)

        assert status == 202
        assert receipt is not None
        assert receipt.attempt_id == original.attempt_id

    asyncio.run(_scenario())


def test_request_navigation_check_calls_playwright_method() -> None:
    """导航判断必须调用 Playwright 方法，不能把方法对象本身当作布尔值。"""

    from app.engine.executor import _request_is_navigation

    class _Request:
        def is_navigation_request(self) -> bool:
            return True

    assert _request_is_navigation(_Request()) is True


def test_admission_ticket_requires_next_slot_generation() -> None:
    """票据必须绑定 worker.slot_generation+1；严格相等，首次接管不得 403。"""

    async def _scenario() -> None:
        import app.engine.executor as executor_module

        class _HoldExecutor:
            def __init__(self, *, settings, slot, execution) -> None:
                self.execution = execution
                self._unblocked = asyncio.Event()

            async def execute(self, *, artifact_dir: Path):
                await self._unblocked.wait()
                raise AssertionError("不应完成")

            async def shutdown(self) -> None:
                self._unblocked.set()

        original = executor_module.RenderExecutor
        executor_module.RenderExecutor = _HoldExecutor
        slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        try:
            assert slot.slot_generation == 0
            status, receipt = await slot.accept(_make_request(attempt_id="gen-next"))
            assert status == 202
            assert receipt is not None
            assert receipt.slot_generation == 1
            assert slot.slot_generation == 1
        finally:
            executor_module.RenderExecutor = original
            await slot.shutdown(grace_seconds=1.0)

        # 槽位释放后，仍用旧 generation=1 签发的票据必须被严格相等拒绝。
        stale = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        stale.slot_generation = 1
        secret = b"renderer-test-secret"
        now = datetime.now(UTC)
        stale_ticket = AdmissionTicket.issue(
            secret=secret,
            request_digest="digest-stale",
            workspace_id=1,
            worker_id="renderer-local",
            worker_epoch="epoch-1",
            slot_generation=1,
            accept_before=now + timedelta(seconds=60),
            stop_by=now + timedelta(seconds=120),
            attempt_id="gen-stale",
        )
        from dataclasses import replace

        stale_req = replace(
            _make_request(attempt_id="gen-stale", digest="digest-stale"),
            admission_ticket=stale_ticket,
        )
        status2, receipt2 = await stale.accept(stale_req)
        assert status2 == 403
        assert receipt2 is not None
        assert receipt2.error is not None
        assert "generation" in str(receipt2.error.get("message") or "").lower()
        assert stale.slot_generation == 1

    asyncio.run(_scenario())


def test_cancellation_before_post_does_not_start_browser() -> None:
    """取消先于 POST 到达时记录标记且不启动执行。"""

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    slot.request_cancel("pre-cancel")
    request = _make_request(attempt_id="pre-cancel")
    status, receipt = asyncio.new_event_loop().run_until_complete(slot.accept(request))
    assert status == 202
    assert receipt is not None
    assert receipt.error is not None
    assert receipt.error["code"] == "RENDER_CANCELLED"
    assert slot.busy is False


def test_should_attach_initial_preview_headers_only_document() -> None:
    """仅初始文档导航可附带预览鉴权头。"""

    from app.engine.executor import _should_attach_initial_preview_headers

    assert _should_attach_initial_preview_headers(
        request_url="http://127.0.0.1:7373/__preview?token=abc",
        preview_url="http://127.0.0.1:7373/__preview?token=abc",
        is_navigation_request=True,
        resource_type="document",
    )
    assert not _should_attach_initial_preview_headers(
        request_url="https://viewer.diagrams.net/js/viewer.min.js",
        preview_url="http://127.0.0.1:7373/__preview?token=abc",
        is_navigation_request=False,
        resource_type="script",
    )
    assert not _should_attach_initial_preview_headers(
        request_url="http://127.0.0.1:8000/public/cached-assets/1/demo",
        preview_url="http://127.0.0.1:7373/__preview?token=abc",
        is_navigation_request=False,
        resource_type="fetch",
    )


def test_layout_script_meta_matches_contract() -> None:
    """页面布局脚本 meta 必须输出 canvas_size + threshold_scale。"""

    from app.engine.layout_scripts import build_page_render_layout_script

    script = build_page_render_layout_script()
    assert "canvas_size" in script
    assert "threshold_scale" in script


def test_component_script_requires_ready_handshake() -> None:
    """组件脚本必须等待 component-preview ready/settled 握手。"""

    from app.engine.layout_scripts import build_component_render_layout_script

    script = build_component_render_layout_script()
    assert "component-preview:ready" in script
    assert "component-preview:render-settled" in script
    assert "__RENDER_APPLY_SCENARIO__" in script


def test_component_message_capture_is_installed_before_navigation() -> None:
    """组件 ready 消息监听脚本必须在文档导航前注入。"""

    from app.engine.executor import _COMPONENT_MESSAGE_CAPTURE_SCRIPT

    assert "window.addEventListener('message'" in _COMPONENT_MESSAGE_CAPTURE_SCRIPT
    assert "component-preview:" in _COMPONENT_MESSAGE_CAPTURE_SCRIPT


def test_credential_file_empty_fails_closed(tmp_path: Path) -> None:
    """密钥文件为空时配置加载必须失败，禁止回退空 HMAC 密钥。"""

    from app.config import RendererSettings

    empty_file = tmp_path / "empty.secret"
    empty_file.write_bytes(b"   \n")
    with pytest.raises(Exception):
        RendererSettings(render_service_credential_file=str(empty_file), render_service_credential="")


def test_credential_file_missing_fails_closed(tmp_path: Path) -> None:
    """密钥文件缺失时配置加载必须失败。"""

    from app.config import RendererSettings

    with pytest.raises(Exception):
        RendererSettings(
            render_service_credential_file=str(tmp_path / "missing.secret"),
            render_service_credential="",
        )


def test_credential_secret_never_returns_empty_bytes(tmp_path: Path) -> None:
    """credential_secret 读取阶段同样 fail-closed，绝不返回空字节。"""

    from app.config import RendererSettings

    secret_file = tmp_path / "ok.secret"
    secret_file.write_bytes(b"strong-render-secret\n")
    settings = RendererSettings(
        render_service_credential_file=str(secret_file),
        render_service_credential="",
    )
    assert settings.credential_secret == b"strong-render-secret"

    # 加载后文件被清空：读取时仍须抛错，不得静默回退。
    secret_file.write_bytes(b"")
    with pytest.raises(Exception):
        _ = settings.credential_secret


def test_inline_placeholder_credential_rejected() -> None:
    """内联占位密钥继续拒绝。"""

    from app.config import RendererSettings

    with pytest.raises(Exception):
        RendererSettings(render_service_credential="change-me", render_service_credential_file=None)


def test_receipt_snapshots_slot_generation_at_accept() -> None:
    """回执 generation 必须使用接管时快照，而非 live slot_generation。"""

    async def _scenario() -> None:
        import app.engine.executor as executor_module

        class _HoldExecutor:
            """模拟执行器：shutdown() 解除阻塞，避免 asyncio.run 收尾卡住。"""

            def __init__(self, *, settings, slot, execution) -> None:
                self.execution = execution
                self._unblocked = asyncio.Event()

            async def execute(self, *, artifact_dir: Path):
                await self._unblocked.wait()
                raise AssertionError("不应完成")

            async def shutdown(self) -> None:
                self._unblocked.set()

        original = executor_module.RenderExecutor
        executor_module.RenderExecutor = _HoldExecutor
        slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        try:
            request = _make_request(attempt_id="gen-1")
            status, receipt = await slot.accept(request)
            assert status == 202
            assert receipt is not None
            snapshotted = receipt.slot_generation
            # 后续 generation 递增不得污染旧回执。
            slot.slot_generation += 10
            execution = slot.get_execution("gen-1")
            assert execution is not None
            rebuilt = slot.build_receipt(execution)
            assert rebuilt.slot_generation == snapshotted
            assert rebuilt.slot_generation != slot.slot_generation
            # 纯回执构建同样使用执行快照。
            direct = SlotExecution(
                request=request,
                accepted_at=datetime.now(UTC),
                slot_generation=7,
            )
            slot.slot_generation = 99
            assert slot.build_receipt(direct).slot_generation == 7
        finally:
            executor_module.RenderExecutor = original
            await slot.shutdown(grace_seconds=1.0)

    asyncio.run(_scenario())


def test_mark_consumed_race_keeps_released_state() -> None:
    """成功路径不得在已消费后把 resource_state 回写为 retained。"""

    request = _make_request(attempt_id="race-1")
    now = datetime.now(UTC)
    execution = SlotExecution(
        request=request,
        accepted_at=now,
        slot_generation=3,
        resource_state=RESOURCE_STATE_RETAINED,
    )
    from render_contracts.schema import ExecutionResult

    execution.result = ExecutionResult(
        request_id=request.request_id,
        attempt_id=request.attempt_id,
        worker_id="renderer-local",
        worker_epoch="epoch-1",
        slot_generation=3,
        operation=request.operation,
        input_digest=request.input_digest,
        render_profile_digest="profile.v1",
        request_digest=request.request_digest,
        result_schema_version="render-result.v1",
        environment_summary={},
    )
    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    slot._receipts["race-1"] = execution

    assert slot.mark_consumed("race-1") is True
    assert execution.consumed is True
    assert execution.resource_state == RESOURCE_STATE_RELEASED

    # 模拟成功路径 finally 在 mark_consumed 之后收尾。
    if execution.consumed or execution.resource_state == RESOURCE_STATE_RELEASED:
        execution.resource_state = RESOURCE_STATE_RELEASED
    else:
        execution.resource_state = RESOURCE_STATE_RETAINED
    assert execution.resource_state == RESOURCE_STATE_RELEASED


def test_expired_receipt_cleanup_happens_before_history_prune(tmp_path: Path) -> None:
    """回执被 TTL 裁剪时，关联 artifact 目录也必须同步删除。"""

    from render_contracts.schema import ExecutionResult

    from app.config import RendererSettings

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    slot.settings = RendererSettings(
        render_worker_id="renderer-local",
        render_worker_epoch="epoch-1",
        render_service_credential="renderer-test-secret",
        render_service_credential_file=None,
        render_workspace_dir=str(tmp_path),
        render_result_ttl_seconds=1,
    )
    request = _make_request(attempt_id="expired-artifact")
    artifact_dir = tmp_path / request.attempt_id
    artifact_dir.mkdir()
    artifact = artifact_dir / "page.png"
    artifact.write_bytes(b"png")
    execution = SlotExecution(
        request=request,
        accepted_at=datetime.now(UTC) - timedelta(seconds=3),
        stage="terminal",
        resource_state=RESOURCE_STATE_RETAINED,
        finished_at=datetime.now(UTC) - timedelta(seconds=3),
        artifacts={"page.png": artifact},
        slot_generation=1,
    )
    execution.result = ExecutionResult(
        request_id=request.request_id,
        attempt_id=request.attempt_id,
        worker_id="renderer-local",
        worker_epoch="epoch-1",
        slot_generation=1,
        operation=request.operation,
        input_digest=request.input_digest,
        render_profile_digest="profile.v1",
        request_digest=request.request_digest,
        result_schema_version="render-result.v1",
        environment_summary={},
    )
    slot._receipts[request.attempt_id] = execution  # noqa: SLF001

    slot.sweep_expired_artifacts()

    assert slot.get_execution(request.attempt_id) is None
    assert not artifact.exists()
    assert not artifact_dir.exists()


def test_success_result_metadata_does_not_claim_cleaned() -> None:
    """成功结果骨架不得在产物仍 retained 时声称 cleaned_at/released。"""

    from app.engine.executor import RenderExecutor

    request = _make_request(attempt_id="meta-1")
    execution = SlotExecution(request=request, accepted_at=datetime.now(UTC), slot_generation=2)
    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    executor = RenderExecutor(settings=slot.settings, slot=slot, execution=execution)
    result = executor._base_result()  # noqa: SLF001
    assert result.cleaned_at == ""
    assert result.resource_state == RESOURCE_STATE_RETAINED
    assert result.slot_generation == 2


def test_executor_timeout_does_not_cancel_playwright_awaitable() -> None:
    """Renderer 阶段超时只能返回错误，不能取消仍需由 shutdown 解除的底层任务。"""

    async def _scenario() -> None:
        from app.engine.executor import DeadlineClock, RenderExecutor

        request = _make_request(attempt_id="bounded-timeout")
        execution = SlotExecution(request=request, accepted_at=datetime.now(UTC), slot_generation=1)
        slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        executor = RenderExecutor(settings=slot.settings, slot=slot, execution=execution)
        executor._deadline = DeadlineClock(deadline_monotonic=asyncio.get_running_loop().time() + 0.03)
        finished = asyncio.Event()

        async def _underlying() -> None:
            await finished.wait()

        task = asyncio.create_task(_underlying())
        with pytest.raises(RenderExecutionError):
            await executor._await_bounded(task, stage="test")
        assert task.cancelled() is False
        finished.set()
        await task

    asyncio.run(_scenario())


def test_cancel_during_run_interrupts_and_shuts_down_executor() -> None:
    """运行中取消须置位 cancel_requested 并调用 executor.shutdown()。"""

    async def _scenario() -> None:
        import app.engine.executor as executor_module

        shutdown_calls = {"count": 0}

        class _FakeExecutor:
            def __init__(self, *, settings, slot, execution) -> None:
                self.settings = settings
                self.slot = slot
                self.execution = execution
                self._shutdown_started = False
                self._unblocked = asyncio.Event()

            async def execute(self, *, artifact_dir: Path):
                try:
                    await asyncio.wait_for(self._unblocked.wait(), timeout=2.0)
                except (TimeoutError, asyncio.TimeoutError) as exc:
                    raise AssertionError("shutdown 未解除执行阻塞") from exc
                if self.execution.cancel_requested:
                    raise RenderExecutionError(
                        RenderError.from_code(ERROR_CODE_CANCELLED, message="执行已取消。", stage="run")
                    )
                raise AssertionError("取消未生效")

            async def shutdown(self) -> None:
                if self._shutdown_started:
                    self._unblocked.set()
                    return
                self._shutdown_started = True
                shutdown_calls["count"] += 1
                self._unblocked.set()

        original = executor_module.RenderExecutor
        executor_module.RenderExecutor = _FakeExecutor
        slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
        try:
            request = _make_request(attempt_id="cancel-run")
            status, _receipt = await slot.accept(request)
            assert status == 202
            await asyncio.sleep(0.05)
            assert slot.request_cancel("cancel-run") is True
            task = slot._task  # noqa: SLF001
            assert task is not None
            await asyncio.wait({task}, timeout=2.0)
            assert task.done()
            execution = slot.get_execution("cancel-run")
            assert execution is not None
            assert execution.cancel_requested is True
            assert execution.error is not None
            assert execution.error["code"] == ERROR_CODE_CANCELLED
            assert shutdown_calls["count"] >= 1
            assert slot.busy is False
        finally:
            executor_module.RenderExecutor = original
            await slot.shutdown(grace_seconds=1.0)

    asyncio.run(_scenario())


def test_artifact_name_and_path_safety() -> None:
    """产物名必须拒绝路径穿越与分隔符。"""

    assert _is_safe_artifact_name("page.png") is True
    assert _is_safe_artifact_name("../etc/passwd") is False
    assert _is_safe_artifact_name("..\\windows\\system32") is False
    assert _is_safe_artifact_name("/abs/path.png") is False
    assert _is_safe_artifact_name("") is False
    assert _is_safe_artifact_name("..") is False

    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    assert slot.artifact_path("missing", "../page.png") is None
    assert slot.artifact_path("missing", "page.png") is None


def test_navigation_url_allowlist_blocks_metadata_hosts() -> None:
    """导航 URL 仅允许 http/https，并拦截元数据主机。"""

    from app.engine.executor import assert_safe_navigation_url, is_control_api_target

    assert_safe_navigation_url("http://127.0.0.1:7373/preview")
    assert_safe_navigation_url("https://preview.example.com/page")
    assert is_control_api_target("http://127.0.0.1:7400/internal/render/v1/executions")
    assert is_control_api_target("http://localhost:7400/internal/render/v1/capabilities")
    assert is_control_api_target("https://evil.example/internal/render/v1/executions")
    assert not is_control_api_target("http://127.0.0.1:7373/preview?artifact=a")
    assert not is_control_api_target("https://cdn.example.com/app.js")
    with pytest.raises(Exception):
        assert_safe_navigation_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(Exception):
        assert_safe_navigation_url("http://metadata.google.internal/computeMetadata/v1/")
    with pytest.raises(Exception):
        assert_safe_navigation_url("file:///etc/passwd")
    with pytest.raises(Exception):
        assert_safe_navigation_url("ftp://example.com/x")
