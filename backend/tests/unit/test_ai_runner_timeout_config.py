"""文件功能：验证 Agent 模型流与工具流独立空闲超时配置。"""

import pytest
from pydantic import ValidationError

from app.core.config import AppSettings


def test_ai_runner_timeout_defaults_should_keep_tool_wait_longer() -> None:
    """默认工具流阈值应长于模型流阈值，容纳成员委派等长任务。"""

    assert AppSettings.model_fields["ai_agent_stream_idle_timeout_seconds"].default == 180.0
    assert AppSettings.model_fields["ai_agent_tool_stream_idle_timeout_seconds"].default == 600.0


@pytest.mark.parametrize(
    "field_name",
    ("ai_agent_stream_idle_timeout_seconds", "ai_agent_tool_stream_idle_timeout_seconds"),
)
def test_ai_runner_timeout_should_reject_non_positive_values(field_name: str) -> None:
    """两个空闲超时都必须为正数，避免节点流立即失败或永久缺少边界。"""

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: 0})
