<!--
  文件用途：Runtime 内部预览缩放容器，按目标宽高比缩放页面内容。
-->

<template>
  <div
class="scaled-canvas-viewport" :class="{ 'scaled-canvas-viewport--fullscreen': isFullscreen }"
    :style="containerStyle">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * Runtime 内部缩放容器。
 * 说明：容器不参与页面内容尺寸计算，仅接收外部计算好的缩放比例并应用。
 */
defineOptions({
  name: 'ScaledCanvasViewport',
})

/**
 * 组件入参
 */
const props = withDefaults(defineProps<{
  /** 设计宽度 */
  designWidth?: number
  /** 设计高度 */
  designHeight?: number
  /** 是否全屏 */
  isFullscreen: boolean
  /** 外部计算后的缩放比例 */
  scale: number
}>(), {
  designWidth: 1920,
  designHeight: 1080
})

/**
 * 计算容器样式
 * 功能：将传入的等比缩放比例应用于插槽内容容器
 */
const containerStyle = computed(() => {
  return {
    transform: `scale(${props.scale})`,
    width: `${props.designWidth}px`,
    height: `${props.designHeight}px`
  }
})
</script>

<style scoped>
.scaled-canvas-viewport {
  position: relative;
  transform-origin: center center;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  flex-shrink: 0;
}

.scaled-canvas-viewport--fullscreen {
  border-radius: 0;
  box-shadow: none;
  transform-origin: center center;
}

.scaled-canvas-viewport>* {
  width: 100%;
  height: 100%;
  overflow: auto;
}

@media (max-width: 768px) {
  .scaled-canvas-viewport {
    padding: 0;
  }
}
</style>
