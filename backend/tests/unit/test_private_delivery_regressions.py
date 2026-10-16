"""文件功能：回归内容寻址截图、S3 缓存、旧字体迁移、源站隔离与真实构建缓存策略。"""

import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.core.config import AppSettings
from app.core.exceptions import AppException
from app.models.page import Page
from app.services.asset_storage_drivers import S3StorageDriver
from app.services.file_auth_service import FileAuthService
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_service import PageScreenshotService
from app.services.page_screenshot_url import build_page_screenshot_url
from app.services.preview_origin_service import isolated_preview_base_url, preview_shell
from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService
from app.services.screenshot_artifact_service import screenshot_object_key, serve_screenshot


def _request(headers=None):
    """创建不读取业务数据的文件请求。"""
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]})


async def _body(response):
    """消费流式结果并模拟响应结束时的退出栈释放。"""
    if not hasattr(response, "body_iterator"):
        return response.body
    try:
        return b"".join([chunk async for chunk in response.body_iterator])
    finally:
        await response.stack.aclose()


@pytest.fixture
def s3_store(tmp_path, monkeypatch):
    """提供实际磁盘缓存与内存 S3 原件，避免 mock 掉缓存行为。"""
    from app.services import object_storage_service as module

    cfg = AppSettings(
        asset_storage_driver="s3", page_screenshot_local_root=str(tmp_path),
        s3_bucket="private", s3_public_bucket="legacy", s3_endpoint_url="https://s3.invalid",
        object_cache_sweep_interval_seconds=0,
    )
    monkeypatch.setattr(module, "get_settings", lambda: cfg)
    objects = {}
    reads = []

    async def read(self, key, *, bucket_name=None):
        """模拟按桶读取，并保留真实缓存命中可观测性。"""
        identity = (bucket_name or "private", key)
        reads.append(identity)
        if identity not in objects:
            raise AppException(404, "OBJECT_NOT_FOUND", "对象不存在。")
        return objects[identity]

    async def write(self, key, content, content_type=None, *, bucket_name=None):
        """模拟对象写入，保留服务层真实的 key 与缓存行为。"""
        objects[(bucket_name or "private", key)] = content

    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", read)
    monkeypatch.setattr(ObjectStorageService, "_put_s3_object", write)
    return ObjectStorageService(), objects, reads


async def test_screenshot_hash_url_history_and_s3_304(s3_store):
    """生成的 URL 能读固定字节；更新 current 后旧图仍可读，S3 热缓存可稳定返回 304。"""
    storage, objects, reads = s3_store
    old, new = b"old-png", b"new-png"
    old_hash, new_hash = (hashlib.sha256(item).hexdigest() for item in (old, new))
    old_key, new_key = (screenshot_object_key(7, item) for item in (old_hash, new_hash))
    objects[("private", old_key)], objects[("private", new_key)] = old, new
    page = Page(id=7, code="page", title="截图", screenshot_storage_key=old_key)
    assert f"/screenshots/{old_hash}/content" in build_page_screenshot_url(page, "http://backend")
    first = await serve_screenshot(_request(), page, old_hash)
    assert await _body(first) == old
    second = await serve_screenshot(_request({"If-None-Match": first.headers["etag"]}), page, old_hash)
    assert second.status_code == 304
    assert len(reads) == 1
    page.screenshot_storage_key = new_key
    assert await _body(await serve_screenshot(_request(), page, "latest")) == new
    assert await _body(await serve_screenshot(_request(), page, old_hash)) == old
    assert not storage._read_pins


async def test_legacy_latest_bypasses_immutable_cache(s3_store):
    """旧 key 被覆盖后 latest 必须读取新原件，不能复用历史缓存字节。"""
    storage, objects, _ = s3_store
    key = "page-screenshots/7/v1/config/10x10.png"
    page = Page(id=7, code="page", title="截图", screenshot_storage_key=key)
    await storage.put_object(key, b"old-png")
    assert await _body(await serve_screenshot(_request(), page, "latest")) == b"old-png"
    await storage.put_object(key, b"new-png")
    assert await _body(await serve_screenshot(_request(), page, "latest")) == b"new-png"
    assert build_page_screenshot_url(page, "http://backend").endswith("/screenshots/latest/content")


