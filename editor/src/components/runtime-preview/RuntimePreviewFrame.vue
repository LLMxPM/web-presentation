<!-- 文件功能：封装 Runtime 预览 iframe 与空态展示，统一处理比例容器和填充容器两种模式。 -->
<template>
  <div data-testid="page-preview-frame" class="relative" :class="props.containerClass" :style="containerStyle">
    <iframe
      v-if="props.frameUrl"
      ref="iframeRef"
      :src="props.frameUrl"
      :title="props.title"
      :class="props.iframeClass"
      referrerpolicy="same-origin"
    />
    <div v-else-if="props.status === 'idle'" :class="props.emptyContentClass">
      <div class="space-y-3">
        <p v-if="props.emptyTitle" class="text-base font-semibold text-text-emphasis">{{ props.emptyTitle }}</p>
        <p v-if="props.emptyDescription" class="text-sm text-text-muted">{{ props.emptyDescription }}</p>
      </div>
    </div>
    <div
      v-if="showStatusOverlay"
      data-testid="page-preview-status-overlay"
      class="absolute inset-0 flex items-center justify-center bg-surface/85 px-8 text-center backdrop-blur-[1px]"
    >
      <div class="max-w-md space-y-3">
        <p class="text-base font-semibold" :class="effectiveStatus === 'error' ? 'text-danger' : 'text-text-emphasis'">
          {{ statusTitle }}
        </p>
        <p class="text-sm text-text-muted">{{ statusDescription }}</p>
        <UiButton v-if="effectiveStatus === 'error'" size="sm" @click="retryPreview">重新生成预览</UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { UiButton } from '@/components/ui'
import { useRuntimePreviewRecovery } from '@/composables/useRuntimePreviewRecovery'
import {
  COMPONENT_PREVIEW_ERROR_EVENT, COMPONENT_PREVIEW_READY_EVENT,
  type ComponentPreviewErrorMessage, type ComponentPreviewReadyMessage,
} from '@/types/component-preview'
import {
  PAGE_PREVIEW_ERROR_EVENT,
  PAGE_PREVIEW_READY_EVENT,
  type PagePreviewErrorMessage,
  type PagePreviewReadyMessage,
  type RuntimePreviewStatus,
} from '@/types/runtime-preview'

interface Props {
  frameUrl: string
  title: string
  viewport?: {
    width: number
    height: number
  } | null
  minHeight?: string
  layout?: 'aspect' | 'fill'
  containerClass?: string
  iframeClass?: string
  emptyContentClass?: string
  emptyTitle?: string
  emptyDescription?: string
  artifactId?: string
  status?: RuntimePreviewStatus
  statusMessage?: string
  autoRecover?: boolean
  recoveryKey?: string
}

const props = withDefaults(defineProps<Props>(), {
  viewport: null,
  minHeight: '',
  layout: 'aspect',
  containerClass: 'overflow-hidden rounded-2xl border border-border bg-surface shadow-sm',
  iframeClass: 'block h-full w-full bg-canvas',
  emptyContentClass: 'flex h-full items-center justify-center px-8 text-center',
  emptyTitle: '',
  emptyDescription: '',
  artifactId: '',
  status: 'idle',
  statusMessage: '',
  autoRecover: false,
  recoveryKey: '',
})

