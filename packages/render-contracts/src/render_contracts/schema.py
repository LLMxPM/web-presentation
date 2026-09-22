"""文件功能：定义远程渲染协议中的数据传输对象与校验逻辑。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Final

from render_contracts.constants import (
    DEFAULT_MAX_CANVAS_EDGE,
    DEFAULT_MAX_CANVAS_PIXELS,
    DEFAULT_MAX_COMPONENT_SCENARIOS,
    DEFAULT_MAX_DIAGNOSTIC_JSON_BYTES,
    DEFAULT_MAX_PNG_BYTES,
    PROTOCOL_VERSION,
    RESULT_SCHEMA_VERSION,
    SUPPORTED_OPERATIONS,
)
from render_contracts.errors import RenderContractError, parse_bool
from render_contracts.tokens import AdmissionTicket, PreviewAccess

# 产物文件名仅允许字母数字、点、短横线与下划线，禁止路径分隔符。
_ARTIFACT_NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_artifact_name(name: str) -> None:
    """校验产物文件名安全字符集，拒绝路径分隔符与上级目录引用。"""

    if not name or not _ARTIFACT_NAME_PATTERN.fullmatch(name):
        raise RenderContractError("产物 name 仅允许字母、数字、点、短横线与下划线。")
    if ".." in name:
        raise RenderContractError("产物 name 禁止包含上级目录引用。")


@dataclass(slots=True, frozen=True)
class ViewportSpec:
    """执行时使用的固定画布视口。"""

    width: int
    height: int
    device_scale_factor: float = 1.0

    def validate(self) -> None:
        """校验视口与物理像素限制。"""

        if self.width <= 0 or self.height <= 0:
            raise RenderContractError("viewport 宽高必须为正整数。")
        if self.device_scale_factor <= 0:
            raise RenderContractError("device_scale_factor 必须大于 0。")
        physical_w = self.width * self.device_scale_factor
        physical_h = self.height * self.device_scale_factor
        if physical_w > DEFAULT_MAX_CANVAS_EDGE or physical_h > DEFAULT_MAX_CANVAS_EDGE:
            raise RenderContractError("物理画布单边超过 8192 像素上限。")
        if physical_w * physical_h > DEFAULT_MAX_CANVAS_PIXELS:
            raise RenderContractError("物理画布超过 16MP 上限。")

    def to_dict(self) -> dict[str, object]:
        """序列化视口。"""

        return {
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ViewportSpec":
        """从字典解析视口。"""

        return cls(
            width=int(payload.get("width") or 0),
            height=int(payload.get("height") or 0),
            device_scale_factor=float(payload.get("device_scale_factor") or 1.0),
        )


@dataclass(slots=True, frozen=True)
class SnapshotRef:
    """不可变输入 artifact 引用。"""

    artifact_id: str
    input_digest: str
    storage_kind: str = "object_store"
    storage_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        """序列化快照引用。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SnapshotRef":
        """从字典解析快照引用。"""

        artifact_id = str(payload.get("artifact_id") or "").strip()
        input_digest = str(payload.get("input_digest") or "").strip()
        if not artifact_id or not input_digest:
            raise RenderContractError("snapshot_ref 缺少 artifact_id 或 input_digest。")
        return cls(
            artifact_id=artifact_id,
            input_digest=input_digest,
            storage_kind=str(payload.get("storage_kind") or "runtime_artifact"),
            storage_path=(str(payload["storage_path"]) if payload.get("storage_path") else None),
        )


