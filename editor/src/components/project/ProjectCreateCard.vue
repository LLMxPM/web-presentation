<!-- 文件功能：渲染项目列表中的新增项目入口卡片，与 ProjectCard 保持一致的圆角与最小高度。 -->
<template>
  <button
    type="button"
    data-testid="project-create-card"
    class="group flex min-h-[13.75rem] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[rgb(var(--ui-border-strong))] bg-[rgb(var(--ui-surface-muted))] p-6 text-center transition-colors hover:border-[rgb(var(--ui-accent))] hover:bg-[rgb(var(--ui-accent-muted))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))] focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--ui-canvas))]"
    @click="emit('open')"
  >
    <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-text-muted))] shadow-sm transition-colors group-hover:bg-[rgb(var(--ui-accent))] group-hover:text-[rgb(var(--ui-text-inverse))]">
      <Plus class="h-7 w-7" />
    </div>
    <span class="text-base font-semibold text-[rgb(var(--ui-text))]">新增项目</span>
    <span class="mt-1 text-sm text-[rgb(var(--ui-text-secondary))]">创建新的演示内容集合</span>
  </button>
</template>

<script setup lang="ts">
import { Plus } from '@lucide/vue'

const emit = defineEmits<{
  /** 用户点击新增入口时触发。 */
  open: []
}>()
</script>
