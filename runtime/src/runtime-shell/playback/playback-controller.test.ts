/** 文件功能：用真实 Scene 会话验证 Deck 三种推进、保持/释放、取消、末页循环与冻结迟到守卫。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPageSceneSlot } from '@/core/scene/page-scene-slot'
import { deferred } from '@/core/scene/session-test-helpers'
import type { SceneRegistration, SceneTaskContext } from '@/core/scene/types'
import { DeckPlaybackSession } from './playback-controller'
import type { DeckAdvance, DeckPage } from './deck-types'

const cleanups: Array<() => void> = []
beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); vi.useRealTimers() })

/** 排空准备与启动 Promise，不跳过任务实际完成。 */
async function flush(): Promise<void> { for (let i = 0; i < 35; i += 1) await Promise.resolve() }

/** 假资源只控制 Promise，调度和完成仍使用正式 Scene/slot。 */
function resource() {
  const pending = deferred(), cleanup = vi.fn(), suspend = vi.fn()
  let context!: SceneTaskContext
  const run = vi.fn((value: SceneTaskContext) => { context = value; value.onCleanup(cleanup); return pending.promise })
  return { pending, cleanup, suspend, run, context: () => context,
    task: { id: 'content', role: 'blocking' as const, run, setSuspended: suspend } }
}

/** 注入页级声明的替身，避免复制 Scene 生命周期或依赖 Router。 */
function fixture(advance: DeckAdvance = { mode: 'timer', delayMs: 1000 }, options: { loop?: boolean; single?: boolean; define?: (context: SceneRegistration) => void | Promise<void> } = {}) {
  const slot = createPageSceneSlot(), r = resource(), paths: string[] = []
  const stage = { ...slot, prepare(input) {
    paths.push(input.path)
    return slot.prepare({ ...input, define: input.path === '/a' ? options.define ?? (context => context.register(r.task)) : () => {} })
  } }
  const pages: DeckPage[] = [{ path: '/a', advance }, ...options.single ? [] : [{ path: '/b', advance: { mode: 'manual' as const, delayMs: 1000 } }]]
  const deck = new DeckPlaybackSession({ pages, stage, loop: options.loop, clock: {
    now: () => Date.now(), setTimeout: (callback, delay) => setTimeout(callback, delay), clearTimeout: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
  } })
  cleanups.push(() => deck.dispose())
  return { deck, slot, r, paths }
}

it('manual 页实际完成后仍等待手动翻页，旧页面任务离场清理', async () => {
  const { deck, r, paths } = fixture({ mode: 'manual', delayMs: 1000 })
  deck.start(); await flush(); r.pending.resolve(); await flush()
  await vi.advanceTimersByTimeAsync(10000)
  expect(paths).toEqual(['/a'])
  expect(deck.getSnapshot().scene?.phase).toBe('completed')
  expect(deck.go(1)).toBe(true); await flush()
  expect(r.cleanup).toHaveBeenCalledOnce()
  expect(paths).toEqual(['/a', '/b'])
})

it('timer 到点取消未完成的 blocking，即使该任务受阻也不等待', async () => {
  const { deck, r, paths } = fixture()
  deck.start(); await flush(); r.context().setBlocked('缓冲')
  expect(deck.getSnapshot().state).toBe('blocked')
  await vi.advanceTimersByTimeAsync(1000)
  expect(paths).toEqual(['/a', '/b'])
  expect(r.context().signal.aborted).toBe(true)
  expect(r.cleanup).toHaveBeenCalledOnce()
})

it('scene_end 等实际完成后再完整停留，多个完成回报只推进一次', async () => {
  const a = resource(), b = resource()
  const { deck, paths } = fixture({ mode: 'scene_end', delayMs: 1000, completionDelayMs: 200 }, {
    define(context) { context.register(a.task); context.register({ ...b.task, id: 'other' }) },
  })
  deck.start(); await flush(); a.pending.resolve(); await flush()
  await vi.advanceTimersByTimeAsync(1500)
  expect(paths).toEqual(['/a'])
  b.pending.resolve(); await flush()
  await vi.advanceTimersByTimeAsync(199); expect(paths).toEqual(['/a'])
  await vi.advanceTimersByTimeAsync(1); expect(paths).toEqual(['/a', '/b'])
})

