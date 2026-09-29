"""文件功能：解码 Renderer Chromium 输出的 RGB/RGBA PNG 并核对固定镜像探针画面。"""

from __future__ import annotations

import struct
import zlib


def decode_png(data: bytes) -> tuple[int, int, list[bytes], int]:
    """校验 PNG 分块与像素行；仅接受 Chromium 使用的 8 位、非交错 RGB/RGBA。"""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("产物不是 PNG")
    offset, width, height, channels = 8, 0, 0, 0
    compressed = bytearray()
    ended = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG 分块截断")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        end = offset + 8 + length
        if end + 4 > len(data):
            raise ValueError("PNG 分块长度无效")
        payload = data[offset + 8 : end]
        if (
            zlib.crc32(kind + payload) & 0xFFFFFFFF
            != struct.unpack(">I", data[end : end + 4])[0]
        ):
            raise ValueError("PNG CRC 不一致")
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if width <= 0 or height <= 0 or width * height > 16_000_000:
                raise ValueError("PNG 尺寸超出探针上限")
            if (
                depth != 8
                or color not in (2, 6)
                or compression
                or filtering
                or interlace
            ):
                raise ValueError("PNG 不属于 Chromium RGB/RGBA 输出")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            ended = end + 4 == len(data)
            break
        offset = end + 4
    if not ended or not channels:
        raise ValueError("PNG 头或结束块缺失")
    stride = width * channels
    expected = (stride + 1) * height
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, expected + 1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError("PNG 像素数据长度无效")
    rows: list[bytes] = []
    previous = bytes(stride)
    for row in range(height):
        start = row * (stride + 1)
        mode = raw[start]
        current = bytearray(raw[start + 1 : start + stride + 1])
        if mode > 4:
            raise ValueError("PNG 行过滤器无效")
        for index in range(stride):
            left = current[index - channels] if index >= channels else 0
            up = previous[index]
            corner = previous[index - channels] if index >= channels else 0
            estimate = left + up - corner
            distances = [abs(estimate - candidate) for candidate in (left, up, corner)]
            paeth = (left, up, corner)[distances.index(min(distances))]
            predictor = (0, left, up, (left + up) // 2, paeth)[mode]
            current[index] = (current[index] + predictor) & 255
        previous = bytes(current)
        rows.append(previous)
    return width, height, rows, channels


def verify_renderer_fixture(data: bytes) -> None:
    """核对上下两块固定颜色，避免空白 PNG 或旧页面也被当作截图成功。"""
    width, height, rows, channels = decode_png(data)
    if (width, height) != (320, 240):
        raise ValueError("Renderer 探针截图尺寸不匹配")
    for y, color in [(60, (210, 80, 30)), (180, (12, 34, 56))]:
        pixel = rows[y][160 * channels : 161 * channels]
        if tuple(pixel[:3]) != color or (channels == 4 and pixel[3] != 255):
            raise ValueError("Renderer 探针截图内容不匹配")
