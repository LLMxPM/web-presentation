<!--
  文件用途：AssetImage — 基于 manifest 资源名称渲染 Backend 托管图片。
  传入 name（asset.name）即可，workspaceId 和路径解析由内部自动完成。
-->
<template>
  <ImageViewer
    :src="src"
    :alt="alt"
    :class="props.class"
    :style="props.style"
    :show-fallback-placeholder="showFallbackPlaceholder"
    v-bind="$attrs"
  >
    <template #fallback>
      <slot v-if="$slots.fallback" name="fallback" />
      <span
        v-else-if="showFallbackPlaceholder"
        :class="props.class"
        :style="props.style"
        class="asset-image--fallback"
      >
        {{ fallbackMessage }}
      </span>
    </template>
  </ImageViewer>
</template>

<script setup lang="ts">
/**
 * AssetImage
 *
 * 使用示例：
 *   <AssetImage name="background" alt="背景图" class="w-full" />
 *
 * Props:
 *   name     — 资源的逻辑名 `asset.name`（必传）
 *   alt      — img 的 alt 属性
 *   fallback — 未命中 manifest 时展示的兜底文案；URL 值仍可作为兼容兜底图地址
 *   class    — 传递给 img 的 class
 *   style    — 传递给 img 的 style
 *   showFallbackPlaceholder — 未解析时是否渲染占位 span，默认 true
 *
 * 关于 name：
 *   manifest.assets 中的 key 为资源逻辑名 `asset.name`，
 *   例：上传 "background.png" 后，默认 name 为 "background"。
 */
import { computed } from 'vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import ImageViewer from '@runtime-kit/internal/renderers/ImageViewer.vue'
import {
  DEFAULT_ASSET_FALLBACK_MESSAGE,
  resolveAssetFallbackMessage,
  resolveAssetFallbackUrl,
} from '@runtime-kit/internal/utils/asset-fallback'

interface Props {
  /** 资源的逻辑名 `asset.name` */
  name: string
  /** img alt 属性 */
  alt?: string
  /** 未命中 manifest 时展示的兜底文案；URL 值仍可作为兼容兜底图地址 */
  fallback?: string
  /** 传给 img 的 class */
  class?: string | string[] | Record<string, boolean>
  /** 传给 img 的 style */
  style?: string | Record<string, string>
  /** 解析失败时是否渲染占位 span，默认 true */
  showFallbackPlaceholder?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  alt: '',
  fallback: DEFAULT_ASSET_FALLBACK_MESSAGE,
  class: '',
  style: () => ({}),
  showFallbackPlaceholder: true,
})

const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, '图片资源无法渲染，请检查资源名称或资源内容。'))
const src = useAssetSrc(() => props.name, () => fallbackUrl.value)
</script>

<style scoped>
.asset-image--fallback {
  box-sizing: border-box;
  display: flex;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
  background-color: #f8fafc;
  border-radius: 4px;
}
</style>
