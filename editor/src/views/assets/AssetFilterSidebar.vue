<!-- 文件功能：资源库筛选侧栏，承载状态、类型、标签与排序筛选控件（纯展示，状态由 useAssetListFilters 持有）。 -->
<template>
  <ToolPanel class="min-h-0" title="筛选资源" description="按状态、类型和标签缩小范围。">
    <template #toolbar>
      <SimpleSearchBar
        v-model="searchKeyword"
        placeholder="搜索资源..."
        aria-label="搜索资源"
        @submit="emit('submit-search')"
      />
    </template>
    <div class="space-y-3">
      <section class="rounded-xl border border-border bg-surface p-3">
        <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-text-disabled">状态</h3>
        <LibrarySegmentedControl
          v-model="activeView"
          :options="viewTabs"
          :columns="3"
        />
      </section>

      <section class="rounded-xl border border-border bg-surface p-3">
        <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-text-disabled">资源类型</h3>
        <LibrarySegmentedControl
          v-model="assetTypeFilter"
          :options="assetTypeSegmentOptions"
          :columns="2"
          aria-label="资源类型筛选"
        />
      </section>

      <section class="rounded-xl border border-border bg-surface p-3">
        <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-text-disabled">标签</h3>
        <LibraryChipFilter
          v-model="activeTagFilter"
          :options="availableTagOptions"
        />
      </section>

      <section class="rounded-xl border border-border bg-surface p-3">
        <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-text-disabled">排序</h3>
        <UiSelect v-model="sortValue" :options="assetSortOptions" />
      </section>
    </div>
  </ToolPanel>
</template>

<script setup lang="ts">
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import LibraryChipFilter from '@/components/project/LibraryChipFilter.vue'
import LibrarySegmentedControl from '@/components/project/LibrarySegmentedControl.vue'
import { UiSelect } from '@/components/ui'
import type { AssetType } from '@/types/api'
import type { AssetView } from '@/views/asset-view-options'
import { ASSET_SORT_OPTIONS, ASSET_TYPE_SEGMENT_OPTIONS, VIEW_TABS } from '@/views/asset-view-options'

const activeView = defineModel<AssetView>('activeView', { required: true })
const assetTypeFilter = defineModel<AssetType | ''>('assetTypeFilter', { required: true })
const searchKeyword = defineModel<string>('searchKeyword', { required: true })
const sortValue = defineModel<string>('sortValue', { required: true })
const activeTagFilter = defineModel<string>('activeTagFilter', { required: true })

defineProps<{
  availableTagOptions: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  'submit-search': []
}>()

const viewTabs = VIEW_TABS
const assetSortOptions = ASSET_SORT_OPTIONS
const assetTypeSegmentOptions = ASSET_TYPE_SEGMENT_OPTIONS
</script>
