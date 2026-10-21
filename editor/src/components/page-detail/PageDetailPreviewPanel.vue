<!-- 文件功能：渲染页面详情的 Runtime 预览画布，保持主区域聚焦在实际页面效果。 -->
<template>
  <ToolPanel class="group relative h-full min-h-0 bg-[rgb(var(--ui-surface-muted))]" :scroll-body="false">
    <div class="absolute right-5 top-5 z-10 flex items-center gap-2 opacity-0 shadow-popover backdrop-blur transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100">
      <UiIconButton
        label="刷新预览"
        :disabled="!props.previewFrameUrl"
        @click="emit('refresh')"
      >
        <RefreshCw class="h-4 w-4" />
      </UiIconButton>

      <UiIconButton
        label="放大查看"
        :disabled="!props.previewFrameUrl"
        @click="openPreviewDialog"
      >
        <Maximize2 class="h-4 w-4" />
      </UiIconButton>

      <UiIconButton
        :label="props.speakerNotesPanelOpen ? '关闭备注' : '打开备注'"
        @click="emit('toggleSpeakerNotes')"
      >
        <FileText class="h-4 w-4" />
      </UiIconButton>
    </div>

    <RuntimePreviewFrame
      ref="previewFrameRef"
      auto-recover
      :frame-url="activePreviewFrameUrl"
      title="runtime-preview"
      :viewport="props.previewViewport"
      :artifact-id="props.previewArtifactId"
      :status="props.previewStatus"
      :status-message="props.previewStatusMessage"
      layout="fill"
      container-class="h-full overflow-hidden bg-surface"
      :empty-title="currentPreviewEmptyTitle"
      :empty-description="currentPreviewEmptyDescription"
      @ready="emit('preview-ready')"
      @error="(message, code) => emit('preview-error', message, code)"
      @motion-state="handleMotionState"
      @retry="emit('retry')"
      @renew="emit('renew', $event)"
    />

    <div
      v-if="motionState?.hasTimeline"
      data-testid="preview-motion-controls"
      class="absolute inset-x-4 bottom-4 z-10 flex flex-wrap items-center gap-2 rounded-ui-lg border border-border bg-surface/95 px-3 py-2 shadow-popover backdrop-blur"
    >
      <UiIconButton
        size="sm"
        variant="secondary"
        :label="motionPlaying ? '暂停页内时间轴' : '播放页内时间轴'"
        @click="toggleMotionPlayback"
      >
        <Pause v-if="motionPlaying" class="h-4 w-4" />
        <Play v-else class="h-4 w-4" />
      </UiIconButton>
      <UiIconButton size="sm" variant="ghost" label="从起点重播页内时间轴" @click="restartMotion">
        <RotateCcw class="h-4 w-4" />
      </UiIconButton>
      <UiInput
        class="!h-1.5 min-w-24 flex-1 cursor-pointer !border-0 !bg-transparent !p-0 accent-[rgb(var(--ui-accent))]"
        type="range"
        min="0"
        :max="Math.max(1, motionState.durationMs)"
        step="10"
        :model-value="motionSeekMs"
        aria-label="页内时间轴位置"
        @update:model-value="beginMotionScrub"
        @change="commitMotionSeek"
      />
      <span class="font-mono text-xs text-text-muted">
        {{ formatMotionTime(motionState.positionMs) }} / {{ formatMotionTime(motionState.durationMs) }}
      </span>
      <UiButton
        size="sm"
        :variant="motionState.visualMode === 'reduced' ? 'primary' : 'ghost'"
        :aria-pressed="motionState.visualMode === 'reduced'"
        title="仅影响当前预览的视觉映射"
        @click="toggleMotionVisualMode"
      >
        降动效
      </UiButton>
      <span v-if="motionState.errorMessage" class="min-w-0 truncate text-xs font-medium text-danger" role="status">
        {{ motionState.errorMessage }}
      </span>
    </div>

    <UiDialog
      :open="isPreviewDialogOpen"
      :title="previewDialogTitle"
      size="workbench"
      body-preset="immersive"
      overlay-class="bg-overlay/70 backdrop-blur-sm"
      @update:open="isPreviewDialogOpen = $event"
    >
      <div class="h-full min-h-0 bg-surface-muted p-3">
        <RuntimePreviewFrame
          v-if="props.previewFrameUrl"
          auto-recover
          :frame-url="activePreviewFrameUrl"
          title="runtime-preview-dialog"
          :viewport="props.previewViewport"
          :artifact-id="props.previewArtifactId"
          :status="props.previewStatus"
          :status-message="props.previewStatusMessage"
          layout="fill"
          container-class="h-full overflow-hidden rounded-xl border border-border bg-surface shadow-sm"
          @ready="emit('preview-ready')"
          @error="(message, code) => emit('preview-error', message, code)"
          @retry="emit('retry')"
          @renew="emit('renew', $event)"
        />
      </div>
    </UiDialog>
  </ToolPanel>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FileText, Maximize2, Pause, Play, RefreshCw, RotateCcw } from '@lucide/vue'

