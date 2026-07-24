# Editor UI 设计系统建设方案

## 1. 文档状态

- 适用范围：`editor/`
- 方案目标：统一 Editor 的视觉语言、组件行为和工具类布局，逐步形成紧凑、简约、高信息密度的创作工作台。
- 方案性质：架构与迁移方案；不代表所有组件已经完成实现。
- 推荐结论：采用“语义化 Design Token + Reka UI 无样式能力 + Tailwind CSS + Editor 自有组件与业务模式”的混合方案。
- 当前实现约束、禁止写法和评审清单以根目录的[项目级界面设计规范](../../../DESIGN.md)为准。

## 2. 背景与问题

Editor 已使用 Vue 3、TypeScript、Tailwind CSS 和 Lucide 图标，并在 `src/components/ui/` 下维护了少量 `Base*` 组件。当前问题不是完全缺少组件，而是基础层覆盖不足、设计规则没有形成单一事实源，业务页面仍然大量直接拼接样式。

截至方案编写时，代码盘点结果如下：

| 指标 | 当前情况 | 影响 |
| :--- | :--- | :--- |
| Vue 单文件组件 | 122 个，约 4 万行 | 页面与复杂组件体量较大，统一改造需要分批进行 |
| 基础按钮使用 | 约 205 处 `BaseButton` | 已具备一定迁移基础 |
| 原生按钮使用 | 约 250 处 `<button>` | 按钮状态、尺寸和可访问性容易漂移 |
| 原生输入控件 | 约 92 处 `<input>`、25 处 `<select>` | 表单密度、焦点和错误状态不统一 |
| 圆角工具类 | 约 844 处 | 同时存在 `rounded-md/lg/xl/2xl/full` 等多档规则 |
| 全局主题 | Tailwind 仅扩展了基础 `primary` 色 | 缺少表面、文字、边框、状态、密度等语义 Token |
| 响应式基础 | `body` 固定 `min-width: 1280px` | 窄窗口直接裁切，无法进行合理重排或降级 |

现有界面主要混合了三种视觉语言：

1. 展示型后台：大圆角、卡片套卡片、较松的留白和强调阴影。
2. 编辑器工作台：多面板、工具栏、属性检查器和缩略图网格。
3. 数据管理页：搜索、筛选、批量选择、分页和实体列表。

三种场景本身都合理，但缺少共享的密度、层级和布局规则，导致相同层级在不同页面具有不同的控件高度、留白、圆角、边框和交互反馈。

## 3. 建设目标

### 3.1 产品目标

- 建立紧凑、简约、工具化的统一视觉语言。
- 提升有限屏幕空间中的有效信息密度。
- 让项目、页面、资源、组件、主题、样式和 AI 面板具有一致的操作结构。
- 降低用户在不同页面之间切换时的认知成本。
- 支持常见桌面窗口尺寸下的合理收缩、折叠和滚动。

### 3.2 工程目标

- 让颜色、间距、圆角、控件高度和阴影从语义 Token 派生。
- 统一复杂交互组件的键盘、焦点、遮罩、浮层和关闭行为。
- 业务页面优先组合公共模式，不再复制长串 Tailwind 类。
- 保持组件 API 可测试，并为后续视觉回归测试提供稳定入口。
- 允许旧页面渐进迁移，不要求一次性重写 Editor。

### 3.3 非目标

- 本方案不统一 Runtime 内页面内容的视觉风格。
- 本方案不把 Editor UI 组件作为 `@runtime-kit` 能力暴露。
- 本方案不在首轮改造中同时升级所有前端依赖。
- 本方案不要求首轮支持移动端完整创作；移动端可以提供受限浏览或明确提示。
- 本方案不以更换品牌主色为目标，颜色调整应服务于层级与可读性。

## 4. 选型结论

### 4.1 推荐方案

Editor UI Kit 采用四部分组成：

```text
语义 Design Token
        ↓
Tailwind 布局与静态样式
        ↓
Reka UI 复杂交互原语
        ↓
Editor UI 组件与业务模式
```

具体职责如下：

