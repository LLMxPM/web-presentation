<!-- 文件功能：提供后台列表通用分页控件，支持完整模式与紧凑模式两种布局。 -->
<template>
  <div
    class="flex shrink-0 items-center gap-3 border-t border-border-muted bg-surface px-4 py-3 text-xs text-text-muted"
    :class="compact ? 'justify-between' : 'justify-between'"
  >
    <div class="flex min-w-0 items-center gap-2">
      <span class="shrink-0 font-semibold">共 {{ total }} 条</span>
      <template v-if="!compact">
        <span class="text-text-faint">/</span>
        <UiSelect
          :model-value="pageSize"
          :options="pageSizeSelectOptions"
          trigger-class="!h-8 !w-auto !min-w-[5.5rem] !text-xs !font-semibold"
          @update:model-value="handlePageSizeChange"
        />
      </template>
    </div>

    <div class="flex shrink-0 items-center gap-1">
      <button
        type="button"
        class="pagination-button"
        :disabled="page <= 1"
        title="上一页"
        @click="emit('update:page', page - 1)"
      >
        上一页
      </button>

      <template v-if="!compact">
        <button
          v-for="item in pageItems"
          :key="item.key"
          type="button"
          class="pagination-page"
          :class="item.page === page ? 'border-accent-ring bg-surface-selected text-accent' : 'border-border bg-surface text-text-muted hover:border-border-strong hover:text-text-emphasis'"
          :disabled="item.ellipsis"
          @click="item.page && emit('update:page', item.page)"
        >
          {{ item.label }}
        </button>
      </template>
      <span v-else class="px-2 font-semibold text-text-secondary">{{ page }} / {{ pageCount }}</span>

      <button
        type="button"
        class="pagination-button"
        :disabled="page >= pageCount"
        title="下一页"
        @click="emit('update:page', page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UiSelect from './select/UiSelect.vue'
import type { SelectOption } from './select'

const props = withDefaults(defineProps<{
  page: number
  pageSize: number
  total: number
  pageSizeOptions?: number[]
  compact?: boolean
}>(), {
  pageSizeOptions: () => [12, 24, 48, 96],
  compact: false,
})

const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
}>()

const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const pageSizeSelectOptions = computed<SelectOption[]>(() =>
  props.pageSizeOptions.map(size => ({ label: `${size} 条/页`, value: size })),
)

const pageItems = computed(() => {
  const pages = new Set<number>([1, pageCount.value, props.page - 1, props.page, props.page + 1])
  const orderedPages = Array.from(pages)
    .filter(page => page >= 1 && page <= pageCount.value)
    .sort((left, right) => left - right)
  const items: Array<{ key: string; label: string; page: number | null; ellipsis: boolean }> = []
  for (const page of orderedPages) {
    const previous = items[items.length - 1]
    if (previous?.page && page - previous.page > 1) {
      items.push({ key: `ellipsis-${page}`, label: '...', page: null, ellipsis: true })
    }
    items.push({ key: `page-${page}`, label: String(page), page, ellipsis: false })
  }
  return items
})

/**
 * 处理页容量变化，外层负责把页码重置为第一页。
 * @param value 选中的页容量数值
 */
function handlePageSizeChange(value: string | number | (string | number)[] | null): void {
  const numericValue = Number(value)
  emit('update:pageSize', Number.isFinite(numericValue) ? numericValue : props.pageSize)
}
</script>

<style scoped>
.pagination-button {
  height: 32px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ui-border));
  background: rgb(var(--ui-surface));
  padding: 0 10px;
  font-weight: 700;
  color: rgb(var(--ui-text-secondary));
  transition: all 0.16s ease;
}

.pagination-button:hover:not(:disabled) {
  border-color: rgb(var(--ui-border-strong));
  color: rgb(var(--ui-text));
}

.pagination-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.pagination-page {
  min-width: 32px;
  height: 32px;
  border-radius: 8px;
  border-width: 1px;
  padding: 0 8px;
  font-weight: 700;
  transition: all 0.16s ease;
}

.pagination-page:disabled {
  cursor: default;
  color: rgb(var(--ui-text-disabled));
}
</style>
