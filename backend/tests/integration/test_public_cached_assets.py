"""文件功能：验证截图专用公开缓存资源入口的本地与 S3 派生缓存行为。"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.object_storage_service import ObjectStorageService


async def test_public_cached_asset_should_return_local_file(authenticated_client: AsyncClient) -> None:
    """本地存储资源应通过 cached-assets 入口直接返回文件内容。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "缓存资源工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("hero.png", b"image-bytes", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    file_hash = upload_response.json()["file_hash"]

    response = await authenticated_client.get(f"/public/cached-assets/{workspace_id}/{file_hash}")

    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["content-type"] == "image/png"


async def test_public_cached_asset_should_reuse_s3_cache_file(
    authenticated_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 资源应先写入 Backend 派生缓存，后续请求复用缓存文件。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "S3 缓存资源工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    content = b"s3-image-bytes"

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("remote.png", content, "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()
    file_hash = uploaded_asset["file_hash"]
    calls = {"read": 0}

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_ACCESS_KEY", "key")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    from app.core.config import get_settings

    get_settings.cache_clear()

    async def fake_read_s3_object(self: ObjectStorageService, storage_key: str) -> bytes:  # noqa: ARG001
        calls["read"] += 1
        assert storage_key == f"assets/{workspace_id}/{uploaded_asset['file_name']}"
        return content

    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)

    first_response = await authenticated_client.get(f"/public/cached-assets/{workspace_id}/{file_hash}")
    second_response = await authenticated_client.get(f"/public/cached-assets/{workspace_id}/{file_hash}")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.content == content
    assert second_response.content == content
    assert calls["read"] == 1
    get_settings.cache_clear()
