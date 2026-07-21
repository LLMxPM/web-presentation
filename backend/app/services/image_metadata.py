"""文件功能：从受支持图片头部提取像素尺寸，不进行完整解码或引入图片处理依赖。"""

from __future__ import annotations

import struct


def read_image_dimensions(content: bytes, content_type: str) -> tuple[int | None, int | None]:
    """按 MIME 解析 PNG、JPEG、WebP 尺寸；数据损坏或未知布局时返回空值。"""

    try:
        if content_type == "image/png":
            return _read_png_dimensions(content)
        if content_type == "image/jpeg":
            return _read_jpeg_dimensions(content)
        if content_type == "image/webp":
            return _read_webp_dimensions(content)
    except (IndexError, struct.error, ValueError):
        return None, None
    return None, None


def _read_png_dimensions(content: bytes) -> tuple[int | None, int | None]:
    """读取 PNG IHDR 中的大端宽高。"""

    if len(content) < 24 or content[:8] != b"\x89PNG\r\n\x1a\n" or content[12:16] != b"IHDR":
        return None, None
    width, height = struct.unpack(">II", content[16:24])
    return _positive_dimensions(width, height)


def _read_jpeg_dimensions(content: bytes) -> tuple[int | None, int | None]:
    """扫描 JPEG SOF 段并读取宽高，不解码压缩像素。"""

    if len(content) < 4 or content[:2] != b"\xff\xd8":
        return None, None
    offset = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(content):
        if content[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset >= len(content):
            break
        marker = content[offset]
        offset += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(content):
            break
        segment_length = int.from_bytes(content[offset:offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(content):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(content[offset + 3:offset + 5], "big")
            width = int.from_bytes(content[offset + 5:offset + 7], "big")
            return _positive_dimensions(width, height)
        offset += segment_length
    return None, None


def _read_webp_dimensions(content: bytes) -> tuple[int | None, int | None]:
    """读取 WebP 的 VP8X、VP8 或 VP8L 图片头尺寸。"""

    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        return None, None
    chunk = content[12:16]
    payload = content[20:]
    if chunk == b"VP8X" and len(payload) >= 10:
        width = 1 + int.from_bytes(payload[4:7], "little")
        height = 1 + int.from_bytes(payload[7:10], "little")
        return _positive_dimensions(width, height)
    if chunk == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
        width = int.from_bytes(payload[6:8], "little") & 0x3FFF
        height = int.from_bytes(payload[8:10], "little") & 0x3FFF
        return _positive_dimensions(width, height)
    if chunk == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
        width = 1 + payload[1] + ((payload[2] & 0x3F) << 8)
        height = 1 + (payload[2] >> 6) + (payload[3] << 2) + ((payload[4] & 0x0F) << 10)
        return _positive_dimensions(width, height)
    return None, None


def _positive_dimensions(width: int, height: int) -> tuple[int | None, int | None]:
    """过滤零值和异常尺寸，避免把损坏头部写入附件元数据。"""

    if width <= 0 or height <= 0:
        return None, None
    return width, height
