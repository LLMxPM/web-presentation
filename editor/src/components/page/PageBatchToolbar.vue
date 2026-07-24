<!-- 文件功能：渲染页面列表分区的批量选择入口与批量操作工具条。 -->
<template>
  <UiButton
    v-if="batchableCount > 0"
    :data-testid="`batch-${scope}-select-all`"
    type="button"
    role="checkbox"
    variant="ghost"
    size="sm"
    class="batch-select-toggle"
    :class="isAllSelected ? 'batch-select-toggle-active' : ''"
    :aria-checked="isAllSelected"
    @mousedown.prevent
    @click="emit('select-all-change', !isAllSelected)"
  >
    <span class="batch-select-box">
      <Check v-if="isAllSelected" class="h-3 w-3" />
    </span>
    <span>{{ isAllSelected ? '已全选' : '全选' }}</span>
  </UiButton>

  <SelectionToolbar
    :visible="selectedCount > 0"
    :count="selectedCount"
    :label="scope === 'routed' ? '已加入路由页面的批量操作' : '未加入路由页面的批量操作'"
    @clear="emit('clear-selection')"
  >
    <span class="sr-only">已选 {{ selectedCount }}</span>
    <span v-if="batchProgressText" class="text-xs text-[rgb(var(--ui-accent))]">{{ batchProgressText }}</span>
    <UiButton
      v-if="scope === 'routed'"
      data-testid="batch-routed-remove-route"
      variant="secondary"
      size="sm"
      :disabled="batchActionPending !== null"
      @click="emit('batch-remove-route')"
    >
      <RouteOff class="h-3.5 w-3.5" />
      移出路由
    </UiButton>
    <UiButton
      v-else
      data-testid="batch-unrouted-add-route"
      variant="secondary"
      size="sm"
      :disabled="batchActionPending !== null"
      @click="emit('batch-add-route')"
    >
      <ListPlus class="h-3.5 w-3.5" />
      加入路由
    </UiButton>
    <UiButton
      :data-testid="`batch-${scope}-screenshot`"
      variant="ghost"
      size="sm"
      :disabled="batchActionPending !== null"
      @click="emit('batch-download-screenshots')"
    >
      <LoaderCircle v-if="batchActionPending === 'download-screenshot'" class="h-3.5 w-3.5 animate-spin" />
      <Download v-else class="h-3.5 w-3.5" />
      {{ batchActionPending === 'download-screenshot' ? '处理中' : '下载截图' }}
    </UiButton>
    <UiButton
      :data-testid="`batch-${scope}-copy`"
      variant="ghost"
      size="sm"
      :disabled="batchActionPending !== null"
      @click="emit('open-batch-copy')"
    >
      <Copy class="h-3.5 w-3.5" />
      复制
    </UiButton>
    <UiButton
      :data-testid="`batch-${scope}-archive`"
      variant="danger"
      size="sm"
      :disabled="batchActionPending !== null"
      @click="emit('batch-archive-pages')"
    >
      <Archive class="h-3.5 w-3.5" />
      归档
    </UiButton>
  </SelectionToolbar>
</template>

<script setup lang="ts">
import { Archive, Check, Copy, Download, ListPlus, LoaderCircle, RouteOff } from '@lucide/vue'

import SelectionToolbar from '@/components/patterns/SelectionToolbar.vue'
import { UiButton } from '@/components/ui'
import type { PageBatchAction, PageBatchScope } from './page-list-types'

defineProps<{
  scope: PageBatchScope
  batchableCount: number
  isAllSelected: boolean
  selectedCount: number
  batchActionPending: PageBatchAction | null
  batchProgressText?: string | null
}>()

const emit = defineEmits<{
  'select-all-change': [checked: boolean]
  'batch-add-route': []
  'batch-remove-route': []
  'batch-download-screenshots': []
  'open-batch-copy': []
  'batch-archive-pages': []
  'clear-selection': []
}>()
</script>

<style scoped>
.batch-select-toggle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.45rem;
  min-height: 2.125rem;
  border-radius: 9999px;
  border: 1px solid rgb(226 232 240);
  background: white;
  padding: 0.35rem 0.75rem 0.35rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(71 85 105);
  cursor: pointer;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
  transition: all 0.18s ease;
}

.batch-select-toggle:hover,
.batch-select-toggle-active {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.batch-select-box {
  display: inline-flex;
  height: 1rem;
  width: 1rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgb(148 163 184);
  background: white;
  color: white;
}

.batch-select-toggle-active .batch-select-box {
  border-color: rgb(79 70 229);
  background: rgb(79 70 229);
}

</style>
