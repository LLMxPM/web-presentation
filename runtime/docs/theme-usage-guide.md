# 主题系统使用指南

## 概述

本项目采用基于 YAML 配置的动态主题系统，通过 Tailwind CSS 扩展实现颜色和字体绑定。页面与工作空间组件使用 Runtime Tailwind 主题类，不使用 Editor 的 `surface`、`text-muted`、`danger`、`success` 等 Token。
Runtime 主题语义颜色包括：`primary`、`secondary`、`invert`、`background`、`background-subtle`、`background-invert`、`border`、`border-subtle`、`link`、`link-hover`、`link-visited`、`accent1` 至 `accent6`。`background-subtle` 是 Runtime 的语义背景槽位，不是工作空间主题写入 Schema 中的 `palette.background.subtle` 字段。
扩展的字体包括：`font-body`, `font-heading`, `font-code`
字体大小包括：`text-xs`, `text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl`, `text-3xl`, `text-4xl`, `text-5xl`, `text-6xl`, `text-7xl`, `text-8xl`, `text-9xl`

主题类支持 `text-*`、`bg-*`、`border-*`、`from-*`、`via-*`、`to-*` 前缀、`50` 至 `900` 色阶和透明度，例如 `text-accent2-600`、`bg-primary/80`、`from-background-invert/80`。主题类必须以完整静态字符串出现在模板、脚本常量或顶层枚举映射中；不要拼接 `text-${tone}`、`from-${color}` 等类名。arbitrary value 也必须以源码中的静态完整类出现。

Runtime 主题类和 Editor 主题类不是同一套设计 Token。页面源码不要使用 `bg-surface`、`text-muted`、`bg-tertiary` 等 Editor 或未声明的语义类；需要自定义 CSS 时优先使用下方列出的 `--tw-*` 变量。

主题中的 `logo` 与 `invertLogo` 推荐使用相对路径或远程绝对 URL，例如 `img/logo/ppt-e.png` 或 `https://cdn.example.com/logo.png`。页面需要渲染主题 Logo 时优先使用 Runtime Kit 公开的 `ThemeLogo`。

基础字号与默认图标描边宽度属于项目页面展示配置，不属于主题。新配置从 `app.config.yaml` 的 `app.page.baseFontSize` 和 `app.page.iconDefaultStrokeWidth` 下发；`baseFontSize` 只用于页面内容作用域，是 Tailwind 默认 `16px` 基准的替换值，`text-*`、`p-*`、`m-*`、`gap-*`、`space-*` 等语义尺度会按 `baseFontSize / 16px` 的倍率渲染。Runtime shell 的侧栏、控制按钮、弹窗和 Toast 使用固定外壳字号基准。页面内图标尺寸默认跟随页面基础字号，局部尺寸使用 `size-*` 或 `h-* w-*` Tailwind 类控制。

### 背景色类名
```html
<!-- 默认背景色 - 完整色阶 -->
<div class="bg-background">默认背景</div>
<div class="bg-background-50">默认背景（最浅）</div>
<div class="bg-background-100">默认背景（很浅）</div>
<div class="bg-background-500">默认背景（标准）</div>
<div class="bg-background-900">默认背景（最深）</div>

<!-- 次级背景色 - 完整色阶 -->
<div class="bg-background-subtle">次级背景</div>
<div class="bg-background-subtle-100">次级背景（很浅）</div>
<div class="bg-background-subtle-300">次级背景（较浅）</div>
<div class="bg-background-subtle-700">次级背景（较深）</div>
```

### 边框色类名
```html
<!-- 默认边框色 - 完整色阶 -->
<div class="border border-border">默认边框</div>
<div class="border border-border-200">默认边框（浅）</div>
<div class="border border-border-400">默认边框（中浅）</div>
<div class="border border-border-600">默认边框（中深）</div>

<!-- 次级边框色 - 完整色阶 -->
<div class="border border-border-subtle">次级边框</div>
<div class="border border-border-subtle-300">次级边框（较浅）</div>
<div class="border border-border-subtle-500">次级边框（标准）</div>
```

### 链接色类名
```html
<!-- 链接色系统 - 完整色阶 -->
<a class="text-link">默认链接</a>
<a class="text-link-300">浅色链接</a>
<a class="text-link-700">深色链接</a>

<!-- 悬浮状态链接色 -->
<a class="text-link-hover">悬浮链接色</a>
<a class="text-link-hover-400">悬浮链接色（中浅）</a>

<!-- 已访问链接色 -->
<a class="text-link-visited">已访问链接</a>
<a class="text-link-visited-600">已访问链接（中深）</a>
```

