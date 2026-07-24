<!-- 文件功能：基于 Reka UI 提供可键盘操作的单选组选项。 -->
<template>
  <RadioGroupRoot
    :model-value="modelValue"
    :disabled="disabled"
    :orientation="orientation"
    class="grid gap-2 data-[orientation=horizontal]:flex data-[orientation=horizontal]:flex-wrap data-[disabled]:cursor-not-allowed"
    @update:model-value="emit('update:modelValue', $event as string)"
  >
    <label
      v-for="option in options"
      :key="option.value"
      class="flex min-w-0 items-start gap-2 text-sm text-text-secondary"
      :class="{ 'cursor-pointer': !disabled && !option.disabled, 'cursor-not-allowed opacity-50': disabled || option.disabled }"
    >
      <RadioGroupItem
        :value="option.value"
        :disabled="option.disabled"
        :aria-label="option.label"
        class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-2 focus-visible:ring-offset-canvas data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:pointer-events-none"
      >
        <RadioGroupIndicator class="h-1.5 w-1.5 rounded-full bg-text-inverse" />
      </RadioGroupItem>
      <span class="grid min-w-0 gap-0.5">
        <span class="text-text">{{ option.label }}</span>
        <span v-if="option.description" class="text-xs text-text-muted">{{ option.description }}</span>
      </span>
    </label>
  </RadioGroupRoot>
</template>

<script setup lang="ts">
import { RadioGroupIndicator, RadioGroupItem, RadioGroupRoot } from 'reka-ui'

/** 单选项的显示信息及禁用状态。 */
export interface UiRadioOption {
  label: string
  value: string
  description?: string
  disabled?: boolean
}

withDefaults(defineProps<{
  /** 当前选中的选项值。 */
  modelValue: string
  /** 需要展示的互斥选项。 */
  options: UiRadioOption[]
  /** 整组是否不可操作。 */
  disabled?: boolean
  /** 选项的键盘导航方向。 */
  orientation?: 'horizontal' | 'vertical'
}>(), {
  disabled: false,
  orientation: 'vertical',
})

const emit = defineEmits<{
  /** 用户选择新选项时回传对应值。 */
  'update:modelValue': [value: string]
}>()
</script>
