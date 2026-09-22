# Runtime Kit 能力说明

本文档说明 Runtime Kit 对 Backend、Editor 和 Agent 暴露的能力边界。Runtime Kit 不是 UI 组件库，也不是页面模板库；它只提供 Backend 无法直接稳定实现、必须依赖浏览器 Runtime 上下文完成的能力。

## 1. 设计原则

- Runtime Kit 只公开运行时能力：资源 URL 解析、特殊格式资源渲染、页面尺寸与路由上下文、图标资源处理、少量 DOM 运行期能力。
- Backend/Agent 负责生成页面结构、内容块、卡片、网格、页头页脚、目录样式、分页样式和其他视觉布局。
- 页面源码、工作空间组件源码和 preview schema 只能引用 manifest 中公开的版本化 `@runtime-kit/public/...` 路径，公开能力文件名必须带 `.vN`。
- `@runtime-kit/internal/...`、`@/core`、`@/runtime-shell`、`@/styles` 都是 Runtime 内部实现，不属于公开契约。
- 不再提供 `AssetRenderer` 这种聚合入口。Backend/Agent 应根据资源元数据显式选择资源组件。

## 2. 能力分组

### asset

用于解决工作空间资源在不同预览、构建、发布形态下的路径解析和特殊格式渲染问题。

| 能力                  | 适用场景                                                   | 不适用场景                         |
| --------------------- | ---------------------------------------------------------- | ---------------------------------- |
| `AssetImage`          | `asset_metadata.render_type=image` 的图片资源              | 普通 HTML 布局和图片说明样式       |
| `AssetVideo`          | `render_type=video` 的视频资源，支持 `posterName` 解析封面 | 视频区域外的标题、卡片和说明排版   |
| `AssetDrawio`         | Draw.io XML 图表资源                                       | Backend 已生成的普通 SVG/PNG 图片  |
| `AssetMermaid`        | Mermaid 文本图表资源                                       | 普通流程图布局组件                 |
| `AssetChart`          | ECharts option JSON 资源                                   | Backend 直接生成的静态表格或指标块 |
| `AssetFormula`        | LaTeX 公式文本资源                                         | 普通文本、编号和公式说明布局       |
| `useAssetSrc`         | 自定义组件中需要响应式资源 URL                             | 静态硬编码路径                     |
| `useAssetBackground`  | 自定义背景容器中只需要 `backgroundImage`                   | 背景容器布局、尺寸、遮罩           |
| `useAssetFontFamily`  | 页面或组件需要按字体资源名使用非主题字体                   | 字体资源注册和字体文件上传         |
| `resolveResourcePath` | 非响应式代码中解析资源路径                                 | 复杂资源类型判断                   |
| `resolveAssetFontFamily` | 非响应式代码中按字体资源名取得 `font-family`             | 字体包下发策略                     |

选择规则：

- Backend/Agent 优先读取 `asset_metadata.render_type`。
- `image/video/drawio/mermaid/chart/formula` 分别选择显式组件。
- 需要自定义 DOM 结构时使用 `useAssetSrc`、`useAssetBackground` 或 `useAssetFontFamily`。
- 实际页面中的资源渲染容器应通过 `class` 同时声明明确宽度和高度；避免使用 `style`、`min-h`、`max-height` 或内容自由高度作为尺寸来源。
- `AssetImage` 的 `class` 控制外层图片框，不是内部 `img` 的 class；完整展示高图时使用 `fit="contain"` 和明确的 `h-*` 图片框，不要写 `object-contain` 类或用外层 `overflow-hidden` 裁剪。
- 非主题字体应使用静态字体资源名声明，例如 `useAssetFontFamily('BrandSerif')`，Backend 会据此下发字体包。
- 不要让页面源码引用 `@runtime-kit/internal/renderers/*`。

## 3. page

用于读取 Runtime 当前页面尺寸、真实画布样式、页码和路由上下文。它们只提供数据或画布能力，不提供视觉模板。

| 能力                   | 适用场景                                       | 不适用场景                           |
| ---------------------- | ---------------------------------------------- | ------------------------------------ |
| `DefaultContainer`     | 页面根容器，提供真实页面宽高、定位上下文和裁剪 | 默认封面页、默认内容页、页头页脚模板 |
| `usePageSize`          | 响应式读取当前页面宽高、宽高比和 `pageStyle`   | 构建卡片、网格、内容块样式           |
| `buildPageCanvasStyle` | 非响应式场景构造真实画布样式                   | 预览缩放、页面背景和布局             |
| `useCurrentPage`       | 读取当前页码、总页数、标题                     | 页码 UI 组件                         |
| `useRouteCatalog`      | 读取目录项和路由查询函数                       | 目录 UI、双列布局、目录装饰线        |
| `usePageNavigation`    | 上一页、下一页和跳转控制                       | 导航按钮视觉、快捷键系统             |

