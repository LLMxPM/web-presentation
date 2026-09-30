/**
 * 文件功能：资源库列表筛选状态、状态范围解析与标签加载，供 AssetsView 与筛选侧栏共用。
 */
import { computed, ref, watch, type Ref } from 'vue'

import { listWorkspaceAssetTags } from '@/api/assets'
import type { AssetType, RecordStatus } from '@/types/api'
import {
  ASSET_SORT_OPTIONS,
  ASSET_TYPE_SEGMENT_OPTIONS,
  VIEW_TABS,
  type AssetView,
} from '@/views/asset-view-options'

export interface AssetStatusScope {
  status: RecordStatus
  includeHistory: boolean
  historyOnly: boolean
}

export interface AssetListFiltersOptions {
  /** 筛选条件变化时重置页码；由编排层注入。 */
  onFilterResetPage?: () => void
}

/**
 * 资源库筛选状态簇：状态/类型/标签/搜索/排序 + 标签列表加载。
 * @param options 筛选变化回调
 * @returns 筛选 ref、派生计算属性与加载方法
 */
export function useAssetListFilters(options: AssetListFiltersOptions = {}) {
  const activeView = ref<AssetView>('active')
  const assetTypeFilter = ref<AssetType | ''>('')
  const activeTag = ref<string | null>(null)
  const searchKeyword = ref('')
  const sortValue = ref('updated_at:desc')
  const availableTags = ref<string[]>([])

  const viewTabs = VIEW_TABS
  const assetSortOptions = ASSET_SORT_OPTIONS
  const assetTypeSegmentOptions = ASSET_TYPE_SEGMENT_OPTIONS

  const resetPage = (): void => {
    options.onFilterResetPage?.()
  }

  const sortParts = computed(() => {
    const [sortBy, sortOrder] = sortValue.value.split(':')
    return {
      sortBy: sortBy || 'updated_at',
      sortOrder: sortOrder === 'asc' ? ('asc' as const) : ('desc' as const),
    }
  })

  const activeTagFilter = computed({
    get: () => activeTag.value || '',
    set: (value: string) => {
      if ((activeTag.value || '') === (value || '')) return
      activeTag.value = value || null
      resetPage()
    },
  })

  const availableTagOptions = computed(() => availableTags.value.map(tag => ({ label: tag, value: tag })))

  const emptyAssetText = computed(() => {
    if (searchKeyword.value.trim()) return '未找到相关资源'
    if (activeTag.value) return '当前标签下暂无资源'
    if (activeView.value === 'archived') return '暂无归档资源'
    if (activeView.value === 'history') return '暂无写入历史副本'
    return '暂无资源'
  })

  // 筛选字段变化时重置页码（与原 AssetsView 行为一致）。
  watch([activeView, assetTypeFilter, searchKeyword, sortValue], resetPage)

  /** 按当前状态视图解析列表/标签查询范围。 */
  function resolveAssetStatusScope(): AssetStatusScope {
    return {
      status: activeView.value === 'active' ? 'active' : 'archived',
      includeHistory: activeView.value === 'history',
      historyOnly: activeView.value === 'history',
    }
  }

  /** 列表查询公共筛选参数（分页由调用方补）。 */
  function buildListQueryParams(): {
    status: RecordStatus
    includeHistory: boolean
    historyOnly: boolean
    assetType?: AssetType
    excludeAssetType?: 'font'
    tag?: string
    keyword?: string
    sort_by: string
    sort_order: 'asc' | 'desc'
  } {
    return {
      ...resolveAssetStatusScope(),
      assetType: assetTypeFilter.value || undefined,
      excludeAssetType: assetTypeFilter.value ? undefined : 'font',
      tag: activeTag.value || undefined,
      keyword: searchKeyword.value.trim() || undefined,
      sort_by: sortParts.value.sortBy,
      sort_order: sortParts.value.sortOrder,
    }
  }

  /** 按当前状态范围加载标签；失效标签会被清掉并重置页码。 */
  async function loadTags(workspaceId: number): Promise<void> {
    try {
      const tags = await listWorkspaceAssetTags(workspaceId, {
        ...resolveAssetStatusScope(),
        assetType: assetTypeFilter.value || undefined,
        excludeAssetType: assetTypeFilter.value ? undefined : 'font',
      })
      availableTags.value = tags
      if (activeTag.value && !tags.includes(activeTag.value)) {
        activeTag.value = null
        resetPage()
      }
    } catch {
      availableTags.value = []
      activeTag.value = null
    }
  }

  return {
    activeView: activeView as Ref<AssetView>,
    assetTypeFilter: assetTypeFilter as Ref<AssetType | ''>,
    activeTag: activeTag as Ref<string | null>,
    searchKeyword,
    sortValue,
    availableTags,
    viewTabs,
    assetSortOptions,
    assetTypeSegmentOptions,
    sortParts,
    activeTagFilter,
    availableTagOptions,
    emptyAssetText,
    resolveAssetStatusScope,
    buildListQueryParams,
    loadTags,
  }
}

export type AssetListFilters = ReturnType<typeof useAssetListFilters>
