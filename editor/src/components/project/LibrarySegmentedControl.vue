<!-- 文件功能：提供库侧栏通用分段选择控件，用于统一分类、类型与页签样式。 -->
<template>
  <div
    class="grid rounded-xl bg-slate-100 p-1"
    :style="{ gridTemplateColumns: `repeat(${resolvedColumns}, minmax(0, 1fr))` }"
  >
    <button
      v-for="option in options"
      :key="option.value || 'all'"
      type="button"
      class="h-8 min-w-0 rounded-lg px-2 text-xs font-bold transition-colors"
      :class="modelValue === option.value
        ? 'bg-white text-indigo-600 shadow-sm'
        : 'text-slate-500 hover:text-slate-800'"
      @click="selectOption(option.value)"
    >
      <span class="block truncate">{{ option.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface LibrarySegmentedOption {
  label: string
  value: string
}

const props = defineProps<{
  modelValue: string
  options: LibrarySegmentedOption[]
  columns?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const resolvedColumns = computed(() => props.columns || Math.max(props.options.length, 1))

/**
 * 选中某个分段项，并把值同步给父级业务面板。
 * @param value 分段项对应的字符串值
 */
function selectOption(value: string) {
  emit('update:modelValue', value)
}
</script>
