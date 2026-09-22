/**
 * 文件用途：暴露基于 Runtime 路由配置的目录、页码与路由查询能力。
 */

import { computed } from 'vue'

import {
  getMaxPageNumber,
  getMinPageNumber,
  getPageNumberByName,
  getPageNumberByPath,
  getRouteInfoByName,
  getRouteInfoByPageNumber,
  getRouteInfoByPath,
  getRouteInfosSortedByOrder,
  getRouteInfosSortedByPageNumber,
  getVisibleRouteInfos,
  type RouteInfo,
} from '@/core/utils/route-generator'

export interface RuntimeKitRouteCatalogItem {
  id: string
  title: string
  path: string
  order: number
  pageNumber?: number
  parentPath?: string
}

/**
 * 将 Runtime 路由信息归一为页面/组件更容易消费的目录项。
 * @param routeInfo Runtime 路由信息
 * @returns 目录项
 */
export function toRouteCatalogItem(routeInfo: RouteInfo): RuntimeKitRouteCatalogItem {
  return {
    id: routeInfo.name,
    title: routeInfo.name,
    path: routeInfo.path,
    order: routeInfo.order,
    pageNumber: routeInfo.pageNumber,
    parentPath: routeInfo.parentPath,
  }
}

/**
 * 读取当前 Runtime 路由目录，并提供常用查询函数。
 * @returns 路由目录、页码范围和查询方法
 */
export function useRouteCatalog() {
  const visibleRoutes = computed(() => getVisibleRouteInfos())
  const routesByOrder = computed(() => getRouteInfosSortedByOrder())
  const routesByPageNumber = computed(() => getRouteInfosSortedByPageNumber())
  const catalogItems = computed(() => routesByPageNumber.value.map(toRouteCatalogItem))
  const minPageNumber = computed(() => getMinPageNumber())
  const maxPageNumber = computed(() => getMaxPageNumber())

  return {
    visibleRoutes,
    routesByOrder,
    routesByPageNumber,
    catalogItems,
    minPageNumber,
    maxPageNumber,
    getPageNumberByName,
    getPageNumberByPath,
    getRouteInfoByName,
    getRouteInfoByPageNumber,
    getRouteInfoByPath,
  }
}
