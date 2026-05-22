/**
 * 文件功能：计算页面详情预览模式的上一页和下一页，统一复用项目路由顺序与未路由页面编码顺序。
 */
import type { PageItem, ProjectRouteBinding } from '@/types/api'

export interface PageDetailNavigationState {
  previousPageId: number | null
  nextPageId: number | null
}

interface RoutedNavigationEntry {
  page: PageItem
  routePath: string
  routeOrderKey: number[]
}

/**
 * 根据当前页面是否加入路由，返回对应序列里的前后页面 ID。
 * @param pages 当前项目内启用中的页面列表
 * @param currentPageId 当前页面 ID
 */
export function resolvePageDetailNavigation(
  pages: PageItem[],
  currentPageId: number,
): PageDetailNavigationState {
  const currentPage = pages.find(page => page.id === currentPageId)
  if (!currentPage) {
    return { previousPageId: null, nextPageId: null }
  }

  const sequence = hasRouteBindings(currentPage)
    ? buildRoutedPageSequence(pages)
    : buildUnroutedPageSequence(pages)
  const currentIndex = sequence.findIndex(page => page.id === currentPageId)

  if (currentIndex < 0) {
    return { previousPageId: null, nextPageId: null }
  }

  return {
    previousPageId: sequence[currentIndex - 1]?.id ?? null,
    nextPageId: sequence[currentIndex + 1]?.id ?? null,
  }
}

/**
 * 生成已加入路由的页面序列，同一页面多次绑定时保留最靠前的绑定。
 * @param pages 当前项目页面列表
 */
export function buildRoutedPageSequence(pages: PageItem[]): PageItem[] {
  const entries = pages
    .flatMap((page) => {
      return getSortedRouteBindings(page).map(binding => ({
        page,
        routePath: normalizeRoutePath(binding.full_path),
        routeOrderKey: getRouteBindingOrderKey(binding),
      }))
    })
    .sort(compareRoutedNavigationEntry)

  const pageMap = new Map<number, PageItem>()
  entries.forEach((entry) => {
    if (!pageMap.has(entry.page.id)) {
      pageMap.set(entry.page.id, entry.page)
    }
  })
  return [...pageMap.values()]
}

/**
 * 生成未加入路由的页面序列，使用页面编码升序作为稳定顺序。
 * @param pages 当前项目页面列表
 */
export function buildUnroutedPageSequence(pages: PageItem[]): PageItem[] {
  return pages
    .filter(page => !hasRouteBindings(page))
    .sort((left, right) => {
      const codeCompare = left.code.localeCompare(right.code, 'zh-CN')
      if (codeCompare !== 0) {
        return codeCompare
      }
      return left.id - right.id
    })
}

/**
 * 判断页面是否存在项目路由绑定。
 * @param page 页面资源
 */
function hasRouteBindings(page: PageItem): boolean {
  return (page.route_bindings ?? []).length > 0
}

/**
 * 按路由树顺序排序页面绑定。
 * @param page 页面资源
 */
function getSortedRouteBindings(page: PageItem): ProjectRouteBinding[] {
  return [...(page.route_bindings ?? [])].sort((left, right) => {
    const routeOrderCompare = compareNumberTuple(getRouteBindingOrderKey(left), getRouteBindingOrderKey(right))
    if (routeOrderCompare !== 0) {
      return routeOrderCompare
    }
    return normalizeRoutePath(left.full_path).localeCompare(normalizeRoutePath(right.full_path), 'zh-CN')
  })
}

/**
 * 把路由绑定映射为可比较的父子顺序元组。
 * @param binding 页面路由绑定
 */
function getRouteBindingOrderKey(binding: ProjectRouteBinding): number[] {
  const fallbackOrder = Number.MAX_SAFE_INTEGER
  const routeOrder = typeof binding.order === 'number' ? binding.order : fallbackOrder
  const parentOrder = typeof binding.parent_order === 'number' ? binding.parent_order : routeOrder
  return [parentOrder, routeOrder, binding.route_id]
}

/**
 * 排序已路由页面条目，保持与项目路由树一致。
 * @param left 左条目
 * @param right 右条目
 */
function compareRoutedNavigationEntry(left: RoutedNavigationEntry, right: RoutedNavigationEntry): number {
  const routeOrderCompare = compareNumberTuple(left.routeOrderKey, right.routeOrderKey)
  if (routeOrderCompare !== 0) {
    return routeOrderCompare
  }
  const routePathCompare = left.routePath.localeCompare(right.routePath, 'zh-CN')
  if (routePathCompare !== 0) {
    return routePathCompare
  }
  return left.page.id - right.page.id
}

/**
 * 比较数字元组，缺失值按 0 处理。
 * @param left 左侧数字元组
 * @param right 右侧数字元组
 */
function compareNumberTuple(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    const diff = (left[index] ?? 0) - (right[index] ?? 0)
    if (diff !== 0) {
      return diff
    }
  }
  return 0
}

/**
 * 归一化路由展示路径，避免空路径影响排序。
 * @param path 后端返回的完整路径
 */
function normalizeRoutePath(path: string | null | undefined): string {
  const trimmedPath = String(path ?? '').trim()
  return trimmedPath || '/'
}
