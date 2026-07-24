<!-- 文件功能：提供实体类型、版本和状态使用的紧凑语义标签。 -->
<template>
  <span :class="badgeClass"><slot /></span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 标签表达的语义状态。 */
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'
  /** 是否使用更紧凑的字号与内边距。 */
  size?: 'sm' | 'md'
}>(), {
  tone: 'neutral',
  size: 'sm',
})

const badgeClass = computed(() => [
  'inline-flex items-center gap-1 whitespace-nowrap rounded-[var(--ui-radius-sm)] border font-medium',
  props.size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm',
  {
    'border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface-muted))] text-[rgb(var(--ui-text-secondary))]': props.tone === 'neutral',
    'border-[rgb(var(--ui-accent-muted))] bg-[rgb(var(--ui-accent-muted))] text-[rgb(var(--ui-accent))]': props.tone === 'accent',
    'border-[rgb(var(--ui-success-muted))] bg-[rgb(var(--ui-success-muted))] text-[rgb(var(--ui-success))]': props.tone === 'success',
    'border-[rgb(var(--ui-warning-muted))] bg-[rgb(var(--ui-warning-muted))] text-[rgb(var(--ui-warning))]': props.tone === 'warning',
    'border-[rgb(var(--ui-danger-muted))] bg-[rgb(var(--ui-danger-muted))] text-[rgb(var(--ui-danger))]': props.tone === 'danger',
    'border-[rgb(var(--ui-info-muted))] bg-[rgb(var(--ui-info-muted))] text-[rgb(var(--ui-info))]': props.tone === 'info',
  },
])
</script>
