# Vue 页面资源引用规范

本文档适用于 Runtime 中运行的 `.vue` 页面和工作空间组件。资源能力的核心原则是：Backend/Agent 根据资源元数据显式选择组件，Runtime 负责在浏览器端解析资源 URL 和渲染特殊格式。

## 1. 职责边界

- Backend/Agent 负责决定页面结构、资源摆放、标题、说明、卡片、网格和样式。
- Runtime Kit 负责解析 `asset.name` 到可访问 URL，并渲染 Draw.io、Mermaid、ECharts、LaTeX、视频等需要浏览器运行时的资源。
- 不再使用 `AssetRenderer` 聚合入口。每种资源类型使用显式组件。
- 不要引用 `@runtime-kit/internal/renderers/*`，内部渲染器只供 Runtime Kit 包装组件使用。

## 2. 选择规则

Backend 创建 artifact 时应在资源元数据中提供 `asset_metadata[name].render_type`。Agent 生成源码时按下表选择：

| `render_type` | 推荐能力 | 说明 |
| --- | --- | --- |
| `image` | `AssetImage` | 图片资源 |
| `video` | `AssetVideo` | 视频资源，可选封面 |
| `drawio` | `AssetDrawio` | Draw.io XML 图表 |
| `mermaid` | `AssetMermaid` | Mermaid 文本图表 |
| `chart` | `AssetChart` | ECharts option JSON |
| `formula` | `AssetFormula` | LaTeX 公式文本 |

如果需要自定义 DOM 或 CSS 结构，使用 `useAssetSrc`、`useAssetBackground`、`useAssetFontFamily` 或 `resolveResourcePath` 取得运行时资源引用，再由页面源码自行组织样式。

资源组件的容器样式只使用 `class`。用完整静态 Tailwind 类声明明确宽高、圆角、边框、内边距、背景和裁剪，例如 `class="w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden"`；实际页面不要使用 `style`、`min-h`、`max-height` 或内容自由高度作为尺寸来源。公式颜色和字号使用 `text-*` 类，例如 `text-primary text-5xl`。`AssetImage` 的 `class` 控制外层图片框和边框尺寸，不是内部 `img` 的 class；图片内容始终位于该边框内，框内显示效果通过 `fit` 和 `position` 控制。

## 3. 显式资源组件

### AssetImage

适用于 `render_type=image`。

```vue
<script setup lang="ts">
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
</script>

<template>
  <AssetImage name="product-hero" alt="产品主图" fit="contain" position="center" class="w-full h-64 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

纵向长图需要完整展示时，给 `AssetImage` 自身明确的图片框高度，并使用 `fit="contain"`：

```vue
<template>
  <div class="flex min-h-0 items-center justify-center">
    <AssetImage name="paper-figure" alt="论文图示" fit="contain" position="center" class="w-full h-[500px] rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
  </div>
</template>
```

不要写成 `class="object-contain"` 或 `style="max-height: 500px"`；这些属性会落在 `AssetImage` 外层图片框上，不能控制内部 `img` 的缩放。也不要用外层 `overflow-hidden` 加 `max-height` 代替图片框高度，否则高图会被外框裁切。

常用输入：

- `name`：资源逻辑名，必填。
- `alt`：图片替代文本。
- `fallback`：资源未命中时使用的兜底 URL。
- `class`：外层图片框样式，使用 Tailwind 控制边框、圆角、尺寸、内边距、背景和裁剪。
- `fit`：图片在边框框体内的填充方式，常用 `contain` 展示完整图片，`cover` 填满并裁切。
- `position`：图片在边框框体内的位置，例如 `center`、`top` 或 `50% 40%`。

失败表现：资源名为空或未命中时，使用 `fallback`；没有 fallback 时显示占位或 fallback slot。

不要用于：非图片资源、复杂图片说明布局、普通卡片结构。

### AssetVideo

适用于 `render_type=video`。

```vue
<script setup lang="ts">
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
</script>

<template>
  <AssetVideo name="demo-video" poster-name="demo-poster" controls class="w-full h-80 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

常用输入：

- `name`：视频资源逻辑名，必填。
- `fallback`：视频资源兜底 URL。
- `posterName`：封面资源逻辑名。
- `poster` / `posterFallback`：普通封面 URL 或封面兜底 URL。
- `controls`、`autoplay`、`loop`、`muted`、`playsInline`、`preload`：视频播放行为。

失败表现：视频 URL 解析为空时由内部视频渲染器显示 fallback slot 或空状态。

不要用于：视频标题、字幕说明、播放区域外的布局。

### AssetDrawio

适用于 `render_type=drawio`。

```vue
<script setup lang="ts">
import AssetDrawio from '@runtime-kit/public/components/assets/AssetDrawio.v1.vue'
</script>

<template>
  <AssetDrawio name="architecture" class="w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

常用输入：

- `name`：Draw.io XML 资源逻辑名。
- `fallback`：未命中时的兜底 URL。
- `class`：容器样式，使用静态 Tailwind 类控制宽高、边框、圆角、背景和裁剪。

失败表现：资源 URL 为空时不渲染图表；XML 解析失败由内部渲染器展示失败状态。

不要用于：已导出为普通图片的架构图，这类资源应使用 `AssetImage`。

### AssetMermaid

适用于 `render_type=mermaid`。

```vue
<script setup lang="ts">
import AssetMermaid from '@runtime-kit/public/components/assets/AssetMermaid.v1.vue'
</script>

<template>
  <AssetMermaid name="process-flow" class="w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

常用输入：

