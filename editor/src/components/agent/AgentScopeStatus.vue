<!-- 文件功能：渲染内容助手活跃 Run 的当前任务焦点状态。 -->
<template>
  <div class="agent-scope-status relative isolate inline-flex h-7 min-w-0 max-w-[176px] items-center gap-1.5 rounded-ui-md border border-info-border bg-info-muted px-1.5 text-xs text-info-strong" :title="tooltip" role="status">
    <span class="relative inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-ui-sm bg-surface/80">
      <Crosshair class="agent-scope-status__icon h-3 w-3" />
    </span>
    <span class="shrink-0 text-[10px] font-semibold">{{ typeLabel }}</span>
    <span class="h-3 w-px shrink-0 bg-info-border" />
    <span class="min-w-0 truncate text-[11px] font-semibold text-text-emphasis">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { Crosshair } from '@lucide/vue'

defineProps<{
  typeLabel: string
  label: string
  tooltip: string
}>()
</script>

<style scoped>
.agent-scope-status::after {
  position: absolute;
  z-index: -1;
  inset: -2px;
  border: 1px solid rgb(var(--ui-info-border));
  border-radius: calc(var(--ui-radius-md) + 2px);
  box-shadow: 0 0 0 1px rgb(var(--ui-info) / 0.08);
  content: '';
  pointer-events: none;
  animation: agent-scope-breathe 2.8s ease-in-out infinite;
}

.agent-scope-status__icon {
  transform-origin: center;
  animation: agent-scope-icon-breathe 2.8s ease-in-out infinite;
}

@keyframes agent-scope-breathe {
  0%,
  100% {
    opacity: 0.18;
    transform: scale(0.99);
  }

  50% {
    opacity: 0.62;
    transform: scale(1.01);
  }
}

@keyframes agent-scope-icon-breathe {
  0%,
  100% {
    opacity: 0.72;
    transform: scale(0.88);
  }

  50% {
    opacity: 1;
    transform: scale(1.08);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-scope-status::after,
  .agent-scope-status__icon {
    animation: none;
  }
}
</style>
