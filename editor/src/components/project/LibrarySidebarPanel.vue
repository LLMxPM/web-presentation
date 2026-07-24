<!-- 文件功能：提供资源库、组件库与主题库共用的侧边栏外壳，统一标题栏、搜索栏和关闭行为。 -->
<template>
  <div
    v-show="modelValue"
    class="relative flex h-full min-h-0 w-[400px] shrink-0 flex-col overflow-hidden border-l border-slate-200 bg-white transition-all duration-300"
  >
    <div class="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2.5">
      <div class="flex min-w-0 items-center gap-2">
        <slot name="icon" />
        <h2 class="truncate text-base font-bold text-slate-800">{{ title }}</h2>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <slot name="actions" />
        <UiIconButton
          v-if="showClose"
          type="button"
          label="关闭侧栏"
          @click="closePanel"
        >
          <X class="h-4 w-4" />
        </UiIconButton>
      </div>
    </div>

    <div v-if="showSearch" class="shrink-0 border-b border-slate-50 bg-slate-50/50 px-3 py-2">
      <SimpleSearchBar v-model="searchText" :placeholder="searchPlaceholder" />
    </div>

    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import { UiIconButton } from '@/components/ui'

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

</script>