- Design Token：定义颜色、字体、圆角、间距、密度、层级、阴影和动效语义。
- Tailwind CSS：负责页面布局、局部排版和低复杂度视觉样式。
- Reka UI：负责 Dialog、Popover、Dropdown Menu、Select、Tabs、Tooltip 等复杂交互和无障碍基础。
- Editor UI Kit：封装统一外观、默认行为、测试契约和业务模式。
- shadcn-vue：仅作为代码组织、复合组件和视觉实现的参考或组件种子，不作为不可修改的黑盒依赖。

### 4.2 不直接全量引入成品库的原因

- 当前问题包含布局、密度和业务模式不统一，单纯替换输入框和按钮不能解决。
- Editor 是多面板创作工具，不是传统表单后台，很多核心界面需要专用的工作台模式。
- 现有代码已经广泛使用 Tailwind，全量引入带样式组件库会增加覆盖规则和调试成本。
- 平台长期需要稳定的页面、资源、组件和 AI 交互模式，应由自身维护公共 API。

## 5. 设计原则

### 5.1 工具优先

- 优先保证任务效率和信息清晰度。
- 装饰不能抢占工作内容空间。
- 操作反馈应清楚但克制，避免普遍使用缩放、强阴影和大幅位移动画。

### 5.2 紧凑但不拥挤

- 通过一致的控件高度和区域间距提高密度。
- 使用分组、对齐和表面层级保持可扫描性。
- 不通过无限缩小文字和点击区域换取密度。

### 5.3 边框优先于阴影

- 常驻面板、工具栏和卡片主要使用背景差与细边框区分。
- 阴影主要用于浮层、拖拽态、Dialog 和临时悬浮元素。
- 页面实体卡片默认不使用明显投影。

### 5.4 少量稳定的圆角

- 控件、面板和浮层使用有限的圆角等级。
- `rounded-full` 只用于头像、状态点、胶囊标签和明确的圆形图标按钮。
- 避免在同一页面同时出现多个相近但无语义差异的圆角。

### 5.5 状态必须可识别

- Hover、Active、Focus、Selected、Disabled、Loading、Error 必须有稳定规则。
- 选中态不能只依赖颜色；应结合边框、图标、背景或文字权重。
- 危险操作默认保持克制，在确认和执行阶段增强警示。

### 5.6 渐进增强

- 旧页面可通过兼容层继续工作。
- 新组件先覆盖高频能力，再迁移业务页面。
- 每批改造都应能独立测试、发布和回滚。

## 6. Design Token 方案

### 6.1 Token 分层

建议将 Token 分为三层：

1. Primitive Token：原始颜色、尺寸和时间值。
2. Semantic Token：界面语义，如画布、面板、正文、弱文字和危险状态。
3. Component Token：少量组件专属变量，如 Dialog 宽度、Sidebar 宽度和控件高度。

业务页面只应直接消费 Semantic Token 或公共组件，不应依赖 Primitive Token。

### 6.2 颜色 Token

建议至少包含：

```text
--ui-canvas
--ui-surface
--ui-surface-raised
--ui-surface-muted
--ui-surface-hover
--ui-surface-selected

--ui-text
--ui-text-secondary
--ui-text-muted
--ui-text-disabled
--ui-text-inverse

--ui-border
--ui-border-strong
--ui-border-focus

--ui-accent
--ui-accent-hover
--ui-accent-muted

--ui-danger
--ui-danger-muted
--ui-warning
--ui-warning-muted
--ui-success
--ui-success-muted
--ui-info
--ui-info-muted
```

要求：

- 组件不得把 `indigo-600`、`slate-200` 等具体色阶当作跨页面契约。
- Tailwind 可以将语义 CSS Variable 映射成 `bg-surface`、`text-muted` 等工具类。
- 状态色需要同时定义文字、背景和边框组合，不只定义一个主色。
- 首轮只要求浅色主题结构正确，但 Token 命名应避免阻塞后续深色主题。

### 6.3 字体 Token

建议保留系统字体栈，并收敛字号：

