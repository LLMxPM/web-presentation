<!-- 文件功能：为普通与放大预览复用 Scene 播放/停止和状态提示，不提供时间轴暂停或定位。 -->
<template>
  <div v-if="state?.hasScene || state?.issue" data-testid="preview-scene-controls"
    class="absolute inset-x-4 bottom-4 z-10 flex flex-wrap items-center gap-2 rounded-ui-lg border border-border bg-surface/95 px-3 py-2 shadow-popover backdrop-blur">
    <UiIconButton size="sm" variant="secondary" label="播放页内 Scene" :disabled="active || !state.hasScene" @click="emit('play')"><Play class="h-4 w-4" /></UiIconButton>
    <UiIconButton size="sm" variant="ghost" label="停止页内 Scene" :disabled="!active" @click="emit('stop')"><Square class="h-4 w-4" /></UiIconButton>
    <span class="text-xs text-text-muted">{{ phaseLabel }}</span>
    <span v-if="state.issue" class="min-w-0 truncate text-xs font-medium text-danger" role="status">{{ state.issue.message }}</span>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { Play, Square } from '@lucide/vue'
import { UiIconButton } from '@/components/ui'
import type { PreviewSceneState } from '@/types/runtime-preview'
const props = defineProps<{ state: PreviewSceneState | null }>()
const emit = defineEmits<{ play: []; stop: [] }>()
const active = computed(() => Boolean(props.state?.phase && ['preparing', 'ready', 'running', 'blocked', 'completed'].includes(props.state.phase)))
const phaseLabel = computed(() => {
  const phase = props.state?.phase
  return phase ? ({ idle: '未播放', preparing: '准备中', ready: '已就绪', running: '播放中', blocked: '等待页面恢复', completed: '有限任务已完成', failed: '播放失败', stopped: '已停止' })[phase] : ''
})
</script>
