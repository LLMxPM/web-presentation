<!-- 文件功能：提供页面级操作、视图切换和上下文命令的紧凑工具栏。 -->
<template>
  <div
    class="flex min-w-0 items-center gap-2 overflow-x-auto rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))] px-2 py-1.5 [scrollbar-width:thin]"
    role="toolbar"
    :aria-label="label"
  >
    <div v-if="$slots.leading" class="flex shrink-0 items-center gap-2"><slot name="leading" /></div>
    <div class="flex min-w-0 flex-1 items-center gap-2"><slot /></div>
    <div v-if="$slots.actions" class="ml-auto flex shrink-0 items-center gap-1.5"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** 为屏幕阅读器说明当前工具栏的操作范围。 */
  label?: string
}>(), {
  label: '页面操作',
})
</script>
