/**
 * 文件功能：封装资源选择器的服务端搜索、分页、并发失效与生命周期清理逻辑。
 */
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

import { listWorkspaceAssets } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import type { AssetResponse, AssetType } from '@/types/api'
import { Message } from '@/utils/message'

interface AssetPickerSearchOptions {
  dialogVisible: Ref<boolean>
  workspaceId: () => number | null
  assetType: () => AssetType
  resourceLabel: () => string
}

/**
 * 为资源选择弹窗建立按类型隔离的分页搜索状态。
 * @param options 弹窗状态与当前资源类型读取函数
 */
export function useAssetPickerSearch(options: AssetPickerSearchOptions) {
  const loading = ref(false)
  const searchKeyword = ref('')
  const assets = ref<AssetResponse[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = 24
  let searchTimer: ReturnType<typeof setTimeout> | null = null
  let requestSerial = 0
  let ignoreQueryWatch = false

  watch(searchKeyword, () => {
    if (!options.dialogVisible.value || ignoreQueryWatch) {
      return
    }
    requestSerial += 1
    ignoreQueryWatch = true
    page.value = 1
    ignoreQueryWatch = false
    scheduleFetch()
  }, { flush: 'sync' })

  watch(page, () => {
    if (options.dialogVisible.value && !ignoreQueryWatch) {
      clearSearchTimer()
      void fetchAssets()
    }
  }, { flush: 'sync' })

  watch([options.workspaceId, options.assetType], () => {
    ignoreQueryWatch = true
    assets.value = []
    total.value = 0
    page.value = 1
    ignoreQueryWatch = false
    requestSerial += 1
    if (options.dialogVisible.value) {
      void fetchAssets()
    }
  })

  onBeforeUnmount(() => {
    clearSearchTimer()
    requestSerial += 1
  })

  /**
   * 重置关键词和页码，并立即加载第一页。
   */
  async function resetSearchAndFetch(): Promise<void> {
    clearSearchTimer()
    ignoreQueryWatch = true
    searchKeyword.value = ''
    page.value = 1
    ignoreQueryWatch = false
    await fetchAssets()
  }

  /**
   * 按当前类型、关键词和页码读取资源，并忽略已经过期的并发响应。
   */
  async function fetchAssets(): Promise<void> {
    const workspaceId = options.workspaceId()
    if (!workspaceId) {
      assets.value = []
      total.value = 0
      return
    }

    const currentRequest = ++requestSerial
    loading.value = true
    try {
      const response = await listWorkspaceAssets(workspaceId, {
        assetType: options.assetType(),
        keyword: searchKeyword.value.trim() || undefined,
        page: page.value,
        page_size: pageSize,
      })
      if (currentRequest !== requestSerial) {
        return
      }
      assets.value = response.items
      total.value = response.total
    } catch (error) {
      if (currentRequest !== requestSerial) {
        return
      }
      assets.value = []
      total.value = 0
      Message.error(getErrorMessage(error, `加载${options.resourceLabel()}资源失败。`))
    } finally {
      if (currentRequest === requestSerial) {
        loading.value = false
      }
    }
  }

  /**
   * 对搜索请求做防抖，避免用户输入过程中产生过多列表请求。
   */
  function scheduleFetch(): void {
    clearSearchTimer()
    searchTimer = setTimeout(() => {
      searchTimer = null
      void fetchAssets()
    }, 300)
  }

  /**
   * 清理尚未执行的搜索定时器。
   */
  function clearSearchTimer(): void {
    if (searchTimer) {
      clearTimeout(searchTimer)
      searchTimer = null
    }
  }

  return {
    assets,
    loading,
    page,
    pageSize,
    resetSearchAndFetch,
    searchKeyword,
    total,
  }
}