const emit = defineEmits<{
  ready: []
  error: [message: string, code?: string]
  retry: []
  renew: [newUrl: string]
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const localError = ref('')
let lastErrorFingerprint = ''
const effectiveStatus = computed(() => localError.value && props.status === 'idle' ? 'error' : props.status)
const recovery = useRuntimePreviewRecovery({
  frameUrl: () => props.frameUrl,
  sourceKey: () => props.recoveryKey || props.title,
  artifactId: () => props.artifactId,
  onRenewed: (newUrl: string) => emit('renew', newUrl),
  enabled: () => props.autoRecover,
  isPending: () => props.status === 'generating',
  recover: () => emit('retry'),
})
watch(() => props.frameUrl, () => {
  localError.value = ''
  lastErrorFingerprint = ''
})

const showStatusOverlay = computed(() => (
  effectiveStatus.value === 'generating'
  || effectiveStatus.value === 'loading'
  || effectiveStatus.value === 'slow'
  || effectiveStatus.value === 'error'
))

const statusTitle = computed(() => {
  if (props.status === 'generating') return '正在生成页面预览'
  if (props.status === 'loading') return '正在加载页面预览'
  if (props.status === 'slow') return '网络较慢，仍在加载'
  return '页面预览加载失败'
})

const statusDescription = computed(() => {
  if (props.statusMessage) return props.statusMessage
  if (localError.value) return localError.value
  if (props.status === 'generating') return '正在准备当前页面的 Runtime artifact。'
  if (props.status === 'loading') return '正在启动 Runtime 并加载页面模块。'
  if (props.status === 'slow') return '冷缓存或网络不稳定时可能需要更长时间，请稍候。'
  return '可以重新生成预览后再试。'
})

const containerStyle = computed(() => {
  const nextStyle: Record<string, string> = {}

  if (props.layout === 'aspect' && hasValidViewport(props.viewport)) {
    nextStyle.aspectRatio = `${props.viewport.width} / ${props.viewport.height}`
  }

  if (props.minHeight) {
    nextStyle.minHeight = props.minHeight
  }

  return nextStyle
})

/**
 * 判断传入的视口尺寸是否可用于生成合法比例。
 * @param viewport 预览视口
 * @returns 是否同时存在大于 0 的宽高
 */
function hasValidViewport(viewport: Props['viewport']): viewport is NonNullable<Props['viewport']> {
  return Boolean(viewport && viewport.width > 0 && viewport.height > 0)
}

/** 显式重试开始新的恢复周期；实际 artifact 创建由持有原始预览目标的宿主负责。 */
function retryPreview(): void {
  recovery.reset()
  lastErrorFingerprint = ''
  emit('retry')
}

/**
 * 接收当前 iframe 的页面预览终态消息，并校验窗口、来源、协议版本与 artifact。
 * @param event 浏览器窗口消息
 */
function handleWindowMessage(event: MessageEvent<unknown>): void {
  if (!props.frameUrl || !props.artifactId || event.source !== iframeRef.value?.contentWindow) {
    return
  }
  try {
    if (event.origin !== new URL(props.frameUrl).origin) {
      return
    }
  } catch {
    return
  }
  if (!event.data || typeof event.data !== 'object') {
    return
  }

  const message = event.data as Partial<
    PagePreviewReadyMessage | PagePreviewErrorMessage | ComponentPreviewReadyMessage | ComponentPreviewErrorMessage
  >
  if (message.payload?.version !== 1 || message.payload.artifactId !== props.artifactId) {
    return
  }
  if (props.status === 'generating') return
  if (message.type === PAGE_PREVIEW_READY_EVENT || message.type === COMPONENT_PREVIEW_READY_EVENT) {
    localError.value = ''
    lastErrorFingerprint = ''
    recovery.reset()
    emit('ready')
    return
  }
  if (message.type === PAGE_PREVIEW_ERROR_EVENT || message.type === COMPONENT_PREVIEW_ERROR_EVENT) {
    const errorMessage = typeof message.payload.message === 'string' ? message.payload.message : '页面预览加载失败。'
    const code = typeof message.payload.code === 'string' ? message.payload.code : undefined
    const fingerprint = JSON.stringify([message.payload.artifactId, code, errorMessage])
    if (fingerprint === lastErrorFingerprint) return
    lastErrorFingerprint = fingerprint
    localError.value = errorMessage
    emit('error', errorMessage, code)
    recovery.tryRecover(code)
  }
}

onMounted(() => window.addEventListener('message', handleWindowMessage))
onUnmounted(() => window.removeEventListener('message', handleWindowMessage))
</script>