- `name`：Mermaid 文本资源逻辑名。
- `fallback`：未命中时的兜底 URL。
- `class`：容器样式，使用静态 Tailwind 类控制宽高、边框、圆角、背景和裁剪。

失败表现：资源 URL 为空时不渲染图表；语法错误由 Mermaid viewer 展示失败状态。

不要用于：Backend/Agent 直接用 HTML/CSS 生成的流程步骤布局。

### AssetChart

适用于 `render_type=chart`，资源内容应为 ECharts option JSON 或内部 viewer 可解析的 option 文本。

```vue
<script setup lang="ts">
import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue'
</script>

<template>
  <AssetChart name="sales-chart" class="w-full h-96 rounded-lg border border-border bg-transparent p-0 overflow-hidden" />
</template>
```

常用输入：

- `name`：图表 option 资源逻辑名。
- `fallback`：未命中时的兜底 URL。
- `class`：容器样式，使用静态 Tailwind 类控制宽高、边框、圆角、背景和裁剪。

失败表现：资源请求失败时内容为空，内部图表不会渲染有效图形。

不要用于：指标卡片、普通表格、Backend 已经生成的静态图片。

### AssetFormula

适用于 `render_type=formula`，资源内容应为 LaTeX 文本。

```vue
<script setup lang="ts">
import AssetFormula from '@runtime-kit/public/components/assets/AssetFormula.v1.vue'
</script>

<template>
  <AssetFormula name="equation" display-mode class="w-full h-20 rounded-lg border border-border bg-transparent p-0 text-primary overflow-hidden" />
</template>
```

常用输入：

- `name`：公式文本资源逻辑名。
- `fallback`：未命中时的兜底 URL。
- `fit`：公式整体适配模式，默认 `contain`，会把公式组等比放大或缩小到容器内；需要旧的自然尺寸和滚动行为时传 `fit="none"`。
- `class`：容器样式、公式颜色和字号，例如 `w-full h-20 text-primary text-5xl overflow-hidden`；块级公式应同时设置明确宽高，避免 `min-h` 或自由高度。
- `displayMode`：块级公式模式。

失败表现：资源请求失败时内容为空；LaTeX 解析失败由内部公式渲染器处理。

不要用于：普通文本公式说明、编号布局、公式周围的解释内容。

## 4. 自定义组件中获取 URL

### useAssetSrc

```vue
<script setup lang="ts">
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'

const src = useAssetSrc('product-hero')
</script>

<template>
  <img :src="src" alt="产品图" class="w-full h-64 object-contain" />
</template>
```

### useAssetBackground

```vue
<script setup lang="ts">
import { useAssetBackground } from '@runtime-kit/public/composables/assets/useAssetBackground.v1'

const backgroundStyle = useAssetBackground('cover')
</script>

<template>
  <section :style="backgroundStyle" class="w-full h-[480px] bg-cover bg-center bg-no-repeat">
    <!-- 布局和内容由页面源码控制 -->
  </section>
</template>
```

### resolveResourcePath

```ts
import { resolveResourcePath } from '@runtime-kit/public/utils/assets.v1'

const logoSrc = resolveResourcePath('img/logo/ppt-e.png')
```

适用于非响应式代码或 Runtime public 静态资源路径解析。Vue 模板中需要响应式资源时优先使用 `useAssetSrc`。解析出的 URL 用于图片、视频或背景容器时，消费方仍应同时设置明确宽度和高度。

### useAssetFontFamily

```vue
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'

const titleFont = useAssetFontFamily('BrandSerif', 'sans-serif')
</script>

<template>
  <h1 :style="{ fontFamily: titleFont }">品牌标题</h1>
</template>
```

字体资源名必须来自工作空间已注册并启用的字体配置。页面和组件源码应使用静态字符串声明字体资源名，Backend 会据此把字体加入预览和构建 artifact。

### resolveAssetFontFamily

```ts
import { resolveAssetFontFamily } from '@runtime-kit/public/utils/fonts.v1'

const titleFont = resolveAssetFontFamily('BrandSerif', 'sans-serif')
```

适用于非响应式代码。Vue 模板中需要响应式字体时优先使用 `useAssetFontFamily`。

## 5. 禁止写法

```vue
<!-- 禁止：聚合入口已经不再作为公开能力 -->
<AssetRenderer name="sales-chart" />
```

```vue
<!-- 禁止：引用内部渲染器 -->
<script setup lang="ts">
import MermaidViewer from '@runtime-kit/internal/renderers/MermaidViewer.vue'
</script>
```

```css
/* 禁止：CSS url() 不经过 Runtime 资源解析 */
.hero {
  background-image: url('/img/illus/background/background.png');
}
```

```vue
<!-- 禁止：硬编码 Backend 资源地址 -->
<img src="http://127.0.0.1:8000/api/v1/public/assets/1/abc123" />
```

## 6. 检查清单

- 页面内容资源是否根据 `asset_metadata.render_type` 选择了显式组件。
- 是否没有使用 `AssetRenderer`。
- 是否没有引用 `@runtime-kit/internal/...`。
- 是否没有引用未带 `.vN` 的 `@runtime-kit/public/...` 路径。
- 背景图是否通过 `useAssetBackground` 或 `resolveResourcePath` 解析。
- 图片是否通过 `AssetImage` 或 `useAssetSrc` 绑定。
- 非主题字体是否通过 `useAssetFontFamily` 或 `resolveAssetFontFamily` 使用静态字体资源名声明。
- 工作空间资源是否统一使用逻辑名 `asset.name`。
