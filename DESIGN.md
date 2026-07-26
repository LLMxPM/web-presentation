# Web Presentation 界面设计与实现规范

## 1. 文档定位

本文档是 `web-presentation` 仓库当前生效的界面设计与实现规范，面向页面开发、组件开发、代码评审和视觉验收。

- [Editor UI 设计系统建设方案](./docs/developer/editor/ui-design-system.md)说明设计目标、技术选型和迁移路线。
- 本文档说明代码现在应当怎样写，以及哪些写法不能进入业务页面。
- 实际 Token、组件 API 和页面行为发生变化时，应同步更新本文档。

当前规范主要约束 Editor 管理与创作界面。Runtime 内演示页面继续遵循主题、页面和 Runtime Kit 规范；若未来增加平台级跨端视觉约束，应在本文档中新增独立章节，不把 Editor 组件直接暴露为 `@runtime-kit` 能力。

## 2. 单一事实源

| 内容 | 单一事实源 |
| :--- | :--- |
| 颜色、密度、圆角、阴影、层级和动效 | `editor/src/style.css` |
| Tailwind 语义映射 | `editor/tailwind.config.js` |
| 基础交互组件 | `editor/src/components/ui/` |
| 页面和工具区公共结构 | `editor/src/components/patterns/` |
| 传统页面标题栏 | `editor/src/components/layout/PageTitleBar.vue` |
| 全局工作台骨架 | `editor/src/layouts/AdminLayout.vue` |
| 右侧工作空间导航 | `editor/src/components/nav/WorkspaceDock.vue` |

业务组件不得复制第二套 Token、按钮尺寸、标题栏规则或层级表。

## 3. 总体视觉原则

### 3.1 工具界面优先

- 优先展示任务、内容和状态，装饰不能持续占用工作区。
- 常驻区域主要依靠表面色与细边框分层。
- 阴影只用于 Dialog、Popover、Dropdown、拖拽预览等临时层。
- 动效使用透明度和小幅位移，不为普通按钮统一增加缩放反馈。

### 3.2 紧凑但可操作

- 默认正文使用 `text-sm`，辅助信息使用 `text-xs`。
- 默认控件使用 `md`，高密度工具栏优先使用 `sm`。
- 不通过缩小到难以点击的尺寸换取密度。
- 同组操作间距使用 4–8px，不同操作组使用 8–12px。

### 3.3 稳定胜过局部“自适应”

- 页面结构、侧栏宽度、标题高度和操作顺序应在相同类型页面中保持稳定。
- 不得仅为了填满宽屏，把固定工具侧栏改成百分比分栏。
- 响应式变化必须是明确的压缩、截断、折叠或覆盖，不依赖意外换行。

## 4. Design Token 使用

### 4.1 优先使用语义类

优先使用 Tailwind 已映射的语义类：

```vue
<section class="border-border bg-surface text-text">
  <p class="text-text-secondary">辅助说明</p>
</section>
```

需要直接引用 CSS Variable 时，颜色变量必须包在 `rgb()` 中：

```vue
<div class="border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))]" />
```

以下写法无效，因为颜色 Token 保存的是 RGB 三元组而不是完整颜色值：

```vue
<!-- 禁止 -->
<div class="bg-[var(--ui-surface)] text-[var(--ui-text)]" />
```

### 4.2 禁止把具体色阶作为跨页面契约

新业务页面不得用 `slate-*`、`indigo-*`、`emerald-*` 等色阶定义公共层级。确有局部业务语义时可以暂时使用，但不得复制为多个页面的约定。

状态色必须组合表达：

- 背景或边框；
- 文字或图标；
- 必要时增加状态文字、图标或形状。

不能只依靠颜色表达选中、错误或禁用状态。

### 4.3 控件和圆角

控件高度只使用：

- `--ui-control-h-xs`：24px；
- `--ui-control-h-sm`：28px；
- `--ui-control-h-md`：32px；
- `--ui-control-h-lg`：36px。

