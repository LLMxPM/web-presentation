"""文件功能：验证 AI 提示中基础字号倍率说明的格式化行为。"""

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.base_font_scale import build_base_font_scale_note


def test_base_font_scale_note_should_describe_tailwind_default_ratio() -> None:
    """已知基础字号应输出相对 Tailwind 默认 16px 的倍率。"""

    note = build_base_font_scale_note("20px")

    assert "当前项目基础字号（base_font_size）：20px" in note
    assert "Tailwind 默认 16px 基准的 1.25 倍" in note
    assert "text-*、p-*、m-*、gap-*、space-*" in note
    assert "arbitrary values 不参与该倍率" in note


def test_base_font_scale_note_should_fallback_to_unknown_ratio() -> None:
    """缺失或非法基础字号应保留字段事实，并回退为未知倍率。"""

    missing_note = build_base_font_scale_note(None)
    invalid_note = build_base_font_scale_note("not-a-size")

    assert "当前项目基础字号（base_font_size）：（未知）" in missing_note
    assert "Tailwind 默认 16px 基准的倍率未知" in missing_note
    assert "当前项目基础字号（base_font_size）：not-a-size" in invalid_note
    assert "Tailwind 默认 16px 基准的倍率未知" in invalid_note


def test_scope_context_should_use_compact_base_font_scale_note() -> None:
    """运行时上下文应使用简化倍率说明，不再注入旧版长篇换算口径。"""

    context_text = build_scope_context_text(
        AgentRuntimeContext(
            scope_type="page",
            workspace_id=1,
            project_id=2,
            page_id=3,
            source="test",
            page_width=1920,
            page_height=1080,
            base_font_size="20px",
        )
    )

    assert "Tailwind 默认 16px 基准的 1.25 倍" in context_text
    assert "text-base 等于该值" not in context_text
    assert "按 Runtime Tailwind 预设比例派生" not in context_text
