<!-- 文件功能：提供组件库同款的紧凑搜索输入，支持前置搜索图标、输入框内清除按钮与提交事件。 -->
<template>
  <div class="group relative">
    <Search
      class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-disabled transition-colors group-focus-within:text-accent-emphasis"
    />
    <input
      :value="modelValue"
      type="text"
      :placeholder="placeholder"
      :aria-label="ariaLabel || placeholder"
      class="h-8 w-full rounded-lg border border-border bg-surface pl-9 pr-9 text-xs transition-all focus:border-border-focus focus:outline-none focus:ring-1 focus:ring-border-focus"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown.enter="emit('submit')"
    >
    <button
      v-if="modelValue"
      type="button"
      class="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-text-disabled transition-colors hover:bg-surface-muted hover:text-text-secondary"
      aria-label="清空搜索"
      @click="emit('update:modelValue', '')"
    >
      <X class="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { Search, X } from '@lucide/vue'

withDefaults(defineProps<{
  /** 当前搜索词，通过 v-model 与外层筛选状态同步。 */
  modelValue: string
  /** 搜索框为空时展示的操作提示。 */
  placeholder?: string
  /** 覆盖占位文本的无障碍名称。 */
  ariaLabel?: string
}>(), {
  placeholder: '搜索...',
  ariaLabel: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  /** 用户在搜索框按下回车，供需要请求服务端筛选的页面刷新数据。 */
  submit: []
}>()
</script>