it('ambient 无限任务不阻塞 scene_end，离页后被取消', async () => {
  const ornament = resource()
  const { deck, r, paths } = fixture({ mode: 'scene_end', delayMs: 1000, completionDelayMs: 10 }, {
    define(context) { context.register({ id: 'done', role: 'blocking', run() {} }); context.register({ ...ornament.task, role: 'ambient', finite: false }) },
  })
  deck.start(); await flush(); await vi.advanceTimersByTimeAsync(10)
  expect(paths).toEqual(['/a', '/b'])
  expect(ornament.context().signal.aborted).toBe(true)
  expect(r.run).not.toHaveBeenCalled()
})

it('hold 不暂停 Scene；release 重算 timer 的完整停留，不补跳', async () => {
  const { deck, r, paths } = fixture()
  deck.start(); await flush(); await vi.advanceTimersByTimeAsync(900)
  deck.hold(); await vi.advanceTimersByTimeAsync(10000)
  expect(r.suspend).not.toHaveBeenCalled()
  expect(r.context().signal.aborted).toBe(false)
  expect(paths).toEqual(['/a'])
  deck.release(); await vi.advanceTimersByTimeAsync(999)
  expect(paths).toEqual(['/a'])
  await vi.advanceTimersByTimeAsync(1); expect(paths).toEqual(['/a', '/b'])
})

it('hold 期间完成的 scene_end 在 release 后重新计结束停留', async () => {
  const { deck, r, paths } = fixture({ mode: 'scene_end', delayMs: 1000, completionDelayMs: 200 })
  deck.start(); await flush(); deck.hold(); r.pending.resolve(); await flush()
  await vi.advanceTimersByTimeAsync(10000); expect(paths).toEqual(['/a'])
  deck.release(); await vi.advanceTimersByTimeAsync(199); expect(paths).toEqual(['/a'])
  await vi.advanceTimersByTimeAsync(1); expect(paths).toEqual(['/a', '/b'])
})

it('冻结暂停 Scene 与推进预算，恢复后按剩余值继续', async () => {
  const { deck, r, paths } = fixture()
  deck.start(); await flush(); await vi.advanceTimersByTimeAsync(700)
  deck.setSuspended(true); await vi.advanceTimersByTimeAsync(10000)
  expect(paths).toEqual(['/a']); expect(r.suspend).toHaveBeenLastCalledWith(true)
  deck.setSuspended(false); expect(r.suspend).toHaveBeenLastCalledWith(false)
  await vi.advanceTimersByTimeAsync(299); expect(paths).toEqual(['/a'])
  await vi.advanceTimersByTimeAsync(1); expect(paths).toEqual(['/a', '/b'])
})

it('计时明显迟到时进入 hold，释放后完整计时而非恢复即连跳', async () => {
  const { deck, paths } = fixture()
  deck.start(); await flush(); vi.setSystemTime(Date.now() + 10000)
  await vi.advanceTimersByTimeAsync(1000)
  expect(deck.getSnapshot().held).toBe(true); expect(paths).toEqual(['/a'])
  deck.release(); await vi.advanceTimersByTimeAsync(1000)
  expect(paths).toEqual(['/a', '/b'])
})

it('末页结束释放 ambient/未完成 blocking，单页循环重新创建 generation', async () => {
  const first = fixture({ mode: 'timer', delayMs: 20 }, { single: true })
  first.deck.start(); await flush(); await vi.advanceTimersByTimeAsync(20)
  expect(first.deck.getSnapshot().state).toBe('ended'); expect(first.r.cleanup).toHaveBeenCalledOnce()
  const second = fixture({ mode: 'timer', delayMs: 20 }, { single: true, loop: true })
  second.deck.start(); await flush(); const generation = second.deck.getSnapshot().scene!.generation
  await vi.advanceTimersByTimeAsync(20)
  expect(second.paths).toEqual(['/a', '/a'])
  expect(second.deck.getSnapshot().scene!.generation).toBeGreaterThan(generation)
})

