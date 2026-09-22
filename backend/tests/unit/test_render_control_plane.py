"""文件功能：远程渲染控制面单元测试，覆盖请求幂等、错误映射与目标解析。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

# 单测不触达 Renderer，但配置默认空凭证不影响 settings 构造。

from app.core.config import AppSettings
from app.services.rendering.target_resolver import RenderTargetResolver
from render_contracts.tokens import AdmissionTicket, compute_request_key, compute_render_digest

pytestmark = pytest.mark.unit


def test_render_settings_reject_legacy_playwright_env(monkeypatch) -> None:
    """旧 PLAYWRIGHT_* 环境变量必须启动失败，禁止静默忽略。"""

    monkeypatch.setenv("PLAYWRIGHT_BROWSER_POOL_SIZE", "2")
    with pytest.raises(ValueError, match="已废弃的本地 Playwright 配置"):
        AppSettings(_env_file=None)


def test_fallback_snapshot_expiry_covers_budget() -> None:
    """无 page_id 的 fallback 快照不得把 expires_at 写成当前时刻。"""

    from datetime import UTC, datetime, timedelta

    settings = AppSettings(_env_file=None, runtime_preview_artifact_ttl_seconds=3600)
    expires = datetime.now(UTC) + timedelta(seconds=settings.runtime_preview_artifact_ttl_seconds)
    assert expires > datetime.now(UTC) + timedelta(minutes=5)


def test_preview_access_rejects_bad_platform_asset_url() -> None:
    """platform_asset_base_url 必须与其它基址一样做 URL 白名单校验。"""

    from render_contracts.errors import RenderContractError
    from render_contracts.tokens import PreviewAccess

    ok = PreviewAccess(
        navigation_base_url="https://runtime.example.com/preview",
        preview_token="t",
        artifact_id="a",
        expires_at="2099-01-01T00:00:00Z",
        runtime_protocol_version="render-ready.v1",
        platform_asset_base_url="https://platform.example.com",
    )
    ok.validate()

    bad = PreviewAccess(
        navigation_base_url="https://runtime.example.com/preview",
        preview_token="t",
        artifact_id="a",
        expires_at="2099-01-01T00:00:00Z",
        runtime_protocol_version="render-ready.v1",
        platform_asset_base_url="file:///etc/passwd",
    )
    with pytest.raises(RenderContractError):
        bad.validate()


def test_ensure_input_digest_query_is_idempotent() -> None:
    """已有 preview URL 必须能稳定补齐/保持 input_digest。"""

    from app.services.rendering.coordinator import _ensure_input_digest_query

    url = "http://runtime.local/preview?artifact=a&token=t"
    first = _ensure_input_digest_query(url, "digest-1")
    assert "input_digest=digest-1" in first
    second = _ensure_input_digest_query(first, "digest-1")
    assert second == first


def test_request_key_stable_for_same_owner_stage() -> None:
    """同一逻辑 owner 与输入应得到相同 request_key。"""

    render_digest = compute_render_digest(
        render_profile_digest="profile.v1",
        viewport={"width": 100, "height": 100},
        operation_options={},
    )
    first = compute_request_key(
        owner_key="page-screenshot:1:v1:h:100x100",
        business_stage="page.screenshot",
        operation="page.capture",
        input_digest="abc",
        render_digest=render_digest,
    )
    second = compute_request_key(
        owner_key="page-screenshot:1:v1:h:100x100",
        business_stage="page.screenshot",
        operation="page.capture",
        input_digest="abc",
        render_digest=render_digest,
    )
    assert first == second


def test_target_resolver_prefers_render_navigation_base_url() -> None:
    """导航基址优先使用 RENDER_RUNTIME_NAVIGATION_BASE_URL。"""

    settings = AppSettings(
        _env_file=None,
        render_runtime_navigation_base_url="https://example.com/runtime",
        runtime_base_url="http://127.0.0.1:7373",
    )
    resolver = RenderTargetResolver(settings)
    assert resolver.navigation_base_url() == "https://example.com/runtime"


def test_worker_endpoints_come_only_from_trusted_config() -> None:
    """Worker 地址只来自部署配置。"""

    settings = AppSettings(
        _env_file=None,
        render_workers_config=[{"worker_id": "renderer-1", "base_url": "http://renderer:7400"}],
    )
    endpoints = RenderTargetResolver(settings).worker_endpoints()
    assert endpoints[0].worker_id == "renderer-1"
    assert endpoints[0].base_url == "http://renderer:7400"


def test_sanitize_owner_key_strips_token_query() -> None:
    """owner key 不得携带预览 token 查询参数。"""

    from app.services.rendering.domain_facade import sanitize_owner_key

    raw = "http://runtime.local/preview?artifact=a1&token=secret-token-value"
    cleaned = sanitize_owner_key(raw)
    assert "secret-token-value" not in cleaned
    assert "token=" not in cleaned


def test_sanitize_url_redacts_token_values() -> None:
    """日志与错误详情中的 token 必须脱敏。"""

    from app.services.rendering.sanitize import sanitize_error_message, sanitize_url

    url = sanitize_url("https://runtime.local/preview?artifact=a&token=abc.def-123")
    assert "abc.def-123" not in url
    assert "[redacted]" in url
    msg = sanitize_error_message("failed for http://x/y?preview_token=zzz999")
    assert "zzz999" not in msg


def test_normalize_layout_analysis_keeps_v3_shape() -> None:
    """布局分析成功/缺失路径都必须保持 schema v3 全量结构。"""

    from app.services.rendering.layout_contract import empty_layout_analysis, normalize_layout_analysis

    empty = empty_layout_analysis()
    assert empty["schema_version"] == 3
    assert empty["meta"] is None
    assert set(empty["summary"]["totals"]) == {
        "text_layouts",
        "item_groups",
        "overflows",
        "spatial_relations",
        "empty_regions",
    }
    assert empty["summary"]["returned"]["text_layouts"] == 0

    normalized = normalize_layout_analysis(
        {
            "summary": {"attention": "review", "message": "有关注项", "totals": {"text_layouts": 9}},
            "text_layouts": [{"id": 1}, "bad"],
            "item_groups": [{"id": 2}],
        }
    )
    assert normalized["summary"]["attention"] == "review"
    assert normalized["summary"]["totals"]["text_layouts"] == 9
    assert normalized["summary"]["returned"]["text_layouts"] == 1
    assert normalized["summary"]["truncated"] is True
    assert normalized["item_groups"] == [{"id": 2}]


def test_stable_artifact_fallback_is_deterministic() -> None:
    """缺失 artifact_id 时必须生成稳定标识，禁止随机 UUID。"""

    from app.services.rendering.domain_facade import _stable_artifact_fallback

    first = _stable_artifact_fallback("http://runtime.local/preview?token=t1", "t1")
    second = _stable_artifact_fallback("http://runtime.local/preview?token=t1", "t1")
    third = _stable_artifact_fallback("http://runtime.local/preview?token=t2", "t2")
    assert first == second
    assert first != third
    assert len(first) == 32


def test_page_snapshot_digest_uses_candidate_source_override() -> None:
    """页面候选源码的快照 digest 不得继续绑定数据库当前版本。"""

    import asyncio
    from types import SimpleNamespace

    from app.services.rendering.snapshot_service import RenderSnapshotService

    page = SimpleNamespace(
        code="demo-page",
        page_content="<template><main>已保存版本</main></template>",
        current_version_no=3,
        workspace_id=1,
        project_id=2,
    )
    version = SimpleNamespace(
        page_content=page.page_content,
        version_no=3,
    )

    class _Session:
        async def get(self, *_args):
            return page

        async def scalar(self, *_args):
            return version

    service = RenderSnapshotService(_Session())

    async def _run() -> None:
        common = dict(
            page_id=1,
            artifact_id="candidate-artifact",
            preview_token="preview-token",
            viewport={"width": 1920, "height": 1080},
            operation_options={},
            preview_url="http://runtime.local/preview",
        )
        saved = await service.build_page_snapshot(**common)
        candidate = await service.build_page_snapshot(
            **common,
            source_override="<template><main>未保存候选版本</main></template>",
        )
        assert saved["input_digest"] != candidate["input_digest"]

    asyncio.run(_run())


def test_request_service_reuses_active_and_recreates_failed() -> None:
    """未终态请求复用；failed 后允许 generation 重建。"""

    import asyncio

    from app.models.render_request import RenderRequest
    from app.services.rendering.request_service import RenderRequestService

    class _StubRepo:
        def __init__(self) -> None:
            self.rows: list[RenderRequest] = []

        async def get_request_by_key(self, *, logical_owner_key, business_stage, operation, request_key):
            for row in self.rows:
                if row.request_key == request_key:
                    return row
            return None

        async def count_queued_requests(self, *, workspace_id=None):
            return 0

        async def lock_scheduler_state_for_queue_admission(self):
            return None

    class _Session:
        def __init__(self, repo: _StubRepo) -> None:
            self.repo = repo

        def add(self, obj) -> None:
            self.repo.rows.append(obj)

        async def flush(self) -> None:
            for index, row in enumerate(self.repo.rows, start=1):
                row.id = index

        def begin_nested(self):
            """兼容 SAVEPOINT 写入路径。"""

            class _Nested:
                async def __aenter__(self_inner):
                    return self

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

            return _Nested()

    repo = _StubRepo()
    service = RenderRequestService.__new__(RenderRequestService)
    service.session = _Session(repo)
    service.repository = repo
    service.settings = AppSettings(_env_file=None)

    async def _run() -> None:
        kwargs = dict(
            logical_owner_key="owner-1",
            business_stage="page.screenshot",
            operation="page.capture",
            workspace_id=1,
            project_id=None,
            page_id=None,
            component_id=None,
            owner_kind="domain_facade",
            owner_ref="owner-1",
            snapshot_ref={"artifact_id": "a"},
            input_digest="in-1",
            operation_options={},
            viewport={"width": 1, "height": 1},
            render_profile_digest="profile.v1",
            trace_id="t",
        )
        first, created = await service.get_or_create_request(**kwargs)
        assert created is True
        again, created2 = await service.get_or_create_request(**kwargs)
        assert created2 is False
        assert again is first

        first.status = "failed"
        third, created3 = await service.get_or_create_request(**kwargs)
        assert created3 is True
        assert third is not first
        assert third.request_key != first.request_key
        assert third.claim_generation == 1

    asyncio.run(_run())


def test_load_secret_rejects_placeholder() -> None:
    """占位服务凭证必须拒绝加载。"""

    from app.services.rendering.credentials import RenderCredentialService
    from render_contracts.errors import RenderExecutionError

    settings = AppSettings(
        _env_file=None,
        render_service_credential="replace-with-strong-shared-secret",
    )
    with pytest.raises(RenderExecutionError, match="占位"):
        RenderCredentialService(settings).load_secret()


def test_admission_ticket_binds_worker_epoch_and_generation() -> None:
    """票据绑定 worker/epoch/slot generation，过期 epoch 不得启动。"""

    secret = b"secret"
    now = datetime.now(UTC)
    ticket = AdmissionTicket.issue(
        secret=secret,
        request_digest="d",
        workspace_id=1,
        worker_id="w1",
        worker_epoch="e1",
        slot_generation=3,
        accept_before=now + timedelta(seconds=30),
        stop_by=now + timedelta(seconds=60),
        attempt_id="att-1",
    )
    ticket.validate(secret=secret, worker_id="w1", worker_epoch="e1", slot_generation=3)
    with pytest.raises(Exception):
        ticket.validate(secret=secret, worker_id="w1", worker_epoch="e2", slot_generation=3)
    # 严格相等：更高期望 generation 视为过期，更低视为未接管/未签发。
    with pytest.raises(Exception):
        ticket.validate(secret=secret, worker_id="w1", worker_epoch="e1", slot_generation=4)
    with pytest.raises(Exception):
        ticket.validate(secret=secret, worker_id="w1", worker_epoch="e1", slot_generation=2)


def test_preview_credentials_are_encrypted_at_rest() -> None:
    """快照中的 preview_token / extra_http_headers 必须加密存储。"""

    from app.services.rendering.credentials import RenderCredentialService

    settings = AppSettings(_env_file=None, ai_secret_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    service = RenderCredentialService(settings)
    token = service.encrypt_sensitive_payload(
        {
            "preview_token": "secret-preview-token",
            "extra_http_headers": {"x-runtime-preview-context": "secret-preview-token"},
            "preview_url": "http://runtime.local/__preview?token=secret",
        }
    )
    assert "secret-preview-token" not in token
    decoded = service.decrypt_sensitive_payload(token)
    assert decoded["preview_token"] == "secret-preview-token"
    assert decoded["extra_http_headers"]["x-runtime-preview-context"] == "secret-preview-token"


def test_page_unavailable_is_not_content_error() -> None:
    """页面渲染执行不可用必须是 warning + unavailable，不得映射为内容错误。"""

    from app.services.rendering.domain_facade import RenderDomainFacade

    result = RenderDomainFacade._page_unavailable_result("Renderer 离线")  # noqa: SLF001
    assert result["status"] == "unavailable"
    assert result["retryable"] is True
    assert result["diagnostics"][0]["severity"] == "warning"
    assert result["diagnostics"][0]["source"] == "infrastructure"


def test_page_deadline_result_defers_artifact_cleanup() -> None:
    """远程等待超时时应标记 artifact 仍可能被在途 attempt 使用。"""

    from app.services.rendering.domain_facade import RenderDomainFacade

    result = RenderDomainFacade._page_unavailable_result(  # noqa: SLF001
        "等待超时",
        defer_artifact_cleanup=True,
    )
    assert result["_render_artifact_cleanup_deferred"] is True


def test_timeout_cancellation_uses_independent_session(monkeypatch) -> None:
    """等待超时的取消标记必须通过独立会话提交并关闭。"""

    import asyncio

    from app.services.rendering import domain_facade as domain_facade_module
    from app.services.rendering.domain_facade import RenderDomainFacade

    calls: dict[str, object] = {}

    class _Session:
        async def commit(self) -> None:
            calls["commit"] = True

        async def rollback(self) -> None:
            calls["rollback"] = True

        async def close(self) -> None:
            calls["close"] = True

    session = _Session()

    class _RequestService:
        def __init__(self, _session) -> None:
            assert _session is session

        async def cancel_request(self, request_id: int) -> None:
            calls["request_id"] = request_id

    monkeypatch.setattr(domain_facade_module, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(domain_facade_module, "RenderRequestService", _RequestService)

    asyncio.run(RenderDomainFacade.__new__(RenderDomainFacade)._cancel_request_after_timeout(17))  # noqa: SLF001

    assert calls == {"request_id": 17, "commit": True, "close": True}


def test_page_render_deadline_marks_artifact_cleanup_deferred() -> None:
    """页面渲染超时时，诊断服务必须把 artifact 生命周期交给 TTL。"""

    import asyncio

    from app.core.exceptions import AppException
    from app.services.capture_viewport_resolver import CaptureViewport
    from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService

    class _DeadlineFacade:
        async def diagnose_page_preview(self, **_kwargs):
            raise AppException(
                status_code=504,
                code="RENDER_DEADLINE_EXCEEDED",
                detail="等待渲染结果超过总预算。",
            )

    service = PageRenderDiagnosticsService(facade=_DeadlineFacade())
    result = asyncio.run(
        service.diagnose_preview(
            "http://runtime.local/preview?token=t",
            CaptureViewport(width=320, height=240),
            workspace_id=1,
        )
    )

    assert result["_render_artifact_cleanup_deferred"] is True


def test_code_check_does_not_delete_artifact_while_render_attempt_may_be_in_flight(monkeypatch) -> None:
    """页面远程渲染返回 deferred 标记时，代码检查不得提前删除输入 artifact。"""

    import asyncio
    from unittest.mock import AsyncMock

    import app.services.code_check_service as code_check_module
    from app.services.capture_viewport_resolver import CaptureViewport
    from app.services.code_check_service import CodeCheckService

    class _RuntimeClient:
        async def dispatch_artifact_diagnostics(self, **_kwargs):
            return {"success": True, "status": "passed", "diagnostics": []}

    class _RenderDiagnostics:
        async def diagnose_preview(self, *_args, **_kwargs):
            return {
                "status": "unavailable",
                "diagnostics": [],
                "layout_analysis": {},
                "_render_artifact_cleanup_deferred": True,
            }

    artifact_store = type("_ArtifactStore", (), {"delete_artifact": AsyncMock()})()
    monkeypatch.setattr(code_check_module, "RuntimeArtifactStore", lambda: artifact_store)
    service = CodeCheckService(
        object(),
        runtime_client=_RuntimeClient(),
        render_diagnostics_service=_RenderDiagnostics(),
    )

    result = asyncio.run(
        service._dispatch_diagnostics(  # noqa: SLF001
            artifact_id="artifact-in-flight",
            workspace_id=1,
            project_id=2,
            label="page:1",
            patch_repaired=False,
            canonical_diff=None,
            render_preview_url="http://runtime.local/preview?token=t",
            render_viewport=CaptureViewport(width=320, height=240),
            page_id=1,
        )
    )

    artifact_store.delete_artifact.assert_not_awaited()
    assert "_render_artifact_cleanup_deferred" not in result


def test_save_result_conflict_must_not_confirm_consumption() -> None:
    """save_result 条件更新失败时不得确认消费。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    repo = RenderRepository(session)
    request = MagicMock()
    request.id = 1
    request.operation = "page.capture"
    attempt = MagicMock()
    attempt.id = 2
    attempt.worker_id = "w"
    attempt.worker_epoch = "e"

    async def _run() -> None:
        result = await repo.save_result(
            request=request,
            attempt=attempt,
            payload={},
            object_refs={},
            environment_summary={},
            input_digest="i",
            render_profile_digest="p",
            request_digest="d",
        )
        assert result is None
        session.rollback.assert_awaited()

    asyncio.run(_run())


