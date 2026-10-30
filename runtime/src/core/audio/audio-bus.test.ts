/** 文件功能：验证窗口音频总线的唯一所有权、真实 play Promise、静音与本地恢复释放，不宣称真实发声。 */
import { afterEach, expect, it, vi } from 'vitest'
import { AudioBus, isAudioBusManaged } from './audio-bus'
import { deferred } from '@/core/scene/session-test-helpers'

const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()) })

/** 原生媒体只替换播放 I/O，Promise 的成败由各用例控制。 */
function fixture() {
  const element = document.createElement('audio'), play = vi.fn().mockResolvedValue(undefined), pause = vi.fn()
  element.play = play; element.pause = pause
  const bus = new AudioBus({ config: () => ({ volume: { master: 0.5, narration: 0.4, effects: 0.2 }, cues: {} }) })
  cleanups.push(() => bus.dispose())
  return { element, play, pause, bus }
}

it('统一 master/分组/增益与静音，重复认领拒绝，释放后可交还其它所有者', () => {
  const { element, bus } = fixture(), lease = bus.claim(element, { owner: 'scene', group: 'narration', gain: 0.5 })
  expect(element.volume).toBeCloseTo(0.1); expect(isAudioBusManaged(element)).toBe(true)
  expect(() => bus.claim(element, { owner: 'content', group: 'content' })).toThrow()
  bus.muted.value = true; expect(element.muted).toBe(true)
  lease.release(); expect(isAudioBusManaged(element)).toBe(false)
  const next = bus.claim(element, { owner: 'content', group: 'content' }); expect(element.volume).toBe(0.5); next.release()
})

it('play 未完成前不报告成功，拒绝只报告受阻，离页后迟到成功不可复活', async () => {
  const { element, bus, play, pause } = fixture(), pending = deferred()
  play.mockReturnValueOnce(pending.promise)
  const lease = bus.claim(element, { owner: 'scene', group: 'narration' }), attempt = lease.play()
  lease.release(); expect(await attempt).toBe('unavailable'); pending.resolve(); expect(pause).toHaveBeenCalledOnce()
  const next = bus.claim(element, { owner: 'scene', group: 'narration' })
  play.mockRejectedValueOnce(new DOMException('浏览器拒绝', 'NotAllowedError'))
  expect(await next.play()).toBe('blocked')
  expect(await next.play()).toBe('played')
})

it('重试只属于当前 Scene；冻结停止所有通道，恢复不补播，已释放通道不会被旧点击重试', async () => {
  const { element, bus, play } = fixture(), lease = bus.claim(element, { owner: 'scene', group: 'narration' })
  const retry = vi.fn(async () => { await lease.play() })
  bus.setRetry(lease, retry); expect(bus.state.value.blocked).toBe(1)
  bus.setSuspended(true); await bus.retryBlocked(); expect(retry).not.toHaveBeenCalled()
  bus.setSuspended(false); expect(play).not.toHaveBeenCalled()
  await bus.retryBlocked(); expect(play).toHaveBeenCalledOnce()
  lease.release(); await bus.retryBlocked(); expect(retry).toHaveBeenCalledOnce(); expect(bus.state.value.channels).toBe(0)
})
