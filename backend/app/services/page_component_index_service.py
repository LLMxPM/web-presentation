"""文件功能：解析 Vue 页面源码并维护版本级组件索引，支持组件统计与资源名统计。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PageFileType
from app.models.page_component_resource import PageVersionComponentResource
from app.models.page import Page
from app.models.page_version import PageVersion
from app.repositories.page_component_index_repository import PageComponentIndexRepository
from app.services.resource_reference_parser import ResourceReferenceParser

_TEMPLATE_BLOCK_PATTERN = re.compile(r"<template\b[^>]*>(.*?)</template>", flags=re.IGNORECASE | re.DOTALL)
_TEMPLATE_TAG_PATTERN = re.compile(r"<\s*(?!/)([A-Za-z][\w.-]*)\b([^>]*)>", flags=re.DOTALL)
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", flags=re.DOTALL)
_STATIC_NAME_ATTR_PATTERN = re.compile(r"""(?:^|\s)name\s*=\s*(["'])(.*?)\1""", flags=re.IGNORECASE | re.DOTALL)
_STATIC_NAME_ATTR_UNQUOTED_PATTERN = re.compile(r"""(?:^|\s)name\s*=\s*([^\s"'=<>`]+)""", flags=re.IGNORECASE)
_BOUND_NAME_ATTR_PATTERN = re.compile(
    r"""(?:^|\s)(?::name|v-bind:name)\s*=\s*(["'])(.*?)\1""",
    flags=re.IGNORECASE | re.DOTALL,
)

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


class PageComponentIndexService:
    """页面组件索引服务，负责在页面保存时解析并写入版本级索引。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PageComponentIndexRepository(session)

    async def rebuild_page_version_index(
        self,
        *,
        page: Page,
        page_version: PageVersion,
        page_content: str,
        file_type: PageFileType | str,
    ) -> None:
        """按页面版本全量重建组件索引，非 Vue 文件会清空该版本索引。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else file_type
        if normalized_file_type != PageFileType.VUE.value:
            await self.repository.replace_for_version(
                project_id=page.project_id,
                page_id=page.id,
                page_version_id=page_version.id,
                component_names=[],
                resource_names=[],
            )
            return

        component_names, resource_names = self._collect_component_index(page_content)
        await self.repository.replace_for_version(
            project_id=page.project_id,
            page_id=page.id,
            page_version_id=page_version.id,
            component_names=component_names,
            resource_names=resource_names,
        )

    async def list_component_names_by_version(self, page_version_id: int) -> list[str]:
        """读取指定版本的组件名称集合，按名称升序返回。"""

        usage_items = await self.repository.list_component_usages_by_version(page_version_id)
        return [item.component_name for item in usage_items]

    async def list_resource_items_by_version(self, page_version_id: int) -> list[PageVersionComponentResource]:
        """读取指定版本的组件资源集合，按组件名和资源名升序返回。"""

        return await self.repository.list_component_resources_by_version(page_version_id)

    @classmethod
    def _collect_component_index(cls, page_content: str) -> tuple[set[str], set[tuple[str, str]]]:
        """从 Vue 源码收集组件集合和资源名参数集合。"""

        return ResourceReferenceParser.collect_vue_component_index(page_content)

    @classmethod
    def _extract_template_content(cls, page_content: str) -> str:
        """提取 Vue 文件中所有 template 块内容；无 template 时返回空串。"""

        return ResourceReferenceParser.extract_template_content(page_content)

    @staticmethod
    def _is_component_tag(tag_name: str) -> bool:
        """判断标签是否应纳入“组件使用”统计。"""

        return ResourceReferenceParser.is_component_tag(tag_name)

    @staticmethod
    def _normalize_component_name(tag_name: str) -> str:
        """统一组件名展示格式，便于跨页面聚合统计。"""

        return ResourceReferenceParser.normalize_component_name(tag_name)

    @staticmethod
    def _needs_name_resource_index(component_name: str) -> bool:
        """判断组件是否需要提取 `name` 参数。"""

        return ResourceReferenceParser.needs_name_resource_index(component_name)

    @classmethod
    def _extract_name_resources(cls, attrs_text: str) -> list[str]:
        """从组件属性串提取 name 参数，静态值可直接落库，动态值统一标记。"""

        return ResourceReferenceParser.extract_name_resources(attrs_text)

    @staticmethod
    def _parse_js_string_literal(expression: str) -> str | None:
        """解析 `:name` 里的简单字符串字面量，非字面量返回 None。"""

        return ResourceReferenceParser.parse_js_string_literal(expression)

    @staticmethod
    def _deduplicate_keep_order(values: Iterable[str]) -> list[str]:
        """在保留顺序的前提下去重，避免单标签重复属性导致重复计数。"""

        return ResourceReferenceParser.deduplicate_keep_order(values)
