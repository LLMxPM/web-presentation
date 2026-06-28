"""文件功能：解析资源内容的近似宽高比例，并生成稳定的渲染提示元数据。"""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from app.core.exceptions import AppException
from app.models.enums import AssetType

AspectRatioSource = Literal["auto", "manual", "agent"]

ASSET_RENDER_HINT_KIND = "asset_render_hint"
ASPECT_RATIO_SCHEMA_VERSION = 1


class AssetRenderMetadataService:
    """生成和维护资源渲染提示元数据；当前只记录近似比例，不记录尺寸。"""

    _NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?", re.IGNORECASE)
    _LENGTH_RE = re.compile(r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))(?:px|pt|pc|mm|cm|in)?\s*$", re.IGNORECASE)
    _DRAWIO_CELL_TAG = "mxCell"
    _DRAWIO_GEOMETRY_TAG = "mxGeometry"

    @classmethod
    def build_auto_metadata(
        cls,
        asset_type: AssetType,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, Any] | None:
        """根据资源内容自动推断近似比例；无法推断时返回 None。"""

        ratio = cls._extract_ratio(asset_type, original_name, content_type, content)
        return cls._build_metadata_from_ratio(ratio, source="auto") if ratio is not None else None

    @classmethod
    def preserve_manual_or_build_auto(
        cls,
        *,
        asset_type: AssetType,
        original_name: str,
        content_type: str | None,
        content: bytes,
        existing_metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """内容变化时保留人工/资源助手比例，否则重新自动推断。"""

        if cls.is_manual_metadata(existing_metadata):
            return existing_metadata
        return cls.build_auto_metadata(asset_type, original_name, content_type, content)

    @classmethod
    def build_manual_or_auto_metadata(
        cls,
        *,
        value: str | None,
        source: AspectRatioSource,
        asset_type: AssetType,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, Any] | None:
        """按用户输入生成比例；空值表示清除人工比例并回退自动推断。"""

        normalized_value = str(value or "").strip()
        if normalized_value:
            return cls.normalize_aspect_ratio_metadata(normalized_value, source=source)
        return cls.build_auto_metadata(asset_type, original_name, content_type, content)

    @classmethod
    def normalize_aspect_ratio_metadata(cls, value: str, *, source: AspectRatioSource) -> dict[str, Any]:
        """把 16:9、4/3 或 1.7778 等输入规范化为渲染提示元数据。"""

        ratio = cls._parse_ratio_input(value)
        return cls._build_metadata_from_ratio(ratio, source=source)

    @classmethod
    def summarize_metadata(cls, metadata: dict[str, Any] | None) -> dict[str, Any]:
        """提取 AI 工具和列表接口使用的近似比例摘要字段。"""

        if not cls.is_render_hint(metadata):
            return {
                "approx_aspect_ratio": None,
                "approx_aspect_ratio_value": None,
                "aspect_ratio_source": None,
            }
        return {
            "approx_aspect_ratio": metadata.get("aspect_ratio"),
            "approx_aspect_ratio_value": metadata.get("aspect_ratio_value"),
            "aspect_ratio_source": metadata.get("aspect_ratio_source"),
        }

    @staticmethod
    def is_render_hint(metadata: dict[str, Any] | None) -> bool:
        """判断元数据是否为当前约定的资源比例提示。"""

        return isinstance(metadata, dict) and metadata.get("kind") == ASSET_RENDER_HINT_KIND

    @classmethod
    def is_manual_metadata(cls, metadata: dict[str, Any] | None) -> bool:
        """判断现有比例是否来自人工或资源助手维护。"""

        return cls.is_render_hint(metadata) and metadata.get("aspect_ratio_source") in {"manual", "agent"}

    @classmethod
    def _extract_ratio(
        cls,
        asset_type: AssetType,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> float | None:
        """按资源类型分派比例解析逻辑。"""

        if asset_type == AssetType.DRAWIO:
            return cls._extract_drawio_ratio(content)
        if asset_type in {AssetType.IMAGE, AssetType.ICON}:
            if cls._is_svg_asset(original_name, content_type):
                return cls._extract_svg_ratio(content)
            return cls._extract_raster_ratio(content)
        return None

    @classmethod
    def _parse_ratio_input(cls, value: str) -> float:
        """解析用户输入的比例表达式，并返回正数比例值。"""

        text = str(value or "").strip()
        if not text:
            raise AppException(status_code=400, code="ASSET_ASPECT_RATIO_INVALID", detail="近似比例不能为空。")
        separator = ":" if ":" in text else "/" if "/" in text else None
        if separator:
            left, right = [item.strip() for item in text.split(separator, 1)]
            ratio = cls._parse_positive_number(left) / cls._parse_positive_number(right)
        else:
            ratio = cls._parse_positive_number(text)
        if not math.isfinite(ratio) or ratio <= 0:
            raise AppException(status_code=400, code="ASSET_ASPECT_RATIO_INVALID", detail="近似比例必须是正数。")
        return ratio

    @staticmethod
    def _parse_positive_number(value: str) -> float:
        """解析正数，失败时抛出业务错误。"""

        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise AppException(status_code=400, code="ASSET_ASPECT_RATIO_INVALID", detail="近似比例格式不合法。") from error
        if not math.isfinite(number) or number <= 0:
            raise AppException(status_code=400, code="ASSET_ASPECT_RATIO_INVALID", detail="近似比例必须是正数。")
        return number

    @classmethod
    def _build_metadata_from_ratio(cls, ratio: float, *, source: AspectRatioSource) -> dict[str, Any]:
        """从比例值生成稳定元数据，不包含任何尺寸字段。"""

        if not math.isfinite(ratio) or ratio <= 0:
            raise AppException(status_code=400, code="ASSET_ASPECT_RATIO_INVALID", detail="近似比例必须是正数。")
        fraction = Fraction(ratio).limit_denominator(100)
        return {
            "schema_version": ASPECT_RATIO_SCHEMA_VERSION,
            "kind": ASSET_RENDER_HINT_KIND,
            "aspect_ratio": f"{fraction.numerator}:{fraction.denominator}",
            "aspect_ratio_value": round(float(ratio), 4),
            "aspect_ratio_source": source,
        }

    @classmethod
    def _extract_svg_ratio(cls, content: bytes) -> float | None:
        """从 SVG viewBox 或 width/height 提取比例。"""

        root = cls._parse_xml(content)
        if root is None or cls._local_xml_name(str(root.tag)).lower() != "svg":
            return None
        view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
        ratio = cls._ratio_from_view_box(view_box)
        if ratio is not None:
            return ratio
        width = cls._parse_svg_length(root.attrib.get("width"))
        height = cls._parse_svg_length(root.attrib.get("height"))
        return cls._ratio_from_pair(width, height)

    @classmethod
    def _extract_drawio_ratio(cls, content: bytes) -> float | None:
        """从 Draw.io XML 的页面配置或图形 bounds 提取近似比例。"""

        root = cls._parse_xml(content)
        if root is None:
            return None
        for graph_model in root.iter():
            if cls._local_xml_name(str(graph_model.tag)) != "mxGraphModel":
                continue
            ratio = cls._ratio_from_pair(
                cls._parse_float(graph_model.attrib.get("pageWidth")),
                cls._parse_float(graph_model.attrib.get("pageHeight")),
            )
            if ratio is not None:
                return ratio
        return cls._extract_drawio_bounds_ratio(root)

    @classmethod
    def _extract_drawio_bounds_ratio(cls, root: ET.Element) -> float | None:
        """从 Draw.io 单元格几何范围计算内容近似比例。"""

        rects: list[tuple[float, float, float, float]] = []
        for cell in root.iter():
            if cls._local_xml_name(str(cell.tag)) != cls._DRAWIO_CELL_TAG:
                continue
            geometry = next(
                (
                    item for item in cell
                    if cls._local_xml_name(str(item.tag)) == cls._DRAWIO_GEOMETRY_TAG
                ),
                None,
            )
            if geometry is None:
                continue
            width = cls._parse_float(geometry.attrib.get("width"))
            height = cls._parse_float(geometry.attrib.get("height"))
            if width is None or height is None or width <= 0 or height <= 0:
                continue
            x = cls._parse_float(geometry.attrib.get("x")) or 0
            y = cls._parse_float(geometry.attrib.get("y")) or 0
            rects.append((x, y, width, height))
        if not rects:
            return None
        min_x = min(x for x, _, _, _ in rects)
        min_y = min(y for _, y, _, _ in rects)
        max_x = max(x + width for x, _, width, _ in rects)
        max_y = max(y + height for _, y, _, height in rects)
        return cls._ratio_from_pair(max_x - min_x, max_y - min_y)

    @classmethod
    def _extract_raster_ratio(cls, content: bytes) -> float | None:
        """从常见位图文件头读取比例。"""

        return (
            cls._extract_png_ratio(content)
            or cls._extract_gif_ratio(content)
            or cls._extract_jpeg_ratio(content)
            or cls._extract_webp_ratio(content)
        )

    @staticmethod
    def _extract_png_ratio(content: bytes) -> float | None:
        """从 PNG IHDR 读取比例。"""

        if len(content) < 24 or not content.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        width, height = struct.unpack(">II", content[16:24])
        return AssetRenderMetadataService._ratio_from_pair(width, height)

    @staticmethod
    def _extract_gif_ratio(content: bytes) -> float | None:
        """从 GIF 逻辑屏幕描述符读取比例。"""

        if len(content) < 10 or content[:6] not in {b"GIF87a", b"GIF89a"}:
            return None
        width, height = struct.unpack("<HH", content[6:10])
        return AssetRenderMetadataService._ratio_from_pair(width, height)

    @staticmethod
    def _extract_jpeg_ratio(content: bytes) -> float | None:
        """从 JPEG SOF 段读取比例。"""

        if len(content) < 4 or content[:2] != b"\xff\xd8":
            return None
        offset = 2
        sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
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
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(content):
                break
            segment_length = int.from_bytes(content[offset:offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(content):
                break
            if marker in sof_markers and segment_length >= 7:
                height = int.from_bytes(content[offset + 3:offset + 5], "big")
                width = int.from_bytes(content[offset + 5:offset + 7], "big")
                return AssetRenderMetadataService._ratio_from_pair(width, height)
            offset += segment_length
        return None

    @staticmethod
    def _extract_webp_ratio(content: bytes) -> float | None:
        """从 WebP VP8X/VP8/VP8L 头读取比例。"""

        if len(content) < 20 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
            return None
        offset = 12
        while offset + 8 <= len(content):
            chunk_type = content[offset:offset + 4]
            chunk_size = int.from_bytes(content[offset + 4:offset + 8], "little")
            payload_start = offset + 8
            payload_end = payload_start + chunk_size
            if payload_end > len(content):
                return None
            payload = content[payload_start:payload_end]
            ratio = AssetRenderMetadataService._ratio_from_webp_chunk(chunk_type, payload)
            if ratio is not None:
                return ratio
            offset = payload_end + (chunk_size % 2)
        return None

    @staticmethod
    def _ratio_from_webp_chunk(chunk_type: bytes, payload: bytes) -> float | None:
        """解析单个 WebP 图像数据块的比例。"""

        if chunk_type == b"VP8X" and len(payload) >= 10:
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
            return AssetRenderMetadataService._ratio_from_pair(width, height)
        if chunk_type == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(payload[6:8], "little") & 0x3FFF
            height = int.from_bytes(payload[8:10], "little") & 0x3FFF
            return AssetRenderMetadataService._ratio_from_pair(width, height)
        if chunk_type == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
            b0, b1, b2, b3 = payload[1], payload[2], payload[3], payload[4]
            width = 1 + (((b1 & 0x3F) << 8) | b0)
            height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
            return AssetRenderMetadataService._ratio_from_pair(width, height)
        return None

    @classmethod
    def _ratio_from_view_box(cls, value: str | None) -> float | None:
        """从 viewBox 提取比例。"""

        numbers = [float(item.group(0)) for item in cls._NUMBER_RE.finditer(str(value or ""))]
        if len(numbers) < 4:
            return None
        return cls._ratio_from_pair(numbers[2], numbers[3])

    @classmethod
    def _parse_svg_length(cls, value: str | None) -> float | None:
        """解析 SVG length；百分比和未知单位不用于比例推断。"""

        match = cls._LENGTH_RE.match(str(value or ""))
        if not match:
            return None
        return cls._parse_float(match.group(1))

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """解析有限数字，失败时返回 None。"""

        try:
            number = float(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _ratio_from_pair(width: float | int | None, height: float | int | None) -> float | None:
        """用一对正数计算比例。"""

        if width is None or height is None:
            return None
        if width <= 0 or height <= 0:
            return None
        return float(width) / float(height)

    @staticmethod
    def _parse_xml(content: bytes) -> ET.Element | None:
        """解析 XML；失败时返回 None，避免影响资源写入主流程。"""

        try:
            return ET.fromstring(content)
        except ET.ParseError:
            return None

    @staticmethod
    def _local_xml_name(tag: str) -> str:
        """去掉 XML 命名空间，仅保留标签局部名。"""

        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _is_svg_asset(original_name: str, content_type: str | None) -> bool:
        """根据文件名或 MIME 判断资源是否为 SVG。"""

        normalized_name = Path(str(original_name or "")).suffix.lower()
        normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
        return normalized_name == ".svg" or normalized_content_type == "image/svg+xml"
