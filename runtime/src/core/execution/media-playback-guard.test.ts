// @vitest-environment jsdom
/** 文件功能：验证媒体守卫按执行作用域阻断自动播放，并保留手势播放。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installMediaPlaybackGuard, type MediaPlaybackGuardOptions } from './media-playback-guard'

const disposers: Array<() => void> = []

afterEach(() => {
  disposers.splice(0).forEach(dispose => dispose())
  document.body.innerHTML = ''
})

function install(options: MediaPlaybackGuardOptions = {}): () => void {
  const dispose = installMediaPlaybackGuard(options)
  disposers.push(dispose)
  return dispose
}

/** 创建可观测暂停状态的视频元素并挂到指定作用域。 */
function mountMedia(scope?: 'allow' | 'gesture' | 'block', parent: HTMLElement = document.body) {
  const container = document.createElement('div')
  if (scope) container.setAttribute('data-runtime-media', scope)
  const element = document.createElement('video')
  let paused = false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  const pause = vi.fn(() => { paused = true })
  element.pause = pause
  element.setAttribute('autoplay', '')
  container.append(element)
  parent.append(container)
  return { container, element, pause, isPaused: () => paused }
}

function dispatchPlay(element: HTMLMediaElement): void {
  element.dispatchEvent(new Event('play'))
}

describe('installMediaPlaybackGuard', () => {
  it('block 作用域阻断播放并移除 autoplay，allow 作用域不干预', () => {
    install({ fallbackMode: 'allow' })
    const blocked = mountMedia('block')
    const allowed = mountMedia('allow')

    dispatchPlay(blocked.element)
    dispatchPlay(allowed.element)

    expect(blocked.pause).toHaveBeenCalledTimes(1)
    expect(blocked.isPaused()).toBe(true)
    expect(blocked.element.hasAttribute('autoplay')).toBe(false)
    expect(allowed.pause).not.toHaveBeenCalled()
    expect(allowed.isPaused()).toBe(false)
  })

  it('gesture 作用域阻断自动播放，用户手势后允许播放', () => {
    install({ fallbackMode: 'allow' })
    const automatic = mountMedia('gesture')
    dispatchPlay(automatic.element)
    expect(automatic.isPaused()).toBe(true)

    const interactive = mountMedia('gesture')
    interactive.container.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    dispatchPlay(interactive.element)
    expect(interactive.pause).not.toHaveBeenCalled()
    expect(interactive.isPaused()).toBe(false)
  })

  it('最近的媒体作用域优先，外层 allow 不能覆盖内层 block', () => {
    install({ fallbackMode: 'allow' })
    const outer = document.createElement('div')
    outer.setAttribute('data-runtime-media', 'allow')
    document.body.append(outer)
    const inner = mountMedia('block', outer)
    const outerOnly = mountMedia(undefined, outer)

    dispatchPlay(inner.element)
    dispatchPlay(outerOnly.element)

    expect(inner.isPaused()).toBe(true)
    expect(outerOnly.isPaused()).toBe(false)
  })

  it('没有作用域时使用宿主回退策略，卸载后不再拦截', () => {
    const dispose = install({ fallbackMode: 'block' })
    const media = mountMedia()
    dispatchPlay(media.element)
    expect(media.isPaused()).toBe(true)

    const later = mountMedia()
    dispose()
    dispatchPlay(later.element)
    expect(later.pause).not.toHaveBeenCalled()
    expect(later.isPaused()).toBe(false)
  })

  it('守卫安装后动态挂载的媒体同样受控', () => {
    install({ fallbackMode: 'block' })
    const media = mountMedia()
    expect(media.pause).not.toHaveBeenCalled()
    dispatchPlay(media.element)
    expect(media.pause).toHaveBeenCalledTimes(1)
  })
})
