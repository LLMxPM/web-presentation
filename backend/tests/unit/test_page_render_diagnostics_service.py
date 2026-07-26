"""文件功能：验证页面渲染诊断脚本及 BrowserContext 清理规则。"""

import pytest

from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService
from app.services.page_render_layout_script import build_page_render_layout_script


def test_render_diagnostics_script_should_support_route_and_standalone_roots() -> None:
    """底部溢出检测应同时支持路由页和单页模块预览的根节点。"""

    script = build_page_render_layout_script()

    assert ".runtime-page-print-source" in script
    assert ".runtime-view-preview-source" in script
    assert "schema_version: 2" in script
    assert "text_layouts" in script
    assert "item_groups" in script
    assert "overflows" in script
    assert "spatial_relations" in script
    assert "style.flexWrap === 'nowrap'" in script
    assert "single_item_last_row" in script
    assert "pill_like" in script
    assert "independent_surfaces_touching" in script
    assert "painted_surface_overlap" in script
    assert "resolveIntentLikelihood" in script
    assert "describeLayoutTarget" in script
    assert "describeCompactTarget" in script
    assert "target: describeCompactTarget(element)" in script
    assert "describeCompactTarget(item.element)" in script
    assert "data-page-visual-node-id" in script
    assert "repeat_index" in script
    assert "text_layouts: 50" in script
    assert "item_groups: 20" in script
    assert "overflows: 30" in script
    assert "spatial_relations: 30" in script
    assert "nowrapOverflowPx <= tolerancePx" in script
    assert "originalClientWidth" in script
    assert "originalOffsetWidth" in script
    assert "element.style.setProperty('flex', '0 0 auto', 'important')" in script
    assert "element.scrollWidth - originalClientWidth" in script
    assert "element.removeAttribute('style')" in script
    assert "element.setAttribute('style', previousStyleAttribute)" in script
    assert "if (stability === 'boundary')" in script
    assert "result.text_truncated = true" in script
    assert "line_height_px" not in script
    assert "Range" in script


def test_render_diagnostics_should_normalize_layout_analysis() -> None:
    """真实渲染结果应规范化为 v2 四类视觉检测契约。"""

    service = PageRenderDiagnosticsService()
    result = service._normalize_render_result(
        {
            "diagnostics": [],
            "layout_analysis": {
                "schema_version": 2,
                "summary": {
                    "attention": "likely_issue",
                    "message": "发现 4 项需要关注的视觉检测结果。",
                    "totals": {
                        "text_layouts": 2,
                        "item_groups": 1,
                        "overflows": 1,
                        "spatial_relations": 1,
                    },
                    "returned": {},
                    "truncated": True,
                },
                "text_layouts": [
                    {
                        "target": {"label": "h2.title"},
                        "text": "企业智能化转型趋势",
                        "line_count": 2,
                        "stability": "stable",
                        "attention": "none",
                    }
                ],
                "item_groups": [
                    {
                        "target": {"label": "div.flex.flex-wrap"},
                        "item_count": 5,
                        "row_count": 2,
                        "last_row_count": 1,
                        "item_pattern": "pill_like",
                        "attention": "review",
                    }
                ],
                "overflows": [
                    {
                        "scope": "container",
                        "target": {"label": "span.clipped"},
                        "directions": ["right"],
                        "clipping": "hidden",
                        "attention": "likely_issue",
                    }
                ],
                "spatial_relations": [
                    {
                        "relation": "touching",
                        "distance_px": 0,
                        "attention": "review",
                    }
                ],
            },
        }
    )

    assert result["diagnostics"] == []
    analysis = result["layout_analysis"]
    assert analysis["schema_version"] == 2
    assert analysis["summary"]["attention"] == "likely_issue"
    assert analysis["summary"]["totals"]["text_layouts"] == 2
    assert analysis["summary"]["returned"]["text_layouts"] == 1
    assert analysis["summary"]["truncated"] is True
    assert analysis["text_layouts"][0]["line_count"] == 2
    assert analysis["item_groups"][0]["last_row_count"] == 1
    assert analysis["overflows"][0]["clipping"] == "hidden"
    assert analysis["spatial_relations"][0]["relation"] == "touching"


def test_diagnostics_should_close_context_when_new_page_fails() -> None:
    """诊断页创建失败也必须关闭独立 Context，避免污染复用浏览器。"""

    class FakeContext:
        """记录 Context 的关闭状态。"""

        def __init__(self) -> None:
            self.closed = False

        def new_page(self) -> object:
            """模拟 Playwright 在创建页面时失败。"""

            raise RuntimeError("browser disconnected")

        def close(self) -> None:
            """记录资源清理。"""

            self.closed = True

    class FakeBrowser:
        """提供测试用 Context 并记录创建参数。"""

        def __init__(self) -> None:
            self.context = FakeContext()
            self.context_options: dict[str, object] = {}

        def new_context(self, **kwargs: object) -> FakeContext:
            """记录入参并返回测试 Context。"""

            self.context_options = kwargs
            return self.context

    browser = FakeBrowser()
    service = PageRenderDiagnosticsService()

    with pytest.raises(RuntimeError, match="disconnected"):
        service._diagnose_preview_with_browser(
            browser,
            service._build_browser_target("http://127.0.0.1:7373/__preview"),
            CaptureViewport(width=1280, height=720),
            timeout_ms=1,
            visual_ready_timeout_ms=1,
        )
    assert browser.context.closed
    # 布局测量必须在 reduced-motion 下执行，避免入场动画位移干扰结果。
    assert browser.context_options.get("reduced_motion") == "reduce"