圆角只使用 `ui-sm`、`ui-md`、`ui-lg`、`ui-xl`。`rounded-full` 只用于头像、状态点、胶囊标签和圆形图标按钮。

### 4.4 语义色 Token 家族

所有颜色 Token 定义在 `editor/src/style.css` 的 `:root`（RGB 三元组），经 `editor/tailwind.config.js` 映射为语义类，是唯一事实源；夜间模式通过 `.dark` 覆盖同名变量实现，业务代码不得再引入具体色阶。

- 表面 / 文字 / 边框：`surface`（含 `raised`/`muted`/`hover`/`selected`）、`text`（`strong`/`emphasis`/`secondary`/`muted`/`disabled`/`faint`/`inverse`）、`border`（`muted`/`strong`/`focus`）。
- 品牌强调：`accent`（`hover` 深、`emphasis` 亮、`border` 选中边框、`ring` 选中环、`muted` 浅底）。
- 状态色统一四档：`success` / `warning` / `danger` / `info` 各含 `DEFAULT`（底色文字）、`strong`（深色文字）、`border`（边框/环）、`muted`（浅背景）。状态徽章按「`bg-*-muted` + `text-*-strong` + `border-*-border`」组合，禁止再用 `emerald/rose/amber/sky` 等原始色阶。
- AI 品牌色：`ai`（`strong`/`border`/`muted`），用于 Agent 相关标识，不复用 `violet-*`。
- 固定深色面（夜间模式不翻转）：`surface-inverse`、`surface-inverse-raised`、`text-on-inverse`（代码块、暗色预览底）；蒙层基色 `overlay`（配透明度用于弹窗遮罩、悬停 scrim、Tooltip 深色底）。

## 5. 页面骨架

### 5.1 页面标题

一级页面优先使用 `PageHeader`；仍依赖传统页面结构的页面使用 `PageTitleBar`。同一页面只能有一个一级标题组件。

桌面工作台中的标题行默认不换行：

```vue
<header class="flex min-w-0 items-center gap-3">
  <div class="min-w-0 flex-1">
    <h1 class="truncate text-title-md">页面标题</h1>
  </div>
  <div class="flex max-w-[60%] shrink-0 items-center gap-1.5 overflow-x-auto">
    <!-- 操作 -->
  </div>
</header>
```

要求：

- 标题容器必须具有 `min-w-0`。
- 标题文本使用 `truncate`，不能挤压操作区或换成两行。
- 操作区使用 `shrink-0`；操作过多时内部横向滚动、收进菜单或减少次要操作。
- 不使用 `flex-wrap` 解决标题与操作冲突。
- 面包屑可以截断，但不能把整个顶栏撑高。

### 5.2 页面操作

- 页面主要操作放在标题栏右侧。
- 成组命令使用 `CommandBar`。
- 搜索和筛选使用 `FilterBar` 或现有搜索模式。
- 批量操作只在存在选择时显示 `SelectionToolbar`。
- 同一操作不能同时出现在标题栏、工具栏和卡片内。

### 5.3 页面宽度

`AdminLayout` 当前主内容最大宽度为 1600px。不要在业务页面重复设置另一套全局最大宽度。

- 列表和管理页使用主内容宽度。
- 全高工作台通过路由 `meta.fullHeight` 获取可用高度。
- 页面自身只控制内部布局，不通过负边距突破全局内容区。

## 6. Flex、Grid 与滚动约束

### 6.1 尺寸传递

全高工作台的每一层父容器都必须显式传递可收缩高度：

```vue
<div class="flex h-full min-h-0 flex-col">
  <header class="shrink-0">...</header>
  <main class="min-h-0 flex-1 overflow-hidden">...</main>
</div>
```

横向多栏布局的可收缩内容必须使用 `min-w-0`：

```vue
<div class="grid min-h-0 flex-1 grid-cols-[400px_minmax(0,1fr)]">
  <aside class="min-h-0 overflow-hidden">...</aside>
  <main class="min-h-0 min-w-0 overflow-hidden">...</main>
</div>
```

