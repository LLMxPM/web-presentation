"""文件功能：验证对象流式读取在各驱动下都真正遵守字节区间语义。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.core.exceptions import AppException
from app.services.object_storage_service import ObjectStorageService

pytestmark = pytest.mark.unit


async def _collect(body: AsyncIterator[bytes]) -> bytes:
    """把异步字节流拼成完整内容，便于按切片断言。"""

    return b"".join([chunk async for chunk in body])


def _build_local_service(monkeypatch: pytest.MonkeyPatch, archive_path: Path) -> ObjectStorageService:
    """构造固定走本地驱动、且路径指向临时文件的服务实例。"""

    service = ObjectStorageService()
    monkeypatch.setattr(ObjectStorageService, "driver", property(lambda self: "local"))
    monkeypatch.setattr(service, "resolve_local_path", lambda storage_key: archive_path)
    return service


async def test_local_stream_should_return_full_object_without_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未指定区间时返回整个对象。"""

    archive_path = tmp_path / "dist.zip"
    archive_path.write_bytes(b"0123456789")
    service = _build_local_service(monkeypatch, archive_path)

    assert await _collect(service.iter_object_body("builds/dist.zip")) == b"0123456789"


async def test_local_stream_should_seek_to_requested_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地驱动的 byte_range 必须真正生效，而不是从头读整包。"""

    archive_path = tmp_path / "dist.zip"
    archive_path.write_bytes(b"0123456789")
    service = _build_local_service(monkeypatch, archive_path)

    assert await _collect(service.iter_object_body("builds/dist.zip", byte_range="bytes=2-5")) == b"2345"


async def test_local_stream_should_respect_chunk_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分块读取不得越过区间结尾，也不得因分块提前截断。"""

    archive_path = tmp_path / "dist.zip"
    archive_path.write_bytes(b"0123456789")
    service = _build_local_service(monkeypatch, archive_path)

    body = await _collect(service.iter_object_body("builds/dist.zip", byte_range="bytes=1-7", chunk_size=3))

    assert body == b"1234567"


async def test_local_stream_should_support_suffix_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后缀区间在本地驱动上同样按 RFC 7233 解析。"""

    archive_path = tmp_path / "dist.zip"
    archive_path.write_bytes(b"0123456789")
    service = _build_local_service(monkeypatch, archive_path)

    assert await _collect(service.iter_object_body("builds/dist.zip", byte_range="bytes=-3")) == b"789"


async def test_local_stream_should_reject_unreachable_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """起点越界的区间在本地驱动上同样返回 416，不能静默返回全量。"""

    archive_path = tmp_path / "dist.zip"
    archive_path.write_bytes(b"0123456789")
    service = _build_local_service(monkeypatch, archive_path)

    with pytest.raises(AppException) as excinfo:
        await _collect(service.iter_object_body("builds/dist.zip", byte_range="bytes=99-"))

    assert excinfo.value.status_code == 416
    assert excinfo.value.headers == {"Content-Range": "bytes */10"}


async def test_local_stream_should_report_missing_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """对象文件不存在时返回 404，而不是把 IO 异常冒泡成 500。"""

    service = _build_local_service(monkeypatch, tmp_path / "missing.zip")

    with pytest.raises(AppException) as excinfo:
        await _collect(service.iter_object_body("builds/missing.zip"))

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "OBJECT_NOT_FOUND"
