/** 文件功能：验证 Scene 实际完成依赖、非负延时、冻结恢复和回调至多一次，不使用真实时间。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deferred, flushScenePromises, scene, task } from './session-test-helpers'
import type { SceneTaskContext } from './types'

describe('PageSceneSession 正向时序', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('startMs 基于本页 start，afterTrack 基于前驱实际完成加非负延时', async () => {
    const predecessor = deferred(), first = vi.fn(() => predecessor.promise), next = vi.fn(), parallel = vi.fn()
    const session = scene([task('voice', { startMs: 40, run: first }),
      task('caption', { afterTrack: 'voice', offsetMs: 30, run: next }), task('parallel', { startMs: 20, run: parallel })])
    await session.prepare()
    await vi.advanceTimersByTimeAsync(500)
    expect(first).not.toHaveBeenCalled()
    await session.start()
    await vi.advanceTimersByTimeAsync(20)
    expect(parallel).toHaveBeenCalledOnce()
    expect(first).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(20)
    expect(first).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(300)
    expect(next).not.toHaveBeenCalled()
    predecessor.resolve(); await flushScenePromises()
    await vi.advanceTimersByTimeAsync(29)
    expect(next).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(next).toHaveBeenCalledOnce()
    expect((await session.finished).phase).toBe('completed')
    session.stop()
  })

  it('blocking 受阻冻结后续起点，媒体恢复后只执行一次并通知已有任务', async () => {
    const pending = deferred(), later = vi.fn(), suspended = vi.fn()
    let context!: SceneTaskContext
    const session = scene([task('voice', { run: value => { context = value; return pending.promise }, setSuspended: suspended }),
      task('callback', { startMs: 50, run: later })])
    await session.start()
    await vi.advanceTimersByTimeAsync(20)
    context.setBlocked('buffering')
    context.setBlocked('buffering')
    expect(session.getSnapshot().blockedTaskIds).toEqual(['voice'])
    expect(suspended.mock.calls).toEqual([[true]])
    await vi.advanceTimersByTimeAsync(200)
    expect(later).not.toHaveBeenCalled()
    context.setBlocked(null)
    await vi.advanceTimersByTimeAsync(29)
    expect(later).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(later).toHaveBeenCalledOnce()
    expect(suspended.mock.calls).toEqual([[true], [false]])
    pending.resolve(); await flushScenePromises()
    expect((await session.finished).phase).toBe('completed')
    session.stop()
  })

  it('宿主冻结和资源受阻合并，不因解除其中一项提前恢复', async () => {
    const pending = deferred(), callback = vi.fn()
    let context!: SceneTaskContext
    const session = scene([task('voice', { run: value => { context = value; return pending.promise } }),
      task('callback', { startMs: 50, run: callback })])
    await session.start()
    session.setSuspended(true)
    context.setBlocked('buffering')
    await vi.advanceTimersByTimeAsync(300)
    session.setSuspended(false)
    expect(session.getSnapshot().phase).toBe('blocked')
    await vi.advanceTimersByTimeAsync(300)
    expect(callback).not.toHaveBeenCalled()
    context.setBlocked(null)
    await vi.advanceTimersByTimeAsync(50)
    expect(callback).toHaveBeenCalledOnce()
    pending.resolve(); await flushScenePromises()
    session.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('ambient 受阻不冻结 blocking，完成后的延后装饰仍运行到离页', async () => {
    const loop = deferred(), blocking = vi.fn(), delayed = vi.fn()
    const session = scene([task('video', { role: 'ambient', finite: false,
      run: context => { context.setBlocked('optional-buffering'); return loop.promise } }),
      task('title', { startMs: 10, run: blocking }), task('decoration', { role: 'ambient', startMs: 50, run: delayed })])
    await session.start()
    expect(session.getSnapshot().phase).toBe('running')
    await vi.advanceTimersByTimeAsync(10)
    expect((await session.finished).phase).toBe('completed')
    expect(blocking).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(40)
    expect(delayed).toHaveBeenCalledOnce()
    session.stop()
    loop.resolve(); await flushScenePromises()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('调度晚到时每个触发点仍至多执行一次，停止后不补发尚未开始的回调', async () => {
    const callback = vi.fn(), cancelled = vi.fn()
    let time = 0
    const session = scene([task('callback', { startMs: 10, run: callback }), task('cancelled', { startMs: 2000, run: cancelled })], { now: () => time })
    await session.start()
    time = 1000
    await vi.advanceTimersByTimeAsync(10)
    expect(callback).toHaveBeenCalledOnce()
    session.setSuspended(true); session.setSuspended(false)
    expect(callback).toHaveBeenCalledOnce()
    session.stop()
    time = 10_000
    await vi.advanceTimersByTimeAsync(10_000)
    expect(cancelled).not.toHaveBeenCalled()
  })

  it('ambient 前驱失败若影响 blocking 则立即失败，不等待完成期限', async () => {
    const next = vi.fn()
    const session = scene([task('optional', { role: 'ambient', run: () => Promise.reject(new Error('failed')) }),
      task('dependent', { afterTrack: 'optional', run: next })])
    await session.start()
    expect((await session.finished).phase).toBe('failed')
    expect(session.getSnapshot().issue?.taskId).toBe('optional')
    expect(next).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('Scene prepare 阶段时序校验', () => {
  it.each([
    [task('missing', { afterTrack: 'none' })],
    [task('self', { afterTrack: 'self' })],
    [task('a', { afterTrack: 'b' }), task('b', { afterTrack: 'a' })],
    [task('a'), task('b', { afterTrack: 'a', offsetMs: -1 })],
    [task('a'), task('b', { afterTrack: 'a', startMs: 1 })],
    [task('a', { role: 'ambient', finite: false }), task('b', { afterTrack: 'a' })],
    [task('a', { finite: false })],
    [task('a', { startMs: Infinity })],
    [task('a', { startMs: NaN })],
    [task('a', { offsetMs: 1 })],
    [task('a'), task('a')],
  ].map(tasks => [tasks]))('拒绝非法或无法完成的任务图 %#', async tasks => {
    const session = scene(tasks)
    expect((await session.prepare()).issue?.code).toBe('SCENE_TASK_INVALID')
    expect(tasks.every(entry => vi.mocked(entry.run).mock.calls.length === 0)).toBe(true)
  })

  it('拒绝超过 128 个任务及非法会话期限', async () => {
    const session = scene(Array.from({ length: 129 }, (_, index) => task(String(index))))
    expect((await session.prepare()).issue?.code).toBe('SCENE_TASK_INVALID')
    for (const completionTimeoutMs of [-1, NaN, Infinity]) {
      expect((await scene([task('x')], { completionTimeoutMs }).prepare()).issue?.code).toBe('SCENE_OPTIONS_INVALID')
    }
  })
})
