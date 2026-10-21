// @vitest-environment jsdom
/** 文件功能：验证活动页媒体会话的收集、真实事件、完成集合、generation 隔离与暂停/恢复清理。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createPageMediaSession, type PageMediaEvent } from './page-media-session'

afterEach(() => {
  document.body.innerHTML = ''
})

interface MediaFixture {
  element: HTMLMediaElement
  isPaused: () => boolean
  play: ReturnType<typeof vi.fn>
  pause: ReturnType<typeof vi.fn>
}

/** 创建带可控播放状态并挂到指定根节点的音视频元素。 */
function createMedia(
  root: HTMLElement,
  options: {
    playing?: boolean
    ended?: boolean
    loop?: boolean
    tag?: 'audio' | 'video'
    purpose?: 'content' | 'narration'
    purposeOnAncestor?: boolean
  } = {},
): MediaFixture {
  const element = document.createElement(options.tag ?? 'video')
  let paused = !(options.playing ?? false)
  let ended = options.ended ?? false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  element.loop = options.loop ?? false
  if (options.purpose) {
    if (options.purposeOnAncestor) {
      const wrapper = document.createElement('div')
      wrapper.dataset.runtimeMediaPurpose = options.purpose
      wrapper.append(element)
      root.append(wrapper)
    } else {
      element.dataset.runtimeMediaPurpose = options.purpose
      root.append(element)
    }
  } else {
    root.append(element)
  }
  element.pause = vi.fn(() => {
    paused = true
  })
  element.play = vi.fn(() => {
    paused = false
    ended = false
    return Promise.resolve()
  })
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

  it('已由页内时间轴独占的媒体不收集、不停播也不归零', () => {
    const root = createRoot()
    const owned = createMedia(root, { playing: true })
    createMedia(root)
    const session = createPageMediaSession({
      root,
      generation: 1,
      isExternallyOwned: element => element === owned.element,
    })

    expect(session.getSnapshot().targets).toHaveLength(1)
    session.dispose()
    expect(owned.pause).not.toHaveBeenCalled()
    expect(owned.isPaused()).toBe(false)
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

  it('dispose 后迟到的 play() 结果会立即停播，不产生旧 generation 幽灵声音', async () => {
    const root = createRoot()
    const fixture = createMedia(root)
    let resolvePlay: (() => void) | null = null
    fixture.element.play = vi.fn(() => new Promise<void>(resolve => { resolvePlay = resolve }))
    const session = createPageMediaSession({ root, generation: 1 })

    const playing = session.play()
    session.dispose()
    resolvePlay?.()
    await playing

    expect(fixture.element.play).toHaveBeenCalledTimes(1)
    expect(fixture.pause).toHaveBeenCalledTimes(1)
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
    createMedia(root)
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

  it('失败元素重试前先 load() 重新选源，服务恢复后可播放', async () => {
    const root = createRoot()
    const media = createMedia(root)
    Object.defineProperty(media.element, 'error', { configurable: true, get: () => ({ code: 4 }) })
    Object.defineProperty(media.element, 'networkState', { configurable: true, get: () => 3 })
    const load = vi.fn(() => {
      Object.defineProperty(media.element, 'error', { configurable: true, get: () => null })
      Object.defineProperty(media.element, 'networkState', { configurable: true, get: () => 1 })
    })
    media.element.load = load
    const session = createPageMediaSession({ root, generation: 2 })

    const result = await session.play()
    expect(load).toHaveBeenCalledTimes(1)
    expect(media.play).toHaveBeenCalledTimes(1)
    expect(load.mock.invocationCallOrder[0]).toBeLessThan(media.play.mock.invocationCallOrder[0])
    expect(result.failed).toBe(false)
    session.dispose()
  })

  it('正常元素播放前不重新加载，避免丢弃已缓冲内容', async () => {
    const root = createRoot()
    const media = createMedia(root)
    const load = vi.fn()
    media.element.load = load
    const session = createPageMediaSession({ root, generation: 1 })

    await session.play()
    expect(load).not.toHaveBeenCalled()
    expect(media.play).toHaveBeenCalledTimes(1)
    session.dispose()
  })

  it('循环背景不参与完成集合，但暂停、恢复与销毁同样生效', () => {
    const root = createRoot()
    const target = createMedia(root, { playing: true })
    const background = createMedia(root, { playing: true, loop: true })
    const session = createPageMediaSession({ root, generation: 1 })
    expect(session.getSnapshot().targets).toHaveLength(1)

    expect(session.suspend()).toBe(2)
    expect(target.isPaused()).toBe(true)
    expect(background.isPaused()).toBe(true)
    expect(session.resume()).toBe(2)
    expect(background.play).toHaveBeenCalledTimes(1)

    session.dispose()
    expect(background.pause).toHaveBeenCalled()
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

  it('restart 将已结束目标归零并重新播放，供单页循环重播', async () => {
    const root = createRoot()
    const media = createMedia(root)
    let currentTime = 42
    Object.defineProperty(media.element, 'currentTime', {
      configurable: true,
      get: () => currentTime,
      set: (value: number) => { currentTime = value },
    })
    const session = createPageMediaSession({ root, generation: 6 })

    media.element.dispatchEvent(new Event('ended'))
    expect(session.getSnapshot().allEnded).toBe(true)

    const result = await session.restart()
    expect(currentTime).toBe(0)
    expect(result.attempts).toHaveLength(1)
    expect(result.attempts[0].outcome).toBe('played')
    expect(session.getSnapshot().allEnded).toBe(false)
    session.dispose()
  })

  it('读取元素或祖先的媒体用途，未声明时按 content 兼容', () => {
    const root = createRoot()
    const video = createMedia(root)
    const content = createMedia(root, { tag: 'audio', purpose: 'content' })
    const narration = createMedia(root, { tag: 'audio', purpose: 'narration', purposeOnAncestor: true })
    const session = createPageMediaSession({ root, generation: 1 })

    const targets = session.getSnapshot().targets
    expect(targets).toEqual(expect.arrayContaining([
      expect.objectContaining({ purpose: 'content', autoplayEligible: false }),
      expect.objectContaining({ purpose: 'narration', autoplayEligible: true }),
    ]))
    expect(targets).toHaveLength(3)
    expect(video.element.tagName).toBe('VIDEO')
    expect(content.element.dataset.runtimeMediaPurpose).toBe('content')
    expect(narration.element.isConnected).toBe(true)
    session.dispose()
  })

  it('playAutoplay 只播放旁白，内容音频保持用户手势播放', async () => {
    const root = createRoot()
    const content = createMedia(root, { tag: 'audio' })
    const narration = createMedia(root, { tag: 'audio', purpose: 'narration' })
    const session = createPageMediaSession({ root, generation: 1 })

    const result = await session.playAutoplay()
    expect(result.attempts).toHaveLength(1)
    expect(narration.play).toHaveBeenCalledTimes(1)
    expect(content.play).not.toHaveBeenCalled()
    session.dispose()
  })

  it('多个旁白目标进入有界契约错误，不参与完成也不自动播放', async () => {
    const root = createRoot()
    const first = createMedia(root, { tag: 'audio', purpose: 'narration' })
    const second = createMedia(root, { tag: 'audio', purpose: 'narration' })
    const content = createMedia(root, { tag: 'audio' })
    const events: PageMediaEvent[] = []
    const session = createPageMediaSession({ root, generation: 1, onEvent: event => events.push(event) })

    const snapshot = session.getSnapshot()
    expect(snapshot.contractError).toContain('最多只能有一个页面旁白目标')
    expect(snapshot.targets).toEqual([
      expect.objectContaining({ purpose: 'content', participating: true }),
    ])
    expect(events.some(event => event.type === 'contract-error')).toBe(true)

    const result = await session.playAutoplay()
    expect(result.attempts).toEqual([])
    expect(first.play).not.toHaveBeenCalled()
    expect(second.play).not.toHaveBeenCalled()
    expect(content.play).not.toHaveBeenCalled()
    session.dispose()
  })

  it('旁白循环属于契约错误，不进入无限完成等待', () => {
    const root = createRoot()
    createMedia(root, { tag: 'audio', purpose: 'narration', loop: true })
    const session = createPageMediaSession({ root, generation: 1 })

    expect(session.getSnapshot().contractError).toContain('旁白不允许循环')
    expect(session.getSnapshot().targets).toHaveLength(0)
    expect(session.getSnapshot().allEnded).toBe(false)
    session.dispose()
  })

  it('动态改用途后重新计算自动播放资格与参与集合', () => {
    const root = createRoot()
    const media = createMedia(root, { tag: 'audio', purpose: 'content' })
    const session = createPageMediaSession({ root, generation: 1 })
    expect(session.getSnapshot().targets[0]).toMatchObject({ purpose: 'content', autoplayEligible: false })

    media.element.dataset.runtimeMediaPurpose = 'narration'
    session.refresh()
    expect(session.getSnapshot().targets[0]).toMatchObject({ purpose: 'narration', autoplayEligible: true })

    media.element.dataset.runtimeMediaPurpose = 'content'
    session.refresh()
    expect(session.getSnapshot().targets[0]).toMatchObject({ purpose: 'content', autoplayEligible: false })
    session.dispose()
  })

  it('会话静音对现有与后续媒体生效，解除时恢复页面自身 muted', () => {
    const root = createRoot()
    const first = createMedia(root, { tag: 'audio', purpose: 'narration' })
    first.element.muted = true
    const session = createPageMediaSession({ root, generation: 1 })

    session.setMuted(true)
    expect(session.isMuted()).toBe(true)
    expect(first.element.muted).toBe(true)

    const second = createMedia(root, { tag: 'audio', purpose: 'narration' })
    session.refresh()
    expect(second.element.muted).toBe(true)
    session.setMuted(false)
    expect(first.element.muted).toBe(true)
    expect(second.element.muted).toBe(false)
    session.dispose()
  })
})
