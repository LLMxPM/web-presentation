<!--
  文件用途：视频资源基础渲染器，负责统一视频展示、播放参数与渲染区域样式。
  根节点声明 data-runtime-kit-media 导出契约，PPTX 导出据此识别，勿随样式类名一并删除。
-->
<template>
  <section
    class="video-viewer"
    :style="surfaceStyle"
    v-bind="$attrs"
    data-runtime-kit-media="v1"
    data-runtime-kit-media-kind="video"
  >
    <video
      v-if="src"
      ref="mediaElement"
      class="video-viewer__media"
      data-runtime-media-target="video"
      :src="src"
      :poster="poster || undefined"
      :controls="controls"
      :autoplay="autoplay"
      :loop="loop"
      :muted="muted"
      :playsinline="playsInline"
      :preload="preload"
      :style="videoStyle"
      @play="emit('play', $event)"
      @pause="emit('pause', $event)"
      @ended="emit('ended', $event)"
      @error="emit('error', $event)"
      @loadstart="emit('media-reset')"
    />
    <slot v-else name="fallback">
      <div class="video-viewer__placeholder">视频资源为空</div>
    </slot>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import { useViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

type VideoPreload = 'none' | 'metadata' | 'auto'

interface Props extends ViewerSurfaceProps {
  /** 视频可访问地址 */
  src?: string
  /** 视频封面图地址 */
  poster?: string
  /** 是否展示浏览器默认播放控件 */
  controls?: boolean
  /** 是否自动播放 */
  autoplay?: boolean
  /** 是否循环播放 */
  loop?: boolean
  /** 是否静音 */
  muted?: boolean
  /** 是否启用移动端行内播放 */
  playsInline?: boolean
  /** 浏览器预加载策略 */
  preload?: VideoPreload
  /** 视频填充方式 */
  fit?: CSSProperties['objectFit']
  /** 视频定位方式 */
  position?: CSSProperties['objectPosition']
}

const props = withDefaults(defineProps<Props>(), {
  src: '',
  poster: '',
  controls: true,
  autoplay: false,
  loop: false,
  muted: false,
  playsInline: true,
  preload: 'metadata',
  fit: 'contain',
  position: 'center',
})

const emit = defineEmits<{
  play: [event: Event]
  pause: [event: Event]
  ended: [event: Event]
  error: [event: Event]
  /** 实际 video 元素挂载或替换后通知宿主注册。 */
  'media-ready': [element: HTMLVideoElement]
  'media-unmounted': []
  'media-reset': []
}>()

const surfaceStyle = useViewerSurfaceStyle(props)
const videoStyle = computed<CSSProperties>(() => ({
  objectFit: props.fit,
  objectPosition: props.position,
}))
const mediaElement = ref<HTMLVideoElement | null>(null)

watch(mediaElement, (element, previous) => {
  if (previous) emit('media-unmounted')
  if (element) emit('media-ready', element)
}, { flush: 'post' })

onBeforeUnmount(() => {
  if (mediaElement.value) emit('media-unmounted')
})

/** 供放映媒体适配层取得受控实例，避免依赖选择器寻找内部元素。 */
function getMediaElement(): HTMLVideoElement | null {
  return mediaElement.value
}

defineExpose({ getMediaElement })
</script>

<style scoped>
.video-viewer {
  box-sizing: border-box;
  display: block;
  overflow: hidden;
}

.video-viewer__media {
  display: block;
  width: 100%;
  height: 100%;
}

.video-viewer__placeholder {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 14px;
}
</style>
