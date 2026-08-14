"""文件功能：验证 Agent 模型流与工具流独立空闲超时配置。"""

import pytest
from pydantic import ValidationError

from app.core.config import AppSettings


def test_ai_runner_timeout_defaults_should_keep_tool_wait_longer() -> None:
    """默认工具流阈值应长于模型流阈值，容纳成员委派等长任务。"""

    assert AppSettings.model_fields["ai_agent_stream_idle_timeout_seconds"].default == 180.0
    assert AppSettings.model_fields["ai_agent_tool_stream_idle_timeout_seconds"].default == 600.0
    assert AppSettings.model_fields["ai_external_task_enqueue_timeout_seconds"].default == 30.0


@pytest.mark.parametrize(
    "field_name",
    (
        "ai_agent_stream_idle_timeout_seconds",
        "ai_agent_tool_stream_idle_timeout_seconds",
        "ai_external_task_enqueue_timeout_seconds",
    ),
)
def test_ai_runner_timeout_should_reject_non_positive_values(field_name: str) -> None:
    """模型、工具和入队阶段超时都必须为正数。"""

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: 0})
