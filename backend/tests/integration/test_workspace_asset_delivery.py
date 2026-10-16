"""文件功能：验证工作空间资源的受保护交付链路——登录要求、本地文件、S3 回源缓存、字体私有桶与版本校验。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.object_storage_service import ObjectStorageService


@pytest.fixture(autouse=True)
def isolated_object_root(tmp_path, monkeypatch):
    """把本地对象根目录隔离到测试临时目录，避免共享派生缓存造成跨用例假命中。"""

    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _login(client: AsyncClient) -> None:
    """登录默认管理员，后续请求复用同一客户端的会话 Cookie。"""

    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin123456"},
    )
    assert response.status_code == 200


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _upload_asset(
    client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
    content: bytes,
    content_type: str,
    asset_type: str,
) -> dict:
    """上传测试资源并返回接口响应。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (file_name, content, content_type)},
        data={"asset_type": asset_type, "tags": "[]"},
    )
    assert response.status_code == 200
    return response.json()


async def test_workspace_asset_file_should_require_login(client: AsyncClient) -> None:
    """匿名请求先被登录依赖拒绝；登录后按内容身份交付文件并支持 ETag 与 Range。"""

    anonymous_response = await client.get("/api/workspaces/1/assets/1/file")
    assert anonymous_response.status_code == 401
    assert anonymous_response.headers["cache-control"] == "no-store"

    await _login(client)
    workspace_id = await _create_workspace(client, "受保护资源交付工作空间")
    asset = await _upload_asset(
        client,
        workspace_id,
        file_name="hero.png",
        content=b"hero-bytes",
        content_type="image/png",
        asset_type="image",
    )

    response = await client.get(f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file")
    assert response.status_code == 200
    assert response.content == b"hero-bytes"
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["etag"] == f'"{asset["file_hash"]}"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "location" not in response.headers

    not_modified = await client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert not_modified.status_code == 304

    partial = await client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        headers={"Range": "bytes=0-3"},
    )
    assert partial.status_code == 206
    assert partial.content == b"hero"
    assert partial.headers["content-range"] == f"bytes 0-3/{len(b'hero-bytes')}"


async def test_workspace_asset_by_hash_should_stream_s3_object_without_public_redirect(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """S3 模式下由 Backend 经本地派生缓存交付素材，不生成预签名直连重定向且二次读取不再回源。"""

    workspace_id = await _create_workspace(authenticated_client, "S3 素材交付工作空间")
    svg_content = b"<svg><path fill='currentColor' d='M0 0'/></svg>"
    asset = await _upload_asset(
        authenticated_client,
        workspace_id,
        file_name="brand.svg",
        content=svg_content,
        content_type="image/svg+xml",
        asset_type="icon",
    )

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("S3_BUCKET", "private-assets")
    get_settings.cache_clear()
    calls = {"presign": 0, "read": 0, "buckets": []}

    async def fake_generate_download_url(  # noqa: ANN001, ARG001
        self,
        workspace_id,
        file_name,
        original_name,
        download=False,
    ):
        calls["presign"] += 1
        return "https://s3.example.com/should-not-be-used.svg"

    async def fake_read_s3_object(  # noqa: ANN001, ARG001
        self: ObjectStorageService,
        storage_key: str,
        *,
        bucket_name: str | None = None,
    ) -> bytes:
        calls["read"] += 1
        calls["buckets"].append(bucket_name)
        assert storage_key == f"assets/{workspace_id}/{asset['file_name']}"
        return svg_content

    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.generate_download_url",
        fake_generate_download_url,
    )
    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)

    try:
        response = await authenticated_client.get(
            f"/api/workspaces/{workspace_id}/assets/by-hash/{asset['file_hash']}"
        )
        assert response.status_code == 200
        assert response.content == svg_content
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert response.headers["cache-control"] == "private, no-cache"
        assert response.headers["access-control-allow-origin"] == "*"
        assert "location" not in response.headers

        repeated = await authenticated_client.get(
            f"/api/workspaces/{workspace_id}/assets/by-hash/{asset['file_hash']}"
        )
        assert repeated.status_code == 200
        assert repeated.content == svg_content
    finally:
        get_settings.cache_clear()

    assert calls["presign"] == 0
    assert calls["read"] == 1
    assert calls["buckets"] == ["private-assets"]


async def test_workspace_asset_font_should_read_private_bucket_without_public_url(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """字体资源统一走私有桶与受保护交付，即使配置了公共桶也不再生成公开直连地址。"""

    workspace_id = await _create_workspace(authenticated_client, "字体私有交付工作空间")
    asset = await _upload_asset(
        authenticated_client,
        workspace_id,
        file_name="BrandSerif.woff2",
        content=b"font-bytes",
        content_type="font/woff2",
        asset_type="font",
    )

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("S3_BUCKET", "private-assets")
    monkeypatch.setenv("S3_PUBLIC_BUCKET", "public-fonts")
    monkeypatch.setenv("S3_PUBLIC_BASE_URL", "https://public-fonts.example.com/")
    get_settings.cache_clear()
    read_buckets: list[str | None] = []

    async def fake_read_s3_object(  # noqa: ANN001, ARG001
        self: ObjectStorageService,
        storage_key: str,
        *,
        bucket_name: str | None = None,
    ) -> bytes:
        read_buckets.append(bucket_name)
        return b"font-bytes"

    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)

    try:
        response = await authenticated_client.get(
            f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file"
        )
        assert response.status_code == 200
        assert response.content == b"font-bytes"
        assert response.headers["content-type"].startswith("font/woff2")
        assert "location" not in response.headers
        assert "public-fonts.example.com" not in str(response.headers)
    finally:
        get_settings.cache_clear()

    assert read_buckets == ["private-assets"]


async def test_workspace_asset_file_should_reject_version_mismatch(
    authenticated_client: AsyncClient,
) -> None:
    """显式指定与当前版本不一致的 hash 时返回 404，不交付其它版本内容。"""

    workspace_id = await _create_workspace(authenticated_client, "资源版本校验工作空间")
    asset = await _upload_asset(
        authenticated_client,
        workspace_id,
        file_name="cover.png",
        content=b"cover-bytes",
        content_type="image/png",
        asset_type="image",
    )

    response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        params={"hash": "0" * 64},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "FILE_NOT_FOUND"

    matched = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file",
        params={"hash": asset["file_hash"]},
    )
    assert matched.status_code == 200
    assert matched.content == b"cover-bytes"


async def test_workspace_asset_file_should_report_missing_object(
    authenticated_client: AsyncClient,
) -> None:
    """底层对象被清理后，受保护入口按对象不存在返回 404 而不是 500。"""

    workspace_id = await _create_workspace(authenticated_client, "对象缺失工作空间")
    asset = await _upload_asset(
        authenticated_client,
        workspace_id,
        file_name="lost.png",
        content=b"lost-bytes",
        content_type="image/png",
        asset_type="image",
    )

    await ObjectStorageService().delete_object(f"assets/{workspace_id}/{asset['file_name']}")

    response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/file"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "OBJECT_NOT_FOUND"
