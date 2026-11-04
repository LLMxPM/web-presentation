"""文件功能：判定页面源码闭包是否能读到路由上下文，作为截图身份里 page_metadata 的开关。

截图身份不包含路由页码目录：页码、总页数和目录文字由 Runtime 在捕获时按 artifact 的路由
配置单点解析（runtime/src/core/utils/page-numbers.ts），Backend 不复算第二套。因此重排、
新增、删除或隐藏路由都不会使已有截图过期。本模块只做纯判定，不访问数据库。
"""

from __future__ import annotations

# 页面源码读取路由信息只能经过这些 @runtime-kit 公开能力。
ROUTE_READING_KIT_CAPABILITIES = frozenset({
    "useCurrentPage.v1",
    "useRouteCatalog.v1",
    "usePageNavigation.v1",
})
# vue-router 的原生能力（useRoute/useRouter）同样能读到当前路由与 meta。
ROUTE_READING_BARE_IMPORTS = frozenset({"vue-router"})


def routes_need_screenshot_identity(
    *,
    kit_capability_names: frozenset[str] | set[str] | tuple[str, ...],
    bare_import_specifiers: frozenset[str] | set[str] | tuple[str, ...],
) -> bool:
    """判断页面闭包能否读到自身路由 meta；只有这样的页面才把 page_metadata 计入截图身份。"""

    normalized_kit = {str(name or "").strip() for name in kit_capability_names}
    normalized_bare = {str(name or "").strip() for name in bare_import_specifiers}
    return bool(normalized_kit & ROUTE_READING_KIT_CAPABILITIES) or bool(
        normalized_bare & ROUTE_READING_BARE_IMPORTS
    )
