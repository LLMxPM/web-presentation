// @vitest-environment jsdom

/**
 * 文件用途：验证全部页面导出时的页面收集回退逻辑，确保页码目录缺失时仍可从可见路由或 Router 路由表收集页面。
 */

import type { Router, RouteRecordNormalized } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { collectAllExportPages } from './export-pages'

const mockRouteCatalog = vi.hoisted(() => ({
  paged: [] as Array<{
    path: string
    name: string
    order?: number
    pageNumber?: number
    level?: number
    hidden?: boolean
    speakerNotes?: string | null
  }>,
  visible: [] as Array<{
    path: string
    name: string
    order?: number
    pageNumber?: number
    level?: number
    hidden?: boolean
    speakerNotes?: string | null
  }>,
}))

vi.mock('@/core/utils/route-generator', () => ({
  getRouteInfosSortedByPageNumber: () => [...mockRouteCatalog.paged],
  getVisibleRouteInfos: () => [...mockRouteCatalog.visible],
}))

describe('collectAllExportPages', () => {
  beforeEach(() => {
    mockRouteCatalog.paged = []
    mockRouteCatalog.visible = []
  })

  it('页码目录为空时应回退到可见路由目录', async () => {
    mockRouteCatalog.visible = [
      { path: '/page-2', name: '第二页', order: 2, level: 0, hidden: false, speakerNotes: '第二页备注' },
      { path: '/page-1', name: '第一页', order: 1, level: 0, hidden: false, speakerNotes: '第一页备注' },
    ]

    const pages = await collectAllExportPages()

    expect(pages.map(page => page.route)).toEqual(['/page-1', '/page-2'])
    expect(pages.map(page => page.title)).toEqual(['第一页', '第二页'])
    expect(pages.map(page => page.meta?.speakerNotes)).toEqual(['第一页备注', '第二页备注'])
  })

  it('路由目录为空时应回退到 Router 路由表', async () => {
    const router = {
      getRoutes: () => ([
        createRouteRecord('/', { children: [createRouteRecord('/layout-child')] }),
        createRouteRecord('/group', { redirect: '/group/index' }),
        createRouteRecord('/hidden', { meta: { title: '隐藏页', hidden: true, order: 3 } }),
        createRouteRecord('/__presenter-display', { meta: { title: '演讲窗口', order: 4 } }),
        createRouteRecord('/:pathMatch(.*)*', { meta: { title: '404', order: 5 } }),
        createRouteRecord('/page-2', { meta: { title: '第二页', order: 2, speakerNotes: '第二页备注' } }),
        createRouteRecord('/page-1', { meta: { title: '第一页', order: 1, speakerNotes: '第一页备注' } }),
      ]),
    } satisfies Pick<Router, 'getRoutes'>

    const pages = await collectAllExportPages(router)

    expect(pages.map(page => page.route)).toEqual(['/page-1', '/page-2'])
    expect(pages.map(page => page.title)).toEqual(['第一页', '第二页'])
    expect(pages.map(page => page.meta?.speakerNotes)).toEqual(['第一页备注', '第二页备注'])
  })
})

/**
 * 创建最小化的标准化路由记录桩。
 * @param path 路由路径
 * @param overrides 需要覆盖的字段
 * @returns 路由记录桩
 */
function createRouteRecord(
  path: string,
  overrides: Partial<RouteRecordNormalized> = {},
): RouteRecordNormalized {
  return {
    path,
    name: overrides.name,
    meta: overrides.meta || {},
    redirect: overrides.redirect,
    aliasOf: overrides.aliasOf,
    children: overrides.children || [],
    components: overrides.components || { default: () => null },
    instances: overrides.instances || {},
    leaveGuards: overrides.leaveGuards || new Set(),
    updateGuards: overrides.updateGuards || new Set(),
    enterCallbacks: overrides.enterCallbacks || {},
    props: overrides.props || { default: false },
    beforeEnter: overrides.beforeEnter,
    mods: overrides.mods || {},
  } as unknown as RouteRecordNormalized
}
