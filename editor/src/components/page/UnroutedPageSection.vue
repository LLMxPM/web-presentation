<!-- 文件功能：渲染未加入路由的页面分区，包括归档入口、批量工具条、页面卡片和新增页面卡片。 -->
<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-bold text-slate-900">未加入路由</h2>
        <span class="text-xs font-semibold text-slate-400">{{ pages.length }} 个页面</span>
      </div>
      <div class="flex min-w-0 flex-wrap items-center justify-end gap-2">
        <BaseButton
          v-if="selectedCount === 0"
          data-testid="batch-refresh-unrouted-page-screenshots"
          variant="ghost"
          size="sm"
          :loading="batchScreenshotRefreshScope === 'unrouted'"
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
          @click="emit('open-archived-pages')"
        >
          <template #icon>
            <Archive class="h-3.5 w-3.5" />
          </template>
          归档页面
        </BaseButton>
        <PageBatchToolbar
          scope="unrouted"
          :batchable-count="pages.length"
          :is-all-selected="isAllSelected"
          :selected-count="selectedCount"
          :batch-action-pending="batchActionPending"
          :batch-progress-text="batchProgressText"
          @select-all-change="emit('select-all-change', $event)"
          @batch-add-route="emit('batch-add-route')"
          @batch-download-screenshots="emit('batch-download-screenshots')"
          @open-batch-copy="emit('open-batch-copy')"
          @batch-archive-pages="emit('batch-archive-pages')"
          @clear-selection="emit('clear-selection')"
        />
      </div>
    </div>

    <div class="grid gap-4" :style="pageCardGridStyle">
      <PageCard
        v-for="page in pages"
        :key="page.id"
        mode="unrouted"
        :page="page"
        :selected="selectedPageIds.has(page.id)"
        :selection-test-id="`batch-unrouted-select-${page.id}`"
        :screenshot-aspect-ratio="screenshotAspectRatio"
        :screenshot-disabled="screenshotPendingPageId !== null || batchScreenshotRefreshing"
        :screenshot-pending="screenshotPendingPageId === page.id"
        :archive-pending="archivingPageId === page.id"
        :route-pending="pageRoutePendingId === page.id"
        @open="emit('open-page', $event)"
        @select-change="(pageId, event) => emit('page-select-change', pageId, event)"
        @add-route="emit('add-page-route', $event)"
        @copy-page="emit('copy-page', $event)"
        @save-screenshot="emit('save-page-screenshot', $event)"
        @archive-page="emit('archive-page', $event)"
      />

      <button
        type="button"
        class="flex min-h-[220px] flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-200 bg-slate-50/50 p-6 text-slate-500 transition-all duration-300 hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-600"
        :style="pageCreateCardStyle"
        @click="emit('open-create')"
      >
        <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm">
          <Plus class="h-6 w-6" />
        </div>
        <span class="text-base font-bold">新增页面</span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { Archive, Plus, RefreshCw } from '@lucide/vue'

import type { PageItem } from '@/types/api'
import BaseButton from '@/components/ui/BaseButton.vue'
import PageBatchToolbar from './PageBatchToolbar.vue'
import PageCard from './PageCard.vue'
import type { PageBatchAction, PageBatchScope } from './page-list-types'

defineProps<{
  pages: PageItem[]
  projectReady: boolean
  refreshableScreenshotCount: number
  batchScreenshotRefreshScope: PageBatchScope | null
  batchScreenshotRefreshing: boolean
  screenshotPendingPageId: number | null
  archivingPageId: number | null
  pageRoutePendingId: number | null
  isAllSelected: boolean
  selectedCount: number
  selectedPageIds: Set<number>
  batchActionPending: PageBatchAction | null
  batchProgressText?: string | null
  pageCardGridStyle: CSSProperties
  pageCreateCardStyle: CSSProperties
  screenshotAspectRatio: string
}>()

const emit = defineEmits<{
  'refresh-screenshots': []
  'open-archived-pages': []
  'select-all-change': [checked: boolean]
  'batch-add-route': []
  'batch-download-screenshots': []
  'open-batch-copy': []
  'batch-archive-pages': []
  'clear-selection': []
  'open-page': [pageId: number]
  'page-select-change': [pageId: number, event: Event]
  'add-page-route': [page: PageItem]
  'copy-page': [page: PageItem]
  'save-page-screenshot': [page: PageItem]
  'archive-page': [page: PageItem]
  'open-create': []
}>()
</script>
