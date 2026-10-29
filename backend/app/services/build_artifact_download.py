"""文件功能：构造项目构建产物下载响应，统一本地文件与大文件流式两条链路。"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.services.http_byte_range import parse_single_byte_range
from app.services.object_storage_service import ObjectStorageService

BUILD_ARTIFACT_MEDIA_TYPE = "application/zip"


async def build_artifact_download_response(
    *,
    request: Request,
    storage: ObjectStorageService,
    storage_key: str,
    filename: str,
    etag: str | None = None,
) -> Response:
    """按存储驱动构造下载响应。

    local 驱动继续使用 FileResponse，享受它自带的 Range/ETag 处理；S3 驱动
    只先取 head_object 元信息，随后直接把 get_object 的响应体转发给客户端，
    响应头在回源开始前即发出，不再等待整个归档落到本地派生缓存。

    代价是 S3 链路不再在下载时做整包 sha256 复核：产物完整性由上传阶段
    （`put_object_stream` 边写边算）与任务行记录共同保证。
    """

    # 先探测一次：既提供 404 语义，也为区间计算拿到真实大小。
    probe = await storage.probe_object(storage_key)
    headers = _build_base_headers(etag)

    if storage.driver != "s3":
        return FileResponse(
            path=str(storage.resolve_local_path(storage_key)),
            media_type=BUILD_ARTIFACT_MEDIA_TYPE,
            filename=filename,
            headers=headers,
        )

    byte_range = parse_single_byte_range(_resolve_range_header(request, etag), probe.size_bytes)
    # probe 与后续 get_object 之间存在窗口：产物对象键含 attempt_id，写入后不会
    # 同名重建，只可能被并发删除命中。此时响应头已按 probe 的长度发出，客户端会
    # 收到长度不足的响应并判为下载失败。这是有意保留的降级——为了这个极窄窗口
    # 改成「先 get 再回头改写响应头」，会把首字节延迟重新绑回对象回源。
    if byte_range is None:
        status_code = 200
        content_length = probe.size_bytes
    else:
        status_code = 206
        content_length = byte_range.length
        headers["Content-Range"] = byte_range.to_content_range(probe.size_bytes)

    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    headers["Content-Length"] = str(content_length)

    if request.method.upper() == "HEAD":
        # HEAD 只回元信息：StreamingResponse 不会自行跳过响应体，必须在此短路，
        # 否则预检会真的触发一次对象回源。
        return Response(status_code=status_code, media_type=BUILD_ARTIFACT_MEDIA_TYPE, headers=headers)

    return StreamingResponse(
        storage.iter_object_body(
            storage_key,
            byte_range=byte_range.to_header_value() if byte_range is not None else None,
        ),
        status_code=status_code,
        media_type=BUILD_ARTIFACT_MEDIA_TYPE,
        headers=headers,
    )


def _build_base_headers(etag: str | None) -> dict[str, str]:
    """构造下载响应的公共安全头。

    产物始终是登录态保护的私有文件，禁止共享缓存与内容嗅探；ETag 用任务行
    保存的 sha256，跨对象存储实现保持稳定，供浏览器做 If-Range 续传校验。
    """

    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
    }
    normalized_etag = (etag or "").strip().lower()
    if normalized_etag:
        headers["ETag"] = f'"{normalized_etag}"'
    return headers


def _resolve_range_header(request: Request, etag: str | None) -> str | None:
    """按 RFC 7233 校验 If-Range，不匹配时忽略 Range 退回整包。"""

    range_header = request.headers.get("range")
    if not range_header:
        return None

    if_range = (request.headers.get("if-range") or "").strip()
    normalized_etag = (etag or "").strip().lower()
    if not if_range or not normalized_etag:
        return range_header

    candidate = if_range.removeprefix("W/").strip().strip('"').lower()
    return range_header if candidate == normalized_etag else None
