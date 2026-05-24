"""文件功能：统一解析 Vue 源码与组件 preview_schema 中的静态资源引用。"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

DYNAMIC_RESOURCE_NAME = "__DYNAMIC__"

_TEMPLATE_BLOCK_PATTERN = re.compile(r"<template\b[^>]*>(.*?)</template>", flags=re.IGNORECASE | re.DOTALL)
_SCRIPT_BLOCK_PATTERN = re.compile(r"<script\b[^>]*>(.*?)</script>", flags=re.IGNORECASE | re.DOTALL)
_TEMPLATE_TAG_SCAN_PATTERN = re.compile(r"<\s*(/?)\s*([A-Za-z][\w.-]*)\b([^<>]*?)(/?)\s*>", flags=re.DOTALL)
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", flags=re.DOTALL)
_STATIC_NAME_ATTR_PATTERN = re.compile(r"""(?:^|\s)name\s*=\s*(["'])(.*?)\1""", flags=re.IGNORECASE | re.DOTALL)
_STATIC_NAME_ATTR_UNQUOTED_PATTERN = re.compile(r"""(?:^|\s)name\s*=\s*([^\s"'=<>`]+)""", flags=re.IGNORECASE)
_BOUND_NAME_ATTR_PATTERN = re.compile(
    r"""(?:^|\s)(?::name|v-bind:name)\s*=\s*(["'])(.*?)\1""",
    flags=re.IGNORECASE | re.DOTALL,
)
_V_FOR_ATTR_PATTERN = re.compile(r"""(?:^|\s)v-for\s*=\s*(["'])(.*?)\1""", flags=re.IGNORECASE | re.DOTALL)
_V_FOR_EXPRESSION_PATTERN = re.compile(
    r"""^\s*(?:\(\s*(?P<tuple_alias>[A-Za-z_$][\w$]*)\s*(?:,\s*[A-Za-z_$][\w$]*)?\s*\)|(?P<alias>[A-Za-z_$][\w$]*))\s+(?:in|of)\s+(?P<collection>[A-Za-z_$][\w$]*)\s*$"""
)
_CONST_ARRAY_START_PATTERN = re.compile(
    r"""\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=\n;]+)?=\s*\[""",
    flags=re.DOTALL,
)
_MEMBER_EXPRESSION_PATTERN = re.compile(
    r"""^\s*(?P<alias>[A-Za-z_$][\w$]*)\s*(?:\.\s*(?P<dot_key>[A-Za-z_$][\w$]*)|\[\s*(?P<quote>["'])(?P<bracket_key>(?:\\.|(?!\3).)*)\3\s*\])\s*$""",
    flags=re.DOTALL,
)
_STATIC_ASSET_CALL_PATTERN = re.compile(
    r"\b(?:useAssetSrc|useAssetBackground|resolveResourcePath|useIcon)\s*\("
    r"\s*(?:'(?P<single>(?:\\.|[^'\\])*)'|\"(?P<double>(?:\\.|[^\"\\])*)\")",
    flags=re.DOTALL,
)
_RUNTIME_KIT_VERSION_SUFFIX_PATTERN = re.compile(r"\.v\d+$")

_VUE_NATIVE_TAGS = {
    "template",
    "slot",
    "component",
    "transition",
    "transition-group",
    "keep-alive",
    "teleport",
    "suspense",
}

_HTML_NATIVE_TAGS = {
    "a",
    "abbr",
    "address",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "base",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "i",
    "iframe",
    "img",
    "input",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "link",
    "main",
    "map",
    "mark",
    "menu",
    "meta",
    "meter",
    "nav",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "param",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "search",
    "section",
    "select",
    "small",
    "source",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "track",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
    "svg",
    "path",
    "circle",
    "ellipse",
    "g",
    "line",
    "lineargradient",
    "mask",
    "pattern",
    "polygon",
    "polyline",
    "radialgradient",
    "rect",
    "stop",
    "symbol",
    "text",
    "tspan",
    "use",
}


@dataclass(frozen=True, slots=True)
class ResourceReferenceResult:
    """资源引用解析结果，区分静态资源名和动态引用标记。"""

    asset_names: list[str]
    has_dynamic: bool = False


class ResourceReferenceParser:
    """集中维护页面与组件共享的资源引用解析规则。"""

    @classmethod
    def collect_vue_component_index(cls, source: str) -> tuple[set[str], set[tuple[str, str]]]:
        """从 Vue template 收集组件集合和 Icon/Asset* 的 name 参数集合。"""

        component_names, resource_items = cls.collect_vue_component_references(source)
        return component_names, set(resource_items)

    @classmethod
    def collect_vue_component_resource_items(cls, source: str) -> list[tuple[str, str]]:
        """按模板出现顺序收集 Icon/Asset* 的 name 参数集合。"""

        _, resource_items = cls.collect_vue_component_references(source)
        return resource_items

    @classmethod
    def collect_vue_component_references(cls, source: str) -> tuple[set[str], list[tuple[str, str]]]:
        """从 Vue template 收集组件集合，并保留资源引用出现顺序。"""

        component_names: set[str] = set()
        resource_names: list[tuple[str, str]] = []
        template_content = cls.extract_template_content(source)
        if not template_content:
            return set(), []

        static_arrays = cls.collect_top_level_const_array_string_fields(source)
        scope_stack: list[tuple[str, dict[str, dict[str, list[str]]]]] = []
        clean_template = _HTML_COMMENT_PATTERN.sub("", template_content)
        for is_closing, raw_tag, attrs_text, is_self_closing in cls.iter_template_tags(clean_template):
            normalized_tag = raw_tag.lower()
            if is_closing:
                cls._pop_template_scope(scope_stack, normalized_tag)
                continue

            current_scope = cls.merge_scope_stack(scope_stack)
            own_scope = cls.extract_v_for_scope(attrs_text, static_arrays)
            scoped_resource_values = {**current_scope, **own_scope}
            if not cls.is_component_tag(raw_tag):
                if not is_self_closing:
                    scope_stack.append((normalized_tag, own_scope))
                continue

            component_name = cls.normalize_component_name(raw_tag)
            component_names.add(component_name)
            if cls.needs_name_resource_index(component_name):
                for resource_name in cls.extract_name_resources(attrs_text, scoped_resource_values):
                    resource_item = (component_name, resource_name)
                    if resource_item not in resource_names:
                        resource_names.append(resource_item)
            if not is_self_closing:
                scope_stack.append((normalized_tag, own_scope))

        return component_names, resource_names

    @classmethod
    def collect_vue_asset_references(cls, source: str) -> ResourceReferenceResult:
        """从 Vue 源码收集资源组件和资源辅助函数中的静态资源名。"""

        _, resource_items = cls.collect_vue_component_index(source)
        names = [resource_name for _, resource_name in resource_items]
        names.extend(cls.collect_static_asset_call_names([source]))
        return cls.build_result(names)

    @classmethod
    def collect_preview_schema_asset_references(cls, schema_text: str | None) -> ResourceReferenceResult:
        """从组件 preview_schema 的 component 节点 props.name 中收集资源名。"""

        if not schema_text or not str(schema_text).strip():
            return ResourceReferenceResult(asset_names=[])

        try:
            parsed_schema = json.loads(schema_text)
        except json.JSONDecodeError:
            return ResourceReferenceResult(asset_names=[])
        if not isinstance(parsed_schema, dict):
            return ResourceReferenceResult(asset_names=[])

        names: list[str] = []
        cls._collect_schema_slot_nodes(parsed_schema.get("slots"), names)
        presets = parsed_schema.get("presets")
        if isinstance(presets, list):
            for preset in presets:
                if isinstance(preset, dict):
                    cls._collect_schema_slot_nodes(preset.get("slots"), names)
        return cls.build_result(names)

    @classmethod
    def collect_static_asset_call_names(cls, sources: Iterable[str]) -> list[str]:
        """从资源辅助函数调用中收集静态字符串参数。"""

        names: list[str] = []
        for source in sources:
            for match in _STATIC_ASSET_CALL_PATTERN.finditer(source or ""):
                raw_value = match.group("single") or match.group("double") or ""
                normalized = cls.parse_escaped_literal_body(raw_value).strip()
                if normalized:
                    names.append(normalized)
        return cls.deduplicate_keep_order(names)

    @classmethod
    def build_result(cls, names: Iterable[str]) -> ResourceReferenceResult:
        """归一化资源名集合，并把动态标记拆分为独立布尔值。"""

        normalized_names: list[str] = []
        has_dynamic = False
        for name in names:
            normalized = str(name or "").strip()
            if not normalized:
                continue
            if normalized == DYNAMIC_RESOURCE_NAME:
                has_dynamic = True
                continue
            normalized_names.append(normalized)
        return ResourceReferenceResult(
            asset_names=sorted(set(normalized_names)),
            has_dynamic=has_dynamic,
        )

    @classmethod
    def extract_template_content(cls, source: str) -> str:
        """提取 Vue 文件中所有 template 块内容。"""

        blocks = _TEMPLATE_BLOCK_PATTERN.findall(source or "")
        return "\n".join(blocks) if blocks else ""

    @staticmethod
    def is_component_tag(tag_name: str) -> bool:
        """判断标签是否应纳入组件使用统计。"""

        lower_name = tag_name.lower()
        if lower_name in _VUE_NATIVE_TAGS:
            return False
        if "-" in tag_name:
            return True
        if tag_name[0].isupper():
            return True
        if lower_name in {"icon"} or lower_name.startswith("asset"):
            return True
        return lower_name not in _HTML_NATIVE_TAGS

    @staticmethod
    def normalize_component_name(tag_name: str) -> str:
        """统一组件名展示格式。"""

        if "-" in tag_name:
            return "".join(part[:1].upper() + part[1:] for part in tag_name.split("-") if part)
        if tag_name.lower() == "icon":
            return "Icon"
        if tag_name.lower().startswith("asset"):
            return tag_name[:1].upper() + tag_name[1:]
        return tag_name

    @staticmethod
    def needs_name_resource_index(component_name: str) -> bool:
        """判断组件是否需要提取 name 参数作为资源引用。"""

        return component_name == "Icon" or component_name.startswith("Asset")

    @classmethod
    def extract_name_resources(
        cls,
        attrs_text: str,
        scoped_resource_values: dict[str, dict[str, list[str]]] | None = None,
    ) -> list[str]:
        """从组件属性串提取 name 参数，动态表达式返回统一标记。"""

        values: list[str] = []

        for _, raw_value in _STATIC_NAME_ATTR_PATTERN.findall(attrs_text or ""):
            normalized = raw_value.strip()
            if normalized:
                values.append(normalized)
        for raw_value in _STATIC_NAME_ATTR_UNQUOTED_PATTERN.findall(attrs_text or ""):
            normalized = raw_value.strip()
            if normalized:
                values.append(normalized)

        has_dynamic_name = False
        for _, expression in _BOUND_NAME_ATTR_PATTERN.findall(attrs_text or ""):
            literal = cls.parse_js_string_literal(expression)
            if literal is None:
                scoped_values = cls.resolve_scoped_resource_values(expression, scoped_resource_values)
                if scoped_values is None:
                    has_dynamic_name = True
                    continue
                values.extend(scoped_values)
                continue
            normalized = literal.strip()
            if normalized:
                values.append(normalized)

        if has_dynamic_name:
            values.append(DYNAMIC_RESOURCE_NAME)

        return cls.deduplicate_keep_order(values)

    @classmethod
    def collect_top_level_const_array_string_fields(cls, source: str) -> dict[str, dict[str, list[str]]]:
        """收集同一 SFC 顶层 const 数组对象字面量中的字符串字段值。"""

        result: dict[str, dict[str, list[str]]] = {}
        for script_content in _SCRIPT_BLOCK_PATTERN.findall(source or ""):
            for match in _CONST_ARRAY_START_PATTERN.finditer(script_content):
                if not cls.is_top_level_script_position(script_content, match.start()):
                    continue
                array_name = match.group("name")
                array_start = match.end() - 1
                array_end = cls.find_balanced_end(script_content, array_start, "[", "]")
                if array_end is None:
                    continue
                field_values = cls.parse_array_object_string_fields(script_content[array_start + 1 : array_end])
                if field_values:
                    result[array_name] = field_values
        return result

    @classmethod
    def iter_template_tags(cls, template_content: str) -> Iterable[tuple[bool, str, str, bool]]:
        """遍历 template 标签，返回关闭标记、标签名、属性文本和自闭合状态。"""

        for match in _TEMPLATE_TAG_SCAN_PATTERN.finditer(template_content or ""):
            yield (
                bool(match.group(1)),
                match.group(2),
                match.group(3) or "",
                bool(match.group(4)),
            )

    @staticmethod
    def merge_scope_stack(scope_stack: list[tuple[str, dict[str, dict[str, list[str]]]]]) -> dict[str, dict[str, list[str]]]:
        """合并当前 template 标签栈上的 v-for 静态资源作用域。"""

        merged: dict[str, dict[str, list[str]]] = {}
        for _, scope_item in scope_stack:
            merged.update(scope_item)
        return merged

    @classmethod
    def extract_v_for_scope(
        cls,
        attrs_text: str,
        static_arrays: dict[str, dict[str, list[str]]],
    ) -> dict[str, dict[str, list[str]]]:
        """从 v-for 属性构造别名到静态数组字段值的映射。"""

        match = _V_FOR_ATTR_PATTERN.search(attrs_text or "")
        if not match:
            return {}
        expression_match = _V_FOR_EXPRESSION_PATTERN.match(match.group(2))
        if not expression_match:
            return {}
        alias = expression_match.group("tuple_alias") or expression_match.group("alias")
        collection_name = expression_match.group("collection")
        field_values = static_arrays.get(collection_name)
        if not alias or not field_values:
            return {}
        return {alias: field_values}

    @classmethod
    def resolve_scoped_resource_values(
        cls,
        expression: str,
        scoped_resource_values: dict[str, dict[str, list[str]]] | None,
    ) -> list[str] | None:
        """解析 `item.icon` 这类可静态枚举的 v-for 数组字段表达式。"""

        if not scoped_resource_values:
            return None
        match = _MEMBER_EXPRESSION_PATTERN.match(expression or "")
        if not match:
            return None
        alias = match.group("alias")
        field_name = match.group("dot_key")
        if field_name is None:
            field_name = cls.parse_escaped_literal_body(match.group("bracket_key") or "", quote=match.group("quote"))
        field_values = scoped_resource_values.get(alias)
        if not field_values or field_name not in field_values:
            return None
        return field_values[field_name]

    @classmethod
    def parse_array_object_string_fields(cls, array_body: str) -> dict[str, list[str]]:
        """解析数组顶层对象字面量中的字符串字段集合。"""

        result: dict[str, list[str]] = {}
        for object_body in cls.iter_top_level_object_bodies(array_body):
            for field_name, field_value in cls.parse_object_string_fields(object_body).items():
                normalized_value = field_value.strip()
                if not normalized_value:
                    continue
                result.setdefault(field_name, [])
                if normalized_value not in result[field_name]:
                    result[field_name].append(normalized_value)
        return result

    @classmethod
    def iter_top_level_object_bodies(cls, array_body: str) -> Iterable[str]:
        """遍历数组字面量第一层对象正文，忽略字符串和注释中的括号。"""

        index = 0
        while index < len(array_body):
            index = cls.skip_js_space_and_comments(array_body, index)
            if index >= len(array_body):
                break
            if array_body[index] != "{":
                index = cls.skip_to_next_top_level_comma(array_body, index) + 1
                continue
            object_end = cls.find_balanced_end(array_body, index, "{", "}")
            if object_end is None:
                break
            yield array_body[index + 1 : object_end]
            index = object_end + 1

    @classmethod
    def parse_object_string_fields(cls, object_body: str) -> dict[str, str]:
        """解析对象第一层属性中值为字符串字面量的字段。"""

        result: dict[str, str] = {}
        index = 0
        while index < len(object_body):
            index = cls.skip_js_space_and_comments(object_body, index)
            if index >= len(object_body):
                break
            if object_body[index] == ",":
                index += 1
                continue
            parsed_key = cls.parse_object_key(object_body, index)
            if parsed_key is None:
                index = cls.skip_to_next_top_level_comma(object_body, index) + 1
                continue
            field_name, index = parsed_key
            index = cls.skip_js_space_and_comments(object_body, index)
            if index >= len(object_body) or object_body[index] != ":":
                index = cls.skip_to_next_top_level_comma(object_body, index) + 1
                continue
            index = cls.skip_js_space_and_comments(object_body, index + 1)
            parsed_value = cls.parse_string_literal_at(object_body, index)
            if parsed_value is not None:
                field_value, index = parsed_value
                result[field_name] = field_value
            index = cls.skip_to_next_top_level_comma(object_body, index)
            if index < len(object_body) and object_body[index] == ",":
                index += 1
        return result

    @classmethod
    def parse_object_key(cls, source: str, start: int) -> tuple[str, int] | None:
        """解析对象属性名，支持标识符和字符串字面量键。"""

        if start >= len(source):
            return None
        if source[start] in {"'", '"'}:
            return cls.parse_string_literal_at(source, start)
        match = re.match(r"[A-Za-z_$][\w$]*", source[start:])
        if not match:
            return None
        return match.group(0), start + len(match.group(0))

    @classmethod
    def parse_string_literal_at(cls, source: str, start: int) -> tuple[str, int] | None:
        """从指定位置解析 JS 单/双引号字符串字面量。"""

        if start >= len(source) or source[start] not in {"'", '"'}:
            return None
        quote = source[start]
        index = start + 1
        escaped = False
        while index < len(source):
            char = source[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\":
                escaped = True
                index += 1
                continue
            if char == quote:
                raw_body = source[start + 1 : index]
                return cls.parse_escaped_literal_body(raw_body, quote=quote), index + 1
            index += 1
        return None

    @classmethod
    def find_balanced_end(cls, source: str, start: int, open_char: str, close_char: str) -> int | None:
        """查找成对括号的结束位置，忽略字符串和注释内容。"""

        depth = 0
        index = start
        while index < len(source):
            skipped_index = cls.skip_js_literal_or_comment(source, index)
            if skipped_index != index:
                index = skipped_index
                continue
            char = source[index]
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    @classmethod
    def is_top_level_script_position(cls, source: str, position: int) -> bool:
        """判断脚本位置是否处于顶层作用域。"""

        stack: list[str] = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        index = 0
        while index < min(position, len(source)):
            skipped_index = cls.skip_js_literal_or_comment(source, index)
            if skipped_index != index:
                index = skipped_index
                continue
            char = source[index]
            if char in pairs:
                stack.append(pairs[char])
            elif stack and char == stack[-1]:
                stack.pop()
            index += 1
        return not stack

    @classmethod
    def skip_to_next_top_level_comma(cls, source: str, start: int) -> int:
        """跳到当前层级的下一个逗号或字符串末尾。"""

        stack: list[str] = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        index = start
        while index < len(source):
            skipped_index = cls.skip_js_literal_or_comment(source, index)
            if skipped_index != index:
                index = skipped_index
                continue
            char = source[index]
            if char in pairs:
                stack.append(pairs[char])
            elif stack and char == stack[-1]:
                stack.pop()
            elif char == "," and not stack:
                return index
            index += 1
        return len(source)

    @classmethod
    def skip_js_space_and_comments(cls, source: str, start: int) -> int:
        """跳过 JS 空白和注释。"""

        index = start
        while index < len(source):
            if source[index].isspace():
                index += 1
                continue
            skipped_index = cls.skip_js_comment(source, index)
            if skipped_index != index:
                index = skipped_index
                continue
            break
        return index

    @classmethod
    def skip_js_literal_or_comment(cls, source: str, start: int) -> int:
        """如果当前位置是字符串、模板字符串或注释，返回其结束后一位。"""

        comment_end = cls.skip_js_comment(source, start)
        if comment_end != start:
            return comment_end
        if start >= len(source) or source[start] not in {"'", '"', "`"}:
            return start
        quote = source[start]
        index = start + 1
        escaped = False
        while index < len(source):
            char = source[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\":
                escaped = True
                index += 1
                continue
            if char == quote:
                return index + 1
            index += 1
        return len(source)

    @staticmethod
    def skip_js_comment(source: str, start: int) -> int:
        """如果当前位置是 JS 注释，返回注释结束后一位。"""

        if source.startswith("//", start):
            line_end = source.find("\n", start + 2)
            return len(source) if line_end == -1 else line_end + 1
        if source.startswith("/*", start):
            block_end = source.find("*/", start + 2)
            return len(source) if block_end == -1 else block_end + 2
        return start

    @staticmethod
    def _pop_template_scope(
        scope_stack: list[tuple[str, dict[str, dict[str, list[str]]]]],
        closing_tag: str,
    ) -> None:
        """关闭 template 标签时回收对应的 v-for 作用域。"""

        for index in range(len(scope_stack) - 1, -1, -1):
            if scope_stack[index][0] == closing_tag:
                del scope_stack[index:]
                return

    @staticmethod
    def parse_js_string_literal(expression: str) -> str | None:
        """解析 `:name` 中的简单字符串字面量，非字面量返回 None。"""

        value = expression.strip()
        if len(value) < 2 or value[0] not in {"'", '"'} or value[-1] != value[0]:
            return None

        return ResourceReferenceParser.parse_escaped_literal_body(value[1:-1], quote=value[0])

    @staticmethod
    def parse_escaped_literal_body(body: str, quote: str | None = None) -> str:
        """反转义简单 JS 字符串字面量正文。"""

        value = body.replace(r"\\", "\\")
        if quote:
            value = value.replace(f"\\{quote}", quote)
        value = value.replace(r"\'", "'").replace(r'\"', '"')
        return value

    @staticmethod
    def deduplicate_keep_order(values: Iterable[str]) -> list[str]:
        """在保留顺序的前提下去重。"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            result.append(value)
            seen.add(value)
        return result

    @classmethod
    def _collect_schema_slot_nodes(cls, slots_value: Any, names: list[str]) -> None:
        """兼容 schema slots 的声明形态并收集节点资源名。"""

        if isinstance(slots_value, list):
            cls._collect_schema_node_list(slots_value, names)
            return
        if not isinstance(slots_value, dict):
            return
        for slot_value in slots_value.values():
            if isinstance(slot_value, list):
                cls._collect_schema_node_list(slot_value, names)
            elif isinstance(slot_value, dict):
                cls._collect_schema_node_list(slot_value.get("default"), names)

    @classmethod
    def _collect_schema_node_list(cls, slot_nodes: Any, names: list[str]) -> None:
        """递归收集 schema component 节点中的资源名。"""

        if not isinstance(slot_nodes, list):
            return
        for node in slot_nodes:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "component":
                cls._collect_schema_component_node(node, names)
            cls._collect_schema_node_list(node.get("children"), names)

    @classmethod
    def _collect_schema_component_node(cls, node: dict[str, Any], names: list[str]) -> None:
        """从 schema component 节点的 props.name 读取资源组件引用。"""

        component_name = cls._resolve_schema_component_name(str(node.get("component") or ""))
        if not component_name or not cls.needs_name_resource_index(component_name):
            return
        props = node.get("props")
        if not isinstance(props, dict) or "name" not in props:
            return
        raw_name = props.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            names.append(raw_name.strip())

    @staticmethod
    def _resolve_schema_component_name(component_path: str) -> str | None:
        """从 Runtime Kit 或工作空间组件导入路径推断组件名。"""

        normalized_path = component_path.strip()
        if not normalized_path:
            return None
        base_name = posixpath.basename(normalized_path)
        if base_name.endswith(".vue"):
            base_name = base_name[:-4]
        base_name = _RUNTIME_KIT_VERSION_SUFFIX_PATTERN.sub("", base_name)
        return ResourceReferenceParser.normalize_component_name(base_name) if base_name else None
