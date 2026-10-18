<!--
  文件用途：控制台回显观众窗口放映状态与剩余时间，并发送开始、暂停、继续和失败恢复命令。
-->

<template>
  <section class="presenter-playback-panel" aria-label="观众放映状态">
    <div class="presenter-playback-panel__metrics">
      <span class="presenter-playback-panel__label">观众放映</span>
      <strong class="presenter-playback-panel__state" data-testid="presenter-playback-state">
        {{ stateLabel }}
      </strong>
      <span class="presenter-playback-panel__remaining" data-testid="presenter-playback-remaining">
        {{ remainingLabel }}
      </span>
    </div>

    <div class="presenter-playback-panel__actions">
      <button
        v-if="primaryAction"
        type="button"
        class="presenter-playback-panel__button presenter-playback-panel__button--primary"
        data-testid="presenter-playback-primary"
        @click="emit('command', primaryAction.command)"
      >
        {{ primaryAction.label }}
      </button>
      <button
        v-if="showNext"
        type="button"
        class="presenter-playback-panel__button"
        data-testid="presenter-playback-next"
        @click="emit('command', 'next')"
      >
        下一页
      </button>
      <button
        v-if="showStop"
        type="button"
        class="presenter-playback-panel__button presenter-playback-panel__button--danger"
        data-testid="presenter-playback-stop"
        @click="emit('command', 'stop')"
      >
        停止
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import type {
  PresenterSyncPlaybackCommandAction,
  ReceivedPresenterSync,
} from './presenter-sync-protocol'

const props = defineProps<{
  playback: ReceivedPresenterSync | null
  displayAvailable: boolean
}>()

const emit = defineEmits<{
  command: [action: PresenterSyncPlaybackCommandAction]
}>()

const nowMs = ref(Date.now())
let tickerId: ReturnType<typeof setInterval> | undefined
const snapshot = computed(() => {
  const message = props.playback?.message
  return message && 'playback' in message ? message.playback : null
})

const stateLabel = computed(() => {
  if (!props.displayAvailable) return '已暂停（观众窗口未连接）'
  const current = snapshot.value
  if (!current) return '等待观众窗口'
  if (current.waitingForMedia) return current.state === 'paused' ? '媒体已暂停' : '媒体播放中'
  switch (current.state) {
    case 'preparing':
      return '准备中'
    case 'playing':
      return '放映中'
    case 'paused':
      return '已暂停'
    case 'ended':
      return '已结束'
    case 'blocked':
      return '受阻'
    case 'error':
      return '错误'
    default:
      return '未开始'
  }
})

const remainingMs = computed(() => {
  const current = snapshot.value
  if (!current) return 0
  if (current.state === 'playing' && props.playback?.deadline != null) {
    return Math.max(0, props.playback.deadline - nowMs.value)
  }
  return current.remainingMs
})

const remainingLabel = computed(() => {
  const current = snapshot.value
  if (!props.displayAvailable || !current) return '—'
  if (current.state === 'preparing' || current.state === 'playing' || current.state === 'paused') {
    if (current.delayMs != null) return formatDuration(remainingMs.value)
    return current.waitingForMedia ? '媒体' : '手动'
  }
  return '—'
})

const primaryAction = computed<{ label: string; command: PresenterSyncPlaybackCommandAction } | null>(() => {
  if (!props.displayAvailable) return null
  switch (snapshot.value?.state) {
    case 'stopped':
    case 'ended':
      return { label: '开始放映', command: 'start' }
    case 'preparing':
    case 'playing':
      return { label: '暂停', command: 'pause' }
    case 'paused':
      return { label: '继续', command: 'resume' }
    case 'blocked':
    case 'error':
      return { label: '重试', command: 'retry' }
    default:
      return null
  }
})

const showNext = computed(() => {
  if (!props.displayAvailable) return false
  const current = snapshot.value
  if (!current || (current.state !== 'blocked' && current.state !== 'error')) return false
  return current.index >= 0 && current.index < current.total - 1
})

const showStop = computed(() => {
  if (!props.displayAvailable) return false
  const state = snapshot.value?.state
  return state === 'preparing'
    || state === 'playing'
    || state === 'paused'
    || state === 'blocked'
    || state === 'error'
})

/** 仅在观众窗口计时播放时刷新本地倒计时；本组件不推进页面。 */
function syncTicker(): void {
  nowMs.value = Date.now()
  if (tickerId !== undefined) {
    clearInterval(tickerId)
    tickerId = undefined
  }
  if (snapshot.value?.state === 'playing' && snapshot.value.delayMs != null) {
    tickerId = setInterval(() => {
      nowMs.value = Date.now()
    }, 250)
  }
}

/** 把毫秒格式化为 m:ss，向上取整避免显示 0:00 时仍在计时。 */
function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}

watch([() => snapshot.value?.state, () => snapshot.value?.delayMs], syncTicker, { immediate: true })

onBeforeUnmount(() => {
  if (tickerId !== undefined) clearInterval(tickerId)
})
</script>

<style scoped>
.presenter-playback-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-height: 2rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.375rem 0.5rem;
  background: #f8fafc;
}

.presenter-playback-panel__metrics {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-width: 0;
}

.presenter-playback-panel__label {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
}

.presenter-playback-panel__state {
  color: #0f172a;
  font-size: 0.75rem;
  font-weight: 800;
}

.presenter-playback-panel__remaining {
  min-width: 3.25em;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.presenter-playback-panel__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.presenter-playback-panel__button {
  height: 1.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  padding: 0 0.625rem;
  color: #334155;
  background: white;
  font-size: 0.75rem;
  font-weight: 800;
  cursor: pointer;
}

.presenter-playback-panel__button--primary {
  border-color: #4338ca;
  color: white;
  background: #4f46e5;
}

.presenter-playback-panel__button--danger {
  border-color: #fecaca;
  color: #b91c1c;
  background: #fff1f2;
}
</style>
