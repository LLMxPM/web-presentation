# 页面添加指南

本文档说明在 Runtime 中新增页面时，页面源码应如何使用 Runtime Kit。当前原则是：Runtime Kit 只提供 Backend/Agent 无法稳定直接实现的运行时能力，不提供通用内容块、布局辅助组件或默认页面模板。

## 1. 标准流程

1. 在工作空间源码的 `src/views` 下新增页面文件。Runtime 仓库自带演示页面放在 `src/examples/local/views`。
2. 页面根部使用页面画布能力，建议导入 `DefaultContainer`。
3. 页面内容结构、卡片、网格、页头页脚、目录样式、分页样式由 Backend/Agent 直接生成。
4. 根据资源元数据显式选择资源组件，或使用资源 composable 解析 URL。
5. 在 `routes.config.yaml` 中添加路由。
6. 通过页面预览或项目预览验证样式、资源和导航。

## 2. 页面根容器

`DefaultContainer` 是页面画布能力，不是默认内容模板。它只负责读取 Runtime 页面尺寸、建立真实画布宽高、提供定位上下文并裁剪溢出内容。

```vue
<script setup lang="ts">
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
</script>

<template>
  <DefaultContainer>
    <main class="relative h-full">
      <section class="absolute inset-0 p-16">
        <!-- 页面结构和样式由 Backend/Agent 生成 -->
      </section>
    </main>
  </DefaultContainer>
</template>
```

不要把 `DefaultContainer` 当作页头、页脚、封面或内容页模板；这些结构应直接写在页面源码里。

## 3. 页面尺寸

项目配置中的 `app.page.width` / `app.page.height` 是真实创作画布尺寸，页面源码坐标、`px`、`rem` 和 Tailwind arbitrary values 都按这个画布解释。Runtime 外壳可能为了预览区、全屏区、缩略图或 iframe 适配而等比缩放画布，但该缩放不改变页面源码中的 CSS 坐标，也不参与字号或间距计算。

需要在自定义组件中读取页面尺寸时，使用 `usePageSize`。

```vue
<script setup lang="ts">
import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'

const { width, height, aspectRatio, pageStyle } = usePageSize()
</script>
```

`usePageSize` 只提供 Runtime 当前页面宽高和标准画布样式，不处理预览缩放、背景、网格或内容块。

非响应式场景可以使用 `buildPageCanvasStyle`：

```ts
import { buildPageCanvasStyle } from '@runtime-kit/public/composables/page/buildPageCanvasStyle.v1'

const style = buildPageCanvasStyle({ width: 1600, height: 900 })
```

## 4. 页码、目录和导航

Runtime Kit 不再推荐公开 `Pagination`、`TableOfContents` 这类 UI 组件。需要页码、目录或跳转能力时，使用 composable 获取数据，由页面源码自行渲染 UI。

### 当前页上下文

```vue
<script setup lang="ts">
import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'

const { currentPage, totalPages, title } = useCurrentPage()
</script>

<template>
  <footer class="absolute bottom-8 right-12 text-sm text-secondary">
    {{ currentPage }} / {{ totalPages }}
  </footer>
</template>
```

### 路由目录

```vue
<script setup lang="ts">
import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'

const { catalogItems } = useRouteCatalog()
</script>

<template>
  <ol class="space-y-4">
    <li v-for="item in catalogItems" :key="item.id" class="flex justify-between">
      <span>{{ item.title }}</span>
      <span>{{ item.pageNumber }}</span>
    </li>
  </ol>
</template>
```

目录的列数、字号、连接线、章节编号样式都由 Backend/Agent 在页面源码中决定。

### 页间导航

```vue
<script setup lang="ts">
import { usePageNavigation } from '@runtime-kit/public/composables/page/usePageNavigation.v1'

const { canGoNext, canGoPrevious, goToNextPage, goToPreviousPage } = usePageNavigation()
</script>
```

导航按钮、快捷键和手势不是 Runtime Kit 公开能力的一部分。

## 5. 资源使用

资源使用应按 `asset_metadata.render_type` 显式选择组件。

