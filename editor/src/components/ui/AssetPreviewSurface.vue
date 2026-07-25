<!-- 文件功能：提供可配置浅色、深色或棋盘格背景的统一资源预览画布。 -->
<template>
  <div
    class="relative transition-colors"
    :class="backgroundClass"
    :data-preview-background="background"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { AssetPreviewBackground } from './asset-preview-background'

const props = defineProps<{
  background: AssetPreviewBackground
}>()

const backgroundClass = computed(() => {
  if (props.background === 'dark') {
    return 'bg-slate-900'
  }
  if (props.background === 'checker') {
    return 'asset-preview-checker'
  }
  return 'bg-white'
})
</script>

<style scoped>
.asset-preview-checker {
  background-color: #fff;
  background-image:
    linear-gradient(45deg, #e2e8f0 25%, transparent 25%),
    linear-gradient(-45deg, #e2e8f0 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #e2e8f0 75%),
    linear-gradient(-45deg, transparent 75%, #e2e8f0 75%);
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-size: 16px 16px;
}
</style>
