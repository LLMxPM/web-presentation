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


@pytest.mark.asyncio
async def test_s3_cache_concurrent_download_cancellation_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试多个调用方等待同一下载时，取消其中一个等待者不会连带取消其他等待者。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    get_settings.cache_clear()

    service = ObjectStorageService()
    test_content = b"content-for-cancellation-test"

    async def slow_mock_read_s3_object(storage_key, bucket_name=None):
        await asyncio.sleep(0.1)
        return test_content

    monkeypatch.setattr(service, "_read_s3_object", slow_mock_read_s3_object)
    storage_key = "assets/1/cancel-test.png"

    results = []

    async def waiter_1():
        try:
            async with service.open_object_for_read(storage_key) as p:
                results.append(("waiter_1_ok", p.read_bytes()))
        except asyncio.CancelledError:
            results.append(("waiter_1_cancelled", None))
            raise

    async def waiter_2():
        try:
            async with service.open_object_for_read(storage_key) as p:
                results.append(("waiter_2_ok", p.read_bytes()))
        except asyncio.CancelledError:
            results.append(("waiter_2_cancelled", None))
            raise

    task1 = asyncio.create_task(waiter_1())
    task2 = asyncio.create_task(waiter_2())

    # 稍等让两个 task 都在等待同一底层下载
    await asyncio.sleep(0.02)
    # 取消第二个等待者
    task2.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task2

    # 第一个等待者必须顺利完成，不能被连带取消
    await task1

    assert ("waiter_1_ok", test_content) in results
    assert ("waiter_2_cancelled", None) in results
