# Connector 连接线组件

`Connector` 是 Runtime Kit 的高级 DOM 运行期能力，用于在两个已经渲染到浏览器中的元素之间绘制 SVG 连线。它依赖真实 DOM 位置、元素尺寸、挂载时机和定位上下文，因此标记为 `recommendation_level=advanced`、`previewable=false`。

该组件适合流程图、架构图、关系图等需要“根据页面实际元素位置连线”的场景。普通布局、静态装饰线和可直接由 SVG 表达的图形不应使用它。

## 快速开始

```vue
<template>
  <div class="relative h-full">
    <div id="box1">起点</div>
    <div id="box2">终点</div>
    <Connector from="#box1" to="#box2" arrow="end" />
  </div>
</template>

<script setup lang="ts">
import Connector from '@runtime-kit/public/components/primitives/Connector.v1.vue'
</script>
```

## 属性

| 属性 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `from` | `string \| HTMLElement` | - | 起始元素选择器或元素引用 |
| `to` | `string \| HTMLElement` | - | 目标元素选择器或元素引用 |
| `type` | `'straight' \| 'polyline' \| 'curve'` | `'straight'` | 连接线类型 |
| `strokeWidth` | `number` | `2` | 线条粗细 |
| `color` | `string` | `'#000000'` | 线条颜色，支持 CSS 变量 |
| `arrow` | `'none' \| 'start' \| 'end' \| 'both'` | `'none'` | 箭头位置 |
| `dashed` | `boolean` | `false` | 是否虚线 |
| `fromAnchor` | `'center' \| 'top' \| 'bottom' \| 'left' \| 'right'` | `'center'` | 起点锚点 |
| `toAnchor` | `'center' \| 'top' \| 'bottom' \| 'left' \| 'right'` | `'center'` | 终点锚点 |
| `curvature` | `number` | `0.5` | 曲线弯曲度，仅对 `curve` 有效 |
| `zIndex` | `number` | `1` | 连线层级 |

## 示例

### 折线连接

```vue
<Connector
  from="#box1"
  to="#box2"
  type="polyline"
  arrow="both"
  color="var(--theme-text-primary)"
/>
```

### 使用元素引用

```vue
<template>
  <div class="relative">
    <div ref="startBox">起点</div>
    <div ref="endBox">终点</div>
    <Connector v-if="startBox && endBox" :from="startBox" :to="endBox" arrow="end" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Connector from '@runtime-kit/public/components/primitives/Connector.v1.vue'

const startBox = ref<HTMLElement | null>(null)
const endBox = ref<HTMLElement | null>(null)
</script>
```

## 使用约束

- `from` 和 `to` 指向的元素必须已经渲染。
- 外层容器应具备稳定定位上下文，通常使用 `position: relative`。
- 组件会监听窗口尺寸、滚动、元素尺寸和部分 DOM 属性变化。
- 不单独提供组件预览 artifact，应在页面预览或项目预览中验证。
- Agent 默认不应推荐该能力，除非用户明确需要 DOM 连线、流程图节点连线或架构图节点连线。

## 禁止用法

- 不要用它绘制普通分割线或静态装饰线。
- 不要在新代码中使用旧路径 `@runtime-kit/components/primitives/Connector.vue`。
- 不要引用 `@runtime-kit/internal/...` 实现连线。
- 不要引用未带 `.vN` 的 `@runtime-kit/public/...` 路径。
