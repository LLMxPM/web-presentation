"""文件功能：定义页面与组件代码规范的系统默认内容，并提供规范类型解析。"""

from __future__ import annotations

from typing import Literal

from app.core.exceptions import AppException

CodeStandardType = Literal["page", "component"]


PAGE_CODE_STANDARD = """
## 页面布局与内容规范

- 页面是固定尺寸的演示画布，本质上是需要整体构图的二维空间，不是从上到下自然增长的网页文档；先读取项目 configuration，遵循真实画布尺寸、基础字号、安全边距和样式基线。
- 编写模板代码前，必须把整张页面或页面组件提供的 slot 区域视为一个完整、有明确边界的空间：先确定主要信息、视觉焦点、阅读动线、视觉重心、对齐关系和留白，再规划标题、主体、资源与辅助信息的空间锚点和尺寸关系，形成整页构图后才实现具体元素。
- 禁止采用“先放标题，再向下依次追加段落、卡片、图片和页脚”的网页文档式生成顺序，也不要让后加入的元素依赖前序内容的自然高度决定整页结构。Flex、Grid、绝对定位和分层布局都用于实现已经规划好的空间关系，不用于让内容自行撑开画布。
- 空间规划不等于把画布机械切成互不重叠的矩形。可以根据表达需要使用非对称构图、自由定位、跨区排版、元素重叠、分层背景、旋转和装饰性出血；装饰元素可以有意超出画布并由画布裁切，但关键信息必须完整、清晰、可读。复杂性应来自有意的视觉构图，而不是无规划的纵向堆叠。
- 页面应围绕一个主要信息组织内容，优先保证叙事顺序、标题结论性、信息层级、数据可读性和跨页一致性，不为填满画布堆砌无关内容。
- 页面根节点使用已发布的页面组件或 DefaultContainer；优先复用项目建议组件，其次查询工作空间内已发布页面组件，最后才直接使用 DefaultContainer。直接使用 DefaultContainer 前，先通过 Runtime Kit 查询真实的版本化 import_path。
- 主要内容、分栏、卡片、图表、图片区和公式区应具有可判断的空间锚点、宽高上下文、flex/grid 约束、overflow 策略和留白；不要求每个元素都位于独立矩形内，但依赖 h-full 的子元素必须具备明确的父级高度。
- 内容无法在既定构图中成立时，应按优先级精简信息、改变表现形式、重新构图、调整分区或拆分页面；不通过 100vh、100vw、页面滚动、内容自然撑高、transform: scale 或 zoom 逃避布局约束。
- 生成或大幅改写页面前，先在内部形成画布构图方案，检查画布方向、安全边距、视觉焦点、阅读动线、空间锚点、层级、资源占位、留白、文字容量、固定高度和潜在溢出；该方案用于指导代码生成，不需要暂停等待用户确认，也不作为默认回复输出。
- `base_font_size` 替代 Tailwind 默认 16px 基准；`text-*`、`p-*`、`m-*`、`gap-*`、`space-*` 等语义字号和间距按 `base_font_size / 16` 理解整体倍率。直接写入的 px、rem 和 Tailwind arbitrary values 不参与该倍率。

## 页面布局诊断判读

- 页面校验结果以精简文本返回：优先处理其中的 code、message、定位和布局类别计数；需要受控布局数值时用相同目标和候选参数调用 `validate_entity(detail=true)`。不要依赖模型侧回传完整 `layout_analysis` 或浏览器几何清单。
- `PAGE_RENDER_BOTTOM_OVERFLOW` 表示固定画布底部可能裁切，应压缩内容、调整容器高度或拆分页面。`severity=warning` 不代表写入失败，但应处理会影响可读性或布局完整性的警告。
- 正常正文多行、正常 `flex-wrap` 分排、滚动容器和有意的装饰出血不应机械修复；越界检测已排除 `aria-hidden`、`pointer-events:none` 和绝对定位的背景/图片装饰层。优先处理真实画布越界、内容裁切、不可读重叠和意外紧贴。
- `touching`/`tight` 在 flex/grid 组合容器内的圆角子项紧贴通常属于组合布局，不应单独修复；独立卡片或需要间距的设计仍需处理。`empty_regions` 描述内容带之间、容器内部、画布边缘的几何空白；封面和章节页的刻意留白、左右对称的居中留白不应机械压缩，正文中的明显空白带应结合安全边距、栅格和容器尺寸判断。
- `interior_gap` 常由 `mt-auto`、固定高度容器或较大 margin 造成，应结合内容判断是否脱节；由 `space-between`、`space-around` 或 `center` 分布产生的间隙通常是布局意图。`short_last_line`、`single_word_last_line` 已过滤窄容器和居中文本场景，剩余孤行/孤词更值得关注。
- `geometry_reliability=approximate` 表示旋转或 `clip-path` 仅按外接矩形近似判断，需要结合视觉语义复核。

## 页面主题、字体、资源与 Icon 规范

- Runtime 主题语义颜色键包括 primary、secondary、invert、background、background-subtle、background-invert、border、border-subtle、link、link-hover、link-visited 和 accent1 至 accent6；页面只能使用这些 Runtime 主题键、版本化 Runtime Kit 能力和工具返回的工作空间资源，不得猜测其它语义颜色键或硬编码品牌资源。
- background-subtle 是 Runtime 提供的语义背景槽位，不是主题写入 Schema 中的 palette.background.subtle 字段。
- 页面可以使用 Runtime safelist 与源码扫描支持的常用 Tailwind 工具类；未列出的语义 Token 不得自行引入。Tailwind 类必须以完整静态字符串出现在模板、脚本常量或顶层枚举映射中；不要拼接 text-${tone}、from-${color} 或运行时生成 import。Tailwind arbitrary values 可以使用，但必须以源码中的静态完整类出现。
- 字体语义类包括 font-heading、font-body 和 font-code；需要非主题字体时，先查询工作空间字体并使用 Runtime Kit 的 useAssetFontFamily。直接写 CSS 时优先使用 Runtime 桥接变量和 useTheme 提供的公开变量，不要猜测未公开的 CSS 变量。主题 Logo 优先使用 Runtime Kit 的 ThemeLogo，不要硬编码资源路径。
- 直接写 CSS 时优先使用公开的 Runtime 桥接变量，例如 `--tw-color-text-primary`、`--tw-color-bg-default`、`--tw-color-bg-subtle`、`--tw-color-bg-invert`、`--tw-color-border-default`、`--tw-color-link-default`、`--tw-color-accent1` 和 `--tw-font-body`；不要猜测 `--color-*` 或其它未公开变量。`ThemeLogo` 优先只通过 `size` 控制等比高度，不传 `width`、`height` 或 `fit`；只有高级场景才直接读取 `useTheme` 的 `themeLogo`、`themeInvertLogo` 或 `themeStyles`。
- 页面颜色、字体、Logo 和强调状态优先使用 Runtime 主题语义类、主题 CSS 变量和 useTheme；不要硬编码品牌色、字体文件或 Logo 路径。
- 需要素材时先查询当前工作空间的 active 资源，读取 render_type、content_editable 和近似宽高比后选择 AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart、AssetFormula 或 Icon。
- 资源槽位应匹配资源近似宽高比；完整展示优先 contain，只有用户明确要求时才使用 cover，避免裁切关键信息。
- AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart 和 AssetFormula 的资源容器必须通过完整静态 class 声明明确宽高；不要给 Asset* 传 style，也不要只依赖内容自由撑高、min-h、max-height 或外层 overflow-hidden。AssetImage 的 class 作用于外层图片框，图片内容使用 `fit="contain"`/`fit="cover"` 和 `position` 控制；纵向长图必须在 AssetImage 自身 class 上提供确定高度，例如 `h-[500px]` 或 `h-full` 且父级高度明确。
- Icon 和 Asset* 的 name 使用字符串字面量，或来自同一 Vue 文件顶层可静态枚举的对象/数组；不要使用 computed、函数返回、字符串拼接或条件表达式动态生成资源名。
- 普通资源 URL 使用 `useAssetSrc`，背景资源使用 `useAssetBackground`；资源名来自 props 时传入 getter，例如 `useAssetSrc(() => props.imageName)`。`resolveResourcePath` 只用于非响应式工具代码或 Runtime public 静态路径，不要在 SFC 中直接解析动态 props。
- 背景图和蒙版应作为画布内独立视觉层：背景层使用 `absolute inset-0 h-full w-full`，正文放在 `relative z-10 h-full w-full` 等更高层级；蒙版、渐变和暗角单独实现并设置 `pointer-events-none`，颜色优先使用主题语义色或 Runtime CSS 变量。
- 资源库没有合适素材时，才根据当前可用能力生成或创建资源；需要跨页面复用或后续编辑的素材应保存为工作空间资源。

## 页面组件复用

- 跨页重复两次及以上、职责单一且具有稳定 props 或 slots 契约的结构，应主动沉淀为工作空间组件。
- 单页一次性结构直接保留在页面源码中，避免过度拆分；新组件创建后完成校验、发布并更新项目 suggested_components。
""".strip()


