/**
 * 页面导航相关的组合式函数
 * 提供基于路由配置的上一页、下一页导航功能
 * 基于pageNumber进行直接查询，简化逻辑
 * 重构后使用route-generator.ts中的工具函数，避免重复逻辑
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getRuntimeSession, navigateRuntimePage } from '@/core/router/runtime-session'
import {
  getPageNumberByPath,
  getRouteInfoByPageNumber,
  getPreviousPageRouteInfo,
  getNextPageRouteInfo,
  getRouteInfosSortedByPageNumber
} from '@/core/utils/route-generator'
import type { RouteInfo } from '@/core/utils/route-generator'

/**
 * 页面导航功能
 */
export function usePageNavigation() {
  const route = useRoute()
  const router = useRouter()
  const session = getRuntimeSession(router)

  /**
   * 获取当前页面的页码
   */
  const getCurrentPageNumber = (): number | undefined => {
    return getPageNumberByPath(session.requestedPath.value || route.path)
  }

  /**
   * 计算属性：上一页路由信息
   */
  const previousPage = computed<RouteInfo | null>(() => {
    const currentPageNumber = getCurrentPageNumber()
    if (currentPageNumber !== undefined) {
      return getPreviousPageRouteInfo(currentPageNumber) ?? null
    }
    return null
  })

  /**
   * 计算属性：下一页路由信息
   */
  const nextPage = computed<RouteInfo | null>(() => {
    const currentPageNumber = getCurrentPageNumber()
    if (currentPageNumber !== undefined) {
      return getNextPageRouteInfo(currentPageNumber) ?? null
    }
    return null
  })

  /**
   * 计算属性：是否可以导航到上一页
   */
  const canGoPrevious = computed(() => {
    return previousPage.value !== null
  })

  /**
   * 计算属性：是否可以导航到下一页
   */
  const canGoNext = computed(() => {
    return nextPage.value !== null
  })

  /**
   * 导航到上一页
   */
  const goToPreviousPage = async (): Promise<void> => {
    if (previousPage.value) {
      try {
        // console.log('导航到上一页', previousPage.value.path)
        await navigateRuntimePage(router, previousPage.value.path)
      } catch (error) {
        console.error('导航到上一页失败', error)
        console.error('目标路径:', previousPage.value.path)
      }
    } else {
      console.warn('没有上一页可导航')
    }
  }

  /**
   * 导航到下一页
   */
  const goToNextPage = async (): Promise<void> => {
    if (nextPage.value) {
      try {
        // console.log('导航到下一页', nextPage.value.path)
        await navigateRuntimePage(router, nextPage.value.path)
      } catch (error) {
        console.error('导航到下一页失败', error)
        console.error('目标路径:', nextPage.value.path)
      }
    } else {
      console.warn('没有下一页可导航')
    }
  }

  /**
   * 获取页面标题
   */
  const getPageTitle = (routeInfo: RouteInfo | null | undefined): string => {
    return routeInfo?.name || '未知页面'
  }

  /**
   * 获取当前页码和总页数
   */
  const getPageInfo = () => {
    const currentPageNumber = getCurrentPageNumber()
    const allNavigableRoutes = getRouteInfosSortedByPageNumber()
    return {
      currentPage: currentPageNumber || 0,
      totalPages: allNavigableRoutes.length
    }
  }

  /**
   * 根据页码获取路由信息
   */
  const getRouteByPageNumber = (pageNumber: number): RouteInfo | null => {
    return getRouteInfoByPageNumber(pageNumber) || null
  }

  /**
   * 获取所有可导航路由
   */
  const getAllNavigableRoutes = () => {
    return getRouteInfosSortedByPageNumber()
  }

  return {
    // 状态
    previousPage,
    nextPage,
    canGoPrevious,
    canGoNext,

    // 方法
    goToPreviousPage,
    goToNextPage,
    getPageTitle,
    getCurrentPageNumber,
    getPageInfo,
    getRouteByPageNumber,
    getAllNavigableRoutes
  }
}
