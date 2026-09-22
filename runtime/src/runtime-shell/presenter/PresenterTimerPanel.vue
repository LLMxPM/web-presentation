<!--
  文件用途：演讲者控制台计时面板，提供开始/暂停、重置、当前页计时和总计时展示。
-->

<template>
  <section class="presenter-timer-panel" data-testid="presenter-timer-panel" aria-label="演讲计时">
    <div class="presenter-timer-panel__metrics">
      <div class="presenter-timer-panel__metric">
        <span class="presenter-timer-panel__label">当前</span>
        <strong class="presenter-timer-panel__value" data-testid="presenter-timer-current">
          {{ currentPageElapsedLabel }}
        </strong>
      </div>
      <div class="presenter-timer-panel__metric">
        <span class="presenter-timer-panel__label">总计时</span>
        <strong class="presenter-timer-panel__value" data-testid="presenter-timer-total">
          {{ totalElapsedLabel }}
        </strong>
      </div>
    </div>

    <div class="presenter-timer-panel__actions">
      <button
        type="button"
        class="presenter-timer-panel__button presenter-timer-panel__button--primary"
        data-testid="presenter-timer-toggle"
        :aria-label="isRunning ? '暂停计时' : '开始计时'"
        :title="isRunning ? '暂停计时' : '开始计时'"
        @click="toggleTimer"
      >
        <component :is="isRunning ? Pause : Play" class="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        class="presenter-timer-panel__button"
        data-testid="presenter-timer-reset"
        aria-label="重置计时"
        title="重置计时"
        @click="resetTimer"
      >
        <RotateCcw class="h-3.5 w-3.5" />
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Pause, Play, RotateCcw } from '@lucide/vue'

interface PresenterTimerPanelProps {
  currentPath: string
}

const props = defineProps<PresenterTimerPanelProps>()
const isRunning = ref(false)
const totalElapsedBeforeRunMs = ref(0)
const currentPageElapsedBeforeRunMs = ref(0)
const totalRunStartedAt = ref<number | null>(null)
const currentPageRunStartedAt = ref<number | null>(null)
const nowMs = ref(Date.now())

let tickerId: number | null = null

const currentPageElapsedMs = computed(() => currentPageElapsedBeforeRunMs.value + resolveActiveElapsedMs(currentPageRunStartedAt.value))
const totalElapsedMs = computed(() => totalElapsedBeforeRunMs.value + resolveActiveElapsedMs(totalRunStartedAt.value))
const currentPageElapsedLabel = computed(() => formatElapsedTime(currentPageElapsedMs.value))
const totalElapsedLabel = computed(() => formatElapsedTime(totalElapsedMs.value))

watch(() => props.currentPath, () => {
  resetCurrentPageTimer()
})

onUnmounted(() => {
  stopTicker()
})

/**
 * 切换计时状态；运行中暂停，暂停时继续计时。
 */
function toggleTimer(): void {
  if (isRunning.value) {
    pauseTimer()
    return
  }
  startTimer()
}

/**
 * 启动或恢复计时。
 * 约束：只在当前未运行时生效，并保留既有累计时长。
 */
function startTimer(): void {
  if (isRunning.value) {
    return
  }
  syncNow()
  isRunning.value = true
  totalRunStartedAt.value = nowMs.value
  currentPageRunStartedAt.value = nowMs.value
  ensureTicker()
}

/**
 * 暂停计时，并把本轮运行时长折算进累计值。
 */
function pauseTimer(): void {
  if (!isRunning.value) {
    return
  }
  syncNow()
  totalElapsedBeforeRunMs.value += resolveActiveElapsedMs(totalRunStartedAt.value)
  currentPageElapsedBeforeRunMs.value += resolveActiveElapsedMs(currentPageRunStartedAt.value)
  totalRunStartedAt.value = null
  currentPageRunStartedAt.value = null
  isRunning.value = false
  stopTicker()
}

/**
 * 重置总计时和当前页计时。
 * 约束：若当前正在计时，则从归零后的当前时刻继续计时。
 */
function resetTimer(): void {
  syncNow()
  totalElapsedBeforeRunMs.value = 0
  currentPageElapsedBeforeRunMs.value = 0
  totalRunStartedAt.value = isRunning.value ? nowMs.value : null
  currentPageRunStartedAt.value = isRunning.value ? nowMs.value : null
  if (!isRunning.value) {
    stopTicker()
  }
}

/**
 * 页面切换时重置当前页计时，总计时保持不变。
 */
function resetCurrentPageTimer(): void {
  syncNow()
  currentPageElapsedBeforeRunMs.value = 0
  currentPageRunStartedAt.value = isRunning.value ? nowMs.value : null
}

/**
 * 计算当前运行片段的增量时长。
 * @param startedAt 本轮计时起点时间戳
 * @returns 当前起点到现在的毫秒差；未运行时返回 0
 */
function resolveActiveElapsedMs(startedAt: number | null): number {
  if (!isRunning.value || startedAt === null) {
    return 0
  }
  return Math.max(nowMs.value - startedAt, 0)
}

/**
 * 同步当前时间，用于刷新计时展示。
 */
function syncNow(): void {
  nowMs.value = Date.now()
}

/**
 * 确保计时刷新定时器存在。
 * 约束：只创建一个定时器，避免重复刷新。
 */
function ensureTicker(): void {
  if (tickerId !== null) {
    return
  }
  tickerId = window.setInterval(() => {
    syncNow()
  }, 1000)
}

/**
 * 清理计时刷新定时器。
 */
function stopTicker(): void {
  if (tickerId === null) {
    return
  }
  window.clearInterval(tickerId)
  tickerId = null
}

/**
 * 格式化计时值。
 * @param elapsedMs 计时毫秒值
 * @returns 固定为 HH:MM:SS 的字符串
 */
function formatElapsedTime(elapsedMs: number): string {
  const totalSeconds = Math.max(Math.floor(elapsedMs / 1000), 0)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  return [hours, minutes, seconds]
    .map(value => String(value).padStart(2, '0'))
    .join(':')
}
</script>

<style scoped>
.presenter-timer-panel {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  width: 100%;
  min-width: 0;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
  background: white;
  padding: 0.375rem 0.5rem;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.presenter-timer-panel__metrics {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  min-width: 0;
  gap: 0.5rem;
}

.presenter-timer-panel__metric {
  display: flex;
  align-items: baseline;
  min-width: 0;
  gap: 0.25rem;
}

.presenter-timer-panel__label {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1;
}

.presenter-timer-panel__value {
  color: #0f172a;
  font-family: Monaco, 'Source Code Pro', monospace;
  font-size: 1.0625rem;
  font-weight: 800;
  line-height: 1.1;
  white-space: nowrap;
}

.presenter-timer-panel__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.25rem;
}

.presenter-timer-panel__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.875rem;
  height: 1.875rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  background: white;
  padding: 0;
  color: #334155;
  cursor: pointer;
}

.presenter-timer-panel__button--primary {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #3730a3;
}
</style>