def test_fail_attempt_release_conflict_does_not_rewrite_request() -> None:
    """release_slot=True 但占用已被其它路径收敛时，不得改写请求状态。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    repo = RenderRepository(session)
    request = MagicMock()
    request.id = 1
    request.attempt_count = 1
    request.max_attempts = 3
    request.status = "executing"
    attempt = MagicMock()
    attempt.id = 2
    attempt.worker_id = "w"
    attempt.worker_epoch = "e"

    async def _run() -> None:
        await repo.fail_attempt(
            request=request,
            attempt=attempt,
            error_code="RENDER_INTERNAL_ERROR",
            error_message="x",
            retryable=True,
            retry_after=None,
            release_slot=True,
            terminal=False,
        )
        assert request.status == "executing"
        assert session.execute.await_count == 1

    asyncio.run(_run())


def test_deadline_exceeded_is_retryable_infrastructure() -> None:
    """attempt 级 deadline 可重试，与超时基础设施语义一致。"""

    from render_contracts.errors import ERROR_CODE_DEADLINE_EXCEEDED, RenderError

    error = RenderError.from_code(ERROR_CODE_DEADLINE_EXCEEDED, message="超时")
    assert error.retryable is True
    assert error.category == "timeout"


def test_credentials_reject_placeholder_secret_file(tmp_path) -> None:
    """凭证文件中的占位密钥必须拒绝。"""

    from app.core.config import AppSettings
    from app.services.rendering.credentials import RenderCredentialService
    from render_contracts.errors import RenderExecutionError

    secret_file = tmp_path / "render_service_credential"
    secret_file.write_text("change-me-render-secret", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        render_service_credential_file=str(secret_file),
        render_service_credential="",
    )
    with pytest.raises(RenderExecutionError, match="占位"):
        RenderCredentialService(settings).load_secret()


def test_credentials_reject_empty_secret_file(tmp_path) -> None:
    """空凭证文件必须 fail-closed，禁止空 HMAC 密钥。"""

    from app.core.config import AppSettings
    from app.services.rendering.credentials import RenderCredentialService
    from render_contracts.errors import RenderExecutionError

    secret_file = tmp_path / "render_service_credential"
    secret_file.write_text("", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        render_service_credential_file=str(secret_file),
        render_service_credential="",
    )
    with pytest.raises(RenderExecutionError, match="空"):
        RenderCredentialService(settings).load_secret()


def test_is_definitely_not_taken_for_4xx_and_busy() -> None:
    """忙、契约/票据拒绝与 HTTP 4xx 均表示未接管，必须释放占用。"""

    import httpx

    from app.services.rendering.coordinator import _is_definitely_not_taken
    from render_contracts.errors import (
        ERROR_CODE_CONTRACT_MISMATCH,
        ERROR_CODE_PROFILE_MISMATCH,
        ERROR_CODE_SERVICE_UNAVAILABLE,
        ERROR_CODE_WORKER_BUSY,
        RenderError,
        RenderExecutionError,
    )

    def _exc(code: str) -> RenderExecutionError:
        return RenderExecutionError(RenderError.from_code(code, message="x", stage="dispatch"))

    assert _is_definitely_not_taken(_exc(ERROR_CODE_WORKER_BUSY))
    assert _is_definitely_not_taken(_exc(ERROR_CODE_CONTRACT_MISMATCH))
    assert _is_definitely_not_taken(_exc(ERROR_CODE_PROFILE_MISMATCH))

    busy = _exc(ERROR_CODE_SERVICE_UNAVAILABLE)
    busy.http_status = 429  # type: ignore[attr-defined]
    assert _is_definitely_not_taken(busy)

    connect_fail = _exc(ERROR_CODE_SERVICE_UNAVAILABLE)
    connect_fail.__cause__ = httpx.ConnectError("refused")
    assert _is_definitely_not_taken(connect_fail)

    read_timeout = _exc(ERROR_CODE_SERVICE_UNAVAILABLE)
    read_timeout.__cause__ = httpx.ReadTimeout("slow")
    assert not _is_definitely_not_taken(read_timeout)

    no_status = _exc(ERROR_CODE_SERVICE_UNAVAILABLE)
    assert not _is_definitely_not_taken(no_status)


def test_reserve_does_not_advance_worker_slot_generation() -> None:
    """reserve 只预约下一 generation，Worker 代次须在 accept 成功后才推进。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    session = MagicMock()
    claim_result = MagicMock()
    claim_result.rowcount = 1
    session.execute = AsyncMock(return_value=claim_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=0)
    repo = RenderRepository(session)

    request = MagicMock()
    request.id = 1
    request.attempt_count = 0
    request.started_at = None
    request.request_digest = "digest"
    worker = MagicMock()
    worker.worker_id = "w1"
    worker.worker_epoch = "e1"
    worker.slot_generation = 4
    worker.slot_state = "idle"

    async def _run() -> None:
        attempt = await repo.reserve_attempt(request=request, worker=worker, request_digest="digest")
        assert attempt.slot_generation == 5
        assert worker.slot_generation == 4
        assert worker.slot_state == "busy"
        assert attempt.status == "reserved"

    asyncio.run(_run())


