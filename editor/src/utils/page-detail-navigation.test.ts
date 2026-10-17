/** 文件功能：验证页面放映入口路由按项目路由树顺序选择。 */
import { describe, expect, it } from 'vitest'
import type { PageItem, ProjectRouteBinding } from '@/types/api'
import { resolvePagePresentationRoute } from './page-detail-navigation'

function pageWith(routeBindings: ProjectRouteBinding[]): PageItem {
  return { route_bindings: routeBindings } as PageItem
}

function binding(overrides: Partial<ProjectRouteBinding>): ProjectRouteBinding {
  return {
    route_id: 1,
    route: 'page',
    full_path: '/page',
    order: 1,
    parent_order: 1,
    ...overrides,
  }
}

describe('resolvePagePresentationRoute', () => {
  it('按父级顺序、同级顺序与路由 ID 选择第一条绑定', () => {
    const page = pageWith([
      binding({ route_id: 3, full_path: '/later/child', parent_order: 2, order: 1 }),
      binding({ route_id: 2, full_path: '/first/b', parent_order: 1, order: 2 }),
      binding({ route_id: 1, full_path: '/first/a', parent_order: 1, order: 1 }),
    ])
    expect(resolvePagePresentationRoute(page)).toBe('/first/a')
  })

  it('未加入路由时返回空串', () => {
    expect(resolvePagePresentationRoute(pageWith([]))).toBe('')
    expect(resolvePagePresentationRoute(null)).toBe('')
  })
})
