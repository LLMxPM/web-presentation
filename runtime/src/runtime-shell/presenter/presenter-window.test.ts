// @vitest-environment jsdom

/**
 * 文件用途：验证演讲模式观众窗口的打开地址与窗口参数。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildPresenterDisplayWindowFeatures,
  openPendingPresenterDisplayWindow,
  openPresenterDisplayWindow,
} from '@/runtime-shell/presenter/presenter-window'

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  Reflect.deleteProperty(window, 'getScreenDetails')
  window.history.replaceState(null, '', '/')
})

describe('presenter-window', () => {
  it('兼容入口应直接打开观众窗口并尽量使用全屏尺寸', () => {
    window.history.replaceState(null, '', '/preview/artifacts/artifact-1?token=abc#/intro')
    const windowRef = createWindowRef()
    const openMock = vi.spyOn(window, 'open').mockReturnValue(windowRef)

    const result = openPendingPresenterDisplayWindow('channel-a', '/intro')

    expect(result).toBe(windowRef)
    expect(openMock).toHaveBeenCalledTimes(1)
    expect(openMock.mock.calls[0][0]).toBe(
      `${window.location.origin}/preview/artifacts/artifact-1?token=abc#/intro?channel=channel-a&runtimeMode=display`,
    )
    expect(openMock.mock.calls[0][1]).toBe('web-presentation-presenter-display-channel-a')
    expect(String(openMock.mock.calls[0][2])).toContain('fullscreen=yes')
    expect(windowRef.moveTo).toHaveBeenCalledWith(0, 0)
    expect(windowRef.resizeTo).toHaveBeenCalled()
  })

  it('直接打开观众窗口应使用真实观众页地址', () => {
    window.history.replaceState(null, '', '/preview/artifacts/artifact-1?token=abc#/intro')
    const windowRef = createWindowRef()
    const openMock = vi.spyOn(window, 'open').mockReturnValue(windowRef)

    const result = openPresenterDisplayWindow('channel-direct', '/intro')

    expect(result).toBe(windowRef)
    expect(openMock).toHaveBeenCalledTimes(1)
    expect(openMock.mock.calls[0][0]).toBe(
      `${window.location.origin}/preview/artifacts/artifact-1?token=abc#/intro?channel=channel-direct&runtimeMode=display`,
    )
    expect(openMock.mock.calls[0][1]).toBe('web-presentation-presenter-display-channel-direct')
  })

  it('窗口特性应包含当前屏幕可用尺寸', () => {
    const features = buildPresenterDisplayWindowFeatures()

    expect(features).toContain('popup=yes')
    expect(features).toContain('fullscreen=yes')
    expect(features).toContain('left=0')
    expect(features).toContain('top=0')
    expect(features).toMatch(/width=\d+/)
    expect(features).toMatch(/height=\d+/)
  })

  it('窗口特性应支持指定目标屏幕坐标', () => {
    const features = buildPresenterDisplayWindowFeatures({
      left: 1920,
      top: 0,
      width: 1600,
      height: 900,
    })

    expect(features).toContain('left=1920')
    expect(features).toContain('top=0')
    expect(features).toContain('width=1600')
    expect(features).toContain('height=900')
  })

  it('打开观众窗口时不应在控制台侧请求屏幕检测权限', () => {
    window.history.replaceState(null, '', '/preview/artifacts/artifact-1?token=abc#/intro')
    const windowRef = createWindowRef()
    vi.spyOn(window, 'open').mockReturnValue(windowRef)
    const getScreenDetails = vi.fn()
    Object.defineProperty(window, 'getScreenDetails', {
      configurable: true,
      value: getScreenDetails,
    })

    openPresenterDisplayWindow('channel-screen', '/intro')

    expect(getScreenDetails).not.toHaveBeenCalled()
    expect(windowRef.moveTo).toHaveBeenCalledTimes(1)
    expect(windowRef.resizeTo).toHaveBeenCalledTimes(1)
  })
})

/**
 * 构造可验证的窗口引用。
 * @returns 满足 presenter-window 所需字段的窗口桩
 */
function createWindowRef(): Window {
  return {
    closed: false,
    document: {
      open: vi.fn(),
      write: vi.fn(),
      close: vi.fn(),
    },
    location: {
      href: '',
    },
    focus: vi.fn(),
    moveTo: vi.fn(),
    resizeTo: vi.fn(),
  } as unknown as Window
}
