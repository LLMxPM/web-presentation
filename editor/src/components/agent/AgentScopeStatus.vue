<!-- 文件功能：渲染内容助手活跃 Run 的当前任务焦点状态。 -->
<template>
  <div class="inline-flex h-7 min-w-0 max-w-[176px] items-center gap-1.5 rounded-ui-md border border-info-border bg-info-muted px-1.5 text-xs text-info-strong" :title="tooltip" role="status">
    <span class="relative inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-ui-sm bg-surface/80">
      <Crosshair class="h-3 w-3" />
      <span class="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-info ring-1 ring-surface" aria-hidden="true" />
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
