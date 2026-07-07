"""文件功能：验证资源近似比例元数据解析与人工输入规范化。"""

from __future__ import annotations

import struct

import pytest

from app.core.exceptions import AppException
from app.models.enums import AssetType
from app.services.asset_render_metadata_service import AssetRenderMetadataService


def _build_webp_vp8x(width: int, height: int) -> bytes:
    """构造最小 VP8X WebP 头用于比例解析测试。"""

    payload = (
        b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    chunk = b"VP8X" + len(payload).to_bytes(4, "little") + payload
    return b"RIFF" + (len(chunk) + 4).to_bytes(4, "little") + b"WEBP" + chunk


def _mp4_box(box_type: bytes, payload: bytes) -> bytes:
    """构造一个普通 32 位长度 MP4 box。"""

    return (len(payload) + 8).to_bytes(4, "big") + box_type + payload


def _build_mp4_tkhd(width: int, height: int) -> bytes:
    """构造包含 tkhd 宽高字段的最小 MP4 box 树。"""

    tkhd_payload = (
        b"\x00\x00\x00\x07"
        + b"\x00" * 76
        + (width << 16).to_bytes(4, "big")
        + (height << 16).to_bytes(4, "big")
    )
    return _mp4_box(b"ftyp", b"isom\x00\x00\x02\x00") + _mp4_box(b"moov", _mp4_box(b"trak", _mp4_box(b"tkhd", tkhd_payload)))


def test_svg_viewbox_should_generate_auto_aspect_ratio() -> None:
    """SVG viewBox 应生成自动近似比例，且不包含宽高尺寸字段。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.IMAGE,
        "hero.svg",
        "image/svg+xml",
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"></svg>',
    )

    assert metadata == {
        "schema_version": 1,
        "kind": "asset_render_hint",
        "aspect_ratio": "16:9",
        "aspect_ratio_value": 1.7778,
        "aspect_ratio_source": "auto",
    }
    assert "width" not in metadata
    assert "height" not in metadata


def test_svg_width_height_should_generate_auto_aspect_ratio() -> None:
    """SVG 缺少 viewBox 时应回退解析 width/height。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.IMAGE,
        "poster.svg",
        "image/svg+xml",
        b'<svg xmlns="http://www.w3.org/2000/svg" width="400px" height="300px"></svg>',
    )

    assert metadata is not None
    assert metadata["aspect_ratio"] == "4:3"
    assert metadata["aspect_ratio_source"] == "auto"


@pytest.mark.parametrize(
    ("content", "expected_ratio"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 800, 600), "4:3"),
        (b"GIF89a" + struct.pack("<HH", 320, 160), "2:1"),
        (
            b"\xff\xd8\xff\xc0"
            + (17).to_bytes(2, "big")
            + b"\x08"
            + (200).to_bytes(2, "big")
            + (300).to_bytes(2, "big")
            + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00",
            "3:2",
        ),
        (_build_webp_vp8x(1920, 1080), "16:9"),
    ],
)
def test_raster_headers_should_generate_auto_aspect_ratio(content: bytes, expected_ratio: str) -> None:
    """常见位图文件头应能解析出近似比例。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(AssetType.IMAGE, "photo.png", "image/png", content)

    assert metadata is not None
    assert metadata["aspect_ratio"] == expected_ratio
    assert metadata["aspect_ratio_source"] == "auto"


def test_mp4_tkhd_should_generate_video_aspect_ratio() -> None:
    """MP4/MOV 的 tkhd 宽高字段应能解析出视频近似比例。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.VIDEO,
        "demo.mp4",
        "video/mp4",
        _build_mp4_tkhd(1920, 1080),
    )

    assert metadata is not None
    assert metadata["aspect_ratio"] == "16:9"
    assert metadata["aspect_ratio_source"] == "auto"


def test_drawio_page_size_should_generate_auto_aspect_ratio() -> None:
    """Draw.io XML 的页面尺寸应转成近似比例提示。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.DRAWIO,
        "flow.drawio",
        "application/xml",
        b'<mxfile><diagram><mxGraphModel pageWidth="960" pageHeight="540" /></diagram></mxfile>',
    )

    assert metadata is not None
    assert metadata["aspect_ratio"] == "16:9"
    assert metadata["aspect_ratio_source"] == "auto"


def test_drawio_bounds_should_generate_auto_aspect_ratio() -> None:
    """Draw.io 缺少页面尺寸时应使用内容 bounds 的近似比例。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.DRAWIO,
        "flow.drawio",
        "application/xml",
        b"""
        <mxfile>
          <diagram>
            <mxGraphModel>
              <root>
                <mxCell id="2" vertex="1"><mxGeometry x="10" y="20" width="400" height="100" /></mxCell>
                <mxCell id="3" vertex="1"><mxGeometry x="210" y="120" width="200" height="200" /></mxCell>
              </root>
            </mxGraphModel>
          </diagram>
        </mxfile>
        """,
    )

    assert metadata is not None
    assert metadata["aspect_ratio"] == "4:3"
    assert metadata["aspect_ratio_source"] == "auto"


def test_mermaid_should_not_generate_auto_aspect_ratio() -> None:
    """Mermaid 默认不自动推断比例。"""

    metadata = AssetRenderMetadataService.build_auto_metadata(
        AssetType.MERMAID,
        "flow.mmd",
        "text/plain",
        b"flowchart TD\n  A --> B",
    )

    assert metadata is None


@pytest.mark.parametrize("value", ["16:9", "4/3", "1.7778"])
def test_manual_aspect_ratio_should_be_normalized(value: str) -> None:
    """人工输入支持常见比例表达式，并统一为稳定元数据。"""

    metadata = AssetRenderMetadataService.normalize_aspect_ratio_metadata(value, source="manual")

    assert metadata["aspect_ratio_value"] > 0
    assert metadata["aspect_ratio_source"] == "manual"


@pytest.mark.parametrize("value", ["", "0", "16:0", "abc"])
def test_invalid_manual_aspect_ratio_should_raise(value: str) -> None:
    """非法人工比例应抛出业务错误。"""

    with pytest.raises(AppException) as exc_info:
        AssetRenderMetadataService.normalize_aspect_ratio_metadata(value, source="manual")

    assert exc_info.value.code == "ASSET_ASPECT_RATIO_INVALID"
