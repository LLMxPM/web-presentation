<!-- 文件功能：提供库侧栏通用胶囊筛选控件，用于统一标签与二级分类筛选样式。 -->
<template>
  <div class="flex max-h-[5.5rem] min-w-0 flex-1 flex-wrap content-start gap-2 overflow-y-auto pr-1">
    <UiButton
      type="button"
      size="xs"
      :variant="modelValue === allValue ? 'primary' : 'secondary'"
      class="max-w-full truncate rounded-full"
      :title="allLabel"
      @click="selectOption(allValue)"
    >
      {{ allLabel }}
    </UiButton>
    <UiButton
      v-for="option in options"
      :key="option.value"
      type="button"
      size="xs"
      :variant="modelValue === option.value ? 'primary' : 'secondary'"
      class="max-w-full truncate rounded-full"
      :title="option.label"
      @click="selectOption(option.value)"
    >
      {{ option.label }}
    </UiButton>
  </div>
</template>

<script setup lang="ts">
import { UiButton } from '@/components/ui'
export interface LibraryChipOption {
  label: string
  value: string
}

withDefaults(defineProps<{
  modelValue: string
  options: LibraryChipOption[]
  allLabel?: string
  allValue?: string
}>(), {
  allLabel: '全部',
  allValue: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

/**
 * 选中胶囊筛选项，并把筛选值同步给父级业务面板。
 * @param value 胶囊筛选项对应的字符串值
 */
function selectOption(value: string) {
  emit('update:modelValue', value)
}
</script>
