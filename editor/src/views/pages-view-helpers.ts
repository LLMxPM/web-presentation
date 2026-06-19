/**
 * 文件功能：提供项目页面列表视图的纯辅助函数和页面卡片尺寸配置。
 */
import { Expand, Maximize2, Minimize2, Square } from '@lucide/vue'

import type { PageBatchScope, PageCardSize, PageCardSizeOption } from '@/components/page/page-list-types'
import type { PageItem, ProjectRouteBinding, ProjectRouteItemWrite } from '@/types/api'
import { Message } from '@/utils/message'
import { normalizeProjectRouteOrders } from '@/utils/project-route'

const PAGE_CARD_SIZE_STORAGE_KEY = 'web-presentation:pages-view:preview-card-size'

export interface AgentProjectPagesMutationDetail {
  workspaceId?: number | null
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  toolName?: string
  result?: unknown
}

export interface ProjectBuildSubmitPayload {
  base_url: string
  extra_asset_names: string[]
}

export interface BatchScreenshotDownloadProgress {
  scope: PageBatchScope
  text: string
}

export const pageCardSizeOptions: PageCardSizeOption[] = [
  { value: 'compact', label: '紧凑', minWidth: 200, icon: Minimize2 },
  { value: 'standard', label: '标准', minWidth: 240, icon: Square },
  { value: 'large', label: '宽大', minWidth: 320, icon: Maximize2 },
  { value: 'huge', label: '超大', minWidth: 520, icon: Expand },
]

/**
 * 按页面路由绑定路径排序，供卡片分组和重复标记共同使用。
 */
export function getSortedRouteBindings(page: PageItem): ProjectRouteBinding[] {
  return [...(page.route_bindings ?? [])].sort((left, right) => {
    const routeOrderCompare = compareNumberTuple(getRouteBindingOrderKey(left), getRouteBindingOrderKey(right))
    if (routeOrderCompare !== 0) {
      return routeOrderCompare
    }
    return normalizeRoutePath(left.full_path).localeCompare(normalizeRoutePath(right.full_path), 'zh-CN')
  })
}

/**
 * 归一化路由展示路径，避免空路径破坏排序与展示。
 */
export function normalizeRoutePath(path: string | null | undefined): string {
  const trimmedPath = String(path ?? '').trim()
  return trimmedPath || '/'
}

/**
 * 从浏览器缓存读取页面预览卡片尺寸偏好。
 */
export function readStoredPageCardSize(): PageCardSize {
  if (typeof window === 'undefined') {
    return 'standard'
  }

  try {
    const storedSize = window.localStorage.getItem(PAGE_CARD_SIZE_STORAGE_KEY)
    return isPageCardSize(storedSize) ? storedSize : 'standard'
  } catch {
    return 'standard'
  }
}

/**
 * 把页面预览卡片尺寸写入浏览器缓存。
 */
export function persistPageCardSize(size: PageCardSize): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(PAGE_CARD_SIZE_STORAGE_KEY, size)
  } catch {
    // 浏览器隐私模式或容量限制下忽略缓存失败，不影响页面使用。
  }
}

/**
 * 判断页面截图是否缺失或已过期，且当前文件类型支持截图。
 */
export function isRefreshableScreenshotPage(page: PageItem): boolean {
  return page.file_type === 'vue' && (!page.screenshot_url || !page.screenshot_is_latest)
}

/**
 * 判断页面是否已经具备可下载的最新截图。
 */
export function isDownloadableLatestScreenshotPage(page: PageItem): boolean {
  return Boolean(page.screenshot_url && page.screenshot_is_latest)
}

/**
 * 生成人类可读的截图未就绪原因，避免批量下载混入旧图。
 */
export function buildScreenshotNotReadyMessage(page: PageItem): string {
  if (page.file_type !== 'vue' && !page.screenshot_url) {
    return `「${page.title}」不是 Vue 页面，无法自动生成截图。`
  }
  if (!page.screenshot_url) {
    return `「${page.title}」暂无可下载截图。`
  }
  return `「${page.title}」截图仍不是最新版本。`
}

/**
 * 从路由草稿中移除所有绑定指定页面的节点，并丢弃被清空的分组。
 */
export function removePagesFromProjectRoutes(routeItems: ProjectRouteItemWrite[], pageIds: Set<number>): ProjectRouteItemWrite[] {
  const nextRoutes: ProjectRouteItemWrite[] = []
  routeItems.forEach((routeItem) => {
    if (routeItem.route_type === 'group') {
      const children = (routeItem.children ?? []).filter(child => !pageIds.has(child.page_id))
      if (children.length > 0) {
        nextRoutes.push({ ...routeItem, children })
      }
      return
    }
    if (routeItem.page_id && !pageIds.has(routeItem.page_id)) {
      nextRoutes.push(routeItem)
    }
  })
  return normalizeProjectRouteOrders(nextRoutes)
}

/**
 * 归一化构建额外资源名列表，和弹窗侧保持一致。
 */
export function normalizeProjectBuildExtraAssetNames(values: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const value of values) {
    const normalized = String(value || '').trim().replace(/\\/g, '/').replace(/^\.?\//, '')
    if (!normalized || /^https?:\/\//i.test(normalized) || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    result.push(normalized)
  }
  return result
}

/**
 * 读取项目当前保存的额外构建资源名。
 */
export function getSavedProjectBuildExtraAssetNames(values: string[] | undefined | null): string[] {
  return normalizeProjectBuildExtraAssetNames(values ?? [])
}

/**
 * 比较两个字符串数组是否完全一致。
 */
export function isSameStringArray(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((item, index) => item === right[index])
}

/**
 * 统一展示批量操作结果。
 */
export function showBatchResultMessage(actionLabel: string, succeededCount: number, firstErrorMessage: string): void {
  if (firstErrorMessage) {
    Message.warning(`批量${actionLabel}完成 ${succeededCount} 个，存在失败：${firstErrorMessage}`)
    return
  }
  Message.success(`批量${actionLabel}完成 ${succeededCount} 个页面。`)
}

export function getRouteBindingOrderKey(binding: ProjectRouteBinding): number[] {
  const fallbackOrder = Number.MAX_SAFE_INTEGER
  const routeOrder = typeof binding.order === 'number' ? binding.order : fallbackOrder
  const parentOrder = typeof binding.parent_order === 'number' ? binding.parent_order : routeOrder
  return [parentOrder, routeOrder, binding.route_id]
}

export function compareNumberTuple(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    const diff = (left[index] ?? 0) - (right[index] ?? 0)
    if (diff !== 0) {
      return diff
    }
  }
  return 0
}

function isPageCardSize(value: string | null): value is PageCardSize {
  return value === 'compact' || value === 'standard' || value === 'large' || value === 'huge'
}
