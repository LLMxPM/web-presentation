"""文件功能：测试 S3 对象缓存的并发回源合并与原子写入提升保障 (W09)。"""

import asyncio
from pathlib import Path
import pytest

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.object_storage_service import ObjectStorageService


@pytest.mark.asyncio
async def test_s3_cache_concurrent_download_deduplication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试多并发读取同一未命中 S3 对象时，进程内合并为单次回源下载。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    get_settings.cache_clear()

    service = ObjectStorageService()

    read_count = 0
    test_content = b"heavy-image-content-for-caching"

    async def mock_read_s3_object(storage_key, bucket_name=None):
        nonlocal read_count
        read_count += 1
        await asyncio.sleep(0.05)
        return test_content

    monkeypatch.setattr(service, "_read_s3_object", mock_read_s3_object)

    storage_key = "assets/1/test-image.png"

    async def read_one():
        async with service.open_object_for_read(storage_key) as file_path:
            assert file_path.exists()
            assert file_path.read_bytes() == test_content

    await asyncio.gather(*(read_one() for _ in range(5)))

    assert read_count == 1


@pytest.mark.asyncio
async def test_s3_cache_atomic_write_failure_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试 S3 下载写入或校验失败时不会遗留半写文件污染缓存。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    get_settings.cache_clear()

    service = ObjectStorageService()

    async def mock_corrupted_s3_object(storage_key, bucket_name=None):
        return b"corrupted-short-bytes"

    monkeypatch.setattr(service, "_read_s3_object", mock_corrupted_s3_object)

    storage_key = "assets/1/bad-image.png"

    with pytest.raises(AppException):
        async with service.open_object_for_read(
            storage_key,
            expected_sha256="expected-correct-hash",
            expected_size=1024,
        ):
            pass

    cache_files = service._list_cache_files()
    assert len(cache_files) == 0
