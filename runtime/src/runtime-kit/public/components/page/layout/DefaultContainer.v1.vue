<!--
  文件用途：默认页面容器组件，按项目级页面尺寸配置生成自适应画布。
-->

<template>
  <div
class="flex flex-col bg-background text-primary border border-border transition-colors duration-300"
    :style="containerStyle">
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'

/**
 * 默认布局容器组件。
 * 主要职责：
 * 1. 读取项目级页面尺寸配置；
 * 2. 为页面模板提供统一的画布宽高；
 * 3. 保持内部布局仍以绝对画布尺寸组织。
 */
defineOptions({
  name: 'DefaultContainer'
})

const { pageStyle: containerStyle } = usePageSize()
</script>

<style scoped>
/* 只保留必要的样式，其他都通过Tailwind类实现 */
</style>
