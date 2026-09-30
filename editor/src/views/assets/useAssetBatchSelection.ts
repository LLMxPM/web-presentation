/**
 * 文件功能：资源库多选状态与批量归档/恢复/删除/导出操作，供 AssetsView 编排层复用。
 */
import { computed, ref, type Ref } from 'vue'

import {
  batchArchiveWorkspaceAssets,
  batchDeleteWorkspaceAssets,
  batchRestoreWorkspaceAssets,
  exportWorkspaceAssetPackage,
} from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import type { AssetBatchOperationResponse, AssetResponse } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { downloadBlob } from '@/utils/zip-download'
import { isBackfillableAssetType, type AssetView } from '@/views/asset-view-options'

export interface AssetBatchSelectionOptions {
  workspaceId: Ref<number>
  activeView: Ref<AssetView>
  assets: Ref<AssetResponse[]>
  /** 批量操作成功后：关闭已删详情、刷新列表等。 */
  onAfterBatch?: (assetIds: number[]) => void | Promise<void>
}

/**
 * 资源多选与批量操作状态簇。
 * @param options 工作空间、当前状态视图、列表数据与副作用回调
 * @returns 选择状态、派生计算与批量动作
 */
export function useAssetBatchSelection(options: AssetBatchSelectionOptions) {
  const selectedAssetIds = ref<Set<number>>(new Set())
  const selectionMode = ref(false)
  const batchOperating = ref(false)
  const batchExporting = ref(false)

  const selectedCount = computed(() => selectedAssetIds.value.size)
  const hasBatchSelection = computed(() => selectedCount.value > 0)
  const currentPageAssetIds = computed(() => options.assets.value.map(asset => asset.id))
  const allCurrentPageSelected = computed(() => (
    currentPageAssetIds.value.length > 0
    && currentPageAssetIds.value.every(assetId => selectedAssetIds.value.has(assetId))
  ))
  const selectedBackfillableAssets = computed(() => options.assets.value.filter(asset => (
    selectedAssetIds.value.has(asset.id)
    && asset.status === 'active'
    && !asset.history_kind
    && isBackfillableAssetType(asset.asset_type)
  )))
  const hasBackfillableBatchSelection = computed(() => selectedBackfillableAssets.value.length > 0)

  function isAssetSelected(assetId: number): boolean {
    return selectedAssetIds.value.has(assetId)
  }

  function toggleAssetSelection(assetId: number): void {
    const next = new Set(selectedAssetIds.value)
    if (next.has(assetId)) {
      next.delete(assetId)
    } else {
      next.add(assetId)
    }
    selectedAssetIds.value = next
  }

  function toggleCurrentPageSelection(): void {
    if (allCurrentPageSelected.value) {
      const next = new Set(selectedAssetIds.value)
      for (const assetId of currentPageAssetIds.value) {
        next.delete(assetId)
      }
      selectedAssetIds.value = next
      return
    }
    const next = new Set(selectedAssetIds.value)
    for (const assetId of currentPageAssetIds.value) {
      next.add(assetId)
    }
    selectedAssetIds.value = next
  }

  function clearBatchSelection(): void {
    selectedAssetIds.value = new Set()
  }

  function toggleSelectionMode(): void {
    if (selectionMode.value) {
      exitSelectionMode()
      return
    }
    selectionMode.value = true
  }

  function exitSelectionMode(): void {
    selectionMode.value = false
    clearBatchSelection()
  }

  function pruneBatchSelection(): void {
    const currentIds = new Set(currentPageAssetIds.value)
    selectedAssetIds.value = new Set([...selectedAssetIds.value].filter(assetId => currentIds.has(assetId)))
  }

  function showBatchOperationResult(result: AssetBatchOperationResponse, actionLabel: string): void {
    if (result.failed_count === 0) {
      Message.success(`已${actionLabel} ${result.succeeded_count} 个资源`)
      return
    }
    if (result.succeeded_count > 0) {
      Message.warning(`已${actionLabel} ${result.succeeded_count} 个资源，${result.failed_count} 个失败：${formatBatchFailure(result)}`)
      return
    }
    Message.error(`批量${actionLabel}失败：${formatBatchFailure(result)}`)
  }

  function formatBatchFailure(result: AssetBatchOperationResponse): string {
    return result.failures[0]?.detail || '请检查资源状态或引用关系'
  }

  async function runBatchOperation(
    actionLabel: string,
    confirmMessage: string,
    confirmTitle: string,
    invoke: (assetIds: number[]) => Promise<AssetBatchOperationResponse>,
    runOptions?: { beforeGuard?: () => boolean },
  ): Promise<void> {
    const assetIds = [...selectedAssetIds.value]
    if (!Number.isFinite(options.workspaceId.value) || assetIds.length === 0) return
    if (runOptions?.beforeGuard && !runOptions.beforeGuard()) return
    const confirmed = await createConfirm(confirmMessage, confirmTitle)
    if (!confirmed) return

    batchOperating.value = true
    try {
      const result = await invoke(assetIds)
      showBatchOperationResult(result, actionLabel)
      await options.onAfterBatch?.(assetIds)
      clearBatchSelection()
    } catch (error) {
      Message.error(getErrorMessage(error, `批量${actionLabel}资源失败`))
    } finally {
      batchOperating.value = false
    }
  }

  async function archiveSelectedAssets(): Promise<void> {
    await runBatchOperation(
      '归档',
      `确认归档选中的 ${selectedAssetIds.value.size} 个资源吗？归档后现有引用仍可用。`,
      '批量归档资源',
      ids => batchArchiveWorkspaceAssets(options.workspaceId.value, ids),
    )
  }

  async function restoreSelectedAssets(): Promise<void> {
    await runBatchOperation(
      '恢复',
      `确认恢复选中的 ${selectedAssetIds.value.size} 个归档资源吗？`,
      '批量恢复资源',
      ids => batchRestoreWorkspaceAssets(options.workspaceId.value, ids),
      {
        beforeGuard: () => {
          if (options.activeView.value !== 'archived') {
            Message.warning('仅归档资源支持批量恢复')
            return false
          }
          return true
        },
      },
    )
  }

  async function deleteSelectedAssets(): Promise<void> {
    await runBatchOperation(
      '删除',
      `确认删除选中的 ${selectedAssetIds.value.size} 个资源吗？该操作只允许无引用的归档或历史资源。`,
      '批量删除资源',
      ids => batchDeleteWorkspaceAssets(options.workspaceId.value, ids),
      {
        beforeGuard: () => {
          if (options.activeView.value === 'active') {
            Message.warning('启用资源需要先归档后才能删除')
            return false
          }
          return true
        },
      },
    )
  }

  async function exportSelectedAssets(): Promise<void> {
    const assetIds = [...selectedAssetIds.value]
    if (!Number.isFinite(options.workspaceId.value) || assetIds.length === 0) return

    batchOperating.value = true
    batchExporting.value = true
    try {
      const { blob, filename } = await exportWorkspaceAssetPackage(options.workspaceId.value, assetIds)
      downloadBlob(blob, filename)
      Message.success(`已导出 ${assetIds.length} 个资源`)
    } catch (error) {
      Message.error(getErrorMessage(error, '批量导出资源失败'))
    } finally {
      batchExporting.value = false
      batchOperating.value = false
    }
  }

  return {
    selectedAssetIds,
    selectionMode,
    batchOperating,
    batchExporting,
    selectedCount,
    hasBatchSelection,
    currentPageAssetIds,
    allCurrentPageSelected,
    selectedBackfillableAssets,
    hasBackfillableBatchSelection,
    isAssetSelected,
    toggleAssetSelection,
    toggleCurrentPageSelection,
    clearBatchSelection,
    toggleSelectionMode,
    exitSelectionMode,
    pruneBatchSelection,
    archiveSelectedAssets,
    restoreSelectedAssets,
    deleteSelectedAssets,
    exportSelectedAssets,
    showBatchOperationResult,
  }
}
