"""文件功能：使用 Chromium 对页面渲染布局检测脚本执行真实 DOM 行为验证。"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.page_render_layout_script import build_page_render_layout_script


def _root_html(width: int, height: int, inner: str) -> str:
    """构造固定画布尺寸的预览根节点页面。"""

    return (
        "<html><head><style>"
        "body{margin:0}"
        f".runtime-page-print-source{{width:{width}px;height:{height}px;"
        "position:relative;overflow:hidden}"
        "</style></head><body>"
        f'<div class="runtime-page-print-source">{inner}</div>'
        "</body></html>"
    )


@pytest.fixture(scope="module")
def browser() -> Any:
    """提供 Chromium 实例，浏览器不可用时跳过整组测试。"""

    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    runner = sync_playwright().start()
    try:
        browser = runner.chromium.launch()
    except Exception as error:  # noqa: BLE001
        runner.stop()
        pytest.skip(f"Chromium 不可用，跳过布局脚本真实渲染测试：{error}")
    yield browser
    runner.stop()


def _evaluate_layout(browser: Any, html: str, width: int, height: int) -> dict[str, object]:
    """在固定 viewport 页面中执行布局检测脚本并返回结果。"""

    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.set_content(html)
        result = page.evaluate(build_page_render_layout_script())
        assert isinstance(result, dict)
        return result
    finally:
        page.close()


def _collect_codes(result: dict[str, object], section: str) -> list[str]:
    """收集指定检测分类下的全部 reason_codes。"""

    return [
        code
        for item in result["layout_analysis"].get(section, [])
        if isinstance(item, dict)
        for code in item.get("reason_codes", [])
        if isinstance(code, str)
    ]


def test_leading_gap_threshold_scales_with_canvas_size(browser: Any) -> None:
    """leading 空白带阈值应随画布短边折算：大画布不再误报、小画布能捕获。"""

    large_html = _root_html(
        3840,
        2160,
        (
            '<div style="width:3000px;height:400px;background:#eee;padding:80px 0 0 0">'
            '<div style="width:2800px;height:100px;background:#ccc">内容</div>'
            "</div>"
        ),
    )
    large = _evaluate_layout(browser, large_html, 3840, 2160)
    large_kinds = [
        item.get("kind")
        for item in large["layout_analysis"]["empty_regions"]
        if isinstance(item, dict)
    ]
    assert "leading_gap" not in large_kinds

    small_html = _root_html(
        1000,
        560,
        (
            '<div style="width:900px;height:160px;background:#eee;padding:40px 0 0 0">'
            '<div style="width:800px;height:100px;background:#ccc">内容</div>'
            "</div>"
        ),
    )
    small = _evaluate_layout(browser, small_html, 1000, 560)
    small_kinds = [
        item.get("kind")
        for item in small["layout_analysis"]["empty_regions"]
        if isinstance(item, dict)
    ]
    assert "leading_gap" in small_kinds


def test_bottom_overflow_ignores_decorative_absolute_background(browser: Any) -> None:
    """底部溢出检测应忽略绝对定位的装饰背景层，只报告真实内容溢出。"""

    decor_html = _root_html(
        1920,
        1080,
        (
            '<div style="position:absolute;left:0;top:0;width:1920px;'
            'height:1200px;background:#123"></div>'
        ),
    )
    decor = _evaluate_layout(browser, decor_html, 1920, 1080)
    decor_codes = [item.get("code") for item in decor["diagnostics"]]
    assert "PAGE_RENDER_BOTTOM_OVERFLOW" not in decor_codes

    mixed_html = _root_html(
        1920,
        1080,
        (
            '<div style="position:absolute;left:0;top:0;width:1920px;'
            'height:1200px;background:#123"></div>'
            '<div style="width:1000px;height:1200px;background:#eee">正文内容</div>'
        ),
    )
    mixed = _evaluate_layout(browser, mixed_html, 1920, 1080)
    mixed_codes = [item.get("code") for item in mixed["diagnostics"]]
    assert "PAGE_RENDER_BOTTOM_OVERFLOW" in mixed_codes


def test_space_between_interior_gap_notes_distribution(browser: Any) -> None:
    """space-between 分布撑开的纵向空隙应在 interior_gap 消息中标注。"""

    html = _root_html(
        1920,
        1080,
        (
            '<div style="display:flex;flex-direction:column;'
            'justify-content:space-between;width:1200px;height:600px;background:#f5f5f5">'
            '<div style="width:400px;height:200px;background:#eee">a</div>'
            '<div style="width:400px;height:200px;background:#eee">b</div>'
            "</div>"
        ),
    )
    result = _evaluate_layout(browser, html, 1920, 1080)
    interior = [
        item
        for item in result["layout_analysis"]["empty_regions"]
        if isinstance(item, dict) and item.get("kind") == "interior_gap"
    ]
    assert interior
    assert "space-between" in str(interior[0].get("message") or "")


def test_sparse_top_aligned_container_is_likely_issue(browser: Any) -> None:
    """稀疏内容贴顶部且底部空白过大时应给出垂直平衡提示。"""

    html = _root_html(
        1920,
        1080,
        (
            '<section style="display:flex;flex-direction:column;'
            'width:900px;height:600px;background:#f5f5f5">'
            '<div style="width:700px;height:120px;background:#eee">主体内容</div>'
            "</section>"
        ),
    )
    result = _evaluate_layout(browser, html, 1920, 1080)
    matches = [
        item
        for item in result["layout_analysis"]["empty_regions"]
        if isinstance(item, dict) and "sparse_top_aligned" in item.get("reason_codes", [])
    ]
    assert matches
    assert matches[0]["attention"] == "likely_issue"
    assert "justify-center" in str(matches[0].get("message") or "")


def test_auto_margin_gap_is_reported_as_sparse_top_alignment(browser: Any) -> None:
    """卡片用 mt-auto 将尾部推到底部时应提示不要制造无规划空白。"""

    html = _root_html(
        1920,
        1080,
        (
            '<section style="display:flex;flex-direction:column;'
            'width:900px;height:600px;background:#f5f5f5">'
            '<div style="width:700px;height:120px;background:#eee">主体内容</div>'
            '<div style="width:700px;height:80px;margin-top:auto;background:#ddd">尾部信息</div>'
            "</section>"
        ),
    )
    result = _evaluate_layout(browser, html, 1920, 1080)
    matches = [
        item
        for item in result["layout_analysis"]["empty_regions"]
        if isinstance(item, dict) and "sparse_top_aligned" in item.get("reason_codes", [])
    ]
    assert matches
    assert matches[0]["attention"] == "likely_issue"
    assert "mt-auto" in str(matches[0].get("message") or "")


def test_rounded_adjacent_items_inside_flex_container_not_touching(browser: Any) -> None:
    """flex 组合容器内圆角子项紧贴应按组合布局豁免贴边报告。"""

    combo_html = _root_html(
        1920,
        1080,
        (
            '<div style="display:flex;width:500px;height:40px">'
            '<div style="width:200px;height:40px;border-radius:12px;background:#eee">a</div>'
            '<div style="width:200px;height:40px;border-radius:12px;background:#ddd">b</div>'
            "</div>"
        ),
    )
    combo = _evaluate_layout(browser, combo_html, 1920, 1080)
    combo_codes = _collect_codes(combo, "spatial_relations")
    assert "independent_surfaces_touching" not in combo_codes

    standalone_html = _root_html(
        1920,
        1080,
        (
            '<div style="width:500px;height:40px">'
            '<span style="display:inline-block;width:200px;height:40px;'
            'border-radius:12px;background:#eee">a</span>'
            '<span style="display:inline-block;width:200px;height:40px;'
            'border-radius:12px;background:#ddd">b</span>'
            "</div>"
        ),
    )
    standalone = _evaluate_layout(browser, standalone_html, 1920, 1080)
    standalone_codes = _collect_codes(standalone, "spatial_relations")
    assert "independent_surfaces_touching" in standalone_codes


def test_short_last_line_requires_plausible_width_or_heading_font(browser: Any) -> None:
    """孤行判定应结合容器宽度与字号：宽容器短句不报、标题级字号仍报。"""

    wide_html = _root_html(
        1920,
        1080,
        '<div style="width:1200px;font-size:16px">第一行内容第一行内容第一行内容<br>孤</div>',
    )
    wide = _evaluate_layout(browser, wide_html, 1920, 1080)
    wide_codes = _collect_codes(wide, "text_layouts")
    assert "short_last_line" not in wide_codes

    heading_html = _root_html(
        1920,
        1080,
        '<div style="width:1200px;font-size:26px">第一行内容第一行内容<br>孤</div>',
    )
    heading = _evaluate_layout(browser, heading_html, 1920, 1080)
    heading_codes = _collect_codes(heading, "text_layouts")
    assert "short_last_line" in heading_codes


def test_centered_short_last_line_message_notes_centering(browser: Any) -> None:
    """居中文本的孤行报告应在消息中标注居中场景。"""

    html = _root_html(
        1920,
        1080,
        (
            '<div style="width:400px;font-size:24px;text-align:center">'
            "第一行内容第一行内容<br>孤</div>"
        ),
    )
    result = _evaluate_layout(browser, html, 1920, 1080)
    layouts = result["layout_analysis"]["text_layouts"]
    short_lines = [
        item
        for item in layouts
        if isinstance(item, dict) and "short_last_line" in item.get("reason_codes", [])
    ]
    assert short_lines
    assert "居中" in str(short_lines[0].get("message") or "")
