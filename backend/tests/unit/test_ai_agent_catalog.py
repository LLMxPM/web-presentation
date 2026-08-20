"""文件功能：验证内容助手默认提示词与页面、组件代码规范的职责边界。"""

from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.code_standards import get_default_code_standard


def test_agent_default_prompt_should_keep_content_baseline_and_query_guidance() -> None:
    """默认提示词应保留内容原则、视觉表达判断和通用源码基线。"""

    catalog = get_agent_catalog_entry("agent-coordinator")

    assert catalog is not None
    prompt = catalog.default_prompt

    assert "演示内容与表达原则" in prompt
    assert "资深前端工程师、界面设计实现专家和内容结构顾问" in prompt
    assert "尤其擅长使用 Vue 3、TypeScript、Tailwind CSS 和平台 Runtime Kit" in prompt
    assert "营销落地页、产品官网、后台管理、数据看板、工作台、表单流程" in prompt
    assert "优先使用 Tailwind CSS 组合语义化工具类" in prompt
    assert "保持 Tailwind class 为源码中的静态完整字符串" in prompt
    assert "空态、加载态和错误态" in prompt
    assert "事实、数字、引用和来源不得凭空补全" in prompt
    assert "处理视觉内容时，先判断当前信息最适合用文字、表格、图表、示意图还是图片表达" in prompt
    assert "需要素材时优先查询工作空间资源，不满足再按可用能力创建或生成" in prompt
    assert "主体内容区、内容面板和稀疏卡片默认应在自身可用高度内上下平衡" in prompt
    assert "sparse_top_aligned" in prompt
    assert "不得仅因为使用 `flex-1`、固定高度或 `mt-auto`" in prompt
    assert "每次用户发起新一轮 Run 时" in prompt
    assert "通用源码与 Runtime 基线" in prompt
    assert "页面或组件源码任务开始前，先调用 get_code_standards" not in prompt
    assert "完整、可运行的 Vue SFC 文件源码" in prompt
    assert "禁止使用 Node API" in prompt
    assert "只能使用工具返回的版本化 Runtime Kit 能力" in prompt
    assert "页面和组件源码应使用 Runtime、主题、字体、资源和 Icon 的公开契约" in prompt
    assert "页面布局、组件契约以及页面或组件专属的主题、字体、资源和 Icon 细则" in prompt
    assert "`scope_type`：本轮默认焦点类型" in prompt
    assert "`work_scope_mode`：项目工作集模式" in prompt
    assert "`allowed_project_ids`：项目工作集的真实 ID 列表" in prompt
    assert "`allowed_projects`：项目工作集的 `{id, name}` 摘要" in prompt
    assert "`canvas.page_width`、`canvas.page_height`、`canvas.base_font_size`" in prompt
    assert "`focus_version`" not in prompt
    assert "DataTable" in prompt
    assert "涉及二维数据或表格时" not in prompt
    assert "页面和组件创建、源码更新，以及组件 `preview_schema` 或 `component_type` 修改" in prompt
    assert "页面或组件源码创建、写入、修改前，必须先调用 `get_code_standards`" in prompt
    assert "读取 layout_analysis" not in prompt
    assert "Runtime 主题语义颜色键包括" not in prompt

    assert "固定演示画布与网页流式布局" not in prompt
    assert "不是可以随着内容自然变高的网页文档" not in prompt

    page_standard = get_default_code_standard("page")
    component_standard = get_default_code_standard("component")
    assert "固定尺寸的演示画布" in page_standard
    assert "形成整页构图后才实现具体元素" in page_standard
    assert "网页文档式生成顺序" in page_standard
    assert "空间规划不等于把画布机械切成互不重叠的矩形" in page_standard
    assert "非对称构图" in page_standard
    assert "复杂性应来自有意的视觉构图" in page_standard
    assert "Runtime 主题语义颜色键包括" in page_standard
    assert "render_type" in page_standard
    assert "PAGE_RENDER_BOTTOM_OVERFLOW" in page_standard
    assert "empty_regions" in page_standard
    assert "固定画布应先划分标题区、主体区和辅助区" in page_standard
    assert "禁止把 `grid/flex-1`、固定高度、顶部排列和 `mt-auto` 组合成默认卡片结构" in page_standard
    assert "对 `flex-col`，垂直方向由 `justify-*` 控制" in page_standard
    assert "sparse_top_aligned" in page_standard
    assert "base_font_size / 16" in page_standard
    assert "useAssetSrc(() => props.imageName)" in page_standard
    assert "ThemeLogo" in page_standard
    assert "preview_schema" in component_standard
    assert "Runtime 主题语义颜色键包括" in component_standard
    assert "Icon 和 Asset* 的 name" in component_standard
    assert "defineProps`/`defineEmits" in component_standard
    assert "2～3 个高质量 presets" in component_standard
    assert "开始创建页面时，先查询并复用已有的页面组件" in catalog.default_prompt
    assert "如果发现同一职责的指标卡、引用卡、图表或表格模块会跨页重复" in catalog.default_prompt
    assert "开始创建页面时，先查询并复用已有的页面组件" in page_standard
    assert "变化可以用稳定的 props 或 slots 表达，再沉淀为内容组件" in page_standard
