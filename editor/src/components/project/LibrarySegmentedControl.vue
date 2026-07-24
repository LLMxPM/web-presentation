<!-- 文件功能：提供库侧栏通用分段选择控件，用于统一分类、类型与页签样式。 -->
<template>
  <UiSegmentedControl
    :model-value="modelValue"
    :options="options"
    :columns="columns"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
import { UiSegmentedControl } from '@/components/ui'

export interface LibrarySegmentedOption {
  label: string
  value: string
}

defineProps<{
  modelValue: string
  options: LibrarySegmentedOption[]
  columns?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

</script>
