<!--
  文件功能：AssetAudio.v1 按 manifest 资源逻辑名渲染内容音频或页面旁白目标。
-->
<template>
  <AudioViewer
    :src="src"
    :fallback-src="fallbackUrl"
    :fallback-message="fallbackMessage"
    :purpose="purpose"
    :controls="controls"
    :volume="volume"
    :playback-rate="playbackRate"
    :preload="preload"
    :loop="loop"
    :validation-message="nameValidationMessage"
    v-bind="forwardedAttrs"
  >
    <template #fallback="{ error }">
      <slot v-if="$slots.fallback" name="fallback" />
      <div v-else class="asset-audio__fallback">{{ error || fallbackMessage }}</div>
    </template>
  </AudioViewer>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import AudioViewer from '@runtime-kit/internal/renderers/AudioViewer.vue'
import {
  validateAssetAudioName,
  type AudioPreload,
  type AudioPurpose,
} from '@runtime-kit/internal/renderers/audio-options'
import {
  resolveAssetFallbackMessage,
  resolveAssetFallbackUrl,
} from '@runtime-kit/internal/utils/asset-fallback'

defineOptions({ inheritAttrs: false })

interface Props {
  /** 音频资源的逻辑名 asset.name。 */
  name: string
  /** 媒体用途：普通内容或页面旁白。 */
  purpose?: AudioPurpose
  /** 是否展示原生控件；未指定时内容显示、旁白隐藏。 */
  controls?: boolean
  /** 组件级音量，范围 0–1。 */
  volume?: number
  /** 播放速率，范围 0.5–2。 */
  playbackRate?: number
  /** 预加载策略；静态上下文强制降为 none。 */
  preload?: AudioPreload
  /** 是否循环；页面旁白禁止循环。 */
  loop?: boolean
  /** 资源未命中时的兼容 URL 或兜底文案。 */
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  purpose: 'content',
  controls: undefined,
  volume: 1,
  playbackRate: 1,
  preload: 'metadata',
  loop: false,
  fallback: '',
})

const attrs = useAttrs()
// 组件不暴露 autoplay：即使宿主透传该标记，也不能落到原生媒体元素。
const forwardedAttrs = computed(() => {
  const result = { ...attrs }
  delete result.autoplay
  // 编排适配器按资源逻辑名定位媒体；显式覆盖防止页面属性伪造目标。
  result['data-runtime-asset-name'] = props.name
  return result
})

const nameValidationMessage = computed(() => validateAssetAudioName(props.name))
const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(
  props.fallback,
  '音频资源无法渲染，请检查资源名称或资源内容。',
))
const src = useAssetSrc(
  () => nameValidationMessage.value ? '' : props.name,
  () => fallbackUrl.value,
)
</script>

<style scoped>
.asset-audio__fallback {
  display: flex;
  width: 100%;
  min-height: 54px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
}
</style>
