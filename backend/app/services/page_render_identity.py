"""文件功能：按 Runtime 相同规则复算路由页码目录，作为静态截图身份中的路由可达部分。

Runtime 侧实现在 runtime/src/core/utils/page-numbers.ts，两侧共用
tests/fixtures/route-page-number-cases.json 对拍。本模块只做纯计算，不访问数据库，
以便在截图、诊断、代码检查与列表页批量刷新等入口复用同一份投影。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 页面源码读取路由信息只能经过这些 @runtime-kit 公开能力。
ROUTE_READING_KIT_CAPABILITIES = frozenset({
    "useCurrentPage.v1",
    "useRouteCatalog.v1",
    "usePageNavigation.v1",
})
# vue-router 的原生能力（useRoute/useRouter）同样能读到当前路由与 meta。
ROUTE_READING_BARE_IMPORTS = frozenset({"vue-router"})

_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests/fixtures/route-page-number-cases.json"


@dataclass(frozen=True, slots=True)
class RouteCatalogProjection:
    """路由目录投影：目录项、最大页码、最小页码。"""

    catalog: tuple[dict[str, object], ...]
    total_pages: int
    min_page_number: int

    def to_identity_payload(self) -> dict[str, object]:
        """输出稳定、可哈希的身份载荷。"""

        return {
            "catalog": [dict(item) for item in self.catalog],
            "totalPages": self.total_pages,
            "minPageNumber": self.min_page_number,
        }


def routes_need_screenshot_identity(
    *,
    kit_capability_names: frozenset[str] | set[str] | tuple[str, ...],
    bare_import_specifiers: frozenset[str] | set[str] | tuple[str, ...],
) -> bool:
    """判断页面闭包是否读取路由上下文；不读取时路由目录不应进入截图身份。"""

    normalized_kit = {str(name or "").strip() for name in kit_capability_names}
    normalized_bare = {str(name or "").strip() for name in bare_import_specifiers}
    return bool(normalized_kit & ROUTE_READING_KIT_CAPABILITIES) or bool(
        normalized_bare & ROUTE_READING_BARE_IMPORTS
    )


def project_route_catalog(runtime_routes: dict[str, object] | None) -> RouteCatalogProjection:
    """把运行时路由配置投影为页面可读取的页码目录。

    只保留静态截图中真正会变像素的字段：path、title、order、pageNumber、
    parentPath、hidden。component 只决定 artifact 模块白名单；speakerNotes 供演讲台
    与 PPTX 导出；transition/advance/playback 在捕获上下文被禁用。
    """

    source = runtime_routes or {}
    routes = source.get("routes")
    catalog: list[dict[str, object]] = []

    for node in _assign_page_numbers(routes if isinstance(routes, list) else []):
        children = node.get("children")
        if isinstance(children, list) and children:
            parent_path = f"/{str(node.get('route') or '').strip()}"
            for child in children:
                catalog.append(_build_catalog_item(_join_path(parent_path, child), child, parent_path))
            continue
        catalog.append(_build_catalog_item(_join_path("", node), node, None))

    page_numbers = [int(item["pageNumber"]) for item in catalog if isinstance(item.get("pageNumber"), int)]
    return RouteCatalogProjection(
        catalog=tuple(catalog),
        total_pages=max(page_numbers) if page_numbers else 0,
        min_page_number=min(page_numbers) if page_numbers else 0,
    )


def _assign_page_numbers(routes: list[object]) -> list[dict[str, object]]:
    """复刻 Runtime assignPageNumbers：顶层按 order 稳定排序，分组自身不占页码。"""

    ordered = [item for item in (_normalize_route_node(node) for node in routes) if item is not None]
    ordered.sort(key=_route_sort_key)

    current_page_number = 1
    for node in ordered:
        children = node.get("children")
        meta = node["meta"]
        has_children = isinstance(children, list) and bool(children)

        if not has_children and not bool(meta.get("hidden")):
            meta["pageNumber"] = current_page_number
            current_page_number += 1

        if has_children and isinstance(children, list):
            # Python sort 是稳定排序，与 JS 的稳定排序语义一致。
            children.sort(key=_route_sort_key)
            for child in children:
                child_meta = child["meta"]
                if not bool(child_meta.get("hidden")):
                    child_meta["pageNumber"] = current_page_number
                    current_page_number += 1

    return ordered


def _normalize_route_node(node: object) -> dict[str, object] | None:
    """只保留页码分配与目录投影需要的字段，并统一 meta 形状。"""

    if not isinstance(node, dict):
        return None
    raw_meta = node.get("meta")
    meta_source = raw_meta if isinstance(raw_meta, dict) else {}
    meta: dict[str, object] = {
        "title": meta_source.get("title") if isinstance(meta_source.get("title"), str) else "",
        "order": _coerce_order(meta_source.get("order")),
        "hidden": bool(meta_source.get("hidden")),
    }
    normalized: dict[str, object] = {"route": str(node.get("route") or "").strip(), "meta": meta}
    children = node.get("children")
    if isinstance(children, list):
        normalized["children"] = [
            child for child in (_normalize_route_node(item) for item in children) if child is not None
        ]
    return normalized


def _coerce_order(value: object) -> float:
    """把 order 归一为数值；缺失或非法值按 0 处理，与 Runtime 的 (order || 0) 一致。"""

    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) if value == value else 0.0
    return 0.0


def _route_sort_key(node: dict[str, object]) -> float:
    """排序键只取 meta.order，保持与 Runtime 相同的稳定排序行为。"""

    meta = node.get("meta")
    return float(meta.get("order") or 0) if isinstance(meta, dict) else 0.0


def _join_path(parent_path: str, node: dict[str, object]) -> str:
    """拼接目录项完整路径，口径与 route-generator.getAllRouteInfos 一致。"""

    segment = str(node.get("route") or "").strip()
    if not segment:
        return parent_path or "/"
    if not parent_path:
        return f"/{segment}"
    return f"{parent_path}/{segment}"


def _build_catalog_item(
    path: str,
    node: dict[str, object],
    parent_path: str | None,
) -> dict[str, object]:
    """构造单条目录项，字段与 Runtime buildCatalogItem 逐项对应。"""

    meta = node["meta"] if isinstance(node.get("meta"), dict) else {}
    item: dict[str, object] = {
        "path": path,
        "title": str(meta.get("title") or ""),
        "order": _order_as_json_value(meta.get("order")),
        "hidden": bool(meta.get("hidden")),
    }
    page_number = meta.get("pageNumber")
    if isinstance(page_number, int):
        item["pageNumber"] = page_number
    if parent_path:
        item["parentPath"] = parent_path
    return item


def _order_as_json_value(value: object) -> int | float:
    """把内部 float order 还原为与 JSON 输入一致的整型或浮点值。"""

    numeric = float(value or 0)
    return int(numeric) if numeric.is_integer() else numeric


def load_contract_fixture_cases() -> list[dict[str, Any]]:
    """读取跨端对拍 fixture 用例，供 pytest 与 vitest 共用。"""

    with _FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    cases = payload.get("cases")
    return list(cases) if isinstance(cases, list) else []
