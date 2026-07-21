"""文件功能：验证轻量图片尺寸解析不会依赖完整像素解码。"""

import struct

from app.services.image_metadata import read_image_dimensions


def test_read_png_dimensions() -> None:
    """PNG 尺寸应直接来自 IHDR。"""

    content = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1536, 1024)
    assert read_image_dimensions(content, "image/png") == (1536, 1024)


def test_read_jpeg_dimensions() -> None:
    """JPEG 尺寸应从 SOF0 段读取。"""

    content = b"\xff\xd8\xff\xc0\x00\x11\x08\x03\x00\x04\x00" + b"\x00" * 10
    assert read_image_dimensions(content, "image/jpeg") == (1024, 768)


def test_read_webp_vp8x_dimensions() -> None:
    """扩展 WebP 尺寸应按 24 位 little-endian 的减一值还原。"""

    payload = b"\x00\x00\x00\x00" + (639).to_bytes(3, "little") + (359).to_bytes(3, "little")
    content = b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + len(payload).to_bytes(4, "little") + payload
    assert read_image_dimensions(content, "image/webp") == (640, 360)


def test_invalid_image_returns_empty_dimensions() -> None:
    """伪造扩展名或损坏数据不应抛异常或产生虚假尺寸。"""

    assert read_image_dimensions(b"png-bytes", "image/png") == (None, None)
