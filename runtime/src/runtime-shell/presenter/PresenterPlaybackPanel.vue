<!--
  文件用途：演讲者控制台的唯一传输栏，回显观众放映状态并发送翻页、自动/手动与失败恢复命令。
-->
<template>
  <section class="presenter-playback-panel" aria-label="观众放映状态">
    <div class="presenter-playback-panel__transport">
      <button
        type="button" class="presenter-playback-panel__icon-button"
        title="上一页" aria-label="上一页"
        :disabled="!displayAvailable || !canGoPrevious" @click="emit('previous')">
        <ChevronLeft :size="14" />
      </button>
      <button
        type="button" class="presenter-playback-panel__button presenter-playback-panel__button--mode"
        data-testid="presenter-playback-auto"
        :title="autoAdvanceEnabled ? '切换为手动：停止自动翻页，媒体继续播放' : '切换为自动：按当前页配置重新计时'"
        :disabled="!displayAvailable" @click="emit('auto', !autoAdvanceEnabled)">
        <span>{{ autoAdvanceEnabled ? '自动' : '手动' }}</span>
      </button>
      <button
        type="button" class="presenter-playback-panel__icon-button"
        title="下一页" aria-label="下一页"
        :disabled="!displayAvailable || !canGoNext" @click="emit('next')">
        <ChevronRight :size="14" />
      </button>

      <span class="presenter-playback-panel__page" data-testid="presenter-playback-page">{{ pageLabel }}</span>
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
import { ChevronLeft, ChevronRight } from '@lucide/vue'

import type {
  PresenterSyncPlaybackCommandAction,
  ReceivedPresenterSync,
} from './presenter-sync-protocol'

const props = defineProps<{
  playback: ReceivedPresenterSync | null
  displayAvailable: boolean
  canGoPrevious: boolean
  canGoNext: boolean
  pageLabel: string
}>()

const emit = defineEmits<{
  command: [action: PresenterSyncPlaybackCommandAction]
  previous: []
  next: []
  auto: [enabled: boolean]
}>()

const nowMs = ref(Date.now())
let tickerId: ReturnType<typeof setInterval> | undefined
const snapshot = computed(() => {
  const message = props.playback?.message
  return message && 'playback' in message ? message.playback : null
})
const autoAdvanceEnabled = computed(() => snapshot.value?.autoAdvanceEnabled ?? false)

const stateLabel = computed(() => {
  if (!props.displayAvailable) return '等待观众窗口全屏'
  const current = snapshot.value
  if (!current) return '等待观众窗口'
  if (current.timelinePhase === 'buffering') return '时间轴缓冲'
  if (current.waitingForTimeline) return current.state === 'paused' ? '时间轴已暂停' : '时间轴播放中'
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
  if (!current.autoAdvanceEnabled) return '手动'
  if (current.delayMs != null) return formatDuration(remainingMs.value)
  if (current.waitingForTimeline) return '等待时间轴'
  return current.waitingForMedia ? '等待媒体' : '本页手动'
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
  min-height: 2.25rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.375rem 0.5rem;
  background: #f8fafc;
}

.presenter-playback-panel__transport {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.375rem;
  min-width: 0;
}

.presenter-playback-panel__page {
  padding: 0 0.25rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
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

.presenter-playback-panel__button,
.presenter-playback-panel__icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
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

.presenter-playback-panel__icon-button {
  width: 1.75rem;
  padding: 0;
}

.presenter-playback-panel__button--mode {
  min-width: 3.5rem;
}

.presenter-playback-panel__button:disabled,
.presenter-playback-panel__icon-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
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
