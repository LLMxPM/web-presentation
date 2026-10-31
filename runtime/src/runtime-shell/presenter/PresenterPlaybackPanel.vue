<!-- 文件功能：展示观众原子状态，只提供开始、停止、保持、释放和失败重试，不计算第二份播放进度。 -->
<template>
  <section class="presenter-playback-panel">
    <div class="presenter-playback-panel__transport">
      <button type="button" class="presenter-playback-panel__icon-button" aria-label="上一页" :disabled="!displayAvailable || !canGoPrevious" @click="emit('previous')"><ChevronLeft :size="14" /></button>
      <button type="button" class="presenter-playback-panel__button" data-testid="presenter-playback-hold" :disabled="!displayAvailable || !active" @click="emit('command', playback?.held ? 'release' : 'hold')">{{ playback?.held ? '释放当前页' : '保持当前页' }}</button>
      <button type="button" class="presenter-playback-panel__icon-button" aria-label="下一页" :disabled="!displayAvailable || !canGoNext" @click="emit('next')"><ChevronRight :size="14" /></button>
      <span class="presenter-playback-panel__page">{{ pageLabel }}</span>
      <strong data-testid="presenter-playback-state">{{ stateLabel }}</strong>
    </div>
    <p v-if="playback?.issue" class="text-xs" role="status">{{ playback.issue.message }}</p>
    <p v-if="playback?.phase === 'blocked'" class="text-xs">请在观众窗口点击允许播放；控制台无法代替该窗口授予媒体许可。</p>
    <div v-if="displayAvailable" class="presenter-playback-panel__actions">
      <button v-if="!playback || ['stopped', 'ended'].includes(playback.phase)" type="button" data-testid="presenter-playback-primary" class="presenter-playback-panel__button" @click="emit('command', 'start')">开始放映</button>
      <button v-if="playback?.phase === 'failed'" type="button" class="presenter-playback-panel__button" @click="emit('command', 'retry')">重试失败页</button>
      <button v-if="active || playback?.phase === 'failed'" type="button" data-testid="presenter-playback-stop" class="presenter-playback-panel__button" @click="emit('command', 'stop')">停止</button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import type { PresenterStateMessage, PresenterSyncIntentAction } from './presenter-sync-protocol'
const props = defineProps<{ playback: PresenterStateMessage | null; displayAvailable: boolean; canGoPrevious: boolean; canGoNext: boolean; pageLabel: string }>()
const emit = defineEmits<{ command: [action: PresenterSyncIntentAction]; previous: []; next: [] }>()
const active = computed(() => Boolean(props.playback && ['preparing', 'playing', 'blocked'].includes(props.playback.phase)))
const stateLabel = computed(() => {
  if (!props.displayAvailable) return '等待观众窗口全屏'
  if (props.playback?.held) return '保持当前页，页内播放继续'
  return ({ stopped: '未开始', preparing: '准备中', playing: '放映中', blocked: '受阻', failed: '失败', ended: '已结束', closed: '观众窗口已关闭' } as const)[props.playback?.phase ?? 'stopped']
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