| 语义 | 建议字号 | 用途 |
| :--- | :--- | :--- |
| `text-xs` | 12px | 辅助信息、编码、时间、状态说明 |
| `text-sm` | 13px 或 14px | 默认工具界面正文 |
| `text-base` | 14px 或 15px | 表单正文、较重要内容 |
| `title-sm` | 16px | 面板标题、卡片标题 |
| `title-md` | 20px | 页面标题 |
| `title-lg` | 24px | 少量一级入口或空状态 |

页面级标题不应默认使用 28px 以上字号。项目代码、页面编码和技术标识建议使用统一的等宽字体样式。

### 6.4 密度 Token

| Token | 建议值 | 用途 |
| :--- | :--- | :--- |
| `--ui-control-h-xs` | 24px | 微型状态筛选、极紧凑工具 |
| `--ui-control-h-sm` | 28px | 工具栏、表格行内操作 |
| `--ui-control-h-md` | 32px | 默认按钮、搜索和选择器 |
| `--ui-control-h-lg` | 36px | 主要表单或低频强调操作 |
| `--ui-icon-sm` | 14px | 行内图标 |
| `--ui-icon-md` | 16px | 默认工具图标 |
| `--ui-icon-lg` | 20px | 导航和主要操作 |

触控目标和实际视觉尺寸可以分离：紧凑图标的可点击区域仍应满足桌面端可操作性要求。

### 6.5 间距 Token

以 4px 为基础步长，主要使用：

```text
2 / 4 / 6 / 8 / 12 / 16 / 20 / 24 / 32
```

推荐规则：

- 控件内部：4–8px。
- 同组控件：6–8px。
- 工具栏操作组：8–12px。
- 面板内部：12–16px。
- 区块之间：16–24px。
- 页面外边距：根据布局在 12–24px 之间变化。

### 6.6 圆角 Token

| Token | 建议值 | 用途 |
| :--- | :--- | :--- |
| `--ui-radius-sm` | 4px | Tag、紧凑控件、代码标识 |
| `--ui-radius-md` | 6px | 默认按钮、输入框、列表项 |
| `--ui-radius-lg` | 8px | 面板、卡片、Popover |
| `--ui-radius-xl` | 12px | Dialog、较大的浮层 |

除圆形元素外，不再新增其它圆角等级。

### 6.7 阴影和层级

建议只保留：

- `shadow-popover`：Dropdown、Tooltip、Popover。
- `shadow-dialog`：Dialog 和 Drawer。
- `shadow-drag`：拖拽项和浮动预览。

常驻卡片与面板使用边框，不使用普遍的 `shadow-sm`。

统一维护 z-index 层级：

```text
base < sticky < dock < dropdown < popover < dialog < toast
```

业务组件不得自行声明任意大数值作为永久层级。

### 6.8 动效

- Hover 和颜色切换：100–150ms。
- 面板展开和收起：150–200ms。
- Dialog 进入和退出：150–200ms。
- 默认只使用透明度和小幅位移。
- 常规按钮不再统一使用 `active:scale-*`。
- 尊重 `prefers-reduced-motion`。

## 7. 布局系统

### 7.1 全局框架

统一为以下区域：

```text
┌────────────── 顶部上下文栏 ──────────────┐
│ AI Rail │ 主工作区 │ 辅助面板 │ Dock    │
└────────────── 状态或页脚区域 ────────────┘
```

规则：

- 顶部栏只承载全局上下文、面包屑和账户入口。
- 页面级操作放在主工作区的 `PageHeader` 或 `CommandBar`。
- 左右辅助区域必须具有显式的最小、默认和最大宽度。
- 主工作区使用 `min-width: 0`，长内容通过截断或内部滚动处理。
- 固定区域与内容滚动区分离，避免整个页面和内部面板同时滚动。

### 7.2 响应式策略

Editor 以桌面端为主，但不能依赖全局 `min-width: 1280px` 直接裁切。

建议断点策略：