```vue
<script setup lang="ts">
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue'
</script>

<template>
  <AssetImage name="product-hero" alt="产品主图" fit="contain" position="center" class="w-full h-64 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
  <AssetChart name="sales-chart" class="w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

资源组件的容器样式只通过 `class` 配置。使用完整静态 Tailwind 类写明确宽高、圆角、边框、内边距、背景和裁剪，例如 `w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden`；实际页面不要使用 `style`、`min-h`、`max-height` 或内容自由高度作为尺寸来源。公式颜色和字号使用 `text-*` 类，例如 `text-primary text-5xl`。`AssetImage` 的 `class` 控制外层图片框和边框尺寸，不是内部 `img` 的 class；图片内容在该边框内显示，用 `fit` 控制 `contain`、`cover` 等填充方式，用 `position` 控制框内图片位置。纵向长图需要完整展示时，在 `AssetImage` 自身 class 上给出确定高度，例如 `w-full h-[500px]` 或 `h-full` 且父级高度明确，不要用 `object-contain` 类、内联 `style="max-height: ..."` 或外层 `overflow-hidden` 裁切图片。

支持的资源能力：

- `AssetImage`：`render_type=image`
- `AssetVideo`：`render_type=video`
- `AssetDrawio`：`render_type=drawio`
- `AssetMermaid`：`render_type=mermaid`
- `AssetChart`：`render_type=chart`
- `AssetFormula`：`render_type=formula`
- `useAssetSrc` / `useAssetBackground`
- `resolveResourcePath`

不要使用 `AssetRenderer`，也不要引用 `@runtime-kit/internal/renderers/*`。

## 6. 文本与代码块

普通文本块在导出 PPTX 时会保持为单个 PowerPoint 文本框。文本节点与安全的行内标签会转换为同一文本框中的多个可编辑 rich text run，可分别保留颜色、字体、字号、粗体、斜体、下划线、删除线、上下标、字符间距和安全外部链接；`br` 会保留为文本框内换行。`padding` 继续映射为文本框内边距，因此代码块可以使用 `pl-*` 表达逐级缩进。

```html
<div class="pl-6 font-code text-base text-primary">
  <span class="text-accent5-600">"model"</span>:
  <span class="text-accent3-600">"xxx"</span>,
</div>
```

富文本合并只适用于字符级行内样式。带背景、边框、padding、margin、显式盒模型、`inline-flex`、`inline-grid`、定位或 transform 的行内元素会继续作为独立对象导出，避免 badge、图标和布局元素被错误压进文本 run。普通 `white-space` 会跨节点折叠可折叠空白并保留 `&nbsp;`；`pre`、`pre-wrap` 和 `pre-line` 按各自规则处理空格与换行。

`rounded-full` 会按最终宽高区分正圆和胶囊：宽高近似相等时导出为保持正方形外接框的 PowerPoint ellipse，宽大于高时导出为满圆角 roundRect。圆形不会为了补偿 PowerPoint 字宽而单独横向扩宽，避免含数字或短标签的圆形徽章变成椭圆；横向胶囊仍会保留有限的宽度冗余以降低末字换行风险。对于非 `rounded-full` 的普通圆角形状，如果通过 `size-*`、同时声明 `w-*` / `h-*`、内联 width/height，或 `aspect-square` 配合单边尺寸明确给出近似正方形，也会锁定宽高比例并保留原始圆角，不会被文本宽度保护拉成长方形。

纯 2D `rotate()` / `rotateZ()` 会优先映射为 PowerPoint 原生旋转：导出前会先等待有限次入场动画自然结束，保留 `animation-fill-mode: forwards` 的最终状态；无限循环动画不会阻塞导出，测量时会回到稳定的静态样式。随后按旋转前盒模型测量背景、文本与 SVG，围绕 `transform-origin` 统一换算位置并写入 `rotate`。旋转装饰元素允许保留负坐标，由幻灯片边界自然裁切。包含缩放、倾斜、3D 或表格等无法稳定原生映射的 transform 子树会整体降级为局部截图，避免拆分后丢失视觉关系。

## 7. 表格

需要在 PPTX 导出中保留 PowerPoint 原生可编辑表格时，可以使用语义化 HTML `table` 或 Runtime Kit `DataTable`：

- 已有 `thead`、`tbody`、`tfoot`、`th`、`td` 结构，或需要 `rowspan`、`colspan` 时，优先使用原生 HTML `table`。
- 数据是规则二维数组、无需合并单元格，并希望通过分层配置统一控制样式时，可以使用 `DataTable`。
- 普通卡片、指标块、排序分页表格和其它复杂交互内容仍由页面源码自行实现，不应伪装成导出表格。

原生 HTML 表格示例：

```vue
<template>
  <table class="w-full h-72 table-fixed border-collapse text-sm">
    <thead>
      <tr class="h-12 bg-slate-100 text-primary">
        <th rowspan="2" class="w-40 border border-slate-300 px-3 text-left">指标</th>
        <th colspan="2" class="border border-slate-300 px-3 text-center">季度收入</th>
      </tr>
      <tr class="h-12 bg-slate-100 text-primary">
        <th class="border border-slate-300 px-3 text-right">Q1</th>
        <th class="border border-slate-300 px-3 text-right">Q2</th>
      </tr>
    </thead>
    <tbody>
      <tr class="h-16">
        <td class="border border-slate-300 px-3">收入</td>
        <td class="border border-slate-300 px-3 text-right">96 万</td>
        <td class="border border-slate-300 px-3 text-right">128 万</td>
      </tr>
    </tbody>
  </table>
</template>
```

PPTX 导出会读取浏览器计算后的行高、列宽、字体、颜色、背景、padding、对齐和四边边框，并把 `rowspan`、`colspan` 映射为 PowerPoint 合并单元格。表格应具有明确宽高；单元格内容应以纯文本和简单行内标签为主。包含图片、SVG、画布、视频、嵌套表格、列表或表单控件时，整表会降级为局部截图，避免内容丢失。

`DataTable` 示例：

```vue
<script setup lang="ts">
import DataTable from '@runtime-kit/public/components/data/DataTable.v1.vue'

const rows = [
  ['指标', 'Q1', 'Q2'],
  ['收入', '96 万', '128 万'],
  ['增长率', '12%', '18%'],
]

const tableStyles = {
  table: {
    border: {
      outer: { color: '#94a3b8', width: 2, style: 'solid' },
      inner: { color: '#cbd5e1', width: 1, style: 'solid' },
    },
  },
  cell: {
    class: 'text-secondary bg-white',
  },
  rows: {
    0: {
      class: 'bg-slate-100 text-primary font-semibold',
      height: 48,
      border: { bottom: { color: '#475569', width: 2, style: 'solid' } },
    },
  },
  columns: {
    0: {
      class: 'text-primary font-medium',
      width: 160,
      border: { right: { color: '#94a3b8', width: 2, style: 'solid' } },
    },
  },
  cells: {
    '1,2': {
      class: 'text-accent1 font-semibold',
      border: {
        top: { color: '#2563eb', width: 2, style: 'solid' },
        right: { color: '#2563eb', width: 2, style: 'solid' },
        bottom: { color: '#2563eb', width: 2, style: 'dashed' },
        left: 'none',
      },
    },
  },
}
</script>

<template>
  <DataTable
    :rows="rows"
    :styles="tableStyles"
    :header-rows="1"
    class="w-full h-72 text-sm rounded-lg border border-border overflow-hidden"
  />
</template>
```

`DataTable` 自身不使用 HTML table；固定宽高后内部不滚动，未指定的行列自动均分剩余空间。`headerRows` 和 `headerColumns` 只声明表头语义，不自动套视觉样式；首行、首列或单元格视觉应通过 `styles.rows`、`styles.columns`、`styles.cells` 显式设置。

边框接近 PPT 表格模型：`border` 和 `styles.table.border` 控制整表区域；`styles.rows[index].border` 控制某行区域；`styles.columns[index].border` 控制某列区域；单元格对象和 `styles.cells["行,列"].border` 控制单格。边框可写统一线条、`'none'` / `{ style: 'none' }`，也可写 `{ all, outer, inner, innerHorizontal, innerVertical, top, right, bottom, left }`。例如整表无边框使用 `border="none"` 或 `:border="{ style: 'none' }"`；只画外框使用 `:border="{ outer: { color: '#111827', width: 2, style: 'solid' } }"`。

## 8. 图标和颜色

图标依赖 Runtime 图标配置、资源解析和 SVG inline 能力，因此保留为 Runtime Kit 能力。

```vue
<script setup lang="ts">
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
</script>

<template>
  <Icon name="home" class="size-8" color="primary" />
</template>
```

自定义 SVG、连线或图表颜色需要解析 Runtime 主题色时，使用 `resolveColor`。

```ts
import { resolveColor } from '@runtime-kit/public/utils/colors.v1'

const color = resolveColor('accent1-300')
```

`resolveColor` 只负责颜色表达式解析，不代表 Runtime Kit 提供通用样式系统。

## 9. 高级 DOM 能力

`Connector` 用于在真实 DOM 元素之间绘制连线，适合流程图、架构图和关系图。

```vue
<script setup lang="ts">
import Connector from '@runtime-kit/public/components/primitives/Connector.v1.vue'
</script>

<template>
  <div class="relative h-full">
    <div id="node-a">A</div>
    <div id="node-b">B</div>
    <Connector from="#node-a" to="#node-b" arrow="end" />
  </div>
</template>
```

该能力依赖元素挂载、尺寸和定位上下文，不进入 Agent 默认推荐流，应在页面预览或项目预览中验证。

## 10. 禁止事项

- 不要使用旧路径 `@runtime-kit/components/...`。
- 不要引用 `@runtime-kit/internal/...`。
- 不要使用未带 `.vN` 的 `@runtime-kit/public/...` 路径。
- 不要把 Runtime Kit 当作通用 UI 组件库。
- 不要要求 Runtime Kit 提供通用内容块、卡片、布局辅助、封面模板或内容页模板。
- 不要使用 `AssetRenderer`。
- 不要在 CSS 中硬编码资源 `url('/...')`，资源路径必须经过 Runtime 解析。

## 11. 相关文档

- [Runtime Kit 能力说明](./runtime-kit-capabilities.md)
- [资源引用规范](./integration/asset-usage-guide.md)
- [路由配置指南](./routes-config-guide.md)
- [图标系统指南](./icon-system-guide.md)