缺少 `min-h-0` 会让内部内容把父容器撑开；缺少 `min-w-0` 会导致长标题、工具栏或预览画布挤压相邻区域。

### 6.2 滚动归属

一个方向只允许一个主要滚动所有者：

- 页面滚动：普通管理页的 `AdminLayout` 主区。
- 面板滚动：全高工作台的 `ToolPanelBody`、实体列表或预览参数区。
- 固定区域：标题、搜索、筛选、操作栏和面板底部操作。

禁止同时让页面、工作台和列表都在同一方向滚动。需要内部滚动时，父级使用 `overflow-hidden`，实际内容区使用 `overflow-y-auto`。

### 6.3 分栏宽度

- 固定工具栏或实体列表应使用明确宽度，例如组件库当前为 400px。
- 主工作区始终使用 `minmax(0, 1fr)` 或 `min-w-0 flex-1`。
- 只有用户确实需要调整宽度时才使用 `SplitPane`。
- 引入百分比分栏前必须验证 1440px、1180px 和 960px 三档布局。
- 不能把“填满可用空间”当成改变信息架构的理由。

### 6.4 网格

实体卡片网格应保持合理卡片宽度，避免少量卡片被拉伸成整行大卡片：

```css
grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 22rem));
```

缩略图网格可以根据内容密度使用 `auto-fill`。只有明确希望现有项目拉伸填满一行时才使用 `auto-fit`。

## 7. 定位、覆盖层与组件样式

### 7.1 定位责任

- 绝对定位元素必须有明确的 `relative` 定位父级。
- 覆盖层使用 `absolute inset-0`，不得参与父级 Flex 或 Grid 排版。
- 浮层使用统一 z-index Token，不声明任意大数值。
- 需要覆盖整个区域的透明交互层，不使用方形图标按钮组件伪装。

### 7.2 不依赖调用方类覆盖组件结构

Vue 会合并组件根节点与调用方的 `class`，但 Tailwind 冲突类的最终胜出顺序不能作为组件 API。

例如，`UiIconButton` 自带 `relative inline-flex`。调用方再传入 `absolute`，不保证最终计算样式一定是绝对定位。以下写法禁止：

```vue
<!-- 禁止：把紧凑图标按钮改造成全区域覆盖层 -->
<UiIconButton class="absolute inset-0 h-full w-full" label="打开预览" />
```

应使用语义正确的原生底层元素或专用组件：

```vue
<button
  type="button"
  class="absolute inset-0 h-full w-full bg-transparent"
  aria-label="打开预览"
/>
```

只有以下内容可以通过调用方 `class` 调整：

- 外边距；
- 父布局中的尺寸上限；
- 文档明确允许的排版；
- 不与组件结构类冲突的局部视觉。

需要改变 `position`、`display`、`flex-direction`、固定宽高或内部 Slot 布局时，应扩展组件 API、使用专用模式或改用更合适的元素。

### 7.3 条件挂载后的测量

依赖 `ResizeObserver`、`getBoundingClientRect()` 或 iframe 缩放的组件，在目标元素通过 `v-if/v-else` 异步挂载后必须重新测量：

```ts
watch(resourceUrl, async value => {
  if (!value) return
  await nextTick()
  observeViewport()
})
```

首次挂载时测得 `0 × 0` 不能作为长期状态。尺寸为 0 时，组件应等待下一次有效测量，不能默认按 1:1 大画布继续布局。

## 8. 组件使用边界

### 8.1 按钮

#### 8.1.1 组件选择

- `UiButton`：文字按钮、图标加文字、导航项和具有明确标签的操作。
- `UiIconButton`：固定方形尺寸的纯图标操作。
- 原生 `<button>`：只允许基础组件内部，或覆盖层、拖拽手柄等公共按钮 API 不适用的底层语义元素。

纯图标按钮必须提供 `label`；原生按钮必须提供可访问名称。

不要通过 CSS 把 `UiButton` 或 `UiIconButton` 改造成职责完全不同的组件。

