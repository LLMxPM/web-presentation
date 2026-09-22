/**
 * 文件用途：验证项目路由使用项目名称作为固定浏览器标签页标题。
 */

import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  getDefaultRouteConfigAsyncMock,
  getRouteConfigsAsyncMock,
  loadAppConfigMock,
} = vi.hoisted(() => ({
  getDefaultRouteConfigAsyncMock: vi.fn(),
  getRouteConfigsAsyncMock: vi.fn(),
  loadAppConfigMock: vi.fn(),
}))

vi.mock('@/core/utils/config', () => ({
  getDefaultRouteConfigAsync: getDefaultRouteConfigAsyncMock,
  getRouteConfigsAsync: getRouteConfigsAsyncMock,
  loadAppConfig: loadAppConfigMock,
}))

vi.mock('@/core/utils/route-generator', () => ({
  generateRoutes: vi.fn(() => []),
}))

import { createProjectRouter } from './project-router'

const PageStub = defineComponent({
  name: 'ProjectRouterPageStub',
  template: '<div />',
})

describe('createProjectRouter', () => {
  beforeEach(() => {
    document.title = '初始标题'
    window.history.replaceState(null, '', '/')
    getDefaultRouteConfigAsyncMock.mockResolvedValue([])
    getRouteConfigsAsyncMock.mockResolvedValue([])
    loadAppConfigMock.mockResolvedValue({
      app: {
        icon: 'slider',
        title: ' 测试项目 ',
        description: '',
      },
    })
  })

  it('页面切换后仍保持浏览器标题为项目名称', async () => {
    const router = await createProjectRouter({
      extraRoutes: [
        {
          path: '/first',
          component: PageStub,
          meta: { title: '第一页' },
        },
        {
          path: '/second',
          component: PageStub,
          meta: { title: '第二页' },
        },
      ],
    })

    expect(document.title).toBe('测试项目')

    await router.push('/first')
    await router.isReady()
    expect(document.title).toBe('测试项目')

    document.title = '第一页'
    await router.push('/second')
    expect(document.title).toBe('测试项目')
  })

  it('应注册演讲模式控制台与观众窗口内部路由', async () => {
    const router = await createProjectRouter()
    const routePaths = router.getRoutes().map(route => route.path)

    expect(routePaths).toContain('/__presenter')
    expect(routePaths).toContain('/__presenter-display')
  })

  it('默认 404 路由存在时演讲模式内部路由不应被吞掉', async () => {
    getDefaultRouteConfigAsyncMock.mockResolvedValue([
      {
        path: '/:pathMatch(.*)*',
        name: 'NotFound',
        component: PageStub,
      },
    ])
    const router = await createProjectRouter()

    const presenterMatch = router.resolve('/__presenter').matched
    const displayMatch = router.resolve('/__presenter-display').matched

    expect(presenterMatch).toHaveLength(1)
    expect(presenterMatch.map(route => route.name)).toEqual(['RuntimePresenterConsole'])
    expect(presenterMatch.map(route => route.name)).not.toContain('NotFound')
    expect(displayMatch).toHaveLength(1)
    expect(displayMatch.map(route => route.name)).toEqual(['RuntimePresenterDisplay'])
    expect(displayMatch.map(route => route.name)).not.toContain('NotFound')
  })
})