| 宽度 | 行为 |
| :--- | :--- |
| ≥ 1440px | 完整多面板布局 |
| 1180–1439px | 压缩辅助面板，缩短面包屑，减少卡片列数 |
| 960–1179px | 辅助面板改为覆盖层；Dock 保留图标；工具栏允许折叠 |
| < 960px | 进入受限模式，隐藏非核心面板，并明确提示推荐桌面尺寸 |

首轮目标不是实现完整移动端编辑，而是消除不可预期裁切并提供可理解的降级行为。

### 7.3 页面骨架

所有一级页面优先组合：

```text
PageHeader
CommandBar / FilterBar
PageBody
SelectionToolbar（按需）
```

`PageHeader` 包含标题、简短说明、主要操作和可选上下文信息。禁止每个页面独立设计标题高度和操作区排列。

### 7.4 工具面板

组件库、资源库、AI 侧栏和属性检查器共享以下结构：

```text
ToolPanel
├─ ToolPanelHeader
├─ ToolPanelToolbar
├─ ToolPanelBody
└─ ToolPanelFooter
```

要求：

- Header、Toolbar 和 Footer 固定，Body 独立滚动。
- 面板标题默认 14–16px，不使用页面标题等级。
- 搜索、筛选和批量操作具有稳定的位置。
- 空状态应说明当前范围和下一步，而不是只显示大面积空白。

## 8. 组件分层

### 8.1 第一层：UI Primitive

建议目录：

```text
editor/src/components/ui/
├─ button/
├─ input/
├─ select/
├─ dialog/
├─ popover/
├─ menu/
├─ tabs/
├─ tooltip/
├─ checkbox/
├─ switch/
├─ badge/
├─ form-field/
├─ scroll-area/
├─ empty-state/
└─ index.ts
```

首批组件：

| 组件 | 主要职责 |
| :--- | :--- |
| `UiButton` | 统一变体、尺寸、Loading、Disabled、图标间距 |
| `UiIconButton` | 统一图标按钮尺寸、Tooltip 和可访问名称 |
| `UiInput` | 输入状态、前后缀、清除、Disabled 和 Error |
| `UiTextarea` | 多行输入、最小高度和字数提示 |
| `UiSelect` | 单选、键盘操作、浮层和空结果 |
| `UiCombobox` | 可搜索选择和异步结果 |
| `UiCheckbox` | 选择、半选和键盘状态 |
| `UiSwitch` | 二元设置项 |
| `UiTabs` | 页面与面板级标签切换 |
| `UiSegmented` | 紧凑互斥选项 |
| `UiDialog` | 遮罩、焦点圈定、Esc、关闭和尺寸预设 |
| `UiDrawer` | 窄窗口辅助面板和临时配置 |
| `UiPopover` | 临时设置与小型编辑面板 |
| `UiDropdownMenu` | 更多操作和上下文菜单 |
| `UiTooltip` | 图标按钮说明和快捷键信息 |
| `UiBadge` | 类型、版本和状态 |
| `UiFormField` | Label、描述、必填和错误信息 |
| `UiScrollArea` | 统一滚动容器与边界阴影 |
| `UiEmptyState` | 轻量空状态与下一步操作 |
| `UiSkeleton` | 列表、卡片和面板加载占位 |

### 8.2 第二层：通用复合组件

```text
editor/src/components/patterns/
├─ PageHeader.vue
├─ CommandBar.vue
├─ FilterBar.vue
├─ ToolPanel.vue
├─ InspectorSection.vue
├─ PropertyRow.vue
├─ SelectionToolbar.vue
├─ EntityListItem.vue
├─ ThumbnailCard.vue
├─ SplitPane.vue
└─ DataState.vue
```

这些组件负责稳定布局和交互结构，不承载项目、页面或资源 API。

### 8.3 第三层：业务组件

继续保留现有业务目录：

- `components/project`
- `components/page`
- `components/agent`
- `components/theme`
- `components/component-preview`
- `components/page-detail`

业务组件只组合 Primitive 与 Pattern，并负责领域数据和业务事件。

## 9. 组件 API 约定

### 9.1 命名

- 新基础组件统一使用 `Ui` 前缀。
- 布局模式使用职责名称，不使用 `Base` 前缀。
- 变体值优先使用语义名：`primary`、`secondary`、`ghost`、`danger`。
- 尺寸统一使用 `xs`、`sm`、`md`、`lg`，默认值由组件明确声明。

