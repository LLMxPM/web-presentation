<!--
  文件功能：音频资源基础渲染器，统一原生 audio 属性、执行策略降级、媒体事件与卸载清理。
-->
<template>
  <section
    class="audio-viewer"
    v-bind="$attrs"
    data-runtime-kit-media="v1"
    data-runtime-kit-media-kind="audio"
    :data-runtime-audio-state="audioState"
  >
    <audio
      v-if="showMedia"
      ref="mediaElement"
      class="audio-viewer__media"
      data-runtime-media-target="audio"
      :data-runtime-media-purpose="resolved.purpose"
      :src="activeSrc"
      :controls="resolved.controls"
      :preload="resolved.preload"
      :loop="resolved.loop"
      @play="emit('play', $event)"
      @pause="emit('pause', $event)"
      @ended="emit('ended', $event)"
      @error="handleMediaError"
      @loadstart="emit('media-reset')"
    />
    <slot v-else name="fallback" :error="fallbackError">
      <div class="audio-viewer__placeholder">{{ fallbackError || '音频资源为空' }}</div>
    </slot>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { resolveNarrationVolume } from '@/core/audio/audio-config'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { audioConfig } from '@/core/utils/config'
import {
  resolveAudioPlaybackOptions,
  type AudioPreload,
  type AudioPurpose,
} from '@runtime-kit/internal/renderers/audio-options'

defineOptions({ inheritAttrs: false })

interface Props {
  /** 音频可访问地址。 */
  src?: string
  /** 主资源加载失败时的一次性兼容兜底地址。 */
  fallbackSrc?: string
  /** 主资源与兜底都不可用时展示的文案。 */
  fallbackMessage?: string
  /** 媒体用途，旁白由放映宿主统一调度。 */
  purpose?: AudioPurpose
  /** 是否展示浏览器默认播放控件；未指定时内容音频显示、旁白隐藏。 */
  controls?: boolean
  /** 组件级音量，范围 0–1。 */
  volume?: number
  /** 播放速率，范围 0.5–2。 */
  playbackRate?: number
  /** 浏览器预加载策略；静态上下文强制为 none。 */
  preload?: AudioPreload
  /** 是否循环播放；页面旁白禁止循环。 */
  loop?: boolean
  /** 外层资源组件产生的校验错误。 */
  validationMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  src: '',
  fallbackSrc: '',
  fallbackMessage: '',
  purpose: 'content',
  controls: undefined,
  volume: 1,
  playbackRate: 1,
  preload: 'metadata',
  loop: false,
  validationMessage: '',
})

const emit = defineEmits<{
  play: [event: Event]
  pause: [event: Event]
  ended: [event: Event]
  error: [event: Event]
  /** 实际 audio 元素挂载或替换后通知放映宿主注册。 */
  'media-ready': [element: HTMLAudioElement]
  'media-unmounted': []
  'media-reset': []
}>()

const executionPolicy = useRuntimeExecutionPolicy()
const mediaElement = ref<HTMLAudioElement | null>(null)
const activeSrc = ref(props.src)
const failed = ref(false)
const resolved = computed(() => {
  const options = resolveAudioPlaybackOptions({
    purpose: props.purpose,
    controls: props.controls,
    volume: props.volume,
    playbackRate: props.playbackRate,
    preload: props.preload,
    loop: props.loop,
    staticContext: !executionPolicy.value.allowMediaPlayback,
  })
  if (props.validationMessage) {
    return { ...options, error: props.validationMessage, preload: 'none' as const, loop: false }
  }
  return options
})
/** 旁白叠加项目 master × narration；内容音频只使用组件自身音量。 */
const effectiveVolume = computed(() => (
  resolved.value.error || resolved.value.purpose !== 'narration'
    ? resolved.value.volume
    : resolveNarrationVolume(audioConfig.value, resolved.value.volume)
))
const showMedia = computed(() => Boolean(activeSrc.value) && !resolved.value.error && !failed.value)
const audioState = computed(() => (
  resolved.value.error || failed.value ? 'error' : activeSrc.value ? 'ready' : 'empty'
))
const fallbackError = computed(() => (
  resolved.value.error || (failed.value ? props.fallbackMessage : '')
))

/** 把已校验的动态音量和速率同步到原生媒体属性。 */
function syncMediaProperties(element = mediaElement.value): void {
  if (!element || resolved.value.error) return
  element.volume = effectiveVolume.value
  element.playbackRate = resolved.value.playbackRate
}

/** 停止并复位媒体，避免资源切换或页面卸载后继续发声。 */
function stopMedia(element = mediaElement.value): void {
  if (!element) return
  element.pause()
  try {
    element.currentTime = 0
  }
  catch {
    // 尚未加载可定位媒体数据时，浏览器可能拒绝写入 currentTime。
  }
}

watch(mediaElement, (element, previous) => {
  if (previous) emit('media-unmounted')
  if (element) {
    syncMediaProperties(element)
    emit('media-ready', element)
  }
}, { flush: 'post' })

watch(
  () => [effectiveVolume.value, resolved.value.playbackRate] as const,
  () => syncMediaProperties(),
)

watch(
  () => [props.src, props.fallbackSrc] as const,
  () => {
    stopMedia()
    activeSrc.value = props.src
    failed.value = false
  },
)

/**
 * 主资源失败时只尝试一次兼容兜底地址，兜底仍失败才上报最终错误。
 * 切换到兜底不算失败，避免放映宿主在兜底仍可能发声时提前中止。
 */
function handleMediaError(event: Event): void {
  if (props.fallbackSrc && activeSrc.value !== props.fallbackSrc) {
    activeSrc.value = props.fallbackSrc
    emit('media-reset')
    return
  }
  failed.value = true
  emit('error', event)
}

onBeforeUnmount(() => {
  if (mediaElement.value) {
    stopMedia()
    emit('media-unmounted')
  }
})

/** 供页面媒体会话取得受控实例，避免依赖选择器寻找内部元素。 */
function getMediaElement(): HTMLAudioElement | null {
  return mediaElement.value
}

defineExpose({ getMediaElement })
</script>

<style scoped>
.audio-viewer {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 54px;
  align-items: center;
}

.audio-viewer__media {
  display: block;
  width: 100%;
}

.audio-viewer__placeholder {
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
