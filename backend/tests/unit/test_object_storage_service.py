"""文件功能：验证统一对象存储服务的本地读写与 S3 临时缓存行为。"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from app.core.exceptions import AppException
from app.services.asset_service import S3StorageDriver
from app.services.object_storage_service import ObjectStorageService


@pytest.mark.asyncio
async def test_object_storage_should_put_and_read_local_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """本地模式应按 storage key 写入并读取对象内容。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "local")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    service = ObjectStorageService()

    storage_key = await service.put_object("page-screenshots/demo.png", b"png-content", "image/png")
    assert storage_key == "page-screenshots/demo.png"
    assert await service.read_object(storage_key) == b"png-content"

    async with service.open_object_for_read(storage_key) as file_path:
        assert file_path == tmp_path / "page-screenshots" / "demo.png"
        assert file_path.read_bytes() == b"png-content"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_object_storage_should_reuse_s3_cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S3 模式下同一对象重复 open 应复用本地临时缓存，避免重复下载 ZIP。"""

    content = b"zip-bytes"
    sha256 = hashlib.sha256(content).hexdigest()
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
        return content

    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)
    service = ObjectStorageService()

    async with service.open_object_for_read(
        "build-artifacts/1/2/dist.zip",
        expected_sha256=sha256,
        expected_size=len(content),
    ) as first_path:
        assert first_path.read_bytes() == content

    async with service.open_object_for_read(
        "build-artifacts/1/2/dist.zip",
        expected_sha256=sha256,
        expected_size=len(content),
    ) as second_path:
        assert second_path == first_path
        assert second_path.read_bytes() == content

    assert calls["read"] == 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_s3_asset_driver_should_split_font_uploads_to_public_bucket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 资产驱动应把字体写入公开 bucket，普通资源仍写入私有 bucket。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_ACCESS_KEY", "key")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    monkeypatch.setenv("S3_BUCKET", "private-assets")
    monkeypatch.setenv("S3_PUBLIC_BUCKET", "public-fonts")
    from app.core.config import get_settings

    get_settings.cache_clear()
    calls: list[dict[str, str | None]] = []

    async def fake_put_s3_object(  # noqa: ANN001
        self,
        storage_key: str,
        content: bytes,
        content_type: str | None,
        *,
        bucket_name: str | None = None,
    ) -> None:
        calls.append(
            {
                "storage_key": storage_key,
                "content_type": content_type,
                "bucket_name": bucket_name,
            }
        )

    monkeypatch.setattr(ObjectStorageService, "_put_s3_object", fake_put_s3_object)
    driver = S3StorageDriver()

    await driver.upload(7, "font-hash", ".woff2", b"font-bytes", "font/woff2")
    await driver.upload(7, "image-hash", ".png", b"image-bytes", "image/png")

    assert calls == [
        {
            "storage_key": "assets/7/font-hash.woff2",
            "content_type": "font/woff2",
            "bucket_name": "public-fonts",
        },
        {
            "storage_key": "assets/7/image-hash.png",
            "content_type": "image/png",
            "bucket_name": "private-assets",
        },
    ]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_object_storage_should_map_s3_missing_key_to_app_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 返回 NoSuchKey 时应转换为平台对象不存在错误，避免底层异常泄漏。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_ACCESS_KEY", "key")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    from app.core.config import get_settings

    get_settings.cache_clear()
    service = ObjectStorageService()

    class FakeS3Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def get_object(self, **kwargs):  # noqa: ANN003
            raise ClientError(
                {
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": "The specified key does not exist.",
                    }
                },
                "GetObject",
            )

    monkeypatch.setattr(service, "_s3_client", lambda: FakeS3Client())

    with pytest.raises(AppException) as exc_info:
        await service.read_object("assets/1/missing.png")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "OBJECT_NOT_FOUND"
    assert "assets/1/missing.png" in exc_info.value.detail
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_object_storage_cache_sweep_should_follow_idle_and_size_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """对象缓存清理应先移除闲置文件，再按容量上限回收最旧文件。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OBJECT_CACHE_IDLE_DAYS", "30")
    monkeypatch.setenv("OBJECT_CACHE_MAX_BYTES", "10")
    monkeypatch.setenv("OBJECT_CACHE_SWEEP_INTERVAL_SECONDS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    service = ObjectStorageService()
    service.cache_root.mkdir(parents=True, exist_ok=True)

    stale_file = service.cache_root / "stale.bin"
    old_file = service.cache_root / "old.bin"
    new_file = service.cache_root / "new.bin"
    stale_file.write_bytes(b"stale")
    old_file.write_bytes(b"12345678")
    new_file.write_bytes(b"12345678")

    now = time.time()
    os.utime(stale_file, (now - 31 * 24 * 60 * 60, now - 31 * 24 * 60 * 60))
    os.utime(old_file, (now - 100, now - 100))
    os.utime(new_file, (now - 10, now - 10))

    service.sweep_object_cache(now=now)

    assert not stale_file.exists()
    assert not old_file.exists()
    assert new_file.exists()
    get_settings.cache_clear()
