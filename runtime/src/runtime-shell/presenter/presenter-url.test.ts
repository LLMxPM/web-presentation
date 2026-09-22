// @vitest-environment jsdom
/**
 * 文件用途：验证 Runtime 演讲模式内部窗口 URL 构造规则。
 */

import { describe, expect, it } from 'vitest'

import {
  buildPresenterRouteUrl,
  normalizePresenterRoutePath,
  PRESENTER_CONSOLE_ROUTE,
  PRESENTER_DISPLAY_ROUTE,
} from '@/runtime-shell/presenter/presenter-url'

describe('presenter-url', () => {
  it('应保留当前 preview token 并构造控制台内部路由', () => {
    window.history.pushState(null, '', '/preview/artifacts/artifact-1?token=abc&tenant=t1#/home')

    const url = buildPresenterRouteUrl(PRESENTER_CONSOLE_ROUTE, 'channel-1', '/chapter/intro')

    expect(url).toBe(
      `${window.location.origin}/preview/artifacts/artifact-1?token=abc&tenant=t1#/chapter/intro?channel=channel-1&runtimeMode=presenter`,
    )
  })

  it('应构造观众窗口内部路由并归一化初始页', () => {
    window.history.pushState(null, '', '/preview/artifacts/artifact-1?token=abc#/home')

    const url = buildPresenterRouteUrl(PRESENTER_DISPLAY_ROUTE, 'channel-2', 'home')

    expect(url).toBe(
      `${window.location.origin}/preview/artifacts/artifact-1?token=abc#/home?channel=channel-2&runtimeMode=display`,
    )
    expect(normalizePresenterRoutePath('')).toBe('/')
    expect(normalizePresenterRoutePath('home')).toBe('/home')
  })
})