#### 8.1.2 变体（variant）使用规范

- `primary`（默认）：主要操作，每个区域通常只有一个，如"保存"、"创建"、"确认"。
- `secondary`：次要操作，与主要操作并列但优先级较低，如"导出"、"导入"、"刷新"。
- `ghost`：辅助操作或低优先级操作，如"取消"、"关闭"、卡片内的次要操作。
- `danger`：危险操作，如"删除"、"归档"。

#### 8.1.3 尺寸（size）使用规范

- `xs`：极紧凑场景，通常不推荐使用。
- `sm`：工具栏、卡片内操作、筛选栏、对话框操作的默认尺寸。
- `md`（默认）：页面标题栏主要操作的默认尺寸。
- `lg`：强调性的主要操作入口，通常用于空状态或引导流程。

#### 8.1.4 图标规范

- 图标位置：图标在文字之前，使用默认 slot。
- 图标尺寸：
  - `size="sm"` 的按钮使用 `h-3.5 w-3.5` 图标。
  - `size="md"` 的按钮使用 `h-3.5 w-3.5` 或 `h-4 w-4` 图标。
  - `size="lg"` 的按钮使用 `h-4 w-4` 或 `h-5 w-5` 图标。
- 图标与文字间距由组件内部 `gap-1.5` 统一管理，不要在外部覆盖。

#### 8.1.5 操作按钮位置规范

- **页面标题栏**：使用 `PageHeader` 组件的 `#actions` slot，按钮从右到左按优先级排列。
- **工具栏**：使用 `ToolPanel` 的 `#toolbar` slot 或独立工具栏区域。
- **卡片操作**：
  - 主要操作：卡片右上角，常驻或半透明显示。
  - 次要操作：悬停时显示，使用 `CardActionBar` 模式（底部或右侧）。
  - 所有卡片操作优先使用 `size="sm"` + `variant="ghost"`。
- **对话框操作**：使用 `UiDialog` 的 `#footer` slot，取消在左，确认在右。
- **表格行操作**：右侧对齐，使用 `size="sm"` + `variant="ghost"`。

#### 8.1.6 操作按钮间距规范

- 同组紧密操作：`gap-1`（4px）。
- 同组常规操作：`gap-1.5` 或 `gap-2`（6-8px）。
- 不同操作组：`gap-3` 或 `gap-4`（12-16px）。

#### 8.1.7 禁止行为

- 禁止在业务代码中为 `UiButton` 或 `UiIconButton` 添加自定义样式类覆盖边框、背景、悬停效果、阴影等结构样式。
- 禁止使用 `style` 属性覆盖组件的颜色、尺寸或定位。
- 禁止复制按钮样式创建第二套按钮组件或样式类。
- 调用方只能通过 `class` 调整外边距、布局定位（如 `flex-1`、`shrink-0`），不能改变按钮本身的视觉呈现。

### 8.2 Tab 切换

Tab 切换应使用 `UiTabs` 组件或 `UiSegmented` 组件，不要用 `UiButton` 模拟 tab。

- **UiTabs**：用于内容切换，适合页面级或面板级的多视图切换。
- **UiSegmented**：用于筛选或模式切换，适合工具栏或筛选区。

禁止使用 `UiButton` + `grid` + 自定义激活样式模拟 tab，这会导致样式不一致和可访问性问题。

### 8.3 Dock

右侧 `WorkspaceDock` 的图标在上、文字在下：

```text
┌──────┐
│ 图标 │
│ 文字 │
└──────┘
```

Dock 项使用固定宽高与纵向排列。由于 `UiButton` 自带内部 Slot 包装，调整 Dock 布局时必须同时检查按钮根节点和内部 `span`，不能只给根节点添加 `flex-col`。

### 8.4 面板

组件库、资源库、属性检查器和 AI 侧栏遵循：

```text
ToolPanel
├─ Header     固定
├─ Toolbar    固定
├─ Body       独立滚动
└─ Footer     按需固定
```

面板标题使用 14–16px，不使用页面标题字号。空状态必须说明当前范围和下一步操作。