async def test_cache_sweep_keeps_active_stream(s3_store):
    """容量清理不能删掉已经交给响应、尚未开始发送的文件。"""
    storage, objects, _ = s3_store
    content = b"stream-png"
    digest = hashlib.sha256(content).hexdigest()
    key = screenshot_object_key(7, digest)
    objects[("private", key)] = content
    page = Page(id=7, code="page", title="截图", screenshot_storage_key=key)
    response = await serve_screenshot(_request(), page, digest)
    storage.settings.object_cache_max_bytes = 0
    storage.sweep_object_cache()
    assert await _body(response) == content
    assert not storage._read_pins
    storage.sweep_object_cache()
    assert not storage._list_cache_files()


async def test_legacy_font_is_copied_privately_without_public_url(s3_store):
    """旧字体仅由服务凭证从旧桶读取，校验后复制，后续使用私有桶。"""
    _, objects, reads = s3_store
    content = b"legacy-font"
    digest = hashlib.sha256(content).hexdigest()
    key = f"assets/1/{digest}.woff2"
    objects[("legacy", key)] = content
    driver = S3StorageDriver()
    async with driver.open_for_read(1, f"{digest}.woff2", expected_sha256=digest) as file:
        assert file.read_bytes() == content
    assert objects[("private", key)] == content
    assert driver._build_public_font_url(1, f"{digest}.woff2") is None
    assert reads.count(("legacy", key)) == 1


async def test_screenshot_result_has_valid_identity_without_name_error(monkeypatch):
    """AI/External 使用同一个截图身份构造结果，不依赖不存在的局部 settings。"""
    service = PageScreenshotService.__new__(PageScreenshotService)
    service.settings = AppSettings()
    service.page_service = SimpleNamespace(_to_item=AsyncMock(return_value="dto"))
    page = Page(id=7, code="page", title="截图", screenshot_storage_key=screenshot_object_key(7, "a" * 64))
    result = await service._build_result(page=page, content=b"png", refreshed=True)
    assert result.public_url.endswith(f"/screenshots/{'a' * 64}/content")


def test_preview_shell_isolates_user_code_and_rejects_remote_cookie_host(monkeypatch):
    """同业务主机名不得执行用户代码；本地自动隔离，宿主页只负责带来源校验的消息桥。"""
    from app.services import preview_origin_service as module

    cfg = AppSettings(backend_public_base_url="http://127.0.0.1:8000", runtime_public_base_url="http://127.0.0.1:7373")
    monkeypatch.setattr(module, "get_settings", lambda: cfg)
    assert isolated_preview_base_url() == "http://preview.localhost:7373"
    response = preview_shell(artifact_id="rt_1", token="ticket", workbench_url="http://localhost:5173/")
    assert b'http://preview.localhost:7373/__preview?token=ticket' in response.body
    assert b'event.source === frame.contentWindow' in response.body
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    cfg.backend_public_base_url = "https://app.example"
    cfg.runtime_public_base_url = "https://app.example/runtime"
    with pytest.raises(AppException, match="独立"):
        isolated_preview_base_url()


def test_build_cache_policy_is_private_without_mocked_headers():
    """直接检查真实构建服务策略，不能在路由测试里手填正确的 mock 响应头。"""
    policy = ProjectBuildArtifactProxyService.build_response_headers
    assert policy(media_type="text/html")["Cache-Control"] == "no-store"
    assert policy(media_type="application/javascript")["Cache-Control"] == "private, no-cache"


async def test_untrusted_preview_origin_cannot_write_business_api(authenticated_client):
    """即使拥有业务登录 Cookie，同站预览子域和 opaque origin 也不能代发写入。"""
    for origin in ("https://preview.example", "null"):
        response = await authenticated_client.post("/api/workspaces", json={"name": "must-not-create"}, headers={"Origin": origin})
        assert response.status_code == 403
        assert response.json()["code"] == "UNTRUSTED_BUSINESS_ORIGIN"