### 强调色类名
```html
<!-- 强调色背景 - 完整色阶 -->
<div class="bg-accent1">强调色1背景</div>
<div class="bg-accent1-100">强调色1背景（很浅）</div>
<div class="bg-accent1-300">强调色1背景（较浅）</div>
<div class="bg-accent1-500">强调色1背景（标准）</div>
<div class="bg-accent1-700">强调色1背景（较深）</div>
<div class="bg-accent1-900">强调色1背景（最深）</div>

<!-- 强调色文本 - 完整色阶 -->
<p class="text-accent2">强调色2文本</p>
<p class="text-accent2-400">强调色2文本（中浅）</p>
<p class="text-accent2-600">强调色2文本（中深）</p>

<!-- 强调色边框 - 完整色阶 -->
<div class="border border-accent3">强调色3边框</div>
<div class="border border-accent3-200">强调色3边框（浅）</div>
<div class="border border-accent3-800">强调色3边框（深）</div>

<!-- 所有六个强调色 -->
<div class="bg-accent1">强调色1</div>
<div class="bg-accent2">强调色2</div>
<div class="bg-accent3">强调色3</div>
<div class="bg-accent4">强调色4</div>
<div class="bg-accent5">强调色5</div>
<div class="bg-accent6">强调色6</div>
```

## 字体系统

### 字体家族类名
```html
<!-- 标题字体 -->
<h1 class="font-heading">标题文本</h1>
<h2 class="font-heading text-2xl">大标题</h2>

<!-- 正文字体 -->
<p class="font-body">正文内容</p>
<span class="font-body text-sm">小号正文</span>

<!-- 代码字体 -->
<code class="font-code">代码文本</code>
<pre class="font-code text-xs">代码块</pre>
```

### 非主题字体资源

主题字体优先使用 `font-heading`、`font-body` 和 `font-code`。如果某个页面或组件需要额外字体，应先在工作空间中注册字体资源，再按资源逻辑名静态声明：

```vue
<script setup lang="ts">
import { useAssetFontFamily } from '@runtime-kit/public/composables/assets/useAssetFontFamily.v1'

const brandFont = useAssetFontFamily('BrandSerif', 'sans-serif')
</script>

<template>
  <h1 :style="{ fontFamily: brandFont }">品牌标题</h1>
</template>
```

Backend 会扫描静态字体资源名并在预览/构建 artifact 中下发对应字体。不要在页面 CSS 中直接手写 `@font-face` 或硬编码字体文件 URL。

导出可编辑 PPTX 时不会嵌入 Runtime 字体文件。为避免目标电脑缺少平台内部字体别名，导出器会把 `Web Presentation Sans` 映射为 `Microsoft YaHei`，把 `Web Presentation Mono` 映射为 `Consolas`；工作空间字体和页面明确指定的其它字体族名保持不变。截图降级内容已经栅格化，不受该映射影响。

## 主题 Logo

```vue
<script setup lang="ts">
import ThemeLogo from '@runtime-kit/public/components/primitives/ThemeLogo.v1.vue'
</script>

<template>
  <ThemeLogo :size="4" />
  <ThemeLogo variant="invert" :size="12" />
</template>
```

`ThemeLogo` 会按当前主题配置解析 `logo` 与 `invertLogo`，并自动适配预览、构建和发布形态下的资源路径。`size` 是唯一尺寸入口，数字按 Runtime Tailwind spacing 解释，`4` 等于一个页面基础字号，Logo 宽度始终自动等比计算，不做拉伸或裁剪。没有配置对应主题 Logo 时组件会空渲染；只有需要自行组合 URL、主题变量或复杂 DOM 结构时，才直接使用 `useTheme` 读取 `themeLogo`、`themeInvertLogo` 或 `themeStyles`。

## 实际使用示例

### 完整组件示例
```vue
<template>
  <div class="bg-background p-6 rounded-lg border border-border">
    <!-- 标题区域 -->
    <header class="mb-4">
      <h1 class="font-heading text-3xl text-primary mb-2">
        产品展示卡片
      </h1>
      <p class="font-body text-secondary">
        使用主题系统的完整示例
      </p>
    </header>
    
    <!-- 内容区域 -->
    <main class="bg-background-subtle p-4 rounded border border-border-subtle">
      <p class="font-body text-primary-700 mb-3">
        这是一个使用主题系统的示例组件，展示了各种颜色和字体的使用。
      </p>
      
      <!-- 按钮组 -->
      <div class="flex gap-3 mb-4">
        <button class="bg-primary text-white px-4 py-2 rounded hover:bg-primary-600">
          主要按钮
        </button>
        <button class="bg-secondary text-white px-4 py-2 rounded hover:bg-secondary-600">
          次要按钮
        </button>
        <button class="border border-border-subtle text-invert px-4 py-2 rounded hover:bg-background-subtle">
          边框按钮
        </button>
      </div>
      
      <!-- 状态标签 -->
      <div class="flex flex-wrap gap-2 mb-4">
        <span class="bg-accent1 text-white px-3 py-1 rounded-full text-sm">设计</span>
        <span class="bg-accent2 text-white px-3 py-1 rounded-full text-sm">开发</span>
        <span class="bg-accent3 text-white px-3 py-1 rounded-full text-sm">测试</span>
        <span class="bg-accent4 text-white px-3 py-1 rounded-full text-sm">部署</span>
      </div>
      
      <!-- 链接示例 -->
      <div class="space-y-2">
        <a href="#" class="text-link hover:text-link-hover block">默认链接样式</a>
        <a href="#" class="text-link-600 hover:text-link-hover-600 block">深色链接样式</a>
        <a href="#" class="text-link-visited block">已访问链接样式</a>
      </div>
    </main>
    
    <!-- 代码示例 -->
    <footer class="mt-4 p-3 bg-background-subtle rounded border border-border-subtle">
      <code class="font-code text-sm text-invert-800">
        class="text-primary bg-background"
      </code>
    </footer>
  </div>
</template>
```

