<!-- 文件功能：渲染智能体会话范围与当前路由范围提示。 -->
<template>
  <div class="flex min-w-0 items-center gap-2 text-xs">
    <div class="flex min-w-0 max-w-[180px] items-center gap-1.5" :title="activeSessionScopeTooltip">
      <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border bg-surface text-text-disabled">
        <MessageCircle class="h-3 w-3" />
      </span>
      <span class="inline-flex h-6 min-w-0 items-center truncate rounded-md border px-2 text-[11px] font-semibold leading-none" :class="activeSessionScopeSummary.colorClass">
        {{ activeSessionScopeSummary.title }}
      </span>
    </div>
    <span class="h-3.5 w-px shrink-0 bg-border" />
    <div class="flex min-w-0 max-w-[180px] items-center gap-1.5" :title="routeScopeTooltip">
      <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border bg-surface text-text-disabled">
        <MapPin class="h-3 w-3" />
      </span>
      <span class="inline-flex h-6 min-w-0 items-center truncate rounded-md border px-2 text-[11px] font-semibold leading-none" :class="routeScopeSummary.colorClass">
        {{ routeScopeSummary.title }}
      </span>
    </div>
    <span
      v-if="!currentRouteInActiveSessionScope"
      class="inline-flex h-6 shrink-0 items-center rounded-md border border-warning-border bg-warning-muted px-2 text-[10px] font-semibold leading-none text-warning-strong"
    >
      不在范围
    </span>
  </div>
</template>

<script setup lang="ts">
import { MapPin, MessageCircle } from '@lucide/vue'

import type { ScopeSummary } from '@/components/agent/agent-session-scope'

defineProps<{
  activeSessionScopeSummary: ScopeSummary
  activeSessionScopeTooltip: string
  routeScopeSummary: ScopeSummary
  routeScopeTooltip: string
  currentRouteInActiveSessionScope: boolean
}>()
</script>