def test_worker_heartbeat_preserves_renderer_busy_without_db_attempt() -> None:
    """Renderer 报告 busy 且暂时没有 DB attempt 时，Worker 不得被写成 idle。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    session = MagicMock()
    worker = MagicMock()
    worker.worker_id = "renderer-1"
    worker.worker_epoch = "epoch-1"
    worker.slot_state = "idle"
    worker.slot_generation = 4
    stale_rows = MagicMock()
    stale_rows.all.return_value = []
    session.scalar = AsyncMock(side_effect=[worker, 0])
    session.scalars = AsyncMock(return_value=stale_rows)
    session.flush = AsyncMock()
    repository = RenderRepository(session)

    async def _run() -> None:
        result = await repository.upsert_worker_heartbeat(
            worker_id="renderer-1",
            worker_epoch="epoch-1",
            service_base_url="http://renderer:7400",
            render_profile_digest="profile.v1",
            environment_summary={},
            slot_state="busy",
            slot_generation=5,
        )

        assert result.slot_state == "busy"
        assert result.slot_generation == 5

    asyncio.run(_run())


def test_expired_attempt_requeues_parent_request() -> None:
    """过期 attempt 释放占用时，父请求必须进入可再次派发的 retry_wait。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    rows_result = MagicMock()
    rows_result.all.return_value = [(7, 11, "worker-1", "epoch-1")]
    release_result = MagicMock(rowcount=1)
    request_update_result = MagicMock(rowcount=1)
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[rows_result, release_result, request_update_result])
    request = MagicMock()
    request.id = 11
    request.status = "executing"
    request.cancel_requested = False
    request.deadline_at = datetime.now(UTC) + timedelta(minutes=5)
    request.attempt_count = 1
    request.max_attempts = 3
    worker = MagicMock()
    worker.slot_state = "busy"
    session.get = AsyncMock(return_value=request)
    session.scalar = AsyncMock(side_effect=[worker, 0])
    repository = RenderRepository(session)

    async def _run() -> None:
        released = await repository.release_expired_attempt_leases()

        assert released == 1
        assert request.status == "retry_wait"
        assert request.error_code == "RENDER_RESULT_LOST"
        assert request.retry_after is not None
        assert worker.slot_state == "idle"

    asyncio.run(_run())