页面推荐形态：

```vue
<script setup lang="ts">
  import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
  import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'

  const { currentPage, totalPages } = useCurrentPage()
</script>

<template>
  <DefaultContainer>
    <main class="relative h-full">
      <section class="absolute inset-0 p-16">
        <!-- 页面内容结构和样式由 Backend/Agent 生成 -->
      </section>
      <footer class="absolute bottom-8 right-12 text-sm">
        {{ currentPage }} / {{ totalPages }}
      </footer>
    </main>
  </DefaultContainer>
</template>
```

## 4. runtime

用于处理依赖 Runtime 配置、主题变量或真实浏览器运行状态的能力。高级能力不再单独作为分类，而是通过 `recommendation_level=advanced` 标识。

| 能力           | 适用场景                                                        | 不适用场景                                      |
| -------------- | --------------------------------------------------------------- | ----------------------------------------------- |
| `Icon`         | 根据 Runtime 图标配置渲染静态图标、inline SVG、主题色和描边宽度 | 负责图标周围的按钮、卡片和布局样式              |
| `ThemeLogo`    | 渲染当前主题的常规 Logo 或反色 Logo                             | 自定义图片资源、图标资源、Logo 周围布局         |
| `DataTable`    | 需要在 PPTX 导出中保留 PowerPoint 原生可编辑表格的二维数据       | 复杂交互表格、排序、分页、合并单元格            |
| `useTheme`     | 读取主题配置、主题样式变量、主题 logo 与反色 logo               | 主题编辑、项目主题切换、普通 Logo 图片渲染      |
| `resolveColor` | 自定义 SVG、连线、图表等需要解析 Runtime 主题色                 | 通用样式系统或配色方案生成                      |
| `Connector`    | 根据真实 DOM 位置绘制流程图、架构图、关系图连线                 | 普通布局、静态线条装饰、可由 SVG 直接表达的图形 |

普通页面使用 `Icon` 组件即可，图标配置读取、SVG 加载和 fallback 处理属于 Runtime 内部实现。

普通页面或工作空间组件需要展示项目主题 Logo 时，优先使用 `ThemeLogo`。`ThemeLogo` 只通过 `size` 控制高度，数字刻度跟随页面基础字号，宽度自动等比计算，不提供拉伸、裁剪或兜底图片。只有需要自行组合 URL、样式变量或复杂 DOM 结构时，才直接使用 `useTheme` 读取 `themeLogo`、`themeInvertLogo` 或 `themeStyles`。没有配置主题 Logo 时，`ThemeLogo` 会直接空渲染。

规则二维数据需要导出为 PPT 原生表格时，可以使用 `DataTable`。它不使用 HTML table，而是通过 CSS Grid 渲染固定宽高的二维表格；`headerRows` 和 `headerColumns` 只声明语义，不自动套样式。整表、行、列和单元格样式分别通过 `styles.table`、`styles.rows`、`styles.columns` 和 `styles.cells` 控制；边框支持统一线条、无边框、外框、内部横竖线和单独四边，并会在 PPTX 导出时映射为 PowerPoint table cell border。

页面已经使用语义化 `table/thead/tbody/tfoot/tr/th/td`，或需要 `rowspan`、`colspan` 时，不必改写为 `DataTable`。PPTX 导出器会直接生成 PowerPoint 原生可编辑表格，并读取浏览器计算后的尺寸和基础单元格样式。包含图片、SVG、嵌套表格、列表、表单控件等复杂单元格内容时会整表截图降级；详细约束参见页面添加指南的“表格”章节。

`Connector` 依赖元素挂载、尺寸、滚动和定位上下文，因此只能在页面预览或项目预览中验证，不单独创建组件预览 artifact。

## 5. Editor 和 Agent 展示建议

- `recommendation_level=default`：可进入常规推荐和搜索结果。
- `recommendation_level=advanced`：只在用户明确描述 DOM 连线等高级场景时推荐。
- `previewable=true`：Editor 可以创建只读组件预览。
- `previewable=false`：只展示文档、导入路径、usage、返回值和约束，不显示预览、编辑、发布和版本历史。
- `category` 只承担一级分组职责，当前固定为 `asset`、`page`、`runtime`。
- `tags` 只保留搜索语义，不重复 `category`、`kind`、`previewable` 或 `recommendation_level` 已经表达的信息。

## 6. 禁止事项

- 不要把 Runtime Kit 当作通用 UI 组件库。
- 不要要求 Runtime Kit 提供通用内容块、卡片、布局辅助、默认封面页或默认内容页。
- 不要在页面源码中引用 `@runtime-kit/internal/...`。
- 不要在新文档或新代码中使用旧路径 `@runtime-kit/components/...`。
- 不要使用未带 `.vN` 的 `@runtime-kit/public/...` 路径。
- 不要使用 `AssetRenderer`，应按资源类型显式选择组件。
