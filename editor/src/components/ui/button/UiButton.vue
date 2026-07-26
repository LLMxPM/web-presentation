<!-- 文件功能：提供 Editor 统一的文字按钮，处理变体、尺寸、加载和禁用状态。 -->
<template>
  <button
    :class="buttonClass"
    :disabled="isDisabled"
    :aria-busy="loading || undefined"
    :data-loading="loading || undefined"
    v-bind="$attrs"
  >
    <span v-if="loading" class="absolute inset-0 inline-flex items-center justify-center" aria-hidden="true">
      <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" />
        <path class="opacity-75" fill="currentColor" d="M12 3a9 9 0 0 0-9 9h3a6 6 0 0 1 6-6V3Z" />
      </svg>
    </span>
    <span :class="contentClass">
      <slot name="icon" />
      <slot />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// 根元素已显式 v-bind="$attrs"，关闭自动继承，避免 class 与事件监听器被绑定两次。
defineOptions({ inheritAttrs: false })

/** 按钮可用的视觉层级。 */
type UiButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

/** 按钮可用的紧凑尺寸。 */
type UiButtonSize = 'xs' | 'sm' | 'md' | 'lg'

/** 按钮内容在可用宽度内的对齐方式。 */
type UiButtonContentAlign = 'center' | 'start' | 'between'

const props = withDefaults(defineProps<{
  /** 按钮的语义层级。 */
  variant?: UiButtonVariant
  /** 按钮视觉高度。 */
  size?: UiButtonSize
  /** 是否显示加载态；加载时按钮不可重复触发。 */
  loading?: boolean
  /** 是否禁用按钮。 */
  disabled?: boolean
  /** 内容对齐方式；start 和 between 会让内容层占满按钮宽度。 */
  contentAlign?: UiButtonContentAlign
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  contentAlign: 'center',
})

const isDisabled = computed(() => props.disabled || props.loading)

/** 根据对齐 API 生成按钮内部内容层样式，避免业务组件覆盖内部 slot 结构。 */
const contentClass = computed(() => [
  'inline-flex items-center gap-1.5',
  {
    'justify-center': props.contentAlign === 'center',
    'w-full justify-start': props.contentAlign === 'start',
    'w-full justify-between': props.contentAlign === 'between',
    'opacity-0': props.loading,
  },
])

/** 根据稳定的组件 Token 组合按钮样式。 */
const buttonClass = computed(() => [
  'relative inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-[var(--ui-radius-md)] border px-3 text-sm font-medium transition-colors duration-150',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))] focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--ui-canvas))]',
  'disabled:pointer-events-none disabled:opacity-50',
  {
    'h-[var(--ui-control-h-xs)] px-2 text-xs': props.size === 'xs',
    'h-[var(--ui-control-h-sm)] px-2.5 text-xs': props.size === 'sm',
    'h-[var(--ui-control-h-md)]': props.size === 'md',
    'h-[var(--ui-control-h-lg)] px-4 text-base': props.size === 'lg',
    'border-[rgb(var(--ui-accent))] bg-[rgb(var(--ui-accent))] text-[rgb(var(--ui-text-inverse))] hover:bg-[rgb(var(--ui-accent-hover))]': props.variant === 'primary',
    'border-[rgb(var(--ui-border-strong))] bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-text))] hover:bg-[rgb(var(--ui-surface-hover))]': props.variant === 'secondary',
    'border-transparent bg-transparent text-[rgb(var(--ui-text-secondary))] hover:bg-[rgb(var(--ui-surface-hover))] hover:text-[rgb(var(--ui-text))]': props.variant === 'ghost',
    'border-[rgb(var(--ui-danger))] bg-[rgb(var(--ui-danger))] text-[rgb(var(--ui-text-inverse))] hover:brightness-95': props.variant === 'danger',
  },
])
</script>
