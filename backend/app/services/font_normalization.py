"""文件功能：集中负责字体格式、字重、样式、显示策略的归一化与校验，以及源码中的字体声明提取。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
from typing import Final

from app.core.exceptions import AppException

FONT_WEIGHT_VALUE_PATTERN: Final = re.compile(r"^\d{1,4}$")
FONT_WEIGHT_RANGE_PATTERN: Final = re.compile(r"^(\d{1,4})\s+(\d{1,4})$")
FONT_STYLE_ALLOWED_VALUES: Final[frozenset[str]] = frozenset({"normal", "italic", "oblique"})
FONT_DISPLAY_ALLOWED_VALUES: Final[frozenset[str]] = frozenset(
    {"auto", "block", "swap", "fallback", "optional"}
)
FONT_ASSET_CALL_PATTERN: Final = re.compile(
    r"\b(?:useAssetFontFamily|resolveAssetFontFamily)\s*\(\s*(?:'(?P<single>[^'\\]*(?:\\.[^'\\]*)*)'|\"(?P<double>[^\"\\]*(?:\\.[^\"\\]*)*)\")"
)


def infer_font_format(asset_name: str) -> str:
    """根据资产文件名推断字体格式。"""
    suffixes = [suffix.lstrip(".").lower() for suffix in Path(asset_name).suffixes]
    for candidate in reversed(suffixes):
        if candidate in {"woff2", "woff", "ttf", "otf"}:
            return candidate
    return "woff2"


def normalize_font_format(font_format: str) -> str:
    """规范化字体格式字段，限定在受支持的标准字体扩展名内。"""
    normalized = str(font_format or "").strip().lower()
    if normalized not in {"woff2", "woff", "ttf", "otf"}:
        raise AppException(
            status_code=400,
            code="FONT_FORMAT_INVALID",
            detail="字体格式仅支持 woff2、woff、ttf、otf。",
        )
    return normalized


def normalize_font_weight(font_weight: str) -> str:
    """规范化 font-weight，允许单值数字（如 "400"）或可变字体范围（如 "100 900"）。"""
    normalized = str(font_weight or "").strip()
    if FONT_WEIGHT_VALUE_PATTERN.match(normalized):
        return normalized
    range_match = FONT_WEIGHT_RANGE_PATTERN.match(normalized)
    if range_match and int(range_match.group(1)) <= int(range_match.group(2)):
        return normalized
    raise AppException(
        status_code=400,
        code="FONT_WEIGHT_INVALID",
        detail='font-weight 仅支持数字（如 "400"）或可变字体范围（如 "100 900"，且最小值不大于最大值）。',
    )


def normalize_font_style(font_style: str) -> str:
    """规范化 font-style，仅允许 normal、italic、oblique。"""
    normalized = str(font_style or "").strip().lower()
    if normalized not in FONT_STYLE_ALLOWED_VALUES:
        raise AppException(
            status_code=400,
            code="FONT_STYLE_INVALID",
            detail="font-style 仅支持 normal、italic、oblique。",
        )
    return normalized


def normalize_font_display(font_display: str) -> str:
    """规范化 font-display，仅允许 auto、block、swap、fallback、optional。"""
    normalized = str(font_display or "").strip().lower()
    if normalized not in FONT_DISPLAY_ALLOWED_VALUES:
        raise AppException(
            status_code=400,
            code="FONT_DISPLAY_INVALID",
            detail="font-display 仅支持 auto、block、swap、fallback、optional。",
        )
    return normalized


def unescape_js_string_literal(value: str) -> str:
    """处理静态 JS 字符串字面量中的常见转义。"""
    return (
        str(value or "")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def normalize_font_asset_name(value: str) -> str:
    """按 Runtime 资源 key 规则规范化字体资源逻辑名。"""
    normalized = str(value or "").strip().replace("\\", "/").lstrip("./")
    if not normalized or re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        return ""
    return normalized


def normalize_font_asset_names(values: Iterable[str]) -> list[str]:
    """规范化并去重字体资源逻辑名列表。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_font_asset_name(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def collect_declared_font_asset_names(sources: Iterable[str]) -> list[str]:
    """从 Vue/TS 源码中收集 useAssetFontFamily/resolveAssetFontFamily 的静态资源名。"""
    result: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for match in FONT_ASSET_CALL_PATTERN.finditer(str(source or "")):
            raw_value = match.group("single") if match.group("single") is not None else match.group("double")
            normalized_name = normalize_font_asset_name(
                unescape_js_string_literal(str(raw_value or ""))
            )
            if not normalized_name or normalized_name in seen:
                continue
            seen.add(normalized_name)
            result.append(normalized_name)
    return result


def collect_declared_font_asset_names_from_modules(modules_data: Iterable[dict[str, str]]) -> list[str]:
    """从模块源码列表中收集 Runtime Kit 字体资源静态声明。"""
    return collect_declared_font_asset_names(
        str(item.get("content") or "") for item in modules_data
    )


def build_font_entry_lookup_by_asset_name(
    runtime_font_entries: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """按资产逻辑名建立字体条目索引。"""
    return {
        entry["asset_name"]: entry
        for entry in runtime_font_entries
        if entry.get("asset_name")
    }


def build_font_entry_lookup_by_family_name(
    runtime_font_entries: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """按字体族名聚合字体条目。"""
    result: dict[str, list[dict[str, str]]] = {}
    for entry in runtime_font_entries:
        family_name = str(entry.get("font_family") or "").strip()
        if not family_name:
            continue
        result.setdefault(family_name, []).append(entry)
    return result
