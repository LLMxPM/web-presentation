// @vitest-environment jsdom
/** 文件功能：验证放映暂停/恢复只处理暂停前正在播放的媒体。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMediaPlaybackCoordinator } from './media-playback-guard'

afterEach(() => {
  document.body.innerHTML = ''
})

/** 创建带可控播放状态的媒体元素。 */
function createMedia(playing: boolean, ended = false) {
  const element = document.createElement('video')
  let paused = !playing
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  element.pause = vi.fn(() => { paused = true })
  element.play = vi.fn(() => {
    paused = false
    return Promise.resolve()
  })
  document.body.append(element)
  return { element, isPaused: () => paused, play: element.play as unknown as ReturnType<typeof vi.fn> }
}

describe('createMediaPlaybackCoordinator', () => {
  it('暂停时记录正在播放的媒体，恢复时只重放该集合', () => {
    const playing = createMedia(true)
    const pausedByUser = createMedia(false)
    const coordinator = createMediaPlaybackCoordinator()

    expect(coordinator.suspend(document)).toBe(1)
    expect(coordinator.isSuspended()).toBe(true)
    expect(playing.isPaused()).toBe(true)
    expect(pausedByUser.isPaused()).toBe(true)

    expect(coordinator.resume()).toBe(1)
    expect(playing.play).toHaveBeenCalledTimes(1)
    expect(pausedByUser.play).not.toHaveBeenCalled()
    expect(coordinator.isSuspended()).toBe(false)
  })

  it('重复暂停不覆盖原始记录，重复恢复无副作用', () => {
    const media = createMedia(true)
    const coordinator = createMediaPlaybackCoordinator()

    expect(coordinator.suspend(document)).toBe(1)
    expect(coordinator.suspend(document)).toBe(1)
    expect(coordinator.resume()).toBe(1)
    expect(coordinator.resume()).toBe(0)
    expect(media.play).toHaveBeenCalledTimes(1)
  })

  it('跳过已结束或已从文档移除的媒体', () => {
    const ended = createMedia(true, true)
    const removed = createMedia(true)
    const coordinator = createMediaPlaybackCoordinator()

    expect(coordinator.suspend(document)).toBe(1)
    removed.element.remove()
    expect(coordinator.resume()).toBe(0)
    expect(ended.play).not.toHaveBeenCalled()
    expect(removed.play).not.toHaveBeenCalled()
  })

  it('释放后不保留待恢复媒体', () => {
    const media = createMedia(true)
    const coordinator = createMediaPlaybackCoordinator()
    expect(coordinator.suspend(document)).toBe(1)
    coordinator.dispose()
    expect(coordinator.isSuspended()).toBe(false)
    expect(coordinator.resume()).toBe(0)
    expect(media.play).not.toHaveBeenCalled()
  })

  it('播放 Promise 拒绝时忽略错误且不中断其余恢复', async () => {
    const rejected = createMedia(true)
    rejected.play.mockRejectedValue(new Error('blocked'))
    const normal = createMedia(true)
    const coordinator = createMediaPlaybackCoordinator()

    expect(coordinator.suspend(document)).toBe(2)
    expect(coordinator.resume()).toBe(2)
    expect(normal.play).toHaveBeenCalledTimes(1)
    await Promise.resolve()
  })
})
