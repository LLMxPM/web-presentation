/**
 * 文件用途：验证路由页码目录投影与单页 module 入口的页码反查规则。
 */

import { describe, expect, it } from 'vitest'

import {
  assignPageNumbers,
  findPageNumberByModuleEntry,
  projectRouteCatalog,
  type RouteNumberingNode,
} from './page-numbers'

/** 构造带组件路径的目录项，省略 component 表示该路由没有页面模块。 */
function catalogItem(
  route: string,
  pageNumber: number | undefined,
  component?: string,
  hidden = false,
) {
  return { path: `/${route}`, pageNumber, component, hidden }
}

describe('findPageNumberByModuleEntry', () => {
  const routes = [
    catalogItem('cover', 1, '@/views/PG001.vue'),
    catalogItem('overview', 2, '@/views/PG002.vue'),
    catalogItem('draft', undefined, '@/views/PG003.vue', true),
  ]

  it('module 入口路径应与路由 component 归一后命中', () => {
    expect(findPageNumberByModuleEntry(routes, '/src/views/PG002.vue')).toBe(2)
  })

  it('入口与 component 的前缀形态不同也应命中', () => {
    expect(findPageNumberByModuleEntry(routes, 'src/views/PG001.vue')).toBe(1)
    expect(findPageNumberByModuleEntry(routes, '@/views/PG001.vue')).toBe(1)
    expect(findPageNumberByModuleEntry(routes, '/views/PG001.vue')).toBe(1)
  })

  it('隐藏路由没有页码时返回 undefined，交由调用方按 0 处理', () => {
    expect(findPageNumberByModuleEntry(routes, '/src/views/PG003.vue')).toBeUndefined()
  })

  it('同一模块被隐藏与可见路由同时引用时取已分配页码的那条', () => {
    expect(
      findPageNumberByModuleEntry(
        [catalogItem('draft', undefined, '@/views/PG003.vue', true), catalogItem('live', 7, '@/views/PG003.vue')],
        '/src/views/PG003.vue',
      ),
    ).toBe(7)
  })

  it('未挂路由的模块入口返回 undefined', () => {
    expect(findPageNumberByModuleEntry(routes, '/src/views/PG999.vue')).toBeUndefined()
  })

  it('非页面模块入口不参与反查，避免把业务路由路径误判成模块', () => {
    expect(findPageNumberByModuleEntry(routes, '/overview')).toBeUndefined()
    expect(findPageNumberByModuleEntry(routes, '/src/runtime-shell/fallback/NotFoundPage.vue')).toBeUndefined()
  })

  it('缺少 component 的目录项不应被匹配', () => {
    const withoutComponent = [{ pageNumber: 1 }]
    expect(findPageNumberByModuleEntry(withoutComponent, '/src/views/a.vue')).toBeUndefined()
  })
})

describe('projectRouteCatalog', () => {
  it('分组路由的子页码按 order 连续编号，分组自身不占页码', () => {
    const routes = [
      { route: 'group', meta: { title: '章节', order: 0 }, children: [
        { route: 'b', component: '@/views/B.vue', meta: { title: 'B', order: 1 } },
        { route: 'a', component: '@/views/A.vue', meta: { title: 'A', order: 0 } },
        { route: 'h', component: '@/views/H.vue', meta: { title: 'H', order: 2, hidden: true } },
      ] },
      { route: 'last', component: '@/views/L.vue', meta: { title: 'L', order: 1 } },
    ] as RouteNumberingNode[]

    const projection = projectRouteCatalog(assignPageNumbers(routes))

    expect(projection.catalog.map(item => [item.path, item.pageNumber])).toEqual([
      ['/group/a', 1],
      ['/group/b', 2],
      ['/group/h', undefined],
      ['/last', 3],
    ])
    expect(projection.totalPages).toBe(3)
    expect(projection.minPageNumber).toBe(1)
  })
})
