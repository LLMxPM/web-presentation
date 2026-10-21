<!--
  文件功能：AssetAudio.v2 为页内时间轴提供受控音频目标；默认隐藏控件且不接受 autoplay。
-->
<template>
  <AssetAudioV1
    v-bind="$attrs"
    :name="name"
    :purpose="purpose"
    :controls="false"
    :volume="volume"
    :playback-rate="playbackRate"
    :preload="preload"
    :loop="false"
    :fallback="fallback"
    data-runtime-kit-motion="timeline"
  />
</template>

<script setup lang="ts">
/**
 * AssetAudio.v2
 *
 * 使用示例：
 *   <AssetAudio.v2 name="chapter-01-narration" purpose="narration" class="w-full h-16" />
 *
 * 与 v1 的差异：播放控件默认关闭、禁止自动播放与原生循环，位置和音量由页内时间轴控制；
 * 未声明时间轴时仍可通过 v1 组件保留普通内容音频行为。
 */
import AssetAudioV1 from './AssetAudio.v1.vue'
import type { AudioPreload, AudioPurpose } from '@runtime-kit/internal/renderers/audio-options'

defineOptions({ inheritAttrs: false })

interface Props {
  /** 音频资源的逻辑名 asset.name。 */
  name: string
  /** 媒体用途：普通内容或页面旁白。 */
  purpose?: AudioPurpose
  /** 初始音量，范围 0–1；时间轴轨道可覆盖。 */
  volume?: number
  /** 播放速率，范围 0.5–2。 */
  playbackRate?: number
  /** 预加载策略；静态上下文强制降为 none。 */
  preload?: AudioPreload
  /** 资源未命中时的兼容 URL 或兜底文案。 */
  fallback?: string
}

withDefaults(defineProps<Props>(), {
  purpose: 'content',
  volume: 1,
  playbackRate: 1,
  preload: 'metadata',
  fallback: '',
})
</script>
