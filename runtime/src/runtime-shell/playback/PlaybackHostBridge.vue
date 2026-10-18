<!-- 文件功能：全屏放映的唯一控制条，负责翻页、自动/手动切换、状态提示、演讲与退出。 -->
<template>
  <div v-if="errorMessage" class="runtime-playback-error" role="alert">{{ errorMessage }}</div>
  <div
    class="runtime-playback-controls" role="group" aria-label="放映控制" :data-wake-lock="wakeLockState">
    <template v-if="snapshot">
      <button
        type="button" class="runtime-playback-controls__button" title="上一页" aria-label="上一页"
        :disabled="!canGoPrevious" @click="goPrevious">
        <ChevronLeft :size="16" />
      </button>
      <button
        type="button" class="runtime-playback-controls__button runtime-playback-controls__button--mode"
        data-testid="playback-auto-toggle" :title="autoTitle" @click="toggleAutoAdvance">
        <Timer v-if="snapshot.autoAdvanceEnabled" :size="14" />
        <Hand v-else :size="14" />
        <span>{{ autoLabel }}</span>
      </button>
      <button
        type="button" class="runtime-playback-controls__button" title="下一页" aria-label="下一页"
        :disabled="!canGoNext" @click="goNext">
        <ChevronRight :size="16" />
      </button>

      <span class="runtime-playback-controls__divider" aria-hidden="true"></span>
      <span class="runtime-playback-controls__page">{{ pageLabel }}</span>
      <span class="runtime-playback-controls__state">{{ stateLabel }}</span>
      <span class="runtime-playback-controls__remaining" data-testid="playback-remaining">{{ remainingLabel }}</span>

      <button
        v-if="snapshot.state === 'paused'" type="button"
        class="runtime-playback-controls__button runtime-playback-controls__button--primary"
        title="继续放映（空格）" @click="resume">
        <Play :size="14" />
        <span>继续</span>
      </button>
      <button
        v-else-if="snapshot.state === 'error' || snapshot.state === 'blocked'" type="button"
        class="runtime-playback-controls__button runtime-playback-controls__button--primary"
        title="重试当前页" @click="retry">
        <RotateCcw :size="14" />
        <span>重试</span>
      </button>
      <button
        v-else-if="snapshot.state === 'ended'" type="button"
        class="runtime-playback-controls__button runtime-playback-controls__button--primary"
        title="从当前页重新开始" @click="start">
        <Play :size="14" />
        <span>重新开始</span>
      </button>
    </template>
    <span v-else class="runtime-playback-controls__state">当前项目未启用放映配置</span>

    <span class="runtime-playback-controls__divider" aria-hidden="true"></span>
    <button
      v-if="presenterAvailable" type="button" class="runtime-playback-controls__button"
      title="演讲模式 (Shift+P)" aria-label="进入演讲模式" @click="emit('presenter')">
      <Monitor :size="14" />
    </button>
    <button
      type="button" class="runtime-playback-controls__button" title="退出放映 (Esc)"
      aria-label="退出放映" @click="emit('exit')">
      <Minimize2 :size="14" />
    </button>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, Hand, Minimize2, Monitor, Play, RotateCcw, Timer } from '@lucide/vue'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { usePlaybackHost } from './usePlaybackHost'
import type { PlaybackState } from './playback-controller'

const props = withDefaults(defineProps<{
  /** 进入放映时的初始推进模式；来自项目 auto_start。 */
  initialAutoAdvance?: boolean
  /** 当前项目是否存在可演讲页面。 */
  presenterAvailable?: boolean
}>(), {
  initialAutoAdvance: true,
  presenterAvailable: false,
})

const emit = defineEmits<{
  presenter: []
  exit: []
}>()

const {
  snapshot, errorMessage, wakeLockState, canGoPrevious, canGoNext,
  start, pause, resume, retry, goPrevious, goNext, toggleAutoAdvance, refresh,
} = usePlaybackHost({ autoStart: true, initialAutoAdvance: props.initialAutoAdvance })
const session = getRuntimeSession(useRouter())

