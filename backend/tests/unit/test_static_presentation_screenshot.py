"""文件功能：验证静态不可呈现的写入附图结果不会变为 pending 或覆盖成功诊断。"""
from unittest.mock import AsyncMock

import pytest
from app.models.page import Page
from app.services.validation_screenshot_publisher import publish_validation_screenshot


@pytest.mark.asyncio
async def test_unavailable_image_does_not_publish_or_queue():
    """无需数据库或对象存储；内容不可呈现保持独立有界描述。"""
    session = AsyncMock()
    page = Page(code="static", title="完整内容", workspace_id=1, current_version_no=3)
    result = await publish_validation_screenshot(session, page=page,
        validation={"stages": {"render": "passed"}, "_screenshot_phase": {
            "status": "unavailable", "reason_code": "STATIC_PRESENTATION_UNAVAILABLE"}}, prepared=None)
    assert result == {"status": "unavailable", "version_no": 3, "reason_code": "STATIC_PRESENTATION_UNAVAILABLE"}
    session.flush.assert_not_awaited()
