<!-- 文件功能：提供资源预览画布的浅色、深色和棋盘格背景切换控件。 -->
<template>
  <UiSegmentedControl
    :model-value="modelValue"
    aria-label="预览背景"
    :options="ASSET_PREVIEW_BACKGROUND_OPTIONS"
    @update:model-value="emit('update:modelValue', $event as AssetPreviewBackground)"
  />
</template>

<script setup lang="ts">
import UiSegmentedControl from './segmented/UiSegmentedControl.vue'
import {
  ASSET_PREVIEW_BACKGROUND_OPTIONS,
  type AssetPreviewBackground,
} from './asset-preview-background'

defineProps<{
  modelValue: AssetPreviewBackground
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AssetPreviewBackground]
}>()
</script>