it('多页循环从末页回到首个可见页，手动边界不会绕回', async () => {
  const slot = createPageSceneSlot(), paths: string[] = []
  const deck = new DeckPlaybackSession({ loop: true, stage: { ...slot, prepare(input) { paths.push(input.path); return slot.prepare({ ...input, define() {} }) } }, pages: [
    { path: '/hidden', hidden: true, advance: { mode: 'timer', delayMs: 10 } },
    { path: '/a', advance: { mode: 'timer', delayMs: 10 } }, { path: '/b', advance: { mode: 'timer', delayMs: 10 } },
  ] })
  cleanups.push(() => deck.dispose()); deck.start(); await flush()
  expect(deck.go(-1)).toBe(false)
  await vi.advanceTimersByTimeAsync(20)
  expect(paths).toEqual(['/a', '/b', '/a'])
})

it('准备中退出立即取消，迟到 define 不启动任务', async () => {
  const ready = deferred(), run = vi.fn()
  const { deck, slot } = fixture({ mode: 'timer', delayMs: 1000 }, { define: async context => {
    await ready.promise
    if (!context.signal.aborted) context.register({ id: 'late', role: 'blocking', run })
  } })
  deck.start(); await flush(); const old = slot.getCurrent()!
  deck.stop(); ready.resolve(); await flush()
  expect(old.getSnapshot().phase).toBe('stopped'); expect(run).not.toHaveBeenCalled()
  expect(deck.getSnapshot().state).toBe('stopped'); expect(vi.getTimerCount()).toBe(0)
})

it('缺少 scene_end 完成目标、准备失败和旧推进模式明确报错', async () => {
  const empty = fixture({ mode: 'scene_end', delayMs: 1000 }, { define() {} })
  empty.deck.start(); await flush()
  expect(empty.deck.getSnapshot().issue?.code).toBe('SCENE_COMPLETION_REQUIRED')
  const failed = fixture({ mode: 'timer', delayMs: 1000 }, { define() { throw new Error('原始异常') } })
  failed.deck.start(); await flush(); expect(failed.deck.getSnapshot().state).toBe('failed')
  expect(failed.deck.retry()).toBe(true); await flush()
  const legacy = fixture({ mode: 'timeline_end', delayMs: 1000 } as unknown as DeckAdvance)
  legacy.deck.start(); await flush(); expect(legacy.deck.getSnapshot().issue?.code).toBe('DECK_ADVANCE_UNSUPPORTED')
})

it('旧 Promise 成败不能污染手动进入的新页，重复 stop/dispose 安全', async () => {
  const { deck, r } = fixture()
  deck.start(); await flush(); deck.go(1); await flush()
  r.pending.reject(new Error('迟到失败')); await flush()
  expect(deck.getSnapshot()).toMatchObject({ path: '/b', state: 'playing' })
  expect(deck.stop()).toBe(true); expect(deck.stop()).toBe(false)
  deck.dispose(); expect(deck.start()).toBe(false); expect(vi.getTimerCount()).toBe(0)
})

it('playing 发布时停止不会再启动任务或建立计时', async () => {
  const { deck, r } = fixture()
  deck.subscribe(value => { if (value.state === 'playing') deck.stop() })
  deck.start(); await flush()
  expect(r.run).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0)
})

it('卸载时用户清理重入切页不能复活已经 dispose 的宿主', async () => {
  const { deck, r, paths } = fixture()
  deck.start(); await flush()
  r.context().onCleanup(() => deck.go(1))
  deck.dispose(); await flush()
  expect(paths).toEqual(['/a']); expect(vi.getTimerCount()).toBe(0)
})
