<!-- 文件功能：在内容助手空闲状态下展示紧凑的 Web-Presentation 品牌标题。 -->
<template>
  <div class="inline-flex min-w-0 max-w-full items-center gap-2" aria-label="Web-Presentation">
    <span class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-ui-md border border-ai-border bg-ai-muted text-ai-strong shadow-sm">
      <Presentation class="h-3.5 w-3.5" />
    </span>
    <span class="min-w-0 truncate text-sm font-bold tracking-tight text-text-emphasis">
      Web<span class="text-ai-strong">-Presentation</span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { Presentation } from '@lucide/vue'
</script>
