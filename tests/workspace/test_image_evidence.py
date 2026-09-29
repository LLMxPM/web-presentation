"""文件功能：验证镜像截图证据会拒绝损坏、空白和错误内容，不启动容器或浏览器。"""

import importlib.util
import struct
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "image_evidence", ROOT / "scripts/contracts/image_evidence.py"
)
assert SPEC and SPEC.loader
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def chunk(kind: bytes, content: bytes) -> bytes:
    """构造带 CRC 的 PNG 块供损坏与内容反例使用。"""
    return (
        struct.pack(">I", len(content))
        + kind
        + content
        + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)
    )


def png(*, correct: bool = True, filter_mode: int = 0) -> bytes:
    """生成固定双色 RGB PNG，同时测试五种 PNG 行过滤器的解码结果。"""
    rows = bytearray()
    previous = bytes(320 * 3)
    for y in range(240):
        color = (
            bytes((210, 80, 30) if y < 120 else (12, 34, 56))
            if correct
            else bytes((255, 255, 255))
        )
        original = color * 320
        encoded = bytearray()
        for index, value in enumerate(original):
            left = original[index - 3] if index >= 3 else 0
            up = previous[index]
            corner = previous[index - 3] if index >= 3 else 0
            estimate = left + up - corner
            paeth = min(
                (left, up, corner), key=lambda candidate: abs(estimate - candidate)
            )
            encoded.append(
                (value - (0, left, up, (left + up) // 2, paeth)[filter_mode]) & 255
            )
        rows.extend(bytes([filter_mode]) + encoded)
        previous = original
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 240, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("filter_mode", range(5))
def test_png_filters_preserve_expected_page(filter_mode: int) -> None:
    """完整解码各行过滤器后，颜色与画面坐标仍一致。"""
    EVIDENCE.verify_renderer_fixture(png(filter_mode=filter_mode))


def test_blank_truncated_or_corrupted_evidence_fails() -> None:
    """健康返回、空白图与损坏的 PNG 均不能作为真实执行通过证据。"""
    valid = png()
    for value in [
        b'{"status":"ok"}',
        valid[:-5],
        valid[:45] + b"bad" + valid[48:],
        png(correct=False),
    ]:
        with pytest.raises(ValueError):
            EVIDENCE.verify_renderer_fixture(value)