### 8.5 数据状态

加载、空、错误和就绪状态优先使用 `DataState` 或业务层统一状态组件。切换状态时应保持容器尺寸稳定，避免工作台整体跳动。

### 8.6 确认弹窗

- 业务代码通过 `createConfirm()` 请求确认，不自行创建全屏遮罩或临时 Vue 应用。
- 全局 `UiConfirmHost` 负责使用 `UiDialog` 串行展示请求，确保嵌套弹窗中的焦点、Esc 和指针交互正常。
- 危险操作通过 `dangerous` 选项使用 `danger` 按钮语义；取消在左，确认在右。
- 同一时刻只显示一个确认框，并按触发顺序结算并发请求。

## 9. 响应式规则

| 窗口宽度 | 行为 |
| :--- | :--- |
| ≥ 1440px | 完整多面板布局 |
| 1180–1439px | 缩短面包屑，压缩辅助区和操作间距 |
| 960–1179px | 辅助面板覆盖显示，保留核心 Dock 与主工作区 |
| < 960px | 受限模式，隐藏非核心面板并给出明确提示 |

要求：

- 断点行为由全局布局或公共 Pattern 负责。
- 页面标题不能因为窗口变窄随意换行。
- 工具栏优先横向滚动、菜单收纳或显式折叠。
- 不能恢复全局 `min-width: 1280px` 来掩盖布局问题。
- 预览区、编辑器和侧栏在断点变化后必须重新测量。

## 10. 可访问性与交互状态

每个交互组件至少覆盖：

- Default；
- Hover；
- Focus Visible；
- Active 或 Selected；
- Disabled；
- Loading；
- Error（适用时）。

同时满足：

- Tab 顺序与视觉顺序一致；
- 焦点样式清晰且不被遮挡；
- Dialog 关闭后焦点回到触发元素；
- 图标按钮和透明覆盖按钮具有可访问名称；
- 状态不能只用颜色表达；
- 200% 缩放下核心操作仍可访问。

## 11. 开发与评审检查清单

### 11.1 开发前

- 是否已有 `Ui*` 或 Pattern 可以复用？
- 这是普通页面还是 `fullHeight` 工作台？
- 滚动应由哪一层负责？
- 标题、侧栏和工具区是否已有同类页面可参考？

### 11.2 代码评审

- 是否使用语义 Token，而不是新增具体色阶契约？
- Flex 子项是否补充了必要的 `min-w-0`、`min-h-0` 和 `shrink-0`？
- 标题栏、工具栏是否出现非预期换行？
- 是否通过调用方 class 覆盖了基础组件的 `position`、`display` 或固定尺寸？
- 绝对定位元素是否仍参与了 Flex/Grid 布局？
- 条件挂载的预览、图表或编辑器是否在挂载后重新测量？
- 是否出现双重滚动或不可见的横向溢出？
- 图标按钮是否有可访问名称？

### 11.3 视觉验收

至少验证：

1. 1440px 以上完整桌面；
2. 1180px 左右紧凑桌面；
3. 960px 左右降级边界；
4. 长标题、长编码和多操作；
5. 空、加载、错误、选中和禁用状态；
6. Dialog、Popover、Dropdown 展开状态；
7. 组件预览、iframe 或图表的实际 DOM 尺寸与裁剪范围。

视觉异常不能只看截图猜测，应检查：

- `getBoundingClientRect()`；
- `position`、`display`、`overflow` 和 `transform` 的计算值；
- Flex/Grid 实际子项数量；
- `scrollWidth/clientWidth`；
- iframe 或缩放舞台的最终比例。

## 12. 验证命令

修改基础组件、Pattern 或全局布局后至少运行：

```powershell
pnpm run test:editor:check
pnpm run test:editor
```

合并前运行：

```powershell
pnpm run test:editor:gate
```

涉及布局、定位、缩放或响应式时，组件测试不能替代真实浏览器验证。应在目标路由检查实际 DOM，并对关键页面进行截图复核。
