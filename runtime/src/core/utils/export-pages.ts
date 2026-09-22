/**
 * 文件用途：统一收集 PDF、PPTX 与浏览器打印所需的全部页面列表，优先使用页码目录，失败时回退到可见路由与 Router 路由表。
 */

import type { Router, RouteRecordNormalized } from 'vue-router'
import type { PageInfo } from '@/core/types/pdf-export'

interface RouteCatalogInfoLike {
  name?: string
  path: string
  order?: number
  pageNumber?: number
  level?: number
  hidden?: boolean
  speakerNotes?: string | null
}

const INTERNAL_RUNTIME_ROUTE_PREFIXES = ['/__presenter']

/**
 * 收集全部可导出的页面信息。
 * @param router 当前运行时 Router；当路由目录为空时用于回退到实际注册路由
 * @returns 按导出顺序排序后的页面列表
 */
export async function collectAllExportPages(
  router?: Pick<Router, 'getRoutes'> | null,
): Promise<PageInfo[]> {
  const routeCatalogPages = await collectRouteCatalogPages()
  if (routeCatalogPages.length > 0) {
    return routeCatalogPages
  }

  return collectRouterPages(router)
}

/**
 * 从运行时路由目录收集页面。
 * 关键约束：优先使用页码排序；若页码链路缺失，则退回可见路由顺序，避免直接判定“没有页面”。
 */
async function collectRouteCatalogPages(): Promise<PageInfo[]> {
  try {
    const routeGenerator = await import('@/core/utils/route-generator')
    const pagedRoutes = normalizeRouteCatalogPages(
      typeof routeGenerator.getRouteInfosSortedByPageNumber === 'function'
        ? routeGenerator.getRouteInfosSortedByPageNumber()
        : [],
    )

    if (pagedRoutes.length > 0) {
      return pagedRoutes
    }

    return normalizeRouteCatalogPages(
      typeof routeGenerator.getVisibleRouteInfos === 'function'
        ? routeGenerator.getVisibleRouteInfos()
        : [],
    )
  } catch (error) {
    console.warn('获取导出页面目录失败，将尝试回退到 Router 路由表:', error)
    return []
  }
}

/**
 * 将路由目录结果归一为导出页面信息。
 * @param routes 路由目录结果
 * @returns 去重且已排序的页面列表
 */
function normalizeRouteCatalogPages(routes: RouteCatalogInfoLike[]): PageInfo[] {
  return dedupeAndSortPages(
    routes
      .filter(route => !route.hidden)
      .map((route, index) => createPageInfo(route, index)),
  )
}

/**
 * 从 Router 实际注册路由回退收集页面。
 * @param router 当前运行时 Router
 * @returns 去重且已排序的页面列表
 */
function collectRouterPages(router?: Pick<Router, 'getRoutes'> | null): PageInfo[] {
  if (!router || typeof router.getRoutes !== 'function') {
    return []
  }

  return dedupeAndSortPages(
    router.getRoutes()
      .filter(record => isExportableRouteRecord(record))
      .map((record, index) => ({
        route: normalizeRoutePath(record.path),
        title: resolveRouterRecordTitle(record),
        order: resolveRouteOrder(record, index),
        meta: {
          pageNumber: resolveNumericMetaValue(record.meta.pageNumber),
          hidden: Boolean(record.meta.hidden),
          speakerNotes: resolveSpeakerNotes(record.meta.speakerNotes),
        },
      })),
  )
}

/**
 * 根据目录路由构造导出页面信息。
 * @param route 路由目录项
 * @param index 当前索引
 * @returns 导出页面信息
 */
function createPageInfo(route: RouteCatalogInfoLike, index: number): PageInfo {
  const pageNumber = resolveNumericMetaValue(route.pageNumber)
  const order = resolveNumericMetaValue(route.order)

  return {
    route: normalizeRoutePath(route.path),
    title: String(route.name || route.path || `页面 ${index + 1}`),
    order: pageNumber ?? order ?? index + 1,
    meta: {
      pageNumber,
      level: route.level,
      hidden: route.hidden,
      speakerNotes: resolveSpeakerNotes(route.speakerNotes),
    },
  }
}