### 9.2 Props 与透传

- 原生属性应通过 `$attrs` 透传到正确的交互元素。
- 不使用 `customClass` 作为主要扩展机制；统一支持 `class` 合并。
- 组件内部使用 class merge 工具处理 Tailwind 冲突。
- Props 只暴露稳定能力，不为单个页面增加一次性视觉开关。
- 需要复杂定制时优先使用 Slot 或组合组件。

### 9.3 v-model

- 表单组件统一使用 `modelValue` 与 `update:modelValue`。
- 打开状态统一使用 `open` 与 `update:open`，旧组件迁移期可提供 `modelValue` 兼容层。
- 受控和非受控模式必须在组件文档中明确。

### 9.4 状态

所有交互组件至少考虑：

- Default
- Hover
- Focus Visible
- Active
- Disabled
- Loading
- Error
- Selected

组件展示页需要覆盖这些状态，不能只展示默认样式。

### 9.5 图标

- 统一使用一个 Lucide Vue 图标入口，避免同一图标库存在多个包和导入方式。
- 默认图标尺寸由组件尺寸派生。
- 纯图标按钮必须具有 `aria-label`，并在含义不明显时提供 Tooltip。
- 禁止使用 Emoji 代替产品图标。

## 10. 可访问性要求

基础组件至少满足以下要求：

- 键盘能够访问所有交互控件。
- `Tab` 顺序与视觉顺序一致。
- Focus Visible 清晰，并且不被 `outline: none` 无替代地移除。
- Dialog 打开后焦点进入内容，关闭后回到触发元素。
- Popover、Menu、Select 支持 Esc 和方向键。
- 表单 Label、描述和错误信息建立语义关联。
- Loading 状态向辅助技术传达，不只显示旋转图标。
- 颜色不作为状态的唯一表达。
- 文字和交互控件对比度在实现阶段通过自动化与人工检查。
- 高密度布局仍保留可操作的点击区域。

截图审阅只能识别部分视觉风险，键盘、读屏和动态状态必须通过真实交互验证。

## 11. 与现有代码的兼容策略

### 11.1 `Base*` 组件

不直接删除：

1. 为 `UiButton`、`UiInput`、`UiDialog` 建立目标 API。
2. 让 `BaseButton`、`BaseInput`、`BaseDialog` 在迁移期代理到新实现。
3. 修正旧组件中无法兼容的新调用。
4. 业务页面迁移完成后删除兼容层。

兼容层只用于迁移，不新增业务能力。

### 11.2 全局 `.btn/.input/.card`

- 冻结旧类，不再新增变体。
- 通过搜索和测试统计剩余使用点。
- 页面迁移时替换为组件或 Pattern。
- 使用量归零后从 `style.css` 删除。

### 11.3 原生控件

允许保留的情况：

- 基础组件内部。
- 需要原生语义且公共组件不能合理覆盖的低层实现。
- 性能敏感的特殊场景，并经过说明。

业务页面不应新增裸按钮、输入框和选择器。

## 12. 重点页面改造

### 12.1 AdminLayout

目标：

- 统一顶部上下文栏高度和左右留白。
- 明确 AI Rail、主工作区、辅助面板和 Dock 的宽度规则。
- 移除全局直接裁切策略。
- 建立面包屑截断、窄窗口折叠和面板覆盖行为。
- 减少品牌区域对工作空间的持续占用。

### 12.2 项目列表

目标：

- 从展示型大卡片转向更紧凑的实体卡片或列表。
- 项目标题、编码、主题、尺寸、更新时间和操作形成稳定层级。
- 次要操作进入更多菜单，减少卡片顶部图标噪音。
- 提供列表/网格密度切换时复用同一实体模式。

### 12.3 页面管理

目标：

- 页面标题和项目操作进入统一 PageHeader。
- 预览大小、预览、样式、资源、组件和新增操作组成 CommandBar。
- 路由、构建、截图和批量操作按任务分组。
- 缩略图卡片统一选中、失效截图、路由和行内操作状态。
- 窄窗口减少列数，不裁切右侧卡片。

