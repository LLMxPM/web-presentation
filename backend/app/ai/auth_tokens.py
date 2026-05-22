"""文件功能：签发历史 AgentOS 兼容令牌，并集中定义工具权限 scope 常量。"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.auth_service import AuthContext
from app.services.token_service import TokenService

PAGE_TOOL_READ_SCOPES = ("tools:page:read",)
PAGE_TOOL_WRITE_SCOPES = ("tools:page:write",)
PAGE_TOOL_SNAPSHOT_SCOPES = ("tools:page:snapshot",)
PAGE_TOOL_PREVIEW_SCOPES = ("tools:preview:refresh",)
PAGE_TOOL_VISUAL_SCOPES = ("tools:page:visual",)
PROJECT_TOOL_READ_SCOPES = ("tools:project:read",)
PROJECT_TOOL_WRITE_SCOPES = ("tools:project:write",)
COMPONENT_TOOL_READ_SCOPES = ("tools:component:read",)
COMPONENT_TOOL_WRITE_SCOPES = ("tools:component:write",)
COMPONENT_TOOL_DELETE_SCOPES = ("tools:component:delete",)
RESOURCE_TOOL_READ_SCOPES = ("tools:resource:read",)
RESOURCE_TOOL_WRITE_SCOPES = ("tools:resource:write",)
CODE_CHECK_TOOL_SCOPES = ("tools:code:check",)


def build_agent_access_token(
    current: AuthContext,
    *,
    agent_id: str,
    session_id: str | None,
    workspace_id: int | None,
    project_id: int | None,
    page_id: int | None,
    role: str,
    component_id: int | None = None,
    source: str = "editor-page-detail",
) -> str:
    """为历史 AgentOS 兼容链路签发短期访问令牌。"""

    settings = get_settings()
    scopes = [
        "agents:read",
        f"agents:{agent_id}:read",
        f"agents:{agent_id}:run",
        "sessions:read",
        "sessions:write",
    ]
    payload: dict[str, Any] = {
        "aud": settings.ai_agent_os_id,
        "sub": f"user:{current.user.id}",
        "session_id": session_id,
        "scopes": scopes,
        "source": source,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "page_id": page_id,
        "component_id": component_id,
        "role": role,
        "backend_session_id": current.backend_session_id,
    }
    return TokenService.generate_signed_token(
        payload,
        expires_in_seconds=settings.ai_agent_token_ttl_seconds,
        subject=f"user:{current.user.id}",
    )


def extract_user_id(subject: str | None) -> int:
    """从 `user:{id}` 形式的 subject 中提取用户主键。"""

    normalized_subject = str(subject or "").strip()
    if not normalized_subject.startswith("user:"):
        raise AppException(status_code=403, code="AI_TOOL_SUBJECT_INVALID", detail="工具调用主体不合法。")
    try:
        return int(normalized_subject.split(":", maxsplit=1)[1])
    except ValueError as exc:
        raise AppException(status_code=403, code="AI_TOOL_SUBJECT_INVALID", detail="工具调用主体不合法。") from exc
