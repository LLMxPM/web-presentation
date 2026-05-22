<!-- 文件功能：提供库侧栏通用胶囊筛选控件，用于统一标签与二级分类筛选样式。 -->
<template>
  <div class="flex max-h-[5.5rem] min-w-0 flex-1 flex-wrap content-start gap-2 overflow-y-auto pr-1">
    <button
      type="button"
      class="max-w-full truncate rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors"
      :title="allLabel"
      :class="modelValue === allValue
        ? 'bg-indigo-600 text-white'
        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
      @click="selectOption(allValue)"
    >
      {{ allLabel }}
    </button>
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="max-w-full truncate rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors"
      :title="option.label"
      :class="modelValue === option.value
        ? 'bg-indigo-600 text-white'
        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
      @click="selectOption(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
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
