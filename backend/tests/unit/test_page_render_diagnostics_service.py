"""文件功能：验证页面渲染诊断脚本覆盖 Runtime 不同页面预览宿主。"""

from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService


def test_render_diagnostics_script_should_support_route_and_standalone_roots() -> None:
    """底部溢出检测应同时支持路由页和单页模块预览的根节点。"""

    script = PageRenderDiagnosticsService._build_bottom_overflow_script()

    assert ".runtime-page-print-source" in script
    assert ".runtime-view-preview-source" in script
