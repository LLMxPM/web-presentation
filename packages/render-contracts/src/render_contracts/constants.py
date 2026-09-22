"""文件功能：定义远程渲染控制协议的版本、操作与状态常量。"""

from __future__ import annotations

from typing import Final

PROTOCOL_VERSION: Final[str] = "internal/render/v1"
PROTOCOL_PATH_PREFIX: Final[str] = "/internal/render/v1"
RUNTIME_RENDER_PROTOCOL_VERSION: Final[str] = "render-ready.v1"
RESULT_SCHEMA_VERSION: Final[str] = "render-result.v1"
LAYOUT_ANALYSIS_SCHEMA_VERSION: Final[int] = 3
COMPONENT_SCENARIO_PROTOCOL_VERSION: Final[str] = "component-scenarios.v1"
ADMISSION_TICKET_VERSION: Final[str] = "admission-ticket.v1"
# Renderer 服务身份凭证的固定用途标识，防止凭证被挪作他用。
WORKER_CREDENTIAL_PURPOSE: Final[str] = "render-service"

OPERATION_PAGE_CAPTURE: Final[str] = "page.capture"
OPERATION_PAGE_DIAGNOSE: Final[str] = "page.diagnose"
# 组件远程渲染诊断协议保留给 Renderer/联调；内容助手业务入口不再调用。
OPERATION_COMPONENT_DIAGNOSE: Final[str] = "component.diagnose"
SUPPORTED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        OPERATION_PAGE_CAPTURE,
        OPERATION_PAGE_DIAGNOSE,
        OPERATION_COMPONENT_DIAGNOSE,
    }
)

# RenderRequest 状态
REQUEST_STATUS_QUEUED: Final[str] = "queued"
REQUEST_STATUS_EXECUTING: Final[str] = "executing"
REQUEST_STATUS_RETRY_WAIT: Final[str] = "retry_wait"
REQUEST_STATUS_SUCCEEDED: Final[str] = "succeeded"
REQUEST_STATUS_FAILED: Final[str] = "failed"
REQUEST_STATUS_CANCELLED: Final[str] = "cancelled"
REQUEST_STATUS_EXPIRED: Final[str] = "expired"
REQUEST_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {
        REQUEST_STATUS_SUCCEEDED,
        REQUEST_STATUS_FAILED,
        REQUEST_STATUS_CANCELLED,
        REQUEST_STATUS_EXPIRED,
    }
)

# RenderAttempt 状态
ATTEMPT_STATUS_RESERVED: Final[str] = "reserved"
ATTEMPT_STATUS_DISPATCHED: Final[str] = "dispatched"
ATTEMPT_STATUS_ACCEPTED: Final[str] = "accepted"
ATTEMPT_STATUS_RUNNING: Final[str] = "running"
ATTEMPT_STATUS_CLEANING: Final[str] = "cleaning"
ATTEMPT_STATUS_TERMINAL: Final[str] = "terminal"
ATTEMPT_STATUS_UNKNOWN: Final[str] = "unknown"
ATTEMPT_OCCUPYING_STATUSES: Final[frozenset[str]] = frozenset(
    {
        ATTEMPT_STATUS_RESERVED,
        ATTEMPT_STATUS_DISPATCHED,
        ATTEMPT_STATUS_ACCEPTED,
        ATTEMPT_STATUS_RUNNING,
        ATTEMPT_STATUS_CLEANING,
        ATTEMPT_STATUS_UNKNOWN,
    }
)

# 执行回执中的资源状态
RESOURCE_STATE_RELEASED: Final[str] = "released"
RESOURCE_STATE_RETAINED: Final[str] = "retained"
RESOURCE_STATE_UNKNOWN: Final[str] = "unknown"

# 业务调度类别
SCHEDULE_CATEGORY_INTERACTIVE: Final[str] = "interactive"
SCHEDULE_CATEGORY_BACKGROUND: Final[str] = "background"
SCHEDULE_CATEGORY_WEIGHT_INTERACTIVE: Final[int] = 3
SCHEDULE_CATEGORY_WEIGHT_BACKGROUND: Final[int] = 1

# 默认限制
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_CLEANUP_GRACE_SECONDS: Final[float] = 5.0
DEFAULT_RESULT_TTL_SECONDS: Final[int] = 600
DEFAULT_MAX_ATTEMPTS: Final[int] = 3
DEFAULT_MAX_CANVAS_PIXELS: Final[int] = 16_000_000
DEFAULT_MAX_CANVAS_EDGE: Final[int] = 8192
DEFAULT_MAX_PNG_BYTES: Final[int] = 32 * 1024 * 1024
DEFAULT_MAX_DIAGNOSTIC_JSON_BYTES: Final[int] = 1024 * 1024
DEFAULT_MAX_COMPONENT_SCENARIOS: Final[int] = 16

# HTTP 端点路径（相对协议前缀）
ENDPOINT_CAPABILITIES: Final[str] = f"{PROTOCOL_PATH_PREFIX}/capabilities"
ENDPOINT_EXECUTIONS: Final[str] = f"{PROTOCOL_PATH_PREFIX}/executions"
ENDPOINT_LIVEZ: Final[str] = "/livez"
ENDPOINT_READYZ: Final[str] = "/readyz"
