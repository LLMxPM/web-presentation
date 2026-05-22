/**
 * 文件功能：验证项目路由工具方法的默认值推导与追加逻辑。
 */
import { describe, expect, it } from 'vitest'

import type { ProjectRouteTreeItem } from '@/types/api'
import {
  appendRootPageRoute,
  buildPageRouteSlug,
  isValidProjectRouteSegment,
  mapRouteTreeToWriteItems,
  normalizeProjectRouteOrders,
  validateProjectRoutes,
} from '@/utils/project-route'

describe('project-route utils', () => {
  it('优先根据页面编码生成默认路由片段', () => {
    expect(buildPageRouteSlug({
      id: 8,
      code: 'Landing_Hero',
      title: '首页横幅',
    })).toBe('landing-hero')
  })

  it('追加顶层页面路由时应自动避开重复 route 并补齐顺序', () => {
    const nextRoutes = appendRootPageRoute([
      {
        route_type: 'page',
        route: 'landing-hero',
        order: 10,
        hidden: false,
        page_id: 1,
        children: [],
      },
    ], {
      id: 2,
      code: 'Landing_Hero',
      title: '首页横幅副本',
    })

    expect(nextRoutes).toHaveLength(2)
    expect(nextRoutes[1]).toMatchObject({
      route_type: 'page',
      route: 'landing-hero-2',
      order: 20,
      hidden: false,
      page_id: 2,
    })
  })

  it('应将树形路由结构转换为可写草稿结构', () => {
    const routeTree: ProjectRouteTreeItem[] = [
      {
        id: 1,
        route_type: 'group',
        route: 'demo',
        order: 10,
        icon: 'folder',
        hidden: false,
        group_title: '示例',
        page_id: null,
        page_code: null,
        page_title: null,
        display_title: '示例',
        children: [
          {
            id: 2,
            route_type: 'page',
            route: 'home',
            order: 10,
            icon: null,
            hidden: false,
            page_id: 100,
            page_code: 'home-page',
            page_title: '首页',
            display_title: '首页',
          },
        ],
      },
    ]

    expect(mapRouteTreeToWriteItems(routeTree)).toEqual([
      {
        route_type: 'group',
        route: 'demo',
        order: 10,
        icon: 'folder',
        hidden: false,
        group_title: '示例',
        page_id: null,
        children: [
          {
            route: 'home',
            order: 10,
            icon: null,
            hidden: false,
            page_id: 100,
          },
        ],
      },
    ])
  })

  it('应按当前顺序重建顶层与子级的 order', () => {
    expect(normalizeProjectRouteOrders([
      {
        route_type: 'group',
        route: 'b',
        order: 999,
        hidden: false,
        group_title: 'B',
        children: [
          { route: 'child-b', order: 500, hidden: false, page_id: 2 },
          { route: 'child-a', order: 100, hidden: false, page_id: 1 },
        ],
      },
      {
        route_type: 'page',
        route: 'a',
        order: 1,
        hidden: false,
        page_id: 3,
        children: [],
      },
    ])).toEqual([
      {
        route_type: 'group',
        route: 'b',
        order: 10,
        icon: null,
        hidden: false,
        group_title: 'B',
        page_id: null,
        children: [
          { route: 'child-b', order: 10, icon: null, hidden: false, page_id: 2 },
          { route: 'child-a', order: 20, icon: null, hidden: false, page_id: 1 },
        ],
      },
      {
        route_type: 'page',
        route: 'a',
        order: 20,
        icon: null,
        hidden: false,
        group_title: null,
        page_id: 3,
        children: [],
      },
    ])
  })

  it('应按 Runtime 单段路由片段规则校验 route', () => {
    expect(isValidProjectRouteSegment('home')).toBe(true)
    expect(isValidProjectRouteSegment('chapter-1')).toBe(true)
    expect(isValidProjectRouteSegment('PAGE_01')).toBe(true)
    expect(isValidProjectRouteSegment('/')).toBe(false)
    expect(isValidProjectRouteSegment('/home')).toBe(false)
    expect(isValidProjectRouteSegment('home/')).toBe(false)
    expect(isValidProjectRouteSegment('a/b')).toBe(false)
    expect(isValidProjectRouteSegment(' ')).toBe(false)
    expect(isValidProjectRouteSegment('has space')).toBe(false)
  })

  it('保存前应提示非法顶层与子级 route', () => {
    const errors = validateProjectRoutes([
      {
        route_type: 'page',
        route: '/home',
        order: 10,
        hidden: false,
        page_id: 1,
        children: [],
      },
      {
        route_type: 'group',
        route: 'chapter',
        order: 20,
        hidden: false,
        group_title: '章节',
        children: [
          { route: 'a/b', order: 10, hidden: false, page_id: 2 },
        ],
      },
    ])

    expect(errors).toEqual([
      '第 1 个顶层节点 的 Route 只能使用单段相对片段，例如 home、chapter-1 或 PAGE_01，不能使用 /、/home、home/、a/b 或包含空格。',
      '第 2 个顶层节点 的第 1 个子页 的 Route 只能使用单段相对片段，例如 home、chapter-1 或 PAGE_01，不能使用 /、/home、home/、a/b 或包含空格。',
    ])
  })
})