### 12.4 组件库

目标：

- 使用 SplitPane 明确组件列表与预览工作区。
- 列表区采用 ToolPanel：标题、搜索、类型筛选、选择状态和列表。
- 预览区提供明确空状态、加载态和编辑态。
- 组件名称、类型、版本、编码、引用名和更新时间统一层级。
- 搜索与批量导出操作保持固定，不随列表滚动消失。

### 12.5 资源库

目标：

- 与组件库共享 FilterBar、ToolPanel 和 Entity 模式。
- 图片、字体、文档等资源类型使用同一选择和状态反馈。
- 上传、导入、替换、引用关系和删除操作按风险分组。

### 12.6 AI 侧栏

目标：

- 对话、工具调用、确认要求和等待状态建立清晰层级。
- Composer、会话列表、上下文范围和运行状态使用统一控件。
- 长消息、代码块和工具结果具有稳定的滚动和折叠行为。
- AI 侧栏的视觉密度与其它 ToolPanel 一致，但保留会话特有模式。

### 12.7 属性检查器

目标：

- 使用 InspectorSection 与 PropertyRow。
- Label 宽度、控件高度、帮助信息和错误状态统一。
- 高频属性默认展开，低频属性折叠。
- 布局、排版、颜色和动画等属性分组稳定。

## 13. 迁移计划

### 阶段 0：基线与决策固化

交付物：

- 确认 Token 命名和默认密度。
- 建立 UI 组件展示页或仅开发环境可访问的 UI Lab。
- 记录项目列表、页面管理、组件库、资源库和 AI 侧栏的视觉基线。
- 建立原生控件、旧类和任意颜色的使用统计。

退出标准：

- 核心 Token 通过评审。
- 组件目录和命名约定确定。
- 迁移统计可以重复执行。

### 阶段 1：Token 与基础组件

交付物：

- 语义 CSS Variable 和 Tailwind 映射。
- `UiButton`、`UiIconButton`、`UiInput`、`UiFormField`、`UiBadge`。
- 统一 Focus Visible、Disabled、Loading 和 Error。
- 旧 `BaseButton`、`BaseInput` 兼容层。

退出标准：

- 新组件覆盖全部状态。
- 基础组件测试通过。
- 新页面不再直接使用旧 `.btn/.input`。

### 阶段 2：复杂交互组件

交付物：

- 接入 Reka UI。
- `UiDialog`、`UiPopover`、`UiDropdownMenu`、`UiTooltip`。
- `UiSelect`、`UiCombobox`、`UiTabs`、`UiCheckbox`。
- 旧 `BaseDialog` 和现有 Select 兼容层。

退出标准：

- Dialog 和浮层通过键盘、焦点和层级测试。
- 现有对话框防漂移测试保持通过。
- 业务方无需直接使用 Reka UI 原语。

### 阶段 3：全局框架与公共模式

交付物：

- AdminLayout 响应式改造。
- `PageHeader`、`CommandBar`、`ToolPanel`、`SplitPane`。
- 统一页面滚动和面板滚动策略。
- 顶部栏、Dock 和辅助面板视觉统一。

退出标准：

- 960px 以上窗口不再出现不可控的整页横向裁切。
- 常用路由之间切换时全局骨架稳定。
- 面板开关和路由切换测试通过。

### 阶段 4：典型业务页面

迁移顺序：

1. 组件库。
2. 资源库。
3. 项目列表。
4. 页面管理。
5. 主题与字体。
6. 样式库。

选择这批页面是因为它们共同覆盖搜索、筛选、卡片、列表、缩略图、SplitPane、批量选择和空状态。

退出标准：

- 三类核心页面使用相同的页面头、工具栏、筛选和数据状态模式。
- 原生控件和旧类使用量显著下降。
- 不引入新的页面级颜色和圆角规则。

### 阶段 5：复杂工作台

迁移范围：

