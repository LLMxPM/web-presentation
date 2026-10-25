"""文件功能：验证页面布局脚本结果进入 Renderer 回执时保留布局事实与警告。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from render_contracts.schema import ExecutionResult
from wp_renderer.engine.executor import RenderExecutor


def _base_result() -> ExecutionResult:
    """构造不依赖浏览器的页面诊断回执骨架。"""

    return ExecutionResult("r", "a", "w", "e", 1, "page.diagnose", "i", "p", "d", "render-result.v1", {})


@pytest.mark.asyncio
async def test_page_diagnostics_keeps_actionable_layout_and_script_warning() -> None:
    """解包脚本的 layout_analysis，并把显式诊断及关注项写入回执。"""

    layout = {
        "summary": {"attention": "review", "message": "发现 1 项需要关注的视觉检测结果。"},
        "overflows": [
            {"attention": "none", "message": None},
            {"attention": "review", "message": "正文超出容器 12px。"},
        ],
    }
    executor = SimpleNamespace(
        _page=SimpleNamespace(evaluate=AsyncMock(return_value={
            "diagnostics": [{"severity": "warning", "code": "PAGE_SCRIPT_WARNING", "message": "脚本提示。"}],
            "layout_analysis": layout,
        })),
        _base_result=_base_result,
    )

    result = await RenderExecutor._diagnose_page(executor)

    assert result.layout == layout
    assert [item.code for item in result.diagnostics] == [
        "PAGE_SCRIPT_WARNING", "PAGE_RENDER_BOTTOM_OVERFLOW", "PAGE_RENDER_LAYOUT_WARNING",
    ]
    assert all(item.severity == "warning" for item in result.diagnostics)


@pytest.mark.asyncio
async def test_page_diagnostics_does_not_warn_for_neutral_overflow() -> None:
    """允许可见溢出的装饰项属于布局事实，不应冒充警告。"""

    layout = {
        "summary": {"attention": "none", "message": "未发现需要关注的视觉检测结果。"},
        "overflows": [{"attention": "none", "message": None}],
    }
    executor = SimpleNamespace(
        _page=SimpleNamespace(evaluate=AsyncMock(return_value={"diagnostics": [], "layout_analysis": layout})),
        _base_result=_base_result,
    )

    result = await RenderExecutor._diagnose_page(executor)

    assert result.layout == layout
    assert result.diagnostics == []
