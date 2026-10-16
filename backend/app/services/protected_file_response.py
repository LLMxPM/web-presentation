"""文件功能：统一私有文件的条件读取与流式响应，并将文件读占用保持到响应结束。"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from fastapi import Request
from fastapi.responses import Response, StreamingResponse


class ScopedFileResponse(StreamingResponse):
    """确保取消、断连或正常完成时都释放文件上下文。"""

    def __init__(self, *args: Any, stack: AsyncExitStack, **kwargs: Any) -> None:
        """接管已打开对象的退出栈，避免路由返回时过早释放缓存读占用。"""
        self.stack = stack
        super().__init__(*args, **kwargs)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """将资源生命周期覆盖整个 ASGI 响应，包括客户端取消。"""
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.stack.aclose()


def protected_bytes_response(
    *, request: Request, content: bytes, etag: str, media_type: str,
    original_name: str = "file", is_download: bool = False,
) -> Response:
    """在调用方已授权后交付内存对象；ETag 必须来自实际内容身份。"""
    from app.services.file_auth_service import FileAuthService as Auth

    size = len(content)
    if Auth.evaluate_preconditions(request, etag):
        return Response(status_code=304, headers=Auth.build_protected_headers(etag=etag, total_size=size))
    span = Auth.parse_single_range(request.headers.get("range"), size) if Auth.evaluate_if_range(request, etag) else None
    headers = Auth.build_protected_headers(
        etag=etag, total_size=size, range_span=span, is_download=is_download, original_name=original_name,
    )
    body = content if span is None else content[span[0]:span[1] + 1]
    return Response(
        content=b"" if request.method == "HEAD" else body,
        status_code=200 if span is None else 206, media_type=media_type, headers=headers,
    )


async def protected_file_response(
    *, request: Request, open_file: Any, etag: str, media_type: str,
    original_name: str = "file", is_download: bool = False,
) -> Response:
    """打开已授权对象并流式发送；条件请求完成后立即释放，正文发送期间保持读占用。"""
    from app.services.file_auth_service import FileAuthService as Auth

    stack = AsyncExitStack()
    try:
        path = await stack.enter_async_context(open_file)
        size = path.stat().st_size
        if Auth.evaluate_preconditions(request, etag):
            await stack.aclose()
            return Response(status_code=304, headers=Auth.build_protected_headers(etag=etag, total_size=size))
        span = Auth.parse_single_range(request.headers.get("range"), size) if Auth.evaluate_if_range(request, etag) else None
        headers = Auth.build_protected_headers(
            etag=etag, total_size=size, range_span=span, is_download=is_download, original_name=original_name,
        )
        status = 200 if span is None else 206
        if request.method == "HEAD":
            await stack.aclose()
            return Response(status_code=status, media_type=media_type, headers=headers)
        start = 0 if span is None else span[0]
        length = size if span is None else span[1] - span[0] + 1
        return ScopedFileResponse(
            Auth.stream_file_chunks(path, start=start, length=length), stack=stack,
            status_code=status, media_type=media_type, headers=headers,
        )
    except BaseException:
        await stack.aclose()
        raise