/**
 * 判断 Router 路由记录是否可作为导出页面。
 * @param record 标准化路由记录
 * @returns 是否为可导出页面
 */
function isExportableRouteRecord(record: RouteRecordNormalized): boolean {
  const routePath = normalizeRoutePath(record.path)
  if (!routePath) {
    return false
  }

  if (record.aliasOf || record.redirect) {
    return false
  }

  if ((record.children?.length ?? 0) > 0) {
    return false
  }

  if (record.meta.hidden) {
    return false
  }

  if (routePath.includes(':pathMatch') || routePath.includes('*')) {
    return false
  }

  if (INTERNAL_RUNTIME_ROUTE_PREFIXES.some(prefix => routePath.startsWith(prefix))) {
    return false
  }

  return hasRenderableRouteComponent(record)
}

/**
 * 判断路由记录是否包含可渲染组件。
 * @param record 标准化路由记录
 * @returns 是否存在默认视图组件
 */
function hasRenderableRouteComponent(record: RouteRecordNormalized): boolean {
  if (!record.components) {
    return false
  }

  return Object.values(record.components).some(component => Boolean(component))
}

/**
 * 解析 Router 路由记录标题。
 * @param record 标准化路由记录
 * @returns 标题文本
 */
function resolveRouterRecordTitle(record: RouteRecordNormalized): string {
  const title = typeof record.meta.title === 'string' ? record.meta.title.trim() : ''
  if (title) {
    return title
  }

  if (typeof record.name === 'string' && record.name.trim()) {
    return record.name
  }

  return normalizeRoutePath(record.path)
}

/**
 * 解析导出顺序。
 * @param record 标准化路由记录
 * @param index 当前索引
 * @returns 页面顺序值
 */
function resolveRouteOrder(record: RouteRecordNormalized, index: number): number {
  return resolveNumericMetaValue(record.meta.pageNumber)
    ?? resolveNumericMetaValue(record.meta.order)
    ?? index + 1
}

/**
 * 对页面列表去重并排序。
 * @param pages 页面列表
 * @returns 去重后的排序结果
 */
function dedupeAndSortPages(pages: PageInfo[]): PageInfo[] {
  const sortedPages = [...pages]
    .filter(page => Boolean(page.route))
    .sort(comparePageInfo)

  const uniquePages = new Map<string, PageInfo>()
  sortedPages.forEach(page => {
    if (!uniquePages.has(page.route)) {
      uniquePages.set(page.route, page)
    }
  })

  return Array.from(uniquePages.values())
}

/**
 * 比较两个导出页面的顺序。
 * @param left 左侧页面
 * @param right 右侧页面
 * @returns 排序结果
 */
function comparePageInfo(left: PageInfo, right: PageInfo): number {
  const leftPageNumber = resolveNumericMetaValue(left.meta?.pageNumber)
  const rightPageNumber = resolveNumericMetaValue(right.meta?.pageNumber)

  if (leftPageNumber !== undefined || rightPageNumber !== undefined) {
    if (leftPageNumber === undefined) {
      return 1
    }
    if (rightPageNumber === undefined) {
      return -1
    }
    if (leftPageNumber !== rightPageNumber) {
      return leftPageNumber - rightPageNumber
    }
  }

  if (left.order !== right.order) {
    return left.order - right.order
  }

  return left.route.localeCompare(right.route)
}

/**
 * 将路由路径归一为导出使用的绝对路径，忽略 query 和 hash。
 * @param routePath 原始路由路径
 * @returns 归一化路径
 */
function normalizeRoutePath(routePath?: string | null): string {
  if (!routePath) {
    return ''
  }

  const normalizedPath = routePath.trim().split(/[?#]/)[0]
  if (!normalizedPath) {
    return ''
  }

  return normalizedPath.startsWith('/') ? normalizedPath : `/${normalizedPath}`
}

/**
 * 解析路由元信息中的数值字段。
 * @param value 原始元信息值
 * @returns 合法数值；非法时返回 undefined
 */
function resolveNumericMetaValue(value: unknown): number | undefined {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : undefined
}

/**
 * 解析演讲者备注，只保留字符串备注。
 * @param value 原始备注值
 * @returns 备注文本；未配置时返回 null
 */
function resolveSpeakerNotes(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}
