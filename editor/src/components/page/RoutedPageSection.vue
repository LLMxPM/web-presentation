<!-- 文件功能：渲染已加入路由的页面分区，包括分区操作、批量工具条和路由页面卡片列表。 -->
<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-bold text-slate-900">已加入路由</h2>
        <span class="text-xs font-semibold text-slate-400">{{ entries.length }} 条路由绑定</span>
      </div>
      <div class="flex min-w-0 flex-wrap items-center justify-end gap-2">
        <BaseButton
          v-if="selectedCount === 0"
          data-testid="batch-refresh-routed-page-screenshots"
          variant="ghost"
          size="sm"
          :loading="batchScreenshotRefreshScope === 'routed'"
          :disabled="!projectReady || refreshableScreenshotCount === 0 || screenshotPendingPageId !== null || batchScreenshotRefreshing"
          @click="emit('refresh-screenshots')"
        >
          <template #icon>
            <RefreshCw class="h-3.5 w-3.5" />
          </template>
          刷新截图
          <span v-if="refreshableScreenshotCount > 0">({{ refreshableScreenshotCount }})</span>
        </BaseButton>
        <BaseButton
          v-if="selectedCount === 0"
          variant="ghost"
          size="sm"
          :disabled="!projectReady"
          @click="emit('open-route-config')"
        >
          <template #icon>
            <RouteIcon class="h-3.5 w-3.5" />
          </template>
          路由
        </BaseButton>
        <BaseButton
          v-if="selectedCount === 0"
          data-testid="project-build-open"
          variant="primary"
          size="sm"
          custom-class="project-build-action"
          :disabled="!projectReady"
          @click="emit('open-build')"
        >
          <template #icon>
            <Hammer class="h-3.5 w-3.5" />
          </template>
          构建
        </BaseButton>
        <PageBatchToolbar
          scope="routed"
          :batchable-count="batchableCount"
          :is-all-selected="isAllSelected"
          :selected-count="selectedCount"
          :batch-action-pending="batchActionPending"
          :batch-progress-text="batchProgressText"
          @select-all-change="emit('select-all-change', $event)"
          @batch-remove-route="emit('batch-remove-route')"
          @batch-download-screenshots="emit('batch-download-screenshots')"
          @open-batch-copy="emit('open-batch-copy')"
          @batch-archive-pages="emit('batch-archive-pages')"
          @clear-selection="emit('clear-selection')"
        />
      </div>
    </div>

    <div
      v-if="entries.length === 0"
      class="rounded-lg border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-400"
    >
      当前没有页面加入项目路由。
    </div>

    <div v-else class="grid gap-4" :style="pageCardGridStyle">
      <PageCard
        v-for="entry in entries"
        :key="entry.key"
        mode="routed"
        :page="entry.page"
        :selected="selectedPageIds.has(entry.page.id)"
        :selection-test-id="`batch-routed-select-${entry.page.id}`"
        :screenshot-aspect-ratio="screenshotAspectRatio"
        :screenshot-disabled="screenshotPendingPageId !== null || batchScreenshotRefreshing"
        :screenshot-pending="screenshotPendingPageId === entry.page.id"
        :archive-pending="archivingPageId === entry.page.id"
        :route-path="entry.routePath"
        :duplicate-index="entry.duplicateIndex"
        :duplicate-total="entry.duplicateTotal"
        :is-duplicate="entry.isDuplicate"
        @open="emit('open-page', $event)"
        @select-change="(pageId, event) => emit('page-select-change', pageId, event)"
        @open-route-config="emit('open-route-config')"
        @copy-page="emit('copy-page', $event)"
        @save-screenshot="emit('save-page-screenshot', $event)"
        @archive-page="emit('archive-page', $event)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { Hammer, RefreshCw, Route as RouteIcon } from '@lucide/vue'

import type { PageItem } from '@/types/api'
import BaseButton from '@/components/ui/BaseButton.vue'
import PageBatchToolbar from './PageBatchToolbar.vue'
import PageCard from './PageCard.vue'
import type { PageBatchAction, PageBatchScope, RoutedPageEntry } from './page-list-types'

defineProps<{
  entries: RoutedPageEntry[]
  projectReady: boolean
  refreshableScreenshotCount: number
  batchScreenshotRefreshScope: PageBatchScope | null
  batchScreenshotRefreshing: boolean
  screenshotPendingPageId: number | null
  archivingPageId: number | null
  batchableCount: number
  isAllSelected: boolean
  selectedCount: number
  selectedPageIds: Set<number>
  batchActionPending: PageBatchAction | null
  batchProgressText?: string | null
  pageCardGridStyle: CSSProperties
  screenshotAspectRatio: string
}>()

const emit = defineEmits<{
  'refresh-screenshots': []
  'open-route-config': []
  'open-build': []
  'select-all-change': [checked: boolean]
  'batch-remove-route': []
  'batch-download-screenshots': []
  'open-batch-copy': []
  'batch-archive-pages': []
  'clear-selection': []
  'open-page': [pageId: number]
  'page-select-change': [pageId: number, event: Event]
  'copy-page': [page: PageItem]
  'save-page-screenshot': [page: PageItem]
  'archive-page': [page: PageItem]
}>()
</script>

<style scoped>
:deep(.project-build-action) {
  border-color: rgb(99 102 241);
  background: linear-gradient(135deg, rgb(79 70 229), rgb(14 165 233));
  box-shadow: 0 8px 18px rgb(79 70 229 / 0.22);
}

:deep(.project-build-action:hover) {
  border-color: rgb(67 56 202);
  box-shadow: 0 10px 22px rgb(79 70 229 / 0.28);
}
</style>