- AI 侧栏和会话面板。
- 页面详情和视觉编辑。
- 组件预览与组件工作台。
- 账户 AI 设置。

这些区域交互复杂、文件体量大，应在基础组件和公共模式稳定后再迁移。

退出标准：

- 工具面板、属性检查器和会话状态统一。
- 复杂页面拆分符合仓库文件职责约束。
- 关键交互 E2E smoke 通过。

### 阶段 6：旧体系清理

交付物：

- 删除不再使用的 `Base*` 兼容组件。
- 删除 `.btn/.input/.card` 等旧全局类。
- 收敛直接使用的 Tailwind 色阶和圆角。
- 增加静态检查或测试，阻止旧模式回流。

退出标准：

- 业务页面不再新增原生高频控件。
- Token、Primitive、Pattern 和业务组件边界清晰。
- 文档与实际组件目录一致。

## 14. 测试与质量门禁

### 14.1 单元与组件测试

基础组件重点验证：

- Props、Slot、事件和属性透传。
- 键盘行为。
- Disabled、Loading、Error 和 Selected。
- Dialog/Popover 的打开、关闭和焦点恢复。
- Select/Combobox 的搜索、选择和空结果。
- class 合并和调用方覆写边界。

### 14.2 类型检查

每个迁移批次至少运行：

```powershell
pnpm run test:editor:check
pnpm run test:editor
```

批次合并前运行：

```powershell
pnpm run test:editor:gate
```

### 14.3 E2E

以下变化需要补充或运行相关 E2E：

- 登录与全局布局。
- 工作空间和项目切换。
- 项目页面预览与构建入口。
- 组件库和资源库核心操作。
- AI 侧栏、工具确认和会话恢复。
- Dialog、Drawer 和辅助面板的关键路径。

### 14.4 视觉验证

建议为以下稳定状态建立截图基线：

- 项目列表。
- 项目页面管理。
- 组件库空状态和选中状态。
- 资源库列表与预览。
- AI 侧栏空会话、运行中、等待确认和工具结果。
- 属性检查器。
- Dialog、Popover、Menu、Select 的展开状态。

至少覆盖：

- 1440px 宽桌面。
- 1180px 左右的紧凑桌面。
- 960px 左右的降级边界。

### 14.5 可访问性检查

自动化检查不能替代人工验证。每个基础组件至少人工检查：

- 只使用键盘能否完成主要操作。
- 焦点是否可见并按预期移动。
- 关闭浮层后是否回到触发元素。
- 缩放至 200% 后核心信息是否仍可访问。
- 状态是否依赖颜色之外的提示。
- 读屏名称是否与视觉含义一致。

## 15. 治理机制

### 15.1 单一事实源

- Token：统一在 Editor 样式入口与 Tailwind 映射中维护。
- Primitive：统一在 `components/ui/` 维护。
- Pattern：统一在 `components/patterns/` 维护。
- 业务组件不得复制组件清单或重新定义同名 Token。

### 15.2 组件准入

新增基础组件前应确认：

1. 是否已有组件可以通过组合解决。
2. 是否属于跨两个以上业务区域的稳定能力。
3. 是否需要 Reka UI 等交互原语。
4. API 是否覆盖可访问性和测试需求。
5. 是否已经在 UI Lab 中展示主要状态。

只服务于单个页面的组件应留在对应业务目录。

### 15.3 变更评审

涉及以下内容时需要额外检查：

- 新增 Token 或改变现有 Token 语义。
- 新增组件变体或尺寸。
- 改变全局布局、断点或面板宽度。
- 改变 Dialog、Popover 和 Select 行为。
- 引入新的组件库或 Tailwind 插件。
- 在业务页面直接使用 Reka UI。

### 15.4 文档维护

实施过程中应同步更新：

- 本文档：方案、阶段、Token 和组件边界变化。
- `docs/developer/editor/README.md`：新增专题入口。
- `docs/developer/editor/testing.md`：新增视觉或可访问性测试入口。
- 顶层 `AGENTS.md`：只有当仓库级协作约束发生变化时更新。

## 16. 风险与缓解

