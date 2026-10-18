<!-- 文件功能：放映主画布的调度入口、控制条与可见错误提示。 -->
<template>
  <div v-if="errorMessage" class="runtime-playback-error" role="alert">{{ errorMessage }}</div>
  <div
    v-if="snapshot" class="runtime-playback-controls" role="group" aria-label="放映控制"
    :data-wake-lock="wakeLockState">
    <button
      type="button" class="runtime-playback-controls__button runtime-playback-controls__button--primary"
      :title="primaryAction.title" aria-keyshortcuts="Space" @click="handlePrimaryAction">
      <Pause v-if="primaryAction.icon === 'pause'" :size="16" />
      <Play v-else :size="16" />
      <span>{{ primaryAction.label }}</span>
    </button>
    <button
      v-if="canNextPage" type="button" class="runtime-playback-controls__button"
      title="跳到下一页并继续放映" aria-label="跳到下一页" @click="next">
      <ChevronRight :size="14" />
      <span>下一页</span>
    </button>
    <button
      v-if="canStop" type="button" class="runtime-playback-controls__button"
      title="停止放映，保留当前页" aria-label="停止放映" @click="stop">
      <Square :size="14" />
    </button>
    <span class="runtime-playback-controls__divider" aria-hidden="true"></span>
    <span class="runtime-playback-controls__page">{{ pageLabel }}</span>
    <span class="runtime-playback-controls__state">{{ stateLabel }}</span>
    <span class="runtime-playback-controls__remaining">{{ remainingLabel }}</span>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronRight, Pause, Play, Square } from '@lucide/vue'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { usePlaybackHost } from './usePlaybackHost'
import type { PlaybackState } from './playback-controller'

const { snapshot, errorMessage, wakeLockState, start, pause, resume, stop, retry, next, refresh } = usePlaybackHost()
const session = getRuntimeSession(useRouter())

/** 进入演讲模式前由会话调用，先停住普通窗口推进和媒体。 */
function pauseForPresenterHandoff(): void {
  pause()
}

onMounted(() => {
  session.pausePlayback = pauseForPresenterHandoff
})

onBeforeUnmount(() => {
  if (session.pausePlayback === pauseForPresenterHandoff) {
    session.pausePlayback = null
  }
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

const primaryAction = computed<{ label: string; title: string; icon: 'play' | 'pause' }>(() => {
  const state = snapshot.value?.state
  if (state === 'paused') return { label: '继续', title: '继续放映（空格）', icon: 'play' }
  if (state === 'preparing' || state === 'playing') return { label: '暂停', title: '暂停放映（空格）', icon: 'pause' }
  if (state === 'error' || state === 'blocked') return { label: '重试', title: '重试当前页（空格）', icon: 'play' }
  return { label: state === 'ended' ? '重新开始' : '开始放映', title: '开始放映（空格）', icon: 'play' }
})

const canStop = computed(() => {
  const state = snapshot.value?.state
  return state === 'preparing' || state === 'playing' || state === 'paused' || state === 'blocked' || state === 'error'
})

/** 失败态允许直接跳过当前页；末页不循环时没有下一页。 */
const canNextPage = computed(() => {
  const current = snapshot.value
  if (!current || (current.state !== 'blocked' && current.state !== 'error')) return false
  if (current.index < 0) return false
  return current.index < current.total - 1 || current.loop
})

const remainingLabel = computed(() => {
  const current = snapshot.value
  if (!current) return ''
  if (current.state === 'preparing' || current.state === 'playing' || current.state === 'paused') {
    if (current.delayMs != null) return formatDuration(current.remainingMs)
    return current.advanceMode === 'media_end' ? '媒体' : '手动'
  }
  return '—'
})

/** 将剩余毫秒格式化为 m:ss，向上取整避免显示 0:00 时仍在计时。 */
function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}

function handlePrimaryAction(): void {
  const state = snapshot.value?.state
  if (state === 'paused') {
    resume()
    return
  }
  if (state === 'preparing' || state === 'playing') {
    pause()
    return
  }
  if (state === 'error' || state === 'blocked') {
    retry()
    return
  }
  start()
}

let tickTimer: ReturnType<typeof setInterval> | undefined

/** 仅在计时页放映中刷新剩余时间；控制条不参与调度。 */
function syncTicker(): void {
  if (tickTimer !== undefined) {
    clearInterval(tickTimer)
    tickTimer = undefined
  }
  if (snapshot.value?.state === 'playing' && snapshot.value.delayMs != null) {
    tickTimer = setInterval(refresh, 250)
  }
}

watch(() => snapshot.value?.state, syncTicker, { immediate: true })
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
  padding: 12px 20px;
  background: #fff;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
  font-size: 14px;
}

.runtime-playback-controls {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 9000;
  display: flex;
  align-items: center;
  gap: 10px;
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

.runtime-playback-controls__button:hover {
  background: rgb(248 250 252 / 20%);
}

.runtime-playback-controls__button--primary {
  background: #2563eb;
}

.runtime-playback-controls__button--primary:hover {
  background: #1d4ed8;
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
  min-width: 3.5em;
  text-align: right;
  color: #e2e8f0;
}
</style>
