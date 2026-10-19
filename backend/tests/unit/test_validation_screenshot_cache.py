"""文件功能：验证有图/无图缓存分离，以及图片引用不可读时诊断仍可复用。"""

from unittest.mock import AsyncMock

import pytest

from app.services.code_check_fingerprint import capture_check_fingerprint
from app.services.code_check_result_cache import CodeCheckResultCache
from app.services.validation_screenshot_publisher import prepare_validation_screenshot


@pytest.mark.asyncio
async def test_diagnostics_cache_does_not_satisfy_capture():
    """独立校验与附图请求使用不同 key，不让无图 in-flight 结果满足有图请求。"""
    cache = CodeCheckResultCache()
    diagnostic = AsyncMock(return_value={"success": True})
    image = AsyncMock(return_value={"success": True, "_candidate_screenshot": {"storage_key": "key"}})
    await cache.get_or_execute("base", diagnostic)
    result, source = await cache.get_or_execute(capture_check_fingerprint("base"), image)
    assert source == "miss" and result["_candidate_screenshot"]["storage_key"] == "key"
    _, source = await cache.get_or_execute(capture_check_fingerprint("base"), image)
    assert source == "hit"
    image.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_image_does_not_rerun_validation(monkeypatch):
    """缓存保留布局事实；图片读取失败后只报告待按需补齐，不重开浏览器。"""
    monkeypatch.setattr("app.services.runtime_release_identity.refresh_runtime_release_identity", AsyncMock(return_value="known"))
    monkeypatch.setattr("app.services.validation_screenshot_publisher.ObjectStorageService.read_object", AsyncMock(side_effect=FileNotFoundError))
    result = {"success": True, "layout_analysis": {"nodes": 1}, "_capture_identity": "id",
              "_screenshot_phase": {"status": "available"}, "_candidate_screenshot": {"workspace_id": 1,
                "expires_at": "2099-01-01T00:00:00+00:00", "storage_key": "missing", "sha256": "h"}}
    cache, execute = CodeCheckResultCache(), AsyncMock(return_value=result)
    await cache.get_or_execute("key", execute)
    cached, source = await cache.get_or_execute("key", execute)
    assert source == "hit" and cached["layout_analysis"] == {"nodes": 1}
    assert await prepare_validation_screenshot(cached, workspace_id=1) is None
    execute.assert_awaited_once()
