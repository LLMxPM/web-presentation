<!-- 文件功能：渲染页面列表中的新增页面入口，并与普通页面卡片保持一致的预览比例和标题栏结构。 -->
<template>
  <button
    type="button"
    data-testid="page-create-card"
    class="group/create-card relative flex min-w-0 cursor-pointer flex-col overflow-hidden rounded-lg border-2 border-dashed border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))] text-left text-[rgb(var(--ui-text-secondary))] transition-colors duration-150 hover:border-[rgb(var(--ui-accent))] hover:bg-[rgb(var(--ui-surface-hover))] hover:text-[rgb(var(--ui-accent))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))] focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--ui-canvas))]"
    @click="emit('open')"
  >
    <div
      class="flex w-full items-center justify-center bg-[rgb(var(--ui-canvas))]"
      :style="{ aspectRatio: screenshotAspectRatio }"
    >
      <span class="inline-flex h-12 w-12 items-center justify-center rounded-full border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))]">
        <Plus class="h-6 w-6" />
      </span>
    </div>

    <div class="p-3">
      <h3 class="truncate text-sm font-bold leading-tight">新增页面</h3>
    </div>
  </button>
</template>

<script setup lang="ts">
import { Plus } from '@lucide/vue'

defineProps<{
  screenshotAspectRatio: string
}>()

const emit = defineEmits<{
  open: []
}>()
</script>