def test_mark_attempt_accepted_advances_worker_slot_generation() -> None:
    """接管成功后才把预约 generation 提交到 Worker 记录。"""

    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.services.rendering.repository import RenderRepository

    session = MagicMock()
    update_result = MagicMock()
    update_result.rowcount = 1
    session.execute = AsyncMock(return_value=update_result)
    session.flush = AsyncMock()
    session.add = MagicMock()

    attempt = MagicMock()
    attempt.id = 9
    attempt.worker_id = "w1"
    attempt.worker_epoch = "e1"
    attempt.slot_generation = 5
    worker = MagicMock()
    worker.slot_generation = 4

    async def _get(model, key):
        return attempt

    async def _scalar(_stmt):
        return worker

    session.get = _get
    session.scalar = _scalar
    repo = RenderRepository(session)

    async def _run() -> None:
        ok = await repo.mark_attempt_accepted(9, request_digest="digest")
        assert ok is True
        assert worker.slot_generation == 5

    asyncio.run(_run())


def test_asset_not_ready_is_infrastructure_not_content() -> None:
    """资源未就绪不得映射为内容失败。"""

    from app.services.rendering.domain_facade import (
        RenderDomainFacade,
        _is_infrastructure_error,
    )

    assert _is_infrastructure_error("RENDER_ASSET_NOT_READY")
    assert not _is_infrastructure_error("RENDER_CONTENT_ERROR")
    result = RenderDomainFacade._page_unavailable_result("资源未就绪")  # noqa: SLF001
    assert result["status"] == "unavailable"
    assert result["retryable"] is True