@dataclass(slots=True, frozen=True)
class ExecutionRequest:
    """Backend 派发给 Renderer 的一次执行尝试请求。"""

    contract_version: str
    operation: str
    request_id: str
    attempt_id: str
    request_digest: str
    workspace_id: int
    trace_id: str
    snapshot_ref: SnapshotRef
    input_digest: str
    render_profile_digest: str
    viewport: ViewportSpec
    operation_options: dict[str, Any]
    deadline_at: str
    remaining_budget_ms: int
    admission_ticket: AdmissionTicket
    preview_access: PreviewAccess
    render_category: str = "background"

    def validate(self) -> None:
        """校验契约版本、操作类型与关键身份字段。"""

        if self.contract_version != PROTOCOL_VERSION:
            raise RenderContractError(
                f"契约版本不匹配：期望 {PROTOCOL_VERSION}，实际 {self.contract_version}。",
            )
        if self.operation not in SUPPORTED_OPERATIONS:
            raise RenderContractError(f"未知渲染操作：{self.operation}")
        if not self.request_id or not self.attempt_id or not self.request_digest:
            raise RenderContractError("执行请求缺少 request_id、attempt_id 或 request_digest。")
        if self.remaining_budget_ms <= 0:
            raise RenderContractError("remaining_budget_ms 必须为正。")
        self.viewport.validate()
        if self.operation in {"component.diagnose"}:
            raw_scenarios = self.operation_options.get("scenarios")
            if raw_scenarios is not None and not isinstance(raw_scenarios, list):
                if raw_scenarios:
                    raise RenderContractError("component.diagnose 的 scenarios 必须为列表。")
            else:
                scenarios = raw_scenarios if isinstance(raw_scenarios, list) else []
                if len(scenarios) > DEFAULT_MAX_COMPONENT_SCENARIOS:
                    raise RenderContractError("组件场景总数超过 16 上限。")
        self.admission_ticket.validate(
            request_digest=self.request_digest,
            workspace_id=self.workspace_id,
            attempt_id=self.attempt_id,
        )
        self.preview_access.validate()

    def to_dict(self) -> dict[str, object]:
        """序列化执行请求。"""

        return {
            "contract_version": self.contract_version,
            "operation": self.operation,
            "request_id": self.request_id,
            "attempt_id": self.attempt_id,
            "request_digest": self.request_digest,
            "workspace_id": self.workspace_id,
            "trace_id": self.trace_id,
            "snapshot_ref": self.snapshot_ref.to_dict(),
            "input_digest": self.input_digest,
            "render_profile_digest": self.render_profile_digest,
            "viewport": self.viewport.to_dict(),
            "operation_options": self.operation_options,
            "deadline_at": self.deadline_at,
            "remaining_budget_ms": self.remaining_budget_ms,
            "admission_ticket": self.admission_ticket.to_dict(),
            "preview_access": self.preview_access.to_dict(),
            "render_category": self.render_category,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ExecutionRequest":
        """从字典解析执行请求。"""

        return cls(
            contract_version=str(payload.get("contract_version") or ""),
            operation=str(payload.get("operation") or ""),
            request_id=str(payload.get("request_id") or ""),
            attempt_id=str(payload.get("attempt_id") or ""),
            request_digest=str(payload.get("request_digest") or ""),
            workspace_id=int(payload.get("workspace_id") or 0),
            trace_id=str(payload.get("trace_id") or ""),
            snapshot_ref=SnapshotRef.from_dict(dict(payload.get("snapshot_ref") or {})),
            input_digest=str(payload.get("input_digest") or ""),
            render_profile_digest=str(payload.get("render_profile_digest") or ""),
            viewport=ViewportSpec.from_dict(dict(payload.get("viewport") or {})),
            operation_options=dict(payload.get("operation_options") or {}),
            deadline_at=str(payload.get("deadline_at") or ""),
            remaining_budget_ms=int(payload.get("remaining_budget_ms") or 0),
            admission_ticket=AdmissionTicket.from_dict(dict(payload.get("admission_ticket") or {})),
            preview_access=PreviewAccess.from_dict(dict(payload.get("preview_access") or {})),
            render_category=str(payload.get("render_category") or "background"),
        )


@dataclass(slots=True, frozen=True)
class ExecutionReceipt:
    """Renderer 接管 attempt 后的稳定回执。"""

    attempt_id: str
    request_id: str
    worker_id: str
    worker_epoch: str
    slot_generation: int
    request_digest: str
    status: str
    resource_state: str
    accepted_at: str
    stage: str = "accepted"
    started_at: str | None = None
    finished_at: str | None = None
    cleaned_at: str | None = None
    error: dict[str, Any] | None = None
    result_descriptor: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        """序列化回执。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ExecutionReceipt":
        """从字典解析回执。"""

        return cls(
            attempt_id=str(payload.get("attempt_id") or ""),
            request_id=str(payload.get("request_id") or ""),
            worker_id=str(payload.get("worker_id") or ""),
            worker_epoch=str(payload.get("worker_epoch") or ""),
            slot_generation=int(payload.get("slot_generation") or 0),
            request_digest=str(payload.get("request_digest") or ""),
            status=str(payload.get("status") or "unknown"),
            resource_state=str(payload.get("resource_state") or "unknown"),
            accepted_at=str(payload.get("accepted_at") or ""),
            stage=str(payload.get("stage") or "accepted"),
            started_at=(str(payload["started_at"]) if payload.get("started_at") else None),
            finished_at=(str(payload["finished_at"]) if payload.get("finished_at") else None),
            cleaned_at=(str(payload["cleaned_at"]) if payload.get("cleaned_at") else None),
            error=(dict(payload["error"]) if payload.get("error") else None),
            result_descriptor=(
                dict(payload["result_descriptor"]) if payload.get("result_descriptor") else None
            ),
        )


@dataclass(slots=True, frozen=True)
class ArtifactDescriptor:
    """Renderer 终态产物描述符。"""

    name: str
    content_type: str
    byte_length: int
    sha256: str
    width: int | None = None
    height: int | None = None

    def __post_init__(self) -> None:
        """构造时校验产物文件名安全字符集。"""

        _validate_artifact_name(self.name)

    def to_dict(self) -> dict[str, object]:
        """序列化产物描述符。"""

        return asdict(self)


@dataclass(slots=True, frozen=True)
class DiagnosticItem:
    """内容诊断条目；成功诊断可以包含内容错误。"""

    severity: str
    code: str
    message: str
    scenario: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        """序列化诊断条目。"""

        return asdict(self)


@dataclass(slots=True, frozen=True)
class ExecutionResult:
    """Renderer 终态成功结果。"""

    request_id: str
    attempt_id: str
    worker_id: str
    worker_epoch: str
    slot_generation: int
    operation: str
    input_digest: str
    render_profile_digest: str
    request_digest: str
    result_schema_version: str
    environment_summary: dict[str, Any]
    artifacts: list[ArtifactDescriptor] = field(default_factory=list)
    diagnostics: list[DiagnosticItem] = field(default_factory=list)
    layout: dict[str, Any] | None = None
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    finished_at: str = ""
    cleaned_at: str = ""
    resource_state: str = "released"
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        """序列化执行结果。"""

        return {
            "request_id": self.request_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "worker_epoch": self.worker_epoch,
            "slot_generation": self.slot_generation,
            "operation": self.operation,
            "input_digest": self.input_digest,
            "render_profile_digest": self.render_profile_digest,
            "request_digest": self.request_digest,
            "result_schema_version": self.result_schema_version,
            "environment_summary": self.environment_summary,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "layout": self.layout,
            "scenarios": self.scenarios,
            "finished_at": self.finished_at,
            "cleaned_at": self.cleaned_at,
            "resource_state": self.resource_state,
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ExecutionResult":
        """从字典解析执行结果并做基础 Schema 校验。"""

        schema_version = str(payload.get("result_schema_version") or "")
        if schema_version != RESULT_SCHEMA_VERSION:
            raise RenderContractError(
                f"结果 Schema 版本不匹配：期望 {RESULT_SCHEMA_VERSION}，实际 {schema_version}。",
            )
        artifacts: list[ArtifactDescriptor] = []
        for raw in payload.get("artifacts") or []:
            item = dict(raw)
            name = str(item.get("name") or "")
            byte_length = int(item.get("byte_length") or 0)
            if not name or byte_length < 0:
                raise RenderContractError("产物描述符缺少 name 或非法 byte_length。")
            _validate_artifact_name(name)
            if byte_length > DEFAULT_MAX_PNG_BYTES:
                raise RenderContractError("产物大小超过 32MiB 上限。")
            artifacts.append(
                ArtifactDescriptor(
                    name=name,
                    content_type=str(item.get("content_type") or "application/octet-stream"),
                    byte_length=byte_length,
                    sha256=str(item.get("sha256") or ""),
                    width=(int(item["width"]) if item.get("width") is not None else None),
                    height=(int(item["height"]) if item.get("height") is not None else None),
                )
            )
        diagnostics = [
            DiagnosticItem(
                severity=str(item.get("severity") or "warning"),
                code=str(item.get("code") or ""),
                message=str(item.get("message") or ""),
                scenario=(str(item["scenario"]) if item.get("scenario") else None),
                evidence=dict(item.get("evidence") or {}),
                truncated=parse_bool(item.get("truncated", False)),
            )
            for item in (payload.get("diagnostics") or [])
        ]
        layout = payload.get("layout")
        if layout is not None:
            encoded = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > DEFAULT_MAX_DIAGNOSTIC_JSON_BYTES:
                raise RenderContractError("诊断 JSON 超过 1MiB 上限。")
        raw_scenarios = payload.get("scenarios")
        if raw_scenarios is not None and not isinstance(raw_scenarios, list):
            if raw_scenarios:
                raise RenderContractError("scenarios 必须为列表。")
            scenarios: list[dict[str, Any]] = []
        else:
            scenarios = list(raw_scenarios or [])
            if len(scenarios) > DEFAULT_MAX_COMPONENT_SCENARIOS:
                raise RenderContractError("组件场景总数超过 16 上限。")
        resource_state = str(payload.get("resource_state") or "")
        return cls(
            request_id=str(payload.get("request_id") or ""),
            attempt_id=str(payload.get("attempt_id") or ""),
            worker_id=str(payload.get("worker_id") or ""),
            worker_epoch=str(payload.get("worker_epoch") or ""),
            slot_generation=int(payload.get("slot_generation") or 0),
            operation=str(payload.get("operation") or ""),
            input_digest=str(payload.get("input_digest") or ""),
            render_profile_digest=str(payload.get("render_profile_digest") or ""),
            request_digest=str(payload.get("request_digest") or ""),
            result_schema_version=schema_version,
            environment_summary=dict(payload.get("environment_summary") or {}),
            artifacts=artifacts,
            diagnostics=diagnostics,
            layout=(dict(layout) if isinstance(layout, dict) else None),
            scenarios=scenarios,
            finished_at=str(payload.get("finished_at") or ""),
            cleaned_at=str(payload.get("cleaned_at") or ""),
            resource_state=resource_state,
            truncated=parse_bool(payload.get("truncated", False)),
        )


@dataclass(slots=True, frozen=True)
class WorkerCapabilities:
    """Renderer 实例能力与环境摘要。"""

    worker_id: str
    worker_epoch: str
    protocol_version: str
    runtime_render_protocol_version: str
    result_schema_version: str
    render_profile_digest: str
    environment_summary: dict[str, Any]
    limits: dict[str, Any]
    slot_state: str
    slot_generation: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "WorkerCapabilities":
        """从字典解析能力响应。"""

        return cls(
            worker_id=str(payload.get("worker_id") or ""),
            worker_epoch=str(payload.get("worker_epoch") or ""),
            protocol_version=str(payload.get("protocol_version") or ""),
            runtime_render_protocol_version=str(payload.get("runtime_render_protocol_version") or ""),
            result_schema_version=str(payload.get("result_schema_version") or ""),
            render_profile_digest=str(payload.get("render_profile_digest") or ""),
            environment_summary=dict(payload.get("environment_summary") or {}),
            limits=dict(payload.get("limits") or {}),
            slot_state=str(payload.get("slot_state") or "unknown"),
            slot_generation=int(payload.get("slot_generation") or 0),
        )
