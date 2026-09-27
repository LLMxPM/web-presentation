"""文件功能：验证统一对象存储服务的本地读写、流式写入与 S3 临时缓存行为。"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services import object_storage_service as object_storage_module
from app.services.asset_storage_drivers import S3StorageDriver
from app.services.object_storage_service import ObjectStorageService


async def _aiter(chunks: list[bytes]) -> AsyncIterator[bytes]:
    """把字节列表包成分片异步迭代器，供流式写入测试复用。"""

    for chunk in chunks:
        yield chunk


def _use_local_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObjectStorageService:
    """切换为本地对象存储驱动并返回服务对象。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "local")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    return ObjectStorageService()


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


@pytest.mark.asyncio
async def test_put_object_stream_should_write_local_object_and_report_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地流式写入应落最终对象、回传大小与 sha256，且不留临时文件。"""

    service = _use_local_driver(tmp_path, monkeypatch)
    payload = [b"chunk-1", b"", b"chunk-2"]

    result = await service.put_object_stream("build-artifacts/1/dist.zip", _aiter(payload), "application/zip")

    expected = b"".join(payload)
    assert result.storage_key == "build-artifacts/1/dist.zip"
    assert result.size_bytes == len(expected)
    assert result.sha256 == hashlib.sha256(expected).hexdigest()
    assert await service.read_object(result.storage_key) == expected
    assert [path.name for path in (tmp_path / "build-artifacts" / "1").iterdir()] == ["dist.zip"]


@pytest.mark.asyncio
async def test_put_object_stream_should_reject_oversized_local_object_without_storing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超过上限的分片应即时中止，既不留下对象也不留下临时文件。"""

    service = _use_local_driver(tmp_path, monkeypatch)

    with pytest.raises(AppException) as exc_info:
        await service.put_object_stream(
            "build-artifacts/2/dist.zip",
            _aiter([b"1234", b"5678"]),
            max_size_bytes=6,
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "OBJECT_TOO_LARGE"
    assert not (tmp_path / "build-artifacts" / "2" / "dist.zip").exists()
    assert not list((tmp_path / "build-artifacts" / "2").iterdir())


@pytest.mark.asyncio
async def test_put_object_stream_should_reject_empty_local_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空分片流应沿用空内容错误，不产生零字节对象。"""

    service = _use_local_driver(tmp_path, monkeypatch)

    with pytest.raises(AppException) as exc_info:
        await service.put_object_stream("build-artifacts/3/dist.zip", _aiter([b""]), max_size_bytes=None)

    assert exc_info.value.code == "OBJECT_CONTENT_EMPTY"
    assert not (tmp_path / "build-artifacts" / "3" / "dist.zip").exists()


class _FakeMultipartClient:
    """记录分片上传调用的最小 S3 替身。"""

    def __init__(self, *, fail_on_part: int | None = None) -> None:
        self.fail_on_part = fail_on_part
        self.calls: list[str] = []
        self.parts: list[dict[str, object]] = []
        self.completed: dict[str, object] | None = None
        self.aborted: str | None = None

    async def __aenter__(self) -> "_FakeMultipartClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:  # noqa: ANN001
        return False

    async def create_multipart_upload(self, **kwargs) -> dict[str, str]:  # noqa: ANN003
        self.calls.append("create")
        assert kwargs["Key"]
        return {"UploadId": "upload-1"}

    async def upload_part(self, **kwargs) -> dict[str, str]:  # noqa: ANN003
        part_number = int(kwargs["PartNumber"])
        if self.fail_on_part == part_number:
            raise RuntimeError("分片上传失败")
        self.parts.append({"PartNumber": part_number, "Body": kwargs["Body"]})
        return {"ETag": f"etag-{part_number}"}

    async def complete_multipart_upload(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
        self.completed = kwargs
        return {}

    async def abort_multipart_upload(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
        self.aborted = str(kwargs["UploadId"])
        return {}


def _use_s3_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObjectStorageService:
    """切换为 S3 驱动并返回服务对象。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("S3_ACCESS_KEY", "key")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    get_settings.cache_clear()
    return ObjectStorageService()


@pytest.mark.asyncio
async def test_put_object_stream_should_split_s3_multipart_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 流式写入应按固定分片大小切块，并以实际字节回报大小与 sha256。"""

    service = _use_s3_driver(tmp_path, monkeypatch)
    client = _FakeMultipartClient()
    monkeypatch.setattr(service, "_s3_client", lambda: client)
    monkeypatch.setattr(object_storage_module, "S3_MULTIPART_PART_SIZE_BYTES", 4)
    payload = [b"abcd", b"efgh", b"ij"]

    result = await service.put_object_stream("build-artifacts/4/dist.zip", _aiter(payload), "application/zip")

    expected = b"".join(payload)
    assert [part["Body"] for part in client.parts] == [b"abcd", b"efgh", b"ij"]
    assert result.size_bytes == len(expected)
    assert result.sha256 == hashlib.sha256(expected).hexdigest()
    assert client.completed is not None
    assert client.completed["MultipartUpload"] == {
        "Parts": [
            {"PartNumber": 1, "ETag": "etag-1"},
            {"PartNumber": 2, "ETag": "etag-2"},
            {"PartNumber": 3, "ETag": "etag-3"},
        ]
    }
    assert client.aborted is None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_put_object_stream_should_abort_s3_multipart_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分片失败或越限都必须 abort，避免 bucket 内遗留未完成的上传。"""

    service = _use_s3_driver(tmp_path, monkeypatch)
    client = _FakeMultipartClient(fail_on_part=2)
    monkeypatch.setattr(service, "_s3_client", lambda: client)
    monkeypatch.setattr(object_storage_module, "S3_MULTIPART_PART_SIZE_BYTES", 4)

    with pytest.raises(RuntimeError):
        await service.put_object_stream("build-artifacts/5/dist.zip", _aiter([b"abcd", b"efgh"]))

    assert client.completed is None
    assert client.aborted == "upload-1"

    oversized_client = _FakeMultipartClient()
    monkeypatch.setattr(service, "_s3_client", lambda: oversized_client)
    with pytest.raises(AppException) as exc_info:
        await service.put_object_stream(
            "build-artifacts/5/dist.zip",
            _aiter([b"abcd", b"efgh"]),
            max_size_bytes=6,
        )

    assert exc_info.value.code == "OBJECT_TOO_LARGE"
    assert oversized_client.aborted == "upload-1"
    get_settings.cache_clear()

