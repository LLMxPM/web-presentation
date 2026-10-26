"""文件功能：验证构建产物下载响应在本地与大文件直连两条驱动下的行为。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.requests import Request

from app.core.exceptions import AppException
from app.services.build_artifact_download import build_artifact_download_response
from app.services.object_storage_service import ObjectProbe

pytestmark = pytest.mark.unit


class _FakeS3Storage:
    """模拟 S3 驱动：只记录拉流参数，不接触真实对象存储。"""

    driver = "s3"

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.stream_calls: list[str | None] = []

    async def probe_object(self, storage_key: str, **_: object) -> ObjectProbe:
        """返回与载荷一致的元信息，模拟 head_object 结果。"""

        return ObjectProbe(size_bytes=len(self.payload), etag=None)

    async def iter_object_body(
        self,
        storage_key: str,
        *,
        byte_range: str | None = None,
        **_: object,
    ) -> AsyncIterator[bytes]:
        """按请求区间切片返回，模拟 get_object 直连转发。"""

        self.stream_calls.append(byte_range)
        data = self.payload
        if byte_range is not None:
            start_text, _, end_text = byte_range.removeprefix("bytes=").partition("-")
            data = data[int(start_text) : int(end_text) + 1]
        yield data


class _FakeLocalStorage:
    """模拟本地驱动：FileResponse 需要真实可读路径。"""

    driver = "local"

    def __init__(self, path: Path) -> None:
        self.path = path

    async def probe_object(self, storage_key: str, **_: object) -> ObjectProbe:
        """返回真实文件大小，模拟本地 stat。"""

        return ObjectProbe(size_bytes=self.path.stat().st_size, etag=None)

    def resolve_local_path(self, storage_key: str) -> Path:
        """把对象键映射到临时文件。"""

        return self.path


def _build_request(method: str = "GET", headers: dict[str, str] | None = None) -> Request:
    """构造最小 HTTP scope，供下载响应读取方法与请求头。"""

    raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": "/api/projects/2/build-jobs/7/artifact",
            "raw_path": b"/api/projects/2/build-jobs/7/artifact",
            "query_string": b"",
            "headers": raw_headers,
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
        }
    )


async def _collect_body(response: StreamingResponse) -> bytes:
    """消费流式响应体，取得实际发送给客户端的字节。"""

    return b"".join([chunk async for chunk in response.body_iterator])


async def test_s3_download_should_stream_full_object() -> None:
    """S3 驱动直接转发对象流，并回传稳定 ETag 与真实长度。"""

    storage = _FakeS3Storage(b"0123456789")

    response = await build_artifact_download_response(
        request=_build_request(),
        storage=storage,  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="ABC123",
    )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    assert response.headers["content-length"] == "10"
    assert response.headers["etag"] == '"abc123"'
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"] == 'attachment; filename="project-2-build-7.zip"'
    assert await _collect_body(response) == b"0123456789"
    assert storage.stream_calls == [None]


async def test_s3_head_should_return_metadata_without_opening_stream() -> None:
    """HEAD 预检只回元信息，不得触发对象回源。"""

    storage = _FakeS3Storage(b"0123456789")

    response = await build_artifact_download_response(
        request=_build_request("HEAD"),
        storage=storage,  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="abc123",
    )

    assert not isinstance(response, StreamingResponse)
    assert isinstance(response, Response)
    assert response.status_code == 200
    assert response.headers["content-length"] == "10"
    assert storage.stream_calls == []


async def test_s3_range_request_should_forward_single_range() -> None:
    """合法单区间透传给对象存储，并回 206 与 Content-Range。"""

    storage = _FakeS3Storage(b"0123456789")

    response = await build_artifact_download_response(
        request=_build_request(headers={"Range": "bytes=2-5"}),
        storage=storage,  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="abc123",
    )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"
    # 拉流是惰性的：只有真正迭代响应体时才向对象存储发起 get_object。
    assert await _collect_body(response) == b"2345"
    assert storage.stream_calls == ["bytes=2-5"]


async def test_s3_range_request_should_be_ignored_when_if_range_mismatches() -> None:
    """If-Range 不匹配时必须回整包，避免拼出跨版本的错误文件。"""

    storage = _FakeS3Storage(b"0123456789")

    response = await build_artifact_download_response(
        request=_build_request(headers={"Range": "bytes=2-5", "If-Range": '"stale-etag"'}),
        storage=storage,  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="abc123",
    )

    assert response.status_code == 200
    assert await _collect_body(response) == b"0123456789"
    assert storage.stream_calls == [None]


async def test_s3_range_request_should_accept_matching_if_range() -> None:
    """If-Range 命中同一产物时正常续传。"""

    storage = _FakeS3Storage(b"0123456789")

    response = await build_artifact_download_response(
        request=_build_request(headers={"Range": "bytes=8-", "If-Range": '"abc123"'}),
        storage=storage,  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="abc123",
    )

    assert response.status_code == 206
    assert await _collect_body(response) == b"89"
    assert storage.stream_calls == ["bytes=8-9"]


async def test_s3_range_request_should_reject_unreachable_start() -> None:
    """起点越界时返回 416，进入流式响应之前就被拦下。"""

    storage = _FakeS3Storage(b"0123456789")

    with pytest.raises(AppException) as excinfo:
        await build_artifact_download_response(
            request=_build_request(headers={"Range": "bytes=99-"}),
            storage=storage,  # type: ignore[arg-type]
            storage_key="builds/p2-job7.zip",
            filename="project-2-build-7.zip",
            etag="abc123",
        )

    assert excinfo.value.status_code == 416
    assert excinfo.value.headers == {"Content-Range": "bytes */10"}
    assert storage.stream_calls == []


async def test_local_download_should_keep_file_response(tmp_path: Path) -> None:
    """本地驱动继续走 FileResponse，保留其自带的 Range 处理。"""

    archive_path = tmp_path / "archive.zip"
    archive_path.write_bytes(b"local-zip")

    response = await build_artifact_download_response(
        request=_build_request(),
        storage=_FakeLocalStorage(archive_path),  # type: ignore[arg-type]
        storage_key="builds/p2-job7.zip",
        filename="project-2-build-7.zip",
        etag="abc123",
    )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == archive_path
    assert response.headers["content-disposition"] == 'attachment; filename="project-2-build-7.zip"'
