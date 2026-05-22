"""文件功能：分析新上传 icon 资产的结构化能力元数据，供预览与 Runtime 按能力消费。"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from app.schemas.asset import AssetAnalysisMetadata, AssetIconAnalysisPayload

UNSAFE_TAGS = {"script", "foreignobject"}
COMPLEX_TAGS = {"style", "mask", "filter", "clippath", "symbol", "use"}
REFERENCE_ATTRIBUTE_NAMES = {"href", "xlink:href"}
SHAPE_TAGS = {
    "path",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "rect",
    "g",
    "svg",
}


class IconAnalysisService:
    """图标分析服务，仅在新上传的 icon 资产入库时执行能力判定。"""

    @classmethod
    def analyze_icon_asset(
        cls,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, object]:
        """分析 icon 资产并返回结构化元数据。"""

        if not cls._looks_like_svg(file_name=file_name, content_type=content_type, content=content):
            return cls._build_metadata(
                format_="image",
                render_mode="image",
                style="unknown",
                inline_safe=False,
                stroke_width_editable=False,
                analysis_status="unsupported",
                reasons=["资产不是 SVG，Runtime 将按图片模式渲染。"],
            ).model_dump(mode="python")

        try:
            root = ElementTree.fromstring(content.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 分析链路只做最佳努力，不阻断上传
            return cls._build_metadata(
                format_="svg",
                render_mode="image",
                style="unknown",
                inline_safe=False,
                stroke_width_editable=False,
                analysis_status="error",
                reasons=[f"SVG 解析失败，已降级为图片模式：{exc}"],
            ).model_dump(mode="python")

        return cls._analyze_svg_tree(root).model_dump(mode="python")

    @classmethod
    def _analyze_svg_tree(cls, root: ElementTree.Element) -> AssetAnalysisMetadata:
        """分析已成功解析的 SVG DOM 树。"""

        has_stroke = False
        has_fill = False
        has_drawable_shape = False
        unsafe_reasons: list[str] = []
        complex_reasons: list[str] = []

        for element in root.iter():
            tag_name = cls._normalize_tag_name(element.tag)
            if tag_name in UNSAFE_TAGS:
                unsafe_reasons.append(f"检测到不安全标签 <{tag_name}>。")
            if tag_name in COMPLEX_TAGS:
                complex_reasons.append(f"检测到复杂 SVG 标签 <{tag_name}>。")
            if cls._has_external_reference(element):
                unsafe_reasons.append(f"检测到外部引用，无法安全内联：<{tag_name}>。")

            if tag_name in SHAPE_TAGS:
                has_drawable_shape = True
                stroke_value = cls._normalize_paint_value(element.attrib.get("stroke"))
                fill_value = cls._normalize_paint_value(element.attrib.get("fill"))
                if stroke_value not in {"", "none"} and not stroke_value.startswith("url(#"):
                    has_stroke = True
                if fill_value not in {"", "none"} and not fill_value.startswith("url(#"):
                    has_fill = True

        if unsafe_reasons:
            return cls._build_metadata(
                format_="svg",
                render_mode="image",
                style="complex" if complex_reasons else "unknown",
                inline_safe=False,
                stroke_width_editable=False,
                analysis_status="unsupported",
                reasons=unsafe_reasons + complex_reasons,
            )

        if complex_reasons:
            return cls._build_metadata(
                format_="svg",
                render_mode="inline_svg",
                style="complex",
                inline_safe=True,
                stroke_width_editable=False,
                analysis_status="unsupported",
                reasons=complex_reasons,
            )

        if has_stroke and not has_fill:
            return cls._build_metadata(
                format_="svg",
                render_mode="inline_svg",
                style="stroke",
                inline_safe=True,
                stroke_width_editable=True,
                analysis_status="analyzed",
                reasons=["检测到纯描边 SVG，可安全应用描边宽度。"],
            )

        if has_stroke and has_fill:
            return cls._build_metadata(
                format_="svg",
                render_mode="inline_svg",
                style="mixed",
                inline_safe=True,
                stroke_width_editable=False,
                analysis_status="unsupported",
                reasons=["检测到 fill / stroke 混合图标，不启用描边宽度调整。"],
            )

        if has_fill or has_drawable_shape:
            return cls._build_metadata(
                format_="svg",
                render_mode="inline_svg",
                style="fill",
                inline_safe=True,
                stroke_width_editable=False,
                analysis_status="unsupported",
                reasons=["检测到填充型 SVG，不启用描边宽度调整。"],
            )

        return cls._build_metadata(
            format_="svg",
            render_mode="inline_svg",
            style="unknown",
            inline_safe=True,
            stroke_width_editable=False,
            analysis_status="unsupported",
            reasons=["未识别到可判定的图标结构，按普通 SVG 处理。"],
        )

    @staticmethod
    def _looks_like_svg(*, file_name: str, content_type: str | None, content: bytes) -> bool:
        """结合扩展名、上传 MIME 与内容头部判断资产是否为 SVG。"""

        normalized_suffix = Path(file_name or "").suffix.lower()
        normalized_content_type = str(content_type or "").lower()
        trimmed_content = content.lstrip()
        return (
            normalized_suffix == ".svg"
            or normalized_content_type in {"image/svg+xml", "text/svg+xml"}
            or trimmed_content.startswith(b"<svg")
            or trimmed_content.startswith(b"<?xml")
        )

    @staticmethod
    def _normalize_tag_name(tag_name: object) -> str:
        """把带命名空间的 XML 标签转换为小写局部名。"""

        normalized = str(tag_name or "")
        if "}" in normalized:
            normalized = normalized.rsplit("}", 1)[-1]
        return normalized.strip().lower()

    @classmethod
    def _has_external_reference(cls, element: ElementTree.Element) -> bool:
        """检测节点属性里是否存在外部引用。"""

        for attr_name, attr_value in element.attrib.items():
            normalized_attr_name = cls._normalize_tag_name(attr_name)
            normalized_attr_value = str(attr_value or "").strip()
            if not normalized_attr_value:
                continue
            if normalized_attr_name in REFERENCE_ATTRIBUTE_NAMES and not normalized_attr_value.startswith("#"):
                return True
            if "url(" in normalized_attr_value.lower() and "url(#" not in normalized_attr_value.lower():
                return True
            if normalized_attr_value.lower().startswith(("http://", "https://", "//")):
                return True
        return False

    @staticmethod
    def _normalize_paint_value(value: object) -> str:
        """归一化 fill / stroke 颜色值文本。"""

        return str(value or "").strip().lower()

    @staticmethod
    def _build_metadata(
        *,
        format_: str,
        render_mode: str,
        style: str,
        inline_safe: bool,
        stroke_width_editable: bool,
        analysis_status: str,
        reasons: list[str],
    ) -> AssetAnalysisMetadata:
        """统一组装分析结果对象。"""

        return AssetAnalysisMetadata(
            schema_version=1,
            kind="icon",
            icon=AssetIconAnalysisPayload(
                format=format_,  # type: ignore[arg-type]
                render_mode=render_mode,  # type: ignore[arg-type]
                style=style,  # type: ignore[arg-type]
                inline_safe=inline_safe,
                stroke_width_editable=stroke_width_editable,
                analysis_status=analysis_status,  # type: ignore[arg-type]
                reasons=reasons,
            ),
        )