| 风险 | 表现 | 缓解措施 |
| :--- | :--- | :--- |
| 改造范围过大 | 长分支、回归集中、无法快速合并 | 按 Token、Primitive、Pattern、页面分批提交 |
| 新旧组件长期并存 | 两套 API 和视觉继续漂移 | 明确兼容层截止阶段并统计剩余使用点 |
| 过度追求密度 | 可读性和点击体验下降 | 用稳定高度、分组和层级提高密度，不无限缩小 |
| Tailwind 类继续扩散 | Token 形同虚设 | 提供语义工具类、组件 API 和防回流检查 |
| 深度封装降低灵活性 | 业务页面需要大量特殊 Props | 优先组合、Slot 和 Pattern，避免一次性 Props |
| 引入 Reka UI 后泄漏底层 API | 业务代码与第三方实现耦合 | 只允许 `components/ui/` 直接依赖 Reka UI |
| 响应式改造影响复杂工作台 | 面板宽度和预览尺寸异常 | 先改全局框架，再逐个验证复杂页面 |
| 视觉改造与功能开发冲突 | 同一文件频繁冲突 | 先迁移公共层，业务页面按区域认领和小批次推进 |

## 17. 验收标准

### 17.1 视觉一致性

- 页面标题、工具栏、面板、输入控件和实体状态具有统一层级。
- 常驻区域主要使用边框和表面色，阴影只用于临时层。
- 圆角、间距和控件高度来自限定等级。
- 组件库、资源库和页面管理共享公共模式。

### 17.2 工程一致性

- 新业务页面不直接新增裸按钮、输入框和选择器。
- 复杂交互只通过 Editor UI 组件使用，不直接散落 Reka UI 调用。
- 旧 `.btn/.input/.card` 使用量持续下降并最终清零。
- 基础组件具备状态测试和类型检查。

### 17.3 布局质量

- 1440px 桌面端具有完整高效的多面板布局。
- 1180px 左右窗口能够合理压缩或折叠。
- 960px 左右进入明确降级，不发生不可预期裁切。
- 页面只在预期容器内滚动，不出现多层滚动争抢。

### 17.4 可用性

- 用户能快速识别主要操作、当前范围和选中状态。
- 键盘可以完成主要控件操作。
- Dialog、Popover、Menu 和 Select 具有稳定焦点行为。
- Loading、Empty、Error 和 Disabled 状态具有统一表达。

## 18. 建议的首个实施批次

首个批次应控制在基础设施范围，不直接重写复杂业务页面：

1. 建立语义颜色、圆角、密度、间距和动效 Token。
2. 新增 class merge 工具。
3. 实现 `UiButton`、`UiIconButton`、`UiInput`、`UiFormField`、`UiBadge`。
4. 为旧 `BaseButton` 和 `BaseInput` 增加兼容代理。
5. 建立只在开发环境使用的 UI Lab，展示全部状态。
6. 选择一个低风险工具栏和一个简单表单作为真实迁移样例。
7. 补充组件测试、类型检查和视觉截图。

该批次完成后再决定是否同步升级 Tailwind，以及 Reka UI 的具体版本和接入方式，避免依赖升级、全局布局和业务页面重写同时发生。

## 19. 参考资料

外部资料：

- [Reka UI](https://reka-ui.com/)：Vue 无样式交互原语与可访问性能力。
- [shadcn-vue Introduction](https://v3.shadcn-vue.com/docs/introduction)：代码所有权和可复制组件模式。

仓库内相关入口：

- [`editor/src/style.css`](../../../editor/src/style.css)：当前全局样式和基础类。
- [`editor/tailwind.config.js`](../../../editor/tailwind.config.js)：当前 Tailwind 主题配置。
- [`editor/src/components/ui/`](../../../editor/src/components/ui/)：当前基础组件目录。
- [`editor/src/layouts/AdminLayout.vue`](../../../editor/src/layouts/AdminLayout.vue)：Editor 全局框架。
- [Editor 前端结构约定](./structure.md)：视图、组件、状态和 API 分层要求。
- [Editor 测试](./testing.md)：类型检查和 Vitest 入口。
