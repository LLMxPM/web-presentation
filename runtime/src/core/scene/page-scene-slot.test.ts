/** 文件功能：验证宿主快速切页的 generation 围栏，以及静态执行在会话创建之前阻断副作用。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPageSceneSlot } from './page-scene-slot'
import { deferred, flushScenePromises, task } from './session-test-helpers'
import type { SceneRegistration } from './types'

describe('PageSceneSlot', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it.each(['capture', 'export', 'thumbnail'] as const)('静态 %s 不创建会话、不执行 define', async execution => {
    const slot = createPageSceneSlot(), define = vi.fn()
    expect(await slot.prepare({ execution, advanceMode: 'scene_end', define })).toBeNull()
    expect(slot.getCurrent()).toBeNull()
    expect(define).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('快速切页中断尚未完成的 prepare，新页成功不受旧 Promise 拒绝影响', async () => {
    const slot = createPageSceneSlot(), pending = deferred(), run = vi.fn(), cleanup = vi.fn()
    let oldContext!: SceneRegistration
    const oldPreparing = slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: async context => {
      oldContext = context
      context.onCleanup(cleanup)
      await pending.promise
      context.register(task('old', { run }))
    } })
    await flushScenePromises()
    const current = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: context => context.register(task('new')) })
    expect(await oldPreparing).toBeNull()
    expect(oldContext.signal.aborted).toBe(true)
    expect(cleanup).toHaveBeenCalledOnce()
    expect(current!.getSnapshot().generation).toBe(2)
    pending.reject(new Error('late'))
    await current!.start(); await flushScenePromises()
    expect((await current!.finished).phase).toBe('completed')
    expect(run).not.toHaveBeenCalled()
    expect(slot.getCurrent()).toBe(current)
    slot.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('旧运行任务迟到完成不影响重新进入的同页；切到静态态立即释放当前任务', async () => {
    const slot = createPageSceneSlot(), oldDone = deferred(), newDone = deferred()
    const old = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end',
      define: context => context.register(task('same-page', { run: () => oldDone.promise })) })
    await old!.start()
    const current = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end',
      define: context => context.register(task('same-page', { run: () => newDone.promise })) })
    await current!.start()
    oldDone.resolve(); await flushScenePromises()
    expect(old!.getSnapshot().phase).toBe('stopped')
    expect(current!.getSnapshot().phase).toBe('running')
    const define = vi.fn()
    expect(await slot.prepare({ execution: 'capture', advanceMode: 'scene_end', define })).toBeNull()
    newDone.reject(new Error('late'))
    await flushScenePromises()
    expect(current!.getSnapshot().phase).toBe('stopped')
    expect(define).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('旧清理回调重入切页时，外层切换不能覆盖较新的 generation', async () => {
    const slot = createPageSceneSlot(), run = vi.fn()
    let reentered: ReturnType<typeof slot.prepare>
    const first = await slot.prepare({ execution: 'presentation', advanceMode: 'manual', define: context => {
      context.onCleanup(() => {
        reentered = slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: next => next.register(task('latest', { run })) })
      })
    } })
    await first!.start()
    const overwritten = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: next => next.register(task('obsolete')) })
    expect(overwritten).toBeNull()
    const latest = await reentered!
    expect(slot.getCurrent()).toBe(latest)
    await latest!.start()
    await flushScenePromises()
    expect(run).toHaveBeenCalledOnce()
    expect(latest!.getSnapshot().generation).toBe(3)
    slot.stop()
    expect(vi.getTimerCount()).toBe(0)
  })
})
