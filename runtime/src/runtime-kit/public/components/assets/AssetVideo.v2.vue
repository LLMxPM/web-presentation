<!--
  文件功能：AssetVideo.v2 为页内时间轴提供受控视频目标；默认隐藏控件且禁止自动播放。
-->
<template>
  <AssetVideoV1
    v-bind="$attrs"
    :name="name"
    :fallback="fallback"
    :poster="poster"
    :poster-name="posterName"
    :poster-fallback="posterFallback"
    :controls="false"
    :autoplay="false"
    :muted="muted"
    :loop="false"
    :preload="preload"
    :fit="fit"
    :position="position"
    data-runtime-kit-motion="timeline"
  />
</template>

<script setup lang="ts">
/**
 * AssetVideo.v2
 *
 * 使用示例：
 *   <AssetVideo.v2 name="demo-video" class="w-full h-80" />
 *
 * 与 v1 的差异：固定隐藏播放控件且禁止自动播放，由页内时间轴统一控制；
 * 需要手动播放的普通视频继续使用 v1。
 */
import AssetVideoV1 from './AssetVideo.v1.vue'
import { DEFAULT_ASSET_FALLBACK_MESSAGE } from '@runtime-kit/internal/utils/asset-fallback'

defineOptions({ inheritAttrs: false })

interface Props {
  /** 视频资源的逻辑名 `asset.name`（必传）。 */
  name: string
  /** 未命中 manifest 时展示的兜底文案；URL 值仍作为兼容视频地址。 */
  fallback?: string
  /** 视频封面兜底 URL。 */
  poster?: string
  /** 视频封面资源的逻辑名 `asset.name`。 */
  posterName?: string
  /** 未命中 posterName 时的封面兜底 URL。 */
  posterFallback?: string
  /** 初始静音；时间轴轨道可覆盖。 */
  muted?: boolean
  /** 预加载策略。 */
  preload?: 'none' | 'metadata' | 'auto'
  /** 视频填充方式。 */
  fit?: 'contain' | 'cover' | 'fill' | 'none'
  /** 视频定位方式。 */
  position?: string
}

withDefaults(defineProps<Props>(), {
  fallback: DEFAULT_ASSET_FALLBACK_MESSAGE,
  poster: '',
  posterName: '',
  posterFallback: '',
  muted: false,
  preload: 'metadata',
  fit: 'contain',
  position: 'center',
})
</script>
