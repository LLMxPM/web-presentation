<!-- 文件功能：提供紧凑、可键盘操作的互斥分段选择控件。 -->
<template>
  <RadioGroupRoot
    :model-value="modelValue"
    :disabled="disabled"
    orientation="horizontal"
    class="grid rounded-ui-lg bg-surface-muted p-1"
    :style="{ gridTemplateColumns: `repeat(${resolvedColumns}, minmax(0, 1fr))` }"
    @update:model-value="emit('update:modelValue', $event as string)"
  >
    <RadioGroupItem
      v-for="option in options"
      :key="option.value"
      :value="option.value"
      :disabled="option.disabled"
      class="flex h-control-sm min-w-0 items-center justify-center rounded-ui-md px-2 text-xs font-medium text-text-secondary outline-none transition-colors hover:text-text focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-2 focus-visible:ring-offset-canvas data-[state=checked]:bg-surface data-[state=checked]:text-accent data-[state=checked]:shadow-sm disabled:pointer-events-none disabled:opacity-50"
    >
      <span class="truncate">{{ option.label }}</span>
    </RadioGroupItem>
  </RadioGroupRoot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RadioGroupItem, RadioGroupRoot } from 'reka-ui'

/** 分段控件中的单个互斥选项。 */
export interface UiSegmentedOption {
  label: string
  value: string
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  /** 当前选中的分段值。 */
  modelValue: string
  /** 需要展示的分段选项。 */
  options: UiSegmentedOption[]
  /** 固定列数；省略时按选项数均分。 */
  columns?: number
  /** 是否禁用整个控件。 */
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  /** 用户选择新分段时回传对应值。 */
  'update:modelValue': [value: string]
}>()

/** 保证空选项时也有有效的 grid 模板。 */
const resolvedColumns = computed(() => props.columns || Math.max(props.options.length, 1))
</script>