/** 进入演讲交接前暂停本窗口放映；观众窗口会从同一页重新开始。 */
onMounted(() => {
  session.pausePlayback = pause
  session.playbackAutoAdvance = () => snapshot.value?.autoAdvanceEnabled ?? props.initialAutoAdvance
})

onBeforeUnmount(() => {
  if (session.pausePlayback === pause) {
    session.pausePlayback = null
  }
  session.playbackAutoAdvance = null
})

const STATE_LABELS: Record<PlaybackState, string> = {
  stopped: '已停止',
  preparing: '准备中',
  playing: '放映中',
  paused: '已暂停',
  ended: '已结束',
  blocked: '受阻',
  error: '错误',
}

const stateLabel = computed(() => {
  const current = snapshot.value
  if (!current) return ''
  if (current.waitingForMedia) return current.state === 'paused' ? '媒体已暂停' : '媒体播放中'
  return STATE_LABELS[current.state]
})

const pageLabel = computed(() => {
  const current = snapshot.value
  if (!current || current.index < 0 || current.total === 0) return '— / —'
  return `${current.index + 1} / ${current.total}`
})

const autoLabel = computed(() => snapshot.value?.autoAdvanceEnabled ? '自动' : '手动')
const autoTitle = computed(() => snapshot.value?.autoAdvanceEnabled
  ? '切换为手动：停止自动翻页，媒体继续播放（空格）'
  : '切换为自动：按当前页配置重新计时（空格）')

const remainingLabel = computed(() => {
  const current = snapshot.value
  if (!current) return ''
  if (current.state === 'ended' || current.state === 'error' || current.state === 'blocked') return '—'
  if (!current.autoAdvanceEnabled) return '手动'
  if (current.effectiveAdvanceMode === 'manual') return '本页手动'
  if (current.waitingForMedia) return '等待媒体'
  if (current.delayMs != null) return formatDuration(current.remainingMs)
  return '手动'
})

/** 将剩余毫秒格式化为 m:ss，向上取整避免显示 0:00 时仍在计时。 */
function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}

let tickTimer: ReturnType<typeof setInterval> | undefined

/** 仅在自动计时页刷新剩余时间；控制条不参与调度。 */
function syncTicker(): void {
  if (tickTimer !== undefined) {
    clearInterval(tickTimer)
    tickTimer = undefined
  }
  if (snapshot.value?.state === 'playing' && snapshot.value.delayMs != null) {
    tickTimer = setInterval(refresh, 250)
  }
}

watch(() => [snapshot.value?.state, snapshot.value?.delayMs], syncTicker, { immediate: true })
onBeforeUnmount(() => {
  if (tickTimer !== undefined) clearInterval(tickTimer)
})
</script>
<style scoped>
.runtime-playback-error {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  max-width: min(680px, calc(100vw - 32px));
  padding: 12px 20px;
  background: #fff;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
  font-size: 14px;
  text-align: center;
}

.runtime-playback-controls {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 9000;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100vw - 32px);
  padding: 8px 14px;
  color: #f8fafc;
  background: rgb(15 23 42 / 82%);
  border: 1px solid rgb(148 163 184 / 22%);
  border-radius: 9999px;
  box-shadow: 0 12px 30px rgb(15 23 42 / 28%);
  backdrop-filter: blur(8px);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.runtime-playback-controls__button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  color: inherit;
  background: rgb(248 250 252 / 10%);
  border: 0;
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
}

.runtime-playback-controls__button:hover:not(:disabled) {
  background: rgb(248 250 252 / 20%);
}

.runtime-playback-controls__button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.runtime-playback-controls__button--primary {
  background: #2563eb;
}

.runtime-playback-controls__button--primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.runtime-playback-controls__button--mode {
  min-width: 4.25rem;
  justify-content: center;
}

.runtime-playback-controls__button:focus-visible {
  outline: 2px solid #93c5fd;
  outline-offset: 2px;
}

.runtime-playback-controls__divider {
  width: 1px;
  height: 18px;
  background: rgb(148 163 184 / 35%);
}

.runtime-playback-controls__page {
  font-weight: 600;
}

.runtime-playback-controls__state {
  color: #cbd5e1;
}

.runtime-playback-controls__remaining {
  min-width: 4.5em;
  text-align: right;
  color: #e2e8f0;
}
</style>
