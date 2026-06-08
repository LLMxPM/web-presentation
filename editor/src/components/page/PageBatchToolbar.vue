<!-- 文件功能：渲染页面列表分区的批量选择入口与批量操作工具条。 -->
<template>
  <button
    v-if="batchableCount > 0"
    :data-testid="`batch-${scope}-select-all`"
    type="button"
    role="checkbox"
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
  </button>

  <div v-if="selectedCount > 0" class="batch-toolbar">
    <span class="batch-toolbar-count">
      已选 {{ selectedCount }}
      <span v-if="batchProgressText" class="batch-toolbar-progress">· {{ batchProgressText }}</span>
    </span>
    <button
      v-if="scope === 'routed'"
      type="button"
      data-testid="batch-routed-remove-route"
      class="batch-toolbar-action"
      :disabled="batchActionPending !== null"
      @click="emit('batch-remove-route')"
    >
      <RouteOff class="h-3.5 w-3.5" />
      移出路由
    </button>
    <button
      v-else
      type="button"
      data-testid="batch-unrouted-add-route"
      class="batch-toolbar-action"
      :disabled="batchActionPending !== null"
      @click="emit('batch-add-route')"
    >
      <ListPlus class="h-3.5 w-3.5" />
      加入路由
    </button>
    <button
      type="button"
      :data-testid="`batch-${scope}-screenshot`"
      class="batch-toolbar-action"
      :disabled="batchActionPending !== null"
      @click="emit('batch-download-screenshots')"
    >
      <LoaderCircle v-if="batchActionPending === 'download-screenshot'" class="h-3.5 w-3.5 animate-spin" />
      <Download v-else class="h-3.5 w-3.5" />
      {{ batchActionPending === 'download-screenshot' ? '处理中' : '下载截图' }}
    </button>
    <button
      type="button"
      :data-testid="`batch-${scope}-copy`"
      class="batch-toolbar-action"
      :disabled="batchActionPending !== null"
      @click="emit('open-batch-copy')"
    >
      <Copy class="h-3.5 w-3.5" />
      复制
    </button>
    <button
      type="button"
      :data-testid="`batch-${scope}-archive`"
      class="batch-toolbar-action text-amber-700 hover:bg-amber-50"
      :disabled="batchActionPending !== null"
      @click="emit('batch-archive-pages')"
    >
      <Archive class="h-3.5 w-3.5" />
      归档
    </button>
    <button
      type="button"
      class="batch-toolbar-icon"
      title="清空选择"
      :aria-label="scope === 'routed' ? '清空已加入路由选择' : '清空未加入路由选择'"
      @click="emit('clear-selection')"
    >
      <X class="h-3.5 w-3.5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { Archive, Check, Copy, Download, ListPlus, LoaderCircle, RouteOff, X } from '@lucide/vue'

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

.batch-toolbar {
  display: flex;
  min-width: 0;
  max-width: 100%;
  flex: 1 1 auto;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.4rem;
  overflow-x: auto;
  overflow-y: hidden;
  border-radius: 1rem;
  border: 1px solid rgb(226 232 240);
  background: white;
  padding: 0.3rem;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
  scrollbar-width: none;
}

.batch-toolbar::-webkit-scrollbar {
  display: none;
}

.batch-toolbar-count {
  flex: 0 0 auto;
  padding: 0 0.4rem;
  white-space: nowrap;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(100 116 139);
}

.batch-toolbar-progress {
  color: rgb(79 70 229);
}

.batch-toolbar-action,
.batch-toolbar-icon {
  display: inline-flex;
  flex: 0 0 auto;
  height: 2rem;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  white-space: nowrap;
  border-radius: 0.5rem;
  padding: 0 0.55rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(71 85 105);
  transition: all 0.2s ease;
}

.batch-toolbar-icon {
  width: 2rem;
  padding: 0;
}

.batch-toolbar-action:hover,
.batch-toolbar-icon:hover {
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.batch-toolbar-action:disabled,
.batch-toolbar-icon:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
