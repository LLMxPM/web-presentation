"""文件功能：远程渲染纯契约 Python 包，不依赖 Backend、ORM、Runtime 或 Playwright。"""

from render_contracts.constants import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
    PROTOCOL_VERSION,
    RESULT_SCHEMA_VERSION,
    RUNTIME_RENDER_PROTOCOL_VERSION,
)
from render_contracts.errors import (
    RenderContractError,
    RenderError,
    RenderExecutionError,
)
from render_contracts.schema import (
    ArtifactDescriptor,
    DiagnosticItem,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionResult,
    SnapshotRef,
    ViewportSpec,
    WorkerCapabilities,
)
from render_contracts.tokens import (
    AdmissionTicket,
    PreviewAccess,
    compute_render_digest,
    compute_request_digest,
    compute_request_key,
    issue_worker_credential,
    sha256_hex,
    verify_worker_credential,
)

__all__ = [
    "PROTOCOL_VERSION",
    "RESULT_SCHEMA_VERSION",
    "RUNTIME_RENDER_PROTOCOL_VERSION",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_RESULT_TTL_SECONDS",
    "RenderError",
    "RenderContractError",
    "RenderExecutionError",
    "ViewportSpec",
    "SnapshotRef",
    "ExecutionRequest",
    "ExecutionReceipt",
    "ExecutionResult",
    "ArtifactDescriptor",
    "DiagnosticItem",
    "WorkerCapabilities",
    "AdmissionTicket",
    "PreviewAccess",
    "compute_request_digest",
    "compute_render_digest",
    "compute_request_key",
    "sha256_hex",
    "issue_worker_credential",
    "verify_worker_credential",
]
