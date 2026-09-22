<!--
  文件用途：AssetVideo — 基于 manifest 资源名称渲染 Backend 托管视频。
-->
<template>
  <VideoViewer :src="src" :poster="posterSrc" v-bind="$attrs">
    <template #fallback>
      <slot v-if="$slots.fallback" name="fallback" />
      <div v-else class="asset-video__fallback">{{ fallbackMessage }}</div>
    </template>
  </VideoViewer>
</template>

<script setup lang="ts">
/**
 * AssetVideo
 *
 * 使用示例：
 *   <AssetVideo name="demo-video" controls />
 *
 * Props:
 *   name           — 视频资源的逻辑名 `asset.name`（必传）
 *   fallback       — 未命中 manifest 时展示的兜底文案；URL 值仍可作为兼容视频地址
 *   poster         — 视频封面兜底 URL（可选）
 *   posterName     — 视频封面资源的逻辑名 `asset.name`（可选）
 *   posterFallback — 未命中 posterName 时的封面兜底 URL（可选）
 */
import { computed } from 'vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import VideoViewer from '@runtime-kit/internal/renderers/VideoViewer.vue'
import {
  DEFAULT_ASSET_FALLBACK_MESSAGE,
  resolveAssetFallbackMessage,
  resolveAssetFallbackUrl,
} from '@runtime-kit/internal/utils/asset-fallback'

interface Props {
  /** 视频资源的逻辑名 `asset.name` */
  name: string
  /** 未命中 manifest 时展示的兜底文案；URL 值仍可作为兼容视频地址 */
  fallback?: string
  /** 视频封面兜底 URL */
  poster?: string
  /** 视频封面资源的逻辑名 `asset.name` */
  posterName?: string
  /** 未命中 posterName 时的封面兜底 URL */
  posterFallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  fallback: DEFAULT_ASSET_FALLBACK_MESSAGE,
  poster: '',
  posterName: '',
  posterFallback: '',
})

const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, '视频资源无法渲染，请检查资源名称或资源内容。'))
const src = useAssetSrc(() => props.name, () => fallbackUrl.value)
const posterSrc = useAssetSrc(() => props.posterName, () => props.poster || resolveAssetFallbackUrl(props.posterFallback))
</script>

<style scoped>
.asset-video__fallback {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
}
</style>
