"""文件功能：声明远程渲染契约包测试，覆盖错误模型、摘要与票据校验。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from render_contracts.errors import ERROR_CODE_WORKER_BUSY, RenderContractError, RenderError  # noqa: E402
from render_contracts.schema import (  # noqa: E402
    ArtifactDescriptor,
    ExecutionRequest,
    ExecutionResult,
    SnapshotRef,
    ViewportSpec,
)
from render_contracts.tokens import (  # noqa: E402
    AdmissionTicket,
    PreviewAccess,
    canonical_json,
    compute_request_key,
    compute_render_digest,
    issue_worker_credential,
    sha256_hex,
    sign_payload,
    verify_worker_credential,
)

pytestmark = pytest.mark.unit


def _issue_ticket(
    *,
    secret: bytes = b"unit-test-secret",
    attempt_id: str = "a1",
    slot_generation: int = 1,
    accept_before_delta: timedelta = timedelta(seconds=30),
    stop_by_delta: timedelta = timedelta(seconds=60),
    request_digest: str = "digest",
) -> AdmissionTicket:
    """构造便于测试的接入票据。"""

    now = datetime.now(UTC)
    return AdmissionTicket.issue(
        secret=secret,
        request_digest=request_digest,
        workspace_id=1,
        worker_id="worker-1",
        worker_epoch="epoch-1",
        slot_generation=slot_generation,
        accept_before=now + accept_before_delta,
        stop_by=now + stop_by_delta,
        attempt_id=attempt_id,
    )


def _make_request(
    *,
    ticket: AdmissionTicket,
    preview_access: PreviewAccess | None = None,
    attempt_id: str = "a1",
    request_digest: str = "digest",
    operation: str = "page.capture",
    operation_options: dict | None = None,
) -> ExecutionRequest:
    """构造便于测试的执行请求。"""

    now = datetime.now(UTC)
    return ExecutionRequest(
        contract_version="internal/render/v1",
        operation=operation,
        request_id="r1",
        attempt_id=attempt_id,
        request_digest=request_digest,
        workspace_id=1,
        trace_id="t1",
        snapshot_ref=SnapshotRef(artifact_id="art", input_digest="in"),
        input_digest="in",
        render_profile_digest="prof",
        viewport=ViewportSpec(width=100, height=100),
        operation_options=operation_options or {},
        deadline_at=now.isoformat(),
        remaining_budget_ms=1000,
        admission_ticket=ticket,
        preview_access=preview_access
        or PreviewAccess(
            navigation_base_url="http://runtime/preview",
            preview_token="tok",
            artifact_id="art",
            expires_at=(now + timedelta(seconds=60)).isoformat(),
            runtime_protocol_version="render-ready.v1",
        ),
    )


def test_render_error_from_code_exposes_category_and_retryable() -> None:
    """按错误码应还原类别与默认可重试性。"""

    error = RenderError.from_code(ERROR_CODE_WORKER_BUSY, message="忙碌")
    assert error.category == "capacity"
    assert error.retryable is True
    assert error.to_dict()["code"] == ERROR_CODE_WORKER_BUSY


def test_request_and_render_digest_are_stable() -> None:
    """同一输入应产生稳定 request/render digest。"""

    render_digest = compute_render_digest(
        render_profile_digest="profile",
        viewport={"width": 1920, "height": 1080, "device_scale_factor": 1},
        operation_options={"quality": "high"},
    )
    first = compute_request_key(
        owner_key="page-screenshot:42:v3",
        business_stage="page.screenshot",
        operation="page.capture",
        input_digest="abc",
        render_digest=render_digest,
    )
    second = compute_request_key(
        owner_key="page-screenshot:42:v3",
        business_stage="page.screenshot",
        operation="page.capture",
        input_digest="abc",
        render_digest=render_digest,
    )
    assert first == second
    assert len(first) == 64


def test_admission_ticket_signature_roundtrip() -> None:
    """票据签发后可通过密钥校验，篡改后失败。"""

    secret = b"unit-test-secret"
    ticket = _issue_ticket(secret=secret)
    ticket.validate(request_digest="digest", workspace_id=1, attempt_id="a1", secret=secret)
    tampered = AdmissionTicket(**{**ticket.to_dict(), "request_digest": "other"})
    with pytest.raises(RenderContractError):
        tampered.validate(request_digest="digest", secret=secret)


def test_admission_ticket_binds_attempt_id() -> None:
    """attempt_id 必须进入签名载荷，且校验时强制匹配。"""

    secret = b"unit-test-secret"
    ticket = _issue_ticket(secret=secret, attempt_id="att-1")
    ticket.validate(attempt_id="att-1", secret=secret)
    with pytest.raises(RenderContractError, match="attempt_id"):
        ticket.validate(attempt_id="att-2", secret=secret)
    tampered = AdmissionTicket(**{**ticket.to_dict(), "attempt_id": "att-2"})
    with pytest.raises(RenderContractError):
        tampered.validate(attempt_id="att-2", secret=secret)
    with pytest.raises(RenderContractError):
        AdmissionTicket.issue(
            secret=secret,
            request_digest="d",
            workspace_id=1,
            worker_id="w",
            worker_epoch="e",
            slot_generation=1,
            accept_before=datetime.now(UTC) + timedelta(seconds=30),
            stop_by=datetime.now(UTC) + timedelta(seconds=60),
            attempt_id="",
        )


def test_admission_ticket_enforces_stop_by() -> None:
    """now >= stop_by 时票据必须拒绝。"""

    secret = b"unit-test-secret"
    expired = _issue_ticket(
        secret=secret,
        accept_before_delta=timedelta(seconds=30),
        stop_by_delta=timedelta(seconds=-1),
    )
    with pytest.raises(RenderContractError, match="停止期限"):
        expired.validate(secret=secret)
    boundary = _issue_ticket(
        secret=secret,
        accept_before_delta=timedelta(seconds=300),
        stop_by_delta=timedelta(seconds=60),
    )
    stop_at = datetime.now(UTC) + timedelta(seconds=60)
    with pytest.raises(RenderContractError, match="停止期限"):
        boundary.validate(secret=secret, now=stop_at)


def test_admission_ticket_slot_generation_strict_equality() -> None:
    """slot_generation 严格相等：更高期望为过期，更低为未接管/未签发。"""

    secret = b"unit-test-secret"
    ticket = _issue_ticket(secret=secret, slot_generation=3)
    ticket.validate(secret=secret, slot_generation=3)
    with pytest.raises(RenderContractError, match="过期"):
        ticket.validate(secret=secret, slot_generation=4)
    with pytest.raises(RenderContractError, match="未接管"):
        ticket.validate(secret=secret, slot_generation=2)


def test_worker_credential_roundtrip() -> None:
    """服务身份凭证应可签发并校验。"""

    secret = b"cred-secret"
    token = issue_worker_credential(worker_id="renderer-1", secret=secret)
    assert verify_worker_credential(token, secret) == "renderer-1"
    assert verify_worker_credential(token, b"other") is None


def test_worker_credential_rejects_non_dict_json() -> None:
    """凭证 JSON 非对象时必须拒绝，避免 pop 崩溃或误验。"""

    secret = b"cred-secret"
    assert verify_worker_credential("[]", secret) is None
    assert verify_worker_credential('["renderer-1"]', secret) is None
    assert verify_worker_credential('"renderer-1"', secret) is None
    assert verify_worker_credential("123", secret) is None
    assert verify_worker_credential("null", secret) is None


def test_worker_credential_requires_purpose() -> None:
    """凭证必须携带 purpose=render-service，否则拒绝。"""

    secret = b"cred-secret"
    payload = {
        "purpose": "other",
        "worker_id": "renderer-1",
        "issued_at": "2020-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "nonce": "n",
    }
    token = canonical_json({**payload, "signature": sign_payload(payload, secret)})
    assert verify_worker_credential(token, secret) is None


def test_preview_access_url_allowlist() -> None:
    """预览 URL 仅允许 http/https，拒绝 file、空 scheme 与链路本地地址。"""

    def access(nav: str, asset: str | None = None, headers: dict | None = None) -> PreviewAccess:
        return PreviewAccess(
            navigation_base_url=nav,
            preview_token="tok",
            artifact_id="art",
            expires_at="2099-01-01T00:00:00Z",
            runtime_protocol_version="render-ready.v1",
            asset_base_url=asset,
            extra_http_headers=headers,
        )

    access("https://example.com/preview").validate()
    access("http://127.0.0.1:7373/preview", asset="http://cdn.example.com/a").validate()
    with pytest.raises(RenderContractError):
        access("file:///etc/passwd").validate()
    with pytest.raises(RenderContractError):
        access("runtime/preview").validate()
    with pytest.raises(RenderContractError):
        access("").validate()
    with pytest.raises(RenderContractError):
        access("http://169.254.169.254/latest/meta-data").validate()
    with pytest.raises(RenderContractError):
        access("http://ok.example.com", asset="file:///tmp").validate()
    for header in ({"Authorization": "x"}, {"cookie": "a=b"}, {"HOST": "evil"}):
        with pytest.raises(RenderContractError):
            access("http://ok.example.com", headers=header).validate()


def test_execution_request_rejects_unknown_operation() -> None:
    """未知操作应在契约层拒绝。"""

    ticket = _issue_ticket()
    request = _make_request(ticket=ticket, operation="page.unknown")
    with pytest.raises(RenderContractError):
        request.validate()


def test_execution_request_rejects_bad_scenarios() -> None:
    """component.diagnose 的 scenarios 必须为列表且不超过上限。"""

    ticket = _issue_ticket()
    with pytest.raises(RenderContractError):
        _make_request(
            ticket=ticket,
            operation="component.diagnose",
            operation_options={"scenarios": "not-a-list"},
        ).validate()
    with pytest.raises(RenderContractError):
        _make_request(
            ticket=ticket,
            operation="component.diagnose",
            operation_options={"scenarios": [{"id": i} for i in range(17)]},
        ).validate()
    _make_request(
        ticket=ticket,
        operation="component.diagnose",
        operation_options={"scenarios": [{"id": 1}]},
    ).validate()


def test_artifact_name_rejects_unsafe_paths() -> None:
    """产物 name 禁止路径分隔符与上级目录引用。"""

    with pytest.raises(RenderContractError):
        ArtifactDescriptor(name="a/b.png", content_type="image/png", byte_length=1, sha256="x")
    with pytest.raises(RenderContractError):
        ArtifactDescriptor(name="..\\evil.png", content_type="image/png", byte_length=1, sha256="x")
    with pytest.raises(RenderContractError):
        ArtifactDescriptor(name="..", content_type="image/png", byte_length=1, sha256="x")
    ArtifactDescriptor(name="shot-v1.png", content_type="image/png", byte_length=1, sha256="x")
    with pytest.raises(RenderContractError):
        ExecutionResult.from_dict(
            {
                "request_id": "r",
                "attempt_id": "a",
                "worker_id": "w",
                "worker_epoch": "e",
                "slot_generation": 1,
                "operation": "page.capture",
                "input_digest": "i",
                "render_profile_digest": "p",
                "request_digest": "d",
                "result_schema_version": "render-result.v1",
                "artifacts": [
                    {
                        "name": "../etc/passwd",
                        "content_type": "image/png",
                        "byte_length": 1,
                        "sha256": "x",
                    }
                ],
            }
        )


def test_bool_string_coercion_is_explicit() -> None:
    """字符串 'false' 必须解析为 False，而非 bool() 误判为真。"""

    error = RenderError.from_dict(
        {"code": ERROR_CODE_WORKER_BUSY, "message": "m", "retryable": "false"}
    )
    assert error.retryable is False
    error_true = RenderError.from_dict(
        {"code": ERROR_CODE_WORKER_BUSY, "message": "m", "retryable": "true"}
    )
    assert error_true.retryable is True
    result = ExecutionResult.from_dict(
        {
            "request_id": "r",
            "attempt_id": "a",
            "worker_id": "w",
            "worker_epoch": "e",
            "slot_generation": 1,
            "operation": "page.capture",
            "input_digest": "i",
            "render_profile_digest": "p",
            "request_digest": "d",
            "result_schema_version": "render-result.v1",
            "truncated": "false",
            "diagnostics": [{"severity": "info", "code": "c", "message": "m", "truncated": "false"}],
        }
    )
    assert result.truncated is False
    assert result.diagnostics[0].truncated is False


def test_execution_result_schema_version_required() -> None:
    """结果 Schema 版本不匹配时拒绝。"""

    with pytest.raises(RenderContractError):
        ExecutionResult.from_dict(
            {
                "request_id": "r",
                "attempt_id": "a",
                "worker_id": "w",
                "worker_epoch": "e",
                "slot_generation": 1,
                "operation": "page.capture",
                "input_digest": "i",
                "render_profile_digest": "p",
                "request_digest": "d",
                "result_schema_version": "old",
            }
        )


def test_viewport_rejects_oversized_canvas() -> None:
    """超过物理像素上限的视口应被拒绝。"""

    with pytest.raises(RenderContractError):
        ViewportSpec(width=9000, height=9000).validate()


def test_sha256_hex_matches_digest() -> None:
    """摘要工具应输出 64 位十六进制。"""

    assert sha256_hex("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
