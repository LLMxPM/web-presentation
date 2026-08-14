"""文件功能：验证内容助手默认提示词中的视觉素材工作流与资源工具分层。"""

from app.ai.agent_catalog import get_agent_catalog_entry


def test_agent_default_prompt_should_describe_visual_asset_workflow() -> None:
    """默认提示词应说明素材判断、查询、创建和条件生图流程。"""

    catalog = get_agent_catalog_entry("agent-coordinator")

    assert catalog is not None
    prompt = catalog.default_prompt

    assert "视觉素材、资源与页面表达" in prompt
    assert "固定演示画布与网页流式布局" in prompt
    assert "不是可以随着内容自然变高的网页文档" in prompt
    assert "卡片是常用的内容布局" in prompt
    assert "justify-between" in prompt
    assert "render_type" in prompt
    assert "content_editable" in prompt
    assert "approx_aspect_ratio" in prompt
    assert "generate_image" in prompt
    assert "图表、公式、SVG、Draw.io、Mermaid" in prompt
    assert "工具规格与操作手册" in prompt
