// @vitest-environment jsdom

/**
 * 文件用途：验证页面翻页组合式函数在首页、末页与正常页面的边界状态。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePageNavigation } from './usePageNavigation'

const { routeState, routerPushSpy, mockRoutes } = vi.hoisted(() => ({
  routeState: {
    path: '/first',
  },
  routerPushSpy: vi.fn(),
  mockRoutes: [
    { name: '第一页', path: '/first', level: 0, order: 1, pageNumber: 1 },
    { name: '第二页', path: '/second', level: 0, order: 2, pageNumber: 2 },
  ],
}))
let consoleWarnSpy: ReturnType<typeof vi.spyOn>

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({
    push: routerPushSpy,
  }),
}))

vi.mock('@/core/utils/route-generator', () => {
  const findByPageNumber = (pageNumber: number) => {
    return mockRoutes.find(route => route.pageNumber === pageNumber)
  }

  const getSortedRoutes = () => [...mockRoutes].sort((a, b) => a.pageNumber - b.pageNumber)

  return {
    getPageNumberByPath: (path: string) => mockRoutes.find(route => route.path === path)?.pageNumber,
    getRouteInfoByPageNumber: findByPageNumber,
    getPreviousPageRouteInfo: (currentPageNumber: number) => {
      const routes = getSortedRoutes()
      const currentIndex = routes.findIndex(route => route.pageNumber === currentPageNumber)
      return currentIndex > 0 ? routes[currentIndex - 1] : undefined
    },
    getNextPageRouteInfo: (currentPageNumber: number) => {
      const routes = getSortedRoutes()
      const currentIndex = routes.findIndex(route => route.pageNumber === currentPageNumber)
      return currentIndex >= 0 && currentIndex < routes.length - 1 ? routes[currentIndex + 1] : undefined
    },
    getRouteInfosSortedByPageNumber: getSortedRoutes,
  }
})

beforeEach(() => {
  consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
})

afterEach(() => {
  routeState.path = '/first'
  routerPushSpy.mockReset()
  consoleWarnSpy.mockRestore()
})

describe('usePageNavigation', () => {
  it('首页应把不存在的上一页归一化为空状态', async () => {
    routeState.path = '/first'

    const navigation = usePageNavigation()

    expect(navigation.previousPage.value).toBeNull()
    expect(navigation.canGoPrevious.value).toBe(false)
    expect(navigation.getPageTitle(navigation.previousPage.value)).toBe('未知页面')

    await navigation.goToPreviousPage()

    expect(routerPushSpy).not.toHaveBeenCalled()
  })

  it('末页应把不存在的下一页归一化为空状态', async () => {
    routeState.path = '/second'

    const navigation = usePageNavigation()

    expect(navigation.nextPage.value).toBeNull()
    expect(navigation.canGoNext.value).toBe(false)
    expect(navigation.getPageTitle(navigation.nextPage.value)).toBe('未知页面')

    await navigation.goToNextPage()

    expect(routerPushSpy).not.toHaveBeenCalled()
  })

  it('非边界页应能导航到下一页', async () => {
    routeState.path = '/first'

    const navigation = usePageNavigation()

    expect(navigation.nextPage.value?.name).toBe('第二页')
    expect(navigation.canGoNext.value).toBe(true)

    await navigation.goToNextPage()

    expect(routerPushSpy).toHaveBeenCalledWith('/second')
  })
})
