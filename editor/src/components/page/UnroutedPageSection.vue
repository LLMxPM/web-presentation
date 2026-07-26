<!-- 文件功能：渲染未加入路由的页面分区，包括归档入口、批量工具条、页面卡片和新增页面卡片。 -->
<template>
  <section class="space-y-4">
    <CommandBar label="未加入路由页面操作">
      <template #leading>
        <div class="flex min-w-0 items-center gap-3">
          <h2 class="truncate text-base font-semibold text-[rgb(var(--ui-text))]">未加入路由</h2>
          <span class="text-xs text-[rgb(var(--ui-text-muted))]">{{ pages.length }} 个页面</span>
        </div>
      </template>
      <template #actions>
        <UiButton
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
        </UiButton>
        <UiButton
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
        </UiButton>
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
      </template>
    </CommandBar>

    <DataState
      :state="pages.length === 0 ? 'empty' : 'ready'"
      title="当前没有未加入路由的页面"
      description="可新增页面，或从路由配置中调整现有页面。"
      :retryable="false"
    >
    <template #empty>
      <UiButton class="mt-2" @click="emit('open-create')">
        <Plus class="h-4 w-4" />
        新增页面
      </UiButton>
    </template>
    <div data-testid="unrouted-page-card-grid" class="grid gap-4" :style="pageCardGridStyle">
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

      <PageCreateCard
        :screenshot-aspect-ratio="screenshotAspectRatio"
        @open="emit('open-create')"
      />
    </div>
    </DataState>
  </section>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { Archive, Plus, RefreshCw } from '@lucide/vue'

import type { PageItem } from '@/types/api'
import CommandBar from '@/components/patterns/CommandBar.vue'
import DataState from '@/components/patterns/DataState.vue'
import { UiButton } from '@/components/ui'
import PageBatchToolbar from './PageBatchToolbar.vue'
import PageCard from './PageCard.vue'
import PageCreateCard from './PageCreateCard.vue'
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
