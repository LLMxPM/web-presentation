<!-- 文件功能：提供带图标的紧凑分段选择控件，用于图标化的互斥选项切换。 -->
<template>
  <div
    class="gap-0.5 rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface-muted))]"
    :class="[
      fluid ? 'flex w-full flex-wrap' : 'inline-flex items-center',
      size === 'xs' ? 'p-px' : 'p-0.5',
    ]"
    role="group"
    :aria-label="ariaLabel"
  >
    <button
      v-for="option in options"
      :key="String(option.value)"
      type="button"
      class="inline-flex items-center justify-center rounded-[var(--ui-radius-md)] text-[rgb(var(--ui-text-secondary))] transition-all duration-150 hover:text-[rgb(var(--ui-text))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))] focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--ui-canvas))]"
      :class="[
        heightClass,
        fluid ? 'min-w-6 flex-1' : widthClass,
        modelValue === option.value
          ? 'bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-accent))] shadow-sm'
          : '',
      ]"
      :aria-pressed="modelValue === option.value"
      :aria-label="option.label"
      :title="option.label"
      @click="emit('update:model-value', option.value)"
    >
      <component :is="option.icon" :class="iconClass" />
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends string | number">
import { computed, type Component } from 'vue'

export interface IconSegmentedOption<T = string | number> {
  value: T
  label: string
  icon: Component
}

const props = withDefaults(defineProps<{
  modelValue: T
  options: IconSegmentedOption<T>[]
  /** 可访问性标签 */
  ariaLabel?: string
  /** 尺寸 */
  size?: 'xs' | 'sm' | 'md'
  /** 是否撑满容器并均分按钮宽度；窄容器下自动换行，避免图标溢出 */
  fluid?: boolean
}>(), {
  ariaLabel: '选项切换',
  size: 'sm',
  fluid: false,
})

const emit = defineEmits<{
  'update:model-value': [value: T]
}>()

/** 按钮高度随尺寸变化，fluid 模式下宽度交由容器均分。 */
const heightClass = computed(() => ({
  'h-[var(--ui-control-h-xs)]': props.size === 'xs',
  'h-[var(--ui-control-h-sm)]': props.size === 'sm',
  'h-[var(--ui-control-h-md)]': props.size === 'md',
}))

/** 非 fluid 模式下按钮保持正方形点击区。 */
const widthClass = computed(() => ({
  'w-[var(--ui-control-h-xs)]': props.size === 'xs',
  'w-[var(--ui-control-h-sm)]': props.size === 'sm',
  'w-[var(--ui-control-h-md)]': props.size === 'md',
}))

const iconClass = computed(() => ({
  'h-3 w-3': props.size === 'xs',
  'h-3.5 w-3.5': props.size === 'sm',
  'h-4 w-4': props.size === 'md',
}))
</script>
