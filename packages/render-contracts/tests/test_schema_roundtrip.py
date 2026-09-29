"""文件功能：render-contracts Python DTO 与 schemas/*.v1.json 双源对拍/往返测试。

AGENTS.md 要求 DTO 与 JSON Schema 双份事实源同步维护并补充对拍测试；本文件是该
承诺的机械化落地：结构对齐、示例 payload 可被 JSON Schema 接受、DTO 往返一致。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from render_contracts.constants import (  # noqa: E402
    ADMISSION_TICKET_VERSION,
    PROTOCOL_VERSION,
    RESULT_SCHEMA_VERSION,
    SUPPORTED_OPERATIONS,
)
from render_contracts.errors import (  # noqa: E402
    CATEGORY_CANCELLATION,
    CATEGORY_CAPACITY,
    CATEGORY_CONFIGURATION,
    CATEGORY_CONTENT,
    CATEGORY_INFRASTRUCTURE,
    CATEGORY_INPUT,
    CATEGORY_INTERNAL,
    CATEGORY_RESOURCE,
    CATEGORY_TIMEOUT,
    ERROR_CODE_CANCELLED,
    ERROR_CODE_CONTENT_ERROR,
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_QUEUE_FULL,
    ERROR_CODE_WORKER_BUSY,
    RenderError,
    error_http_status_table,
    http_status_for_error_code,
)
from render_contracts.schema import (  # noqa: E402
    ArtifactDescriptor,
    DiagnosticItem,
    ExecutionRequest,
    ExecutionResult,
    SnapshotRef,
    ViewportSpec,
)
from render_contracts.tokens import (  # noqa: E402
    AdmissionTicket,
    PreviewAccess,
)

pytestmark = pytest.mark.unit

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    """读取本地 JSON Schema 文件。"""

    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate_required_and_types(payload: dict[str, Any], schema: dict[str, Any], *, label: str) -> None:
    """轻量对拍：校验 required 字段存在，以及标量字段类型与 enum/const 约束。"""

    for key in schema.get("required", []):
        assert key in payload, f"{label} 缺少 required 字段 {key}"

    properties = schema.get("properties", {})
    for key, value in payload.items():
        prop = properties.get(key)
        if prop is None:
            continue
        if "const" in prop:
            assert value == prop["const"], f"{label}.{key} 应为 const={prop['const']!r}，实际 {value!r}"
        if "enum" in prop:
            assert value in prop["enum"], f"{label}.{key}={value!r} 不在 enum {prop['enum']}"
        expected_type = prop.get("type")
        if expected_type is None or value is None:
            continue
        type_ok = (
            (expected_type == "string" and isinstance(value, str))
            or (expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (expected_type == "number" and isinstance(value, int | float) and not isinstance(value, bool))
            or (expected_type == "boolean" and isinstance(value, bool))
            or (expected_type == "object" and isinstance(value, dict))
            or (expected_type == "array" and isinstance(value, list))
            or (
                isinstance(expected_type, list)
                and any(
                    (t == "string" and isinstance(value, str))
                    or (t == "integer" and isinstance(value, int) and not isinstance(value, bool))
                    or (t == "object" and isinstance(value, dict))
                    or (t == "array" and isinstance(value, list))
                    or (t == "null" and value is None)
                    for t in expected_type
                )
            )
        )
        assert type_ok, f"{label}.{key} 类型不符：schema={expected_type}，实际 {type(value).__name__}"


def _ticket() -> AdmissionTicket:
    """构造测试用接入票据。"""

    return AdmissionTicket(
        version=ADMISSION_TICKET_VERSION,
        ticket_id="t-1",
        attempt_id="a-1",
        request_digest="digest",
        workspace_id=1,
        worker_id="w-1",
        worker_epoch="e-1",
        slot_generation=1,
        issued_at="2026-09-28T00:00:00+00:00",
        accept_before="2026-09-28T00:01:00+00:00",
        stop_by="2026-09-28T00:02:00+00:00",
        signature="sig",
    )


def _preview() -> PreviewAccess:
    """构造测试用预览授权。"""

    return PreviewAccess(
        navigation_base_url="http://runtime/preview",
        preview_token="tok",
        artifact_id="art-1",
        expires_at="2026-09-28T00:02:00+00:00",
        runtime_protocol_version="render-ready.v1",
    )


def _request() -> ExecutionRequest:
    """构造测试用执行请求。"""

    return ExecutionRequest(
        contract_version=PROTOCOL_VERSION,
        operation="page.capture",
        request_id="r-1",
        attempt_id="a-1",
        request_digest="digest",
        workspace_id=1,
        trace_id="trace-1",
        snapshot_ref=SnapshotRef(artifact_id="art-1", input_digest="in-1"),
        input_digest="in-1",
        render_profile_digest="prof-1",
        viewport=ViewportSpec(width=1280, height=720),
        operation_options={},
        deadline_at="2026-09-28T00:02:00+00:00",
        remaining_budget_ms=30_000,
        admission_ticket=_ticket(),
        preview_access=_preview(),
        render_category="background",
    )


def _result() -> ExecutionResult:
    """构造测试用执行结果。"""

    return ExecutionResult(
        request_id="r-1",
        attempt_id="a-1",
        worker_id="w-1",
        worker_epoch="e-1",
        slot_generation=1,
        operation="page.capture",
        input_digest="in-1",
        render_profile_digest="prof-1",
        request_digest="digest",
        result_schema_version=RESULT_SCHEMA_VERSION,
        environment_summary={"browser": "chromium"},
        artifacts=[
            ArtifactDescriptor(
                name="page.png",
                content_type="image/png",
                byte_length=128,
                sha256="a" * 64,
                width=1280,
                height=720,
            )
        ],
        diagnostics=[
            DiagnosticItem(severity="warning", code="W1", message="overflow", truncated=False)
        ],
        layout={"nodes": 1},
        scenarios=[],
        finished_at="2026-09-28T00:01:00+00:00",
        cleaned_at="2026-09-28T00:01:01+00:00",
        resource_state="released",
        truncated=False,
    )


def test_execution_request_roundtrip_matches_json_schema() -> None:
    """执行请求 DTO 序列化应通过 JSON Schema 对拍，且 from_dict 往返一致。"""

    schema = _load_schema("execution-request.v1.json")
    payload = _request().to_dict()
    _validate_required_and_types(payload, schema, label="ExecutionRequest")

    nested = schema.get("$defs", {})
    _validate_required_and_types(payload["admission_ticket"], nested["admission_ticket"], label="admission_ticket")
    _validate_required_and_types(payload["preview_access"], nested["preview_access"], label="preview_access")

    restored = ExecutionRequest.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.operation in SUPPORTED_OPERATIONS
    assert restored.contract_version == PROTOCOL_VERSION


def test_execution_result_roundtrip_matches_json_schema() -> None:
    """执行结果 DTO 序列化应通过 JSON Schema 对拍，且 from_dict 往返一致。"""

    schema = _load_schema("execution-result.v1.json")
    payload = _result().to_dict()
    _validate_required_and_types(payload, schema, label="ExecutionResult")

    restored = ExecutionResult.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.result_schema_version == RESULT_SCHEMA_VERSION


def test_error_payload_matches_json_schema_and_code_enum() -> None:
    """错误结构应对拍 JSON Schema，且错误码 enum 与 errors.py 常量一致。"""

    schema = _load_schema("error.v1.json")
    schema_codes = set(schema["properties"]["code"]["enum"])
    expected_codes = {
        ERROR_CODE_QUEUE_FULL,
        ERROR_CODE_WORKER_BUSY,
        ERROR_CODE_CONTENT_ERROR,
        ERROR_CODE_CONTRACT_MISMATCH,
        ERROR_CODE_DEADLINE_EXCEEDED,
        ERROR_CODE_CANCELLED,
        ERROR_CODE_INTERNAL_ERROR,
    }
    assert expected_codes <= schema_codes

    schema_categories = set(schema["properties"]["category"]["enum"])
    expected_categories = {
        CATEGORY_CAPACITY,
        CATEGORY_INFRASTRUCTURE,
        CATEGORY_CONFIGURATION,
        CATEGORY_INPUT,
        CATEGORY_CONTENT,
        CATEGORY_RESOURCE,
        CATEGORY_TIMEOUT,
        CATEGORY_CANCELLATION,
        CATEGORY_INTERNAL,
    }
    assert schema_categories == expected_categories

    err = RenderError.from_code(ERROR_CODE_WORKER_BUSY, message="busy", stage="dispatch")
    payload = err.to_dict()
    _validate_required_and_types(payload, schema, label="RenderError")
    assert RenderError.from_dict(payload).to_dict() == payload


def test_json_schema_required_fields_align_with_dto_to_dict() -> None:
    """JSON Schema 的顶层 required 必须是 DTO to_dict 键的子集，避免双源漂移。"""

    request_schema = _load_schema("execution-request.v1.json")
    request_keys = set(_request().to_dict())
    assert set(request_schema["required"]) <= request_keys

    result_schema = _load_schema("execution-result.v1.json")
    result_keys = set(_result().to_dict())
    assert set(result_schema["required"]) <= result_keys


def test_error_http_status_map_matches_json_schema() -> None:
    """错误码→HTTP 状态映射必须与 error.v1.json 的 x-http-status-by-code 完全一致。"""

    schema = _load_schema("error.v1.json")
    schema_map = schema["x-http-status-by-code"]["properties"]
    python_map = error_http_status_table()
    assert schema_map == python_map
    assert set(schema_map) == set(schema["properties"]["code"]["enum"])
    for code, status in python_map.items():
        assert http_status_for_error_code(code) == status
        assert 400 <= status <= 599
    assert http_status_for_error_code("RENDER_UNKNOWN_CODE") == 500
