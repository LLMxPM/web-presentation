// @vitest-environment jsdom
/** 文件功能：验证活动页媒体会话的收集、真实事件、完成集合、generation 隔离与暂停/恢复清理。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createPageMediaSession, type PageMediaEvent } from './page-media-session'

afterEach(() => {
  document.body.innerHTML = ''
})

interface MediaFixture {
  element: HTMLVideoElement
  isPaused: () => boolean
  play: ReturnType<typeof vi.fn>
  pause: ReturnType<typeof vi.fn>
}

/** 创建带可控播放状态并挂到指定根节点的视频元素。 */
function createMedia(
  root: HTMLElement,
  options: { playing?: boolean; ended?: boolean; loop?: boolean } = {},
): MediaFixture {
  const element = document.createElement('video')
  let paused = !(options.playing ?? false)
  let ended = options.ended ?? false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  element.loop = options.loop ?? false
  element.pause = vi.fn(() => {
    paused = true
  })
  element.play = vi.fn(() => {
    paused = false
    ended = false
    return Promise.resolve()
  })
  root.append(element)
  return {
    element,
    isPaused: () => paused,
    play: element.play as unknown as ReturnType<typeof vi.fn>,
    pause: element.pause as unknown as ReturnType<typeof vi.fn>,
  }
}

/** 创建活动页根节点。 */
function createRoot(): HTMLElement {
  const root = document.createElement('div')
  document.body.append(root)
  return root
}

describe('createPageMediaSession', () => {
  it('只收集当前页非循环原生媒体，循环背景不参与完成集合', () => {
    const root = createRoot()
    createMedia(root)
    createMedia(root, { loop: true })
    const audio = document.createElement('audio')
    root.append(audio)
    const events: PageMediaEvent[] = []
    const session = createPageMediaSession({ root, generation: 3, onEvent: event => events.push(event) })

    const snapshot = session.getSnapshot()
    expect(snapshot.generation).toBe(3)
    expect(snapshot.targets).toHaveLength(2)
    expect(snapshot.allEnded).toBe(false)
    expect(events.some(event => event.type === 'targets')).toBe(true)
    session.dispose()
  })

  it('实际元素 ended 事件全部到达后才完成，并携带 generation', () => {
    const root = createRoot()
    const first = createMedia(root)
    const second = createMedia(root)
    const events: PageMediaEvent[] = []
    const session = createPageMediaSession({ root, generation: 7, onEvent: event => events.push(event) })

    first.element.dispatchEvent(new Event('ended'))
    expect(session.getSnapshot().allEnded).toBe(false)

    second.element.dispatchEvent(new Event('ended'))
    expect(session.getSnapshot().allEnded).toBe(true)
    expect(events.filter(event => event.type === 'ended')).toEqual([
      expect.objectContaining({ type: 'ended', generation: 7 }),
      expect.objectContaining({ type: 'ended', generation: 7 }),
    ])
    session.dispose()
  })

  it('动态增删目标并停掉被移除的媒体', () => {
    const root = createRoot()
    const first = createMedia(root)
    const session = createPageMediaSession({ root, generation: 1 })
    expect(session.getSnapshot().targets).toHaveLength(1)

    const second = createMedia(root, { playing: true })
    session.refresh()
    expect(session.getSnapshot().targets).toHaveLength(2)

    second.element.remove()
    session.refresh()
    expect(session.getSnapshot().targets).toHaveLength(1)
    expect(second.pause).toHaveBeenCalled()
    expect(first.element.isConnected).toBe(true)
    session.dispose()
  })

  it('同一元素替换 src 时重置结束态，迟到 ended 不会提前完成新内容', () => {
    const root = createRoot()
    const media = createMedia(root)
    const session = createPageMediaSession({ root, generation: 2 })

    media.element.dispatchEvent(new Event('ended'))
    expect(session.getSnapshot().allEnded).toBe(true)

    media.element.dispatchEvent(new Event('loadstart'))
    expect(session.getSnapshot().allEnded).toBe(false)

    media.element.dispatchEvent(new Event('ended'))
    expect(session.getSnapshot().allEnded).toBe(true)
    session.dispose()
  })

  it('dispose 后旧 generation 的事件不再上报，并停掉当前媒体', () => {
    const root = createRoot()
    const media = createMedia(root, { playing: true })
    const events: PageMediaEvent[] = []
    const session = createPageMediaSession({ root, generation: 4, onEvent: event => events.push(event) })
    const count = events.length

    session.dispose()
    media.element.dispatchEvent(new Event('ended'))
    expect(events).toHaveLength(count)
    expect(media.pause).toHaveBeenCalled()

    const nextEvents: PageMediaEvent[] = []
    const next = createPageMediaSession({ root, generation: 5, onEvent: event => nextEvents.push(event) })
    media.element.dispatchEvent(new Event('play'))
    expect(nextEvents.at(-1)).toEqual(expect.objectContaining({ type: 'play', generation: 5 }))
    next.dispose()
  })

  it('暂停/恢复只处理本会话暂停前正在播放的媒体', () => {
    const root = createRoot()
    const playing = createMedia(root, { playing: true })
    const alreadyPaused = createMedia(root, { playing: false })
    const session = createPageMediaSession({ root, generation: 1 })

    expect(session.suspend()).toBe(1)
    expect(session.isSuspended()).toBe(true)
    expect(playing.isPaused()).toBe(true)
    expect(alreadyPaused.isPaused()).toBe(true)

    expect(session.resume()).toBe(1)
    expect(playing.play).toHaveBeenCalledTimes(1)
    expect(alreadyPaused.play).not.toHaveBeenCalled()
    expect(session.isSuspended()).toBe(false)
    session.dispose()
  })

  it('play() 区分真实播放、策略阻止和媒体错误，并支持错误目标重试', async () => {
    const root = createRoot()
    const normal = createMedia(root)
    const blocked = createMedia(root)
    const failed = createMedia(root)
    blocked.play.mockRejectedValue(new DOMException('blocked', 'NotAllowedError'))
    failed.play.mockRejectedValueOnce(new Error('decode failed')).mockResolvedValue(undefined)
    const events: PageMediaEvent[] = []
    const session = createPageMediaSession({ root, generation: 9, onEvent: event => events.push(event) })

    const result = await session.play()
    expect(result.attempts).toEqual(expect.arrayContaining([
      expect.objectContaining({ targetId: expect.any(String), outcome: 'played' }),
      expect.objectContaining({ targetId: expect.any(String), outcome: 'blocked' }),
      expect.objectContaining({ targetId: expect.any(String), outcome: 'error', message: 'decode failed' }),
    ]))
    expect(result.blocked).toBe(true)
    expect(result.failed).toBe(true)
    expect(session.getSnapshot().blocked).toBe(true)
    expect(events.some(event => event.type === 'blocked')).toBe(true)

    const retry = await session.play()
    expect(retry.attempts.find(attempt => attempt.targetId === result.attempts.find(item => item.outcome === 'error')?.targetId)?.outcome).toBe('played')
    session.dispose()
  })

  it('执行上下文不允许播放时不触碰媒体元素', async () => {
    const root = createRoot()
    const media = createMedia(root)
    const session = createPageMediaSession({ root, generation: 1, allowPlayback: false })

    const result = await session.play()
    expect(result.attempts).toEqual([])
    expect(media.play).not.toHaveBeenCalled()
    session.dispose()
  })
})
