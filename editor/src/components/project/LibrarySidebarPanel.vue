<!-- 文件功能：提供资源库、组件库与主题库共用的侧边栏外壳，统一标题栏、搜索栏和关闭行为。 -->
<template>
  <div
    v-show="modelValue"
    class="relative flex h-full min-h-0 w-[430px] shrink-0 flex-col overflow-hidden border-l border-slate-200 bg-white transition-all duration-300"
  >
    <div class="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-3">
      <div class="flex min-w-0 items-center gap-2">
        <slot name="icon" />
        <h2 class="truncate text-base font-bold text-slate-800">{{ title }}</h2>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <slot name="actions" />
        <button
          v-if="showClose"
          type="button"
          class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          title="关闭侧栏"
          @click="closePanel"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div v-if="showSearch" class="shrink-0 border-b border-slate-50 bg-slate-50/50 px-4 py-2">
      <div class="group relative">
        <Search
          class="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500"
        />
        <input
          v-model="searchText"
          type="text"
          :placeholder="searchPlaceholder"
          class="h-9 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-9 text-xs transition-all focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          v-if="searchText"
          type="button"
          class="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          title="清空搜索"
          @click="clearSearch"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Search, X } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  searchValue?: string
  searchPlaceholder?: string
  showSearch?: boolean
  showClose?: boolean
}>(), {
  searchValue: '',
  searchPlaceholder: '搜索...',
  showSearch: false,
  showClose: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:searchValue': [value: string]
}>()

const searchText = computed({
  get: () => props.searchValue,
  set: value => emit('update:searchValue', value),
})

/**
 * 关闭当前库侧栏，并把状态同步给外层布局。
 */
function closePanel() {
  emit('update:modelValue', false)
}

/**
 * 清空搜索关键字，恢复当前库侧栏的完整列表。
 */
function clearSearch() {
  searchText.value = ''
}
</script>
