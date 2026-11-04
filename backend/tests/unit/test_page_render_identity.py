"""文件功能：验证截图身份的路由可达性判定，确认只有能读到路由 meta 的页面才计入 page_metadata。"""

from __future__ import annotations

import pytest

from app.services.page_render_identity import routes_need_screenshot_identity


@pytest.mark.parametrize(
    ("kit_capabilities", "bare_imports", "expected"),
    [
        ({"useRouteCatalog.v1"}, set(), True),
        ({"useCurrentPage.v1"}, set(), True),
        ({"usePageNavigation.v1"}, set(), True),
        (set(), {"vue-router"}, True),
        ({"useTheme.v1"}, set(), False),
        ({"useAssetSrc.v1"}, {"vue"}, False),
        (set(), set(), False),
    ],
)
def test_route_reading_gate_should_detect_route_capabilities(
    kit_capabilities: set[str],
    bare_imports: set[str],
    expected: bool,
) -> None:
    """只有引用路由能力或 vue-router 的闭包才读得到自身 meta，其余页面不因路由变化而判旧。"""

    assert (
        routes_need_screenshot_identity(
            kit_capability_names=kit_capabilities,
            bare_import_specifiers=bare_imports,
        )
        is expected
    )


def test_route_reading_gate_should_tolerate_blank_and_padded_names() -> None:
    """能力名允许空白与缺项，避免调用方拼出的集合把读者判成非读者。"""

    assert routes_need_screenshot_identity(
        kit_capability_names={"  useCurrentPage.v1 ", ""},
        bare_import_specifiers=tuple(),
    ) is True
