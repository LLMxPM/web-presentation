"""文件功能：验证 AI 工具授权窗口相关配置默认值与约束。"""

from types import SimpleNamespace

import pytest

from app.ai.auth_tokens import (
    CODE_CHECK_TOOL_SCOPES,
    COMPONENT_TOOL_DELETE_SCOPES,
    COMPONENT_TOOL_READ_SCOPES,
    COMPONENT_TOOL_WRITE_SCOPES,
    RESOURCE_TOOL_READ_SCOPES,
    build_agent_tool_token,
)
from app.ai.tool_specs import COMPONENT_MANAGER_AGENT_ID, list_agent_group_specs
from app.core.config import AppSettings
from app.core.config import get_settings
from app.services.token_service import TokenService


def test_ai_tool_auth_defaults_should_cover_long_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认短租约应覆盖常见长推理模型调用窗口。"""

    monkeypatch.delenv("AI_TOOL_AUTH_WINDOW_SECONDS", raising=False)
    monkeypatch.delenv("AI_TOOL_AUTH_MAX_SECONDS", raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.ai_tool_auth_window_seconds == 1800
    assert settings.ai_tool_auth_max_seconds == 7200


def test_ai_tool_auth_max_should_not_be_shorter_than_default_window() -> None:
    """绝对上限不能短于默认短租约窗口。"""

    with pytest.raises(ValueError, match="1800"):
        AppSettings(_env_file=None, ai_tool_auth_max_seconds=1799)


def test_ai_tool_token_should_use_tool_auth_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具 token 应使用工具授权窗口，而不是历史 AgentOS TTL。"""

    monkeypatch.setenv("AI_AGENT_TOKEN_TTL_SECONDS", "600")
    monkeypatch.setenv("AI_TOOL_AUTH_WINDOW_SECONDS", "1800")
    monkeypatch.setenv("AI_TOOL_AUTH_MAX_SECONDS", "7200")
    get_settings.cache_clear()

    try:
        token = build_agent_tool_token(
            _build_auth_context(),
            run_id="run-tool-ttl",
            session_id="session-tool-ttl",
            agent_id="component-manager",
            workspace_id=1,
            project_id=None,
            page_id=None,
            component_id=None,
            source="test",
            scopes=("tools:component:read",),
        )
        claims = TokenService.verify_signed_token(token, audience="agent-tool")
    finally:
        get_settings.cache_clear()

    assert claims["exp"] - claims["iat"] == 1800


def test_ai_tool_token_should_not_exceed_tool_auth_max(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具 token 生命周期超过绝对上限时应被上限截断。"""

    monkeypatch.setenv("AI_TOOL_AUTH_WINDOW_SECONDS", "9000")
    monkeypatch.setenv("AI_TOOL_AUTH_MAX_SECONDS", "7200")
    get_settings.cache_clear()

    try:
        token = build_agent_tool_token(
            _build_auth_context(),
            run_id="run-tool-max",
            session_id="session-tool-max",
            agent_id="component-manager",
            workspace_id=1,
            project_id=None,
            page_id=None,
            component_id=None,
            source="test",
            scopes=("tools:component:read",),
        )
        claims = TokenService.verify_signed_token(token, audience="agent-tool")
    finally:
        get_settings.cache_clear()

    assert claims["exp"] - claims["iat"] == 7200


def test_component_manager_group_scopes_should_cover_runtime_tools() -> None:
    """组件助手签发 token 的 scope 应覆盖实际暴露的读写检查工具。"""

    scopes = {
        scope
        for group in list_agent_group_specs(COMPONENT_MANAGER_AGENT_ID)
        for scope in group.token_scopes
    }

    assert set(COMPONENT_TOOL_READ_SCOPES).issubset(scopes)
    assert set(COMPONENT_TOOL_WRITE_SCOPES).issubset(scopes)
    assert set(COMPONENT_TOOL_DELETE_SCOPES).issubset(scopes)
    assert set(CODE_CHECK_TOOL_SCOPES).issubset(scopes)
    assert set(RESOURCE_TOOL_READ_SCOPES).issubset(scopes)


def _build_auth_context() -> SimpleNamespace:
    """构造签发工具 token 所需的最小鉴权上下文。"""

    return SimpleNamespace(user=SimpleNamespace(id=1), backend_session_id="backend-session-test")
