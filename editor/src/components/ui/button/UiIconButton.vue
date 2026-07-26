<!-- 文件功能：提供带可访问名称的统一纯图标按钮。 -->
<template>
  <button
    :class="buttonClass"
    :disabled="disabled || loading"
    :aria-label="label"
    :aria-busy="loading || undefined"
    :title="title ?? label"
    v-bind="$attrs"
  >
    <span v-if="loading" class="absolute inset-0 inline-flex items-center justify-center" aria-hidden="true">
      <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" />
        <path class="opacity-75" fill="currentColor" d="M12 3a9 9 0 0 0-9 9h3a6 6 0 0 1 6-6V3Z" />
      </svg>
    </span>
    <span :class="{ 'opacity-0': loading }"><slot /></span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// 根元素已显式 v-bind="$attrs"，关闭自动继承，避免 class 与事件监听器被绑定两次。
defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  /** 供读屏和原生 Tooltip 使用的操作名称。 */
  label: string
  /** 覆盖默认原生 Tooltip 的文本。 */
  title?: string
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
}>(), {
  variant: 'ghost',
  size: 'md',
  loading: false,
  disabled: false,
})

/** 图标按钮保持方形点击区，尺寸与 UiButton 一致。 */
const buttonClass = computed(() => [
  'relative inline-flex shrink-0 items-center justify-center rounded-[var(--ui-radius-md)] border transition-colors duration-150',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))] focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--ui-canvas))]',
  'disabled:pointer-events-none disabled:opacity-50',
  {
    'h-[var(--ui-control-h-xs)] w-[var(--ui-control-h-xs)] [&_svg]:h-3.5 [&_svg]:w-3.5': props.size === 'xs',
    'h-[var(--ui-control-h-sm)] w-[var(--ui-control-h-sm)] [&_svg]:h-4 [&_svg]:w-4': props.size === 'sm',
    'h-[var(--ui-control-h-md)] w-[var(--ui-control-h-md)] [&_svg]:h-4 [&_svg]:w-4': props.size === 'md',
    'h-[var(--ui-control-h-lg)] w-[var(--ui-control-h-lg)] [&_svg]:h-5 [&_svg]:w-5': props.size === 'lg',
    'border-[rgb(var(--ui-accent))] bg-[rgb(var(--ui-accent))] text-[rgb(var(--ui-text-inverse))] hover:bg-[rgb(var(--ui-accent-hover))]': props.variant === 'primary',
    'border-[rgb(var(--ui-border-strong))] bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-text))] hover:bg-[rgb(var(--ui-surface-hover))]': props.variant === 'secondary',
    'border-transparent bg-transparent text-[rgb(var(--ui-text-secondary))] hover:bg-[rgb(var(--ui-surface-hover))] hover:text-[rgb(var(--ui-text))]': props.variant === 'ghost',
    'border-[rgb(var(--ui-danger))] bg-[rgb(var(--ui-danger))] text-[rgb(var(--ui-text-inverse))] hover:brightness-95': props.variant === 'danger',
  },
])
</script>
