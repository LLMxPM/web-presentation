"""文件功能：验证页面渲染诊断无法完成时不会被判为通过。"""

from app.services.code_check_service import _render_stage_status
from app.services.page_render_diagnostics_service import PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE


def test_missing_render_root_is_unavailable_even_when_renderer_returns_ok() -> None:
    """脚本找不到渲染根节点时，没有视觉检查结果，写入门禁应阻断。"""

    diagnostics = [{
        "severity": "warning",
        "code": PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE,
        "message": "未找到页面渲染根节点，无法分析布局。",
    }]

    assert _render_stage_status({"status": "ok"}, diagnostics) == "unavailable"
