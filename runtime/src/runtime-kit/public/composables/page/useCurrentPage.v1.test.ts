// @vitest-environment jsdom

/**
 * 文件用途：验证当前页上下文在放映路由与单页 module 入口两种挂载方式下的页码取值。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCurrentPage } from './useCurrentPage.v1'

/** 目录行形状：与 route-generator.RouteInfo 的关键字段对齐。 */
interface CatalogRow {
  name: string
  path: string
  level: number
  order: number
  pageNumber?: number
  hidden?: boolean
  component: string
}

const { routeState, mockCatalog } = vi.hoisted(() => ({
  routeState: {
    path: '/overview',
    meta: {} as Record<string, unknown>,
    name: undefined as string | undefined,
  },
  mockCatalog: [
    { name: '封面', path: '/cover', level: 0, order: 0, pageNumber: 1, component: '@/views/PG001.vue' },
    { name: '概览', path: '/overview', level: 0, order: 1, pageNumber: 2, component: '@/views/PG002.vue' },
    { name: '草稿', path: '/draft', level: 0, order: 2, hidden: true, component: '@/views/PG003.vue' },
  ] as CatalogRow[],
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
}))

vi.mock('@/core/utils/route-generator', () => ({
  getMaxPageNumber: () => Math.max(
    ...mockCatalog.map(item => item.pageNumber).filter((value): value is number => typeof value === 'number'),
  ),
  getRouteInfoByPath: (path: string) => mockCatalog.find(item => item.path === path),
  getPageNumberByPath: (path: string) => mockCatalog.find(item => item.path === path)?.pageNumber,
  getPageNumberByModuleEntryPath: (path: string) => {
    const normalized = path.replace(/^\/+/, '').replace(/^src\//, '@/')
    const matched = mockCatalog.find(item => item.component === normalized)
    return matched?.pageNumber
  },
}))

beforeEach(() => {
  routeState.path = '/overview'
  routeState.meta = {}
  routeState.name = undefined
})

describe('useCurrentPage', () => {
  it('放映态应按路由 path 取页码，不再触发 module 入口反查', () => {
    routeState.path = '/overview'

    const page = useCurrentPage()

    expect(page.currentPage.value).toBe(2)
    expect(page.totalPages.value).toBe(2)
    expect(page.routeInfo.value?.name).toBe('概览')
    expect(page.title.value).toBe('概览')
  })

  it('单页 module 入口在 path 未命中时按入口路径反查真实页码', () => {
    routeState.path = '/src/views/PG002.vue'

    const page = useCurrentPage()

    expect(page.currentPage.value).toBe(2)
    expect(page.totalPages.value).toBe(2)
  })

  it('隐藏路由与未挂路由的模块都归一为 0', () => {
    routeState.path = '/src/views/PG003.vue'
    expect(useCurrentPage().currentPage.value).toBe(0)

    routeState.path = '/src/views/PG999.vue'
    expect(useCurrentPage().currentPage.value).toBe(0)
  })

  it('module 入口态下 routeInfo 仍为空，标题回退到宿主路由 meta', () => {
    routeState.path = '/src/views/PG002.vue'
    routeState.meta = { title: '宿主标题' }

    const page = useCurrentPage()

    expect(page.routeInfo.value).toBeNull()
    expect(page.title.value).toBe('宿主标题')
  })
})
