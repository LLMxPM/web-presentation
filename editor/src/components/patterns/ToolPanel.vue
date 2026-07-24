<!-- 文件功能：提供工具侧栏固定头部、工具栏、独立滚动正文和页脚的稳定骨架。 -->
<template>
  <section class="flex min-h-0 flex-col overflow-hidden rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))]" :aria-labelledby="titleId">
    <header v-if="title || $slots.header" class="shrink-0 border-b border-[rgb(var(--ui-border))] px-3 py-2.5">
      <slot name="header">
        <h2 :id="titleId" class="text-title-sm font-semibold text-[rgb(var(--ui-text))]">{{ title }}</h2>
        <p v-if="description" class="mt-0.5 text-xs text-[rgb(var(--ui-text-muted))]">{{ description }}</p>
      </slot>
    </header>
    <div v-if="$slots.toolbar" class="shrink-0 border-b border-[rgb(var(--ui-border))] px-2 py-1.5"><slot name="toolbar" /></div>
    <div :class="bodyClass"><slot /></div>
    <footer v-if="$slots.footer" class="shrink-0 border-t border-[rgb(var(--ui-border))] px-3 py-2"><slot name="footer" /></footer>
  </section>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(defineProps<{
  /** 面板标题；自定义 header 插槽时可省略。 */
  title?: string
  /** 标题下的辅助说明。 */
  description?: string
  /** 正文是否独立滚动，默认适用于侧栏和检查器。 */
  scrollBody?: boolean
}>(), {
  scrollBody: true,
})

const titleId = useId()
const bodyClass = computed(() => [
  'min-h-0 flex-1 p-3',
  props.scrollBody ? 'overflow-auto' : '',
])
</script>
