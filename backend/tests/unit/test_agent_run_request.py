"""文件功能：验证智能体运行请求的消息与图片附件数量约束。"""

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentFocusRequest, AgentRunRequest


def test_agent_run_request_accepts_up_to_ten_images() -> None:
    """单条消息可以携带最多十张图片。"""

    request = AgentRunRequest(
        image_attachment_ids=list(range(1, 11)),
        focus=AgentFocusRequest(scope_type="workspace", source="test"),
    )

    assert len(request.image_attachment_ids) == 10


def test_agent_run_request_rejects_more_than_ten_images() -> None:
    """绕过 Editor 提交超过十张图片时应由请求 Schema 拒绝。"""

    with pytest.raises(ValidationError):
        AgentRunRequest(
            image_attachment_ids=list(range(1, 12)),
            focus=AgentFocusRequest(scope_type="workspace", source="test"),
        )
