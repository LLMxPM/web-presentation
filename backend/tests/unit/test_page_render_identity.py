"""文件功能：验证 Backend 路由页码目录投影与 Runtime 实现逐字节一致。"""

from __future__ import annotations

import pytest

from app.services.page_render_identity import (
    load_contract_fixture_cases,
    project_route_catalog,
    routes_need_screenshot_identity,
)


def _case_id(case: dict) -> str:
    """用 fixture 中的用例名生成 pytest id。"""

    return str(case.get("name") or "unnamed")


@pytest.mark.parametrize("case", load_contract_fixture_cases(), ids=_case_id)
def test_projection_should_match_runtime_fixture(case: dict) -> None:
    """同一份 fixture 下，Backend 投影必须与 Runtime 完全一致。"""

    projection = project_route_catalog({"routes": case["routes"]})
    assert projection.to_identity_payload() == case["expected"]


def test_projection_should_not_mutate_input() -> None:
    """投影不得改写调用方传入的运行时路由配置。"""

    routes = {
        "transitionDefaults": {"effect": "fade", "durationMs": 400},
        "playback": {"autoStart": False, "loop": False},
        "routes": [
            {"route": "b", "meta": {"title": "B", "order": 1, "hidden": False}},
            {"route": "a", "meta": {"title": "A", "order": 0, "hidden": False}},
        ],
    }
    snapshot = {"routes": [dict(item) for item in routes["routes"]]}
    project_route_catalog(routes)
    assert routes["routes"] == snapshot["routes"]
    assert routes["transitionDefaults"] == {"effect": "fade", "durationMs": 400}


def test_projection_should_ignore_playback_and_display_fields() -> None:
    """放映参数、组件路径、备注与画布展示字段都不进入阴影身份。"""

    base = {"routes": [{"route": "a", "meta": {"title": "A", "order": 0, "hidden": False}}]}
    noisy = {
        "transitionDefaults": {"effect": "push", "durationMs": 900},
        "playback": {"autoStart": True, "loop": True},
        "routes": [
            {
                "route": "a",
                "component": "@/views/a.vue",
                "meta": {
                    "title": "A",
                    "order": 0,
                    "hidden": False,
                    "speakerNotes": "备注",
                    "transition": {"effect": "fade", "durationMs": 600},
                    "advance": {"mode": "timer", "delayMs": 1000, "mediaTimeoutMs": 60000, "timelineTimeoutMs": 300000},
                },
            }
        ],
    }
    assert project_route_catalog(base) == project_route_catalog(noisy)


def test_projection_should_handle_none_and_empty() -> None:
    """空配置与 None 输入返回稳定空投影。"""

    empty = project_route_catalog(None)
    assert empty.catalog == ()
    assert empty.total_pages == 0
    assert empty.min_page_number == 0
    assert project_route_catalog({}) == empty


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
    """只有引用路由能力或 vue-router 的页面才需要把目录放进截图身份。"""

    assert (
        routes_need_screenshot_identity(
            kit_capability_names=kit_capabilities,
            bare_import_specifiers=bare_imports,
        )
        is expected
    )
