/**
 * 文件用途：暴露当前页面的路由、页码与标题信息。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'

import {
  getMaxPageNumber,
  getPageNumberByPath,
  getRouteInfoByPath,
} from '@/core/utils/route-generator'

/**
 * 读取当前路由对应的页面信息。
 * @returns 当前路由、页码、总页数与页面标题
 */
export function useCurrentPage() {
  const route = useRoute()
  const routeInfo = computed(() => getRouteInfoByPath(route.path) ?? null)
  const currentPage = computed(() => getPageNumberByPath(route.path) ?? 0)
  const totalPages = computed(() => Math.max(1, getMaxPageNumber()))
  const title = computed(() => String(routeInfo.value?.name || route.meta?.title || route.name || ''))

  return {
    route,
    routeInfo,
    currentPage,
    totalPages,
    title,
  }
}