COMPONENT_CODE_STANDARD = """
## 组件结构与复用规范

- 组件按页面组件、内容组件和原子组件选择正确的 component_type；页面组件负责整页骨架，内容组件负责页面内内容块，原子组件保持单一职责。
- 组件 content 必须是完整、可运行的 Vue SFC；优先使用 `<script setup lang="ts">`、Composition API、`defineProps`/`defineEmits`、顶层静态 import 和 Vue 响应式能力，不使用 Node API、服务端文件系统 API、远程脚本、未声明依赖、全局副作用或运行时动态拼接 import。
- 页面组件用于封面、目录、章节页、页面骨架或整页视觉组件，应以 DefaultContainer 或已发布页面骨架为根部，并具备独立的整页画布承载能力，不依赖父页面偶然提供的 h-full/w-full 高度上下文；通过 props 或具名 slot 接收可变内容，不硬编码具体页面文案。
- 跨项目和主题复用的结构才应进入工作空间组件；组件接口稳定后优先使用 props/slots 表达变化，避免把当前项目内容写死在组件源码中。
- 内容组件必须在 preview_schema.props 中声明至少一个尺寸控制字段，例如 width、height、minHeight 或 aspectRatio；所有组件都必须提供合法的 preview_schema。
- 内容组件用于卡片、图表、指标组、表格、资源展示块和普通业务区块；应通过 props 或 preview_schema 明确尺寸和 fit 等控制参数，并处理默认数据、空态、长文本和溢出。组件不绑定具体项目的画布尺寸或基础字号。
- 原子组件用于页码、角标、图标、主题 Logo、小标签和装饰符号等小型显示单元；优先提供 size、density、variant、tone 等语义参数，避免默认暴露裸 fontSize/padding 数值 props。
- preview_schema.props 中的字段定义必须与 Vue defineProps 保持一致，包含必要的 type、label 和 default 信息；preview_schema 应与真实 props、slots、mocks 对齐，预览值不能混在 Schema 根节点；优先提供 2～3 个高质量 presets。
- preview_schema 中的资源名和默认值必须来自真实工具结果；找不到合适资源时使用空值或清晰占位说明，不要编造资源名称。

## 组件主题、字体、资源与 Icon 规范

- Runtime 主题语义颜色键包括 primary、secondary、invert、background、background-subtle、background-invert、border、border-subtle、link、link-hover、link-visited 和 accent1 至 accent6；组件只能使用这些 Runtime 主题键、版本化 Runtime Kit 能力和工具返回的工作空间资源，不得猜测其它语义颜色键或硬编码品牌资源。
- background-subtle 是 Runtime 提供的语义背景槽位，不是主题写入 Schema 中的 palette.background.subtle 字段。
- 组件可以使用 Runtime safelist 与源码扫描支持的常用 Tailwind 工具类；未列出的语义 Token 不得自行引入。Tailwind 类必须以完整静态字符串出现在模板、脚本常量或顶层枚举映射中；不要拼接 text-${tone}、from-${color} 或运行时生成 import。Tailwind arbitrary values 可以使用，但必须以源码中的静态完整类出现。
- 字体语义类包括 font-heading、font-body 和 font-code；需要非主题字体时，先查询工作空间字体并使用 Runtime Kit 的 useAssetFontFamily。直接写 CSS 时优先使用 Runtime 桥接变量和 useTheme 提供的公开变量，不要猜测未公开的 CSS 变量。主题 Logo 优先使用 Runtime Kit 的 ThemeLogo，不要硬编码资源路径。
- 直接写 CSS 时优先使用公开的 Runtime 桥接变量，例如 `--tw-color-text-primary`、`--tw-color-bg-default`、`--tw-color-bg-subtle`、`--tw-color-bg-invert`、`--tw-color-border-default`、`--tw-color-link-default`、`--tw-color-accent1` 和 `--tw-font-body`；不要猜测未公开变量。`ThemeLogo` 优先只通过 `size` 控制等比高度，不传 `width`、`height` 或 `fit`。
- 组件应保持主题中立，颜色、字体、Logo 和强调状态优先使用 Runtime 主题语义类、主题 CSS 变量和 useTheme，不绑定当前项目的具体 palette。
- 组件使用工作空间资源和 Icon 时，先查询真实资源名称、render_type、版本和使用契约；不要猜测资源 ID、名称或渲染方式。
- 组件内部的图片、图表、公式和图标应有明确尺寸上下文与 overflow 策略，资源比例和显示方式应符合资源元数据。
- AssetImage、AssetVideo、AssetDrawio、AssetMermaid、AssetChart 和 AssetFormula 的资源容器必须通过完整静态 class 声明明确宽高；不要给 Asset* 传 style，也不要只依赖内容自由撑高、min-h、max-height 或外层 overflow-hidden。AssetImage 的 class 作用于外层图片框，图片内容使用 `fit="contain"`/`fit="cover"` 和 `position` 控制；纵向长图必须在 AssetImage 自身 class 上提供确定高度。
- Icon 和 Asset* 的 name 使用字符串字面量，或来自同一 Vue 文件顶层可静态枚举的对象/数组；不要使用 computed、函数返回、字符串拼接或条件表达式动态生成资源名。
- 普通资源 URL 使用 `useAssetSrc`，背景资源使用 `useAssetBackground`；资源名来自 props 时传入 getter。`resolveResourcePath` 只用于非响应式工具代码或 Runtime public 静态路径，不要在 SFC 中直接解析动态 props。
- 背景图和蒙版应作为画布内独立视觉层，背景使用 `absolute inset-0 h-full w-full`，正文置于更高层级；蒙版、渐变和暗角单独实现并设置 `pointer-events-none`，颜色优先使用主题语义色或 Runtime CSS 变量。
- 组件需要跨页面复用的视觉资源应优先引用工作空间资源；仅当前页面使用且不需要后续编辑的简单表达才直接写在页面源码中。

## 组件发布前检查

- 修改组件源码、component_type 或 preview_schema 前，读取最新草稿和版本基线，使用结构化 edits 或完整候选内容完成修改。
- 写入前关注 Runtime 编译、默认态、预览 presets 和布局诊断结果；校验失败时根据精简文本中的 code、message、scenario、profile 和 detail facts 修复，需要更多上下文时调用 `validate_entity(detail=true)`，不绕过组件契约或版本锁。
""".strip()


_DEFAULT_CODE_STANDARDS: dict[str, str] = {
    "page": PAGE_CODE_STANDARD,
    "component": COMPONENT_CODE_STANDARD,
}


def list_code_standard_types() -> tuple[CodeStandardType, ...]:
    """返回当前支持的代码规范类型。"""

    return ("page", "component")


def get_default_code_standard(standard_type: str) -> str:
    """读取指定类型的系统默认规范，不接受未登记的规范类型。"""

    normalized_type = str(standard_type or "").strip()
    content = _DEFAULT_CODE_STANDARDS.get(normalized_type)
    if content is None:
        raise AppException(
            status_code=400,
            code="AI_CODE_STANDARD_TYPE_INVALID",
            detail="代码规范类型必须是 page 或 component。",
        )
    return content