### 数据可视化示例
```vue
<template>
  <div class="bg-background p-6 rounded-lg border border-border">
    <h2 class="font-heading text-2xl text-primary mb-4">项目进度统计</h2>
    
    <!-- 图表图例 -->
    <div class="flex flex-wrap gap-4 mb-6">
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-accent1 rounded"></div>
        <span class="font-body text-sm text-secondary">需求分析 (25%)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-accent2 rounded"></div>
        <span class="font-body text-sm text-secondary">UI设计 (20%)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-accent3 rounded"></div>
        <span class="font-body text-sm text-secondary">前端开发 (30%)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-accent4 rounded"></div>
        <span class="font-body text-sm text-secondary">后端开发 (15%)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 bg-accent5 rounded"></div>
        <span class="font-body text-sm text-secondary">测试 (10%)</span>
      </div>
    </div>
    
    <!-- 柱状图 -->
    <div class="flex items-end gap-2 h-32 mb-4">
      <div class="bg-accent1 w-12 rounded-t" style="height: 75%">
        <div class="text-white text-xs text-center pt-2">25%</div>
      </div>
      <div class="bg-accent2 w-12 rounded-t" style="height: 60%">
        <div class="text-white text-xs text-center pt-2">20%</div>
      </div>
      <div class="bg-accent3 w-12 rounded-t" style="height: 90%">
        <div class="text-white text-xs text-center pt-2">30%</div>
      </div>
      <div class="bg-accent4 w-12 rounded-t" style="height: 45%">
        <div class="text-white text-xs text-center pt-2">15%</div>
      </div>
      <div class="bg-accent5 w-12 rounded-t" style="height: 30%">
        <div class="text-white text-xs text-center pt-2">10%</div>
      </div>
    </div>
    
    <!-- 进度条 -->
    <div class="space-y-3">
      <div>
        <div class="flex justify-between text-sm text-secondary mb-1">
          <span>整体进度</span>
          <span>68%</span>
        </div>
        <div class="w-full bg-background-subtle rounded-full h-2">
          <div class="bg-primary h-2 rounded-full" style="width: 68%"></div>
        </div>
      </div>
      
      <div>
        <div class="flex justify-between text-sm text-secondary mb-1">
          <span>质量评分</span>
          <span>85%</span>
        </div>
        <div class="w-full bg-background-subtle rounded-full h-2">
          <div class="bg-secondary h-2 rounded-full" style="width: 85%"></div>
        </div>
      </div>
    </div>
  </div>
</template>
```
## CSS 变量直接使用

如果需要在特殊情况下直接使用 CSS 变量，可以参考以下变量名：

### 可用的主题变量
```css
/* Tailwind 扩展变量 - 用于色阶生成 */
--tw-color-text-primary
--tw-color-text-secondary  
--tw-color-text-invert
--tw-color-bg-default
--tw-color-bg-subtle
--tw-color-border-default
--tw-color-border-subtle
--tw-color-link-default
--tw-color-link-hover
--tw-color-link-visited
--tw-color-accent1
--tw-color-accent2
--tw-color-accent3
--tw-color-accent4
--tw-color-accent5
--tw-color-accent6

/* 字体变量 */
--tw-font-heading
--tw-font-body
--tw-font-code
--tw-font-size-base
```

`--tw-font-size-base` 在 `:root` 中固定为 Runtime shell 基准 `16px`；页面内容容器会按 `app.page.baseFontSize` 覆写为页面基础字号，相当于替换 Tailwind 默认 16px 基准，不再根据页面宽高做额外缩放。

### 在样式中使用变量
```vue
<template>
  <div class="custom-component">
    <p class="custom-text">自定义样式文本</p>
  </div>
</template>

<style scoped>
.custom-component {
  background: rgb(from var(--tw-color-bg-default) r g b / 0.8);
  border: 1px solid var(--tw-color-border-default);
  border-radius: 8px;
  padding: 1rem;
}

.custom-text {
  color: var(--tw-color-text-primary);
  font-family: var(--tw-font-body);
  font-size: calc(var(--tw-font-size-base) * 1.125);
}
</style>
```

## 最佳实践

1. **优先使用语义化类名**：`text-primary`、`bg-background` 等
2. **复杂场景使用 Runtime 变量**：在 CSS 中使用 `var(--tw-color-text-primary)` 等变量
3. **保持一致性**：在同一组件中使用相同的命名方式
4. **利用状态色变体**：主题色使用 50-900 色阶，默认 Tailwind 色可使用 Runtime 支持的 950 色阶
5. **响应式设计**：结合 Tailwind 的响应式前缀使用
6. **强调色用于数据可视化**：使用 `accent1-accent6` 确保颜色和谐
7. **避免过度使用强调色**：强调色主要用于图表、标签等需要区分的场景

