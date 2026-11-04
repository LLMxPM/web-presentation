/**
 * 文件用途：暴露当前页面的路由、页码与标题信息。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'

import {
  getMaxPageNumber,
  getPageNumberByModuleEntryPath,
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
  // 单页预览与截图按 module 入口挂载，路由 path 匹配不到时按入口路径反查同一份目录。
  const currentPage = computed(() => getPageNumberByPath(route.path) ?? getPageNumberByModuleEntryPath(route.path) ?? 0)
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