import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiButton, UiDialog, UiIconButton, UiInput } from '@/components/ui'
import type { PreviewMotionState, PreviewMotionVisualMode, RuntimePreviewStatus } from '@/types/runtime-preview'

interface Props {
  previewEnabled: boolean
  previewUrl: string
  previewFrameUrl: string
  previewArtifactId: string
  previewStatus: RuntimePreviewStatus
  previewStatusMessage: string
  previewViewport: {
    width: number
    height: number
  }
  pageTitle: string
  previewDisplayFileName: string
  speakerNotesPanelOpen: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  refresh: []
  'preview-ready': []
  'preview-error': [message: string, code?: string]
  retry: []
  renew: [newUrl: string]
  toggleSpeakerNotes: []
}>()

const isPreviewDialogOpen = ref(false)
const motionState = ref<PreviewMotionState | null>(null)
const motionSeekMs = ref(0)
const motionScrubbing = ref(false)
let motionSeekTimer: number | null = null

interface RuntimePreviewMotionApi {
  playMotion: () => void
  pauseMotion: () => void
  restartMotion: () => void
  seekMotion: (positionMs: number) => void
  setMotionVisualMode: (mode: PreviewMotionVisualMode) => void
  syncMotion: () => void
}

const previewFrameRef = ref<RuntimePreviewMotionApi | null>(null)
const motionPlaying = computed(() => motionState.value?.intent === 'playing')

watch(
  () => motionState.value?.positionMs,
  positionMs => {
    if (!motionScrubbing.value && typeof positionMs === 'number') {
      motionSeekMs.value = positionMs
    }
  },
)

/** 缓存 Runtime 回传状态；无时间轴时直接隐藏控制条。 */
function handleMotionState(state: PreviewMotionState): void {
  motionState.value = state
}

/** 播放按钮在播放中暂停，其余状态从当前页起点或暂停点继续。 */
function toggleMotionPlayback(): void {
  if (motionPlaying.value) {
    previewFrameRef.value?.pauseMotion()
  } else {
    previewFrameRef.value?.playMotion()
  }
}

function restartMotion(): void {
  previewFrameRef.value?.restartMotion()
}

/** 拖动期间只更新本地位置，停顿后发送一次 seek，避免逐像素定位媒体。 */
function beginMotionScrub(value: string | number): void {
  motionScrubbing.value = true
  const next = Number(value)
  if (!Number.isFinite(next)) return
  motionSeekMs.value = next
  if (motionSeekTimer !== null) window.clearTimeout(motionSeekTimer)
  motionSeekTimer = window.setTimeout(() => {
    motionSeekTimer = null
    motionScrubbing.value = false
    previewFrameRef.value?.seekMotion(motionSeekMs.value)
  }, 120)
}

function commitMotionSeek(): void {
  if (motionSeekTimer !== null) {
    window.clearTimeout(motionSeekTimer)
    motionSeekTimer = null
  }
  motionScrubbing.value = false
  previewFrameRef.value?.seekMotion(motionSeekMs.value)
}

onBeforeUnmount(() => {
  if (motionSeekTimer !== null) window.clearTimeout(motionSeekTimer)
})

/** 降动效偏好只作用于当前预览，不修改用户系统设置或项目配置。 */
function toggleMotionVisualMode(): void {
  const next: PreviewMotionVisualMode = motionState.value?.visualMode === 'reduced' ? 'full' : 'reduced'
  previewFrameRef.value?.setMotionVisualMode(next)
}

/** 把毫秒格式化为 mm:ss，供预览控制条展示。 */
function formatMotionTime(value: number): string {
  const seconds = Math.max(0, Math.round((Number.isFinite(value) ? value : 0) / 1000))
  const minutes = Math.floor(seconds / 60)
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

const previewDialogTitle = computed(() => (
  props.previewDisplayFileName ? `Runtime 预览 · ${props.previewDisplayFileName}` : `Runtime 预览 · ${props.pageTitle}`
))

const activePreviewFrameUrl = computed(() => (
  props.previewEnabled && props.previewUrl ? props.previewFrameUrl : ''
))

const currentPreviewEmptyTitle = computed(() => (
  props.previewEnabled ? '预览尚未生成' : '预览不可用'
))

const currentPreviewEmptyDescription = computed(() => (
  props.previewEnabled
    ? '保存后会自动把当前页面推送到 Runtime，并在这里刷新展示最新结果。'
    : '当前页面暂时没有可用的 Runtime 预览地址。'
))

/**
 * 打开放大的 Runtime 预览弹窗，仅在已生成预览地址时生效。
 */
function openPreviewDialog(): void {
  if (!props.previewFrameUrl) return
  isPreviewDialogOpen.value = true
}

</script>
