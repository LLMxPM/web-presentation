"""文件功能：验证 AI 工具授权窗口相关配置默认值与约束。"""

import pytest

from app.core.config import AppSettings


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
