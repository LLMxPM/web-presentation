/** 文件功能：验证 Scene 会话的幂等生命周期、取消清理、有限完成和有界失败。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deferred, flushScenePromises, scene, task } from './session-test-helpers'

describe('PageSceneSession 生命周期与完成聚合', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('prepare 只注册和准备一次，start 才执行任务', async () => {
    const prepare = vi.fn(), run = vi.fn()
    const session = scene([task('title', { prepare, run })])
    expect(session.getSnapshot().phase).toBe('idle')
    expect(session.prepare()).toBe(session.prepare())
    await session.prepare()
    expect(prepare).toHaveBeenCalledOnce()
    expect(run).not.toHaveBeenCalled()
    expect(session.getSnapshot().phase).toBe('ready')
    expect(session.start()).toBe(session.start())
    await session.start()
    await flushScenePromises()
    expect(run).toHaveBeenCalledOnce()
    expect((await session.finished).phase).toBe('completed')
    session.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('多个有限任务只结算一次，ambient 完成不影响聚合且离页才清理', async () => {
    const first = deferred(), second = deferred(), loop = deferred(), cleanup = vi.fn()
    const session = scene([task('a', { run: () => first.promise }), task('b', { run: () => second.promise }),
      task('particles', { role: 'ambient', finite: false, run: context => { context.onCleanup(cleanup); return loop.promise } })])
    const completed = vi.fn()
    session.subscribe(snapshot => { if (snapshot.phase === 'completed') completed() })
    await session.start()
    first.resolve(); await flushScenePromises()
    expect(session.getSnapshot().phase).toBe('running')
    second.resolve(); await flushScenePromises()
    expect((await session.finished).phase).toBe('completed')
    expect(completed).toHaveBeenCalledOnce()
    expect(cleanup).not.toHaveBeenCalled()
    loop.resolve(); await flushScenePromises()
    expect(completed).toHaveBeenCalledOnce()
    session.stop(); session.stop()
    expect(cleanup).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('stop 先取消信号并逆序清理，清理异常不阻断，迟到登记立即释放', async () => {
    const pending = deferred(), order: number[] = []
    const session = scene([], { advanceMode: 'manual', define: async context => {
      context.onCleanup(() => { order.push(1); expect(context.signal.aborted).toBe(true) })
      context.onCleanup(() => { order.push(2); throw new Error('cleanup') })
      await pending.promise
      context.onCleanup(() => order.push(3))
    } })
    const preparing = session.prepare()
    await flushScenePromises()
    session.stop(); session.stop()
    expect((await preparing).phase).toBe('stopped')
    expect(order).toEqual([2, 1])
    pending.resolve(); await flushScenePromises()
    expect(order).toEqual([2, 1, 3])
    expect(session.getSnapshot().phase).toBe('stopped')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('准备失败不启动任务，未知错误只返回稳定摘要', async () => {
    const run = vi.fn(), cleanup = vi.fn()
    const session = scene([task('voice', { prepare: context => {
      context.onCleanup(cleanup)
      throw new Error('secret://private-token')
    }, run })])
    expect((await session.start()).phase).toBe('failed')
    expect(run).not.toHaveBeenCalled()
    expect(session.getSnapshot().issue).toMatchObject({ code: 'SCENE_TASK_FAILED', message: '页面任务执行失败。' })
    expect(cleanup).toHaveBeenCalledOnce()
    session.stop()
    expect(session.getSnapshot().phase).toBe('failed')
  })

  it('Promise 没有提供拒绝原因时仍按准备失败处理', async () => {
    const session = scene([task('empty-rejection', { prepare: () => Promise.reject(undefined) })])
    expect((await session.prepare()).phase).toBe('failed')
    expect((await session.finished).issue?.code).toBe('SCENE_TASK_FAILED')
  })

  it('注册与准备共用超时，超时取消信号并拒绝迟到注册', async () => {
    const pending = deferred(), cleanup = vi.fn(), run = vi.fn()
    const session = scene([], { prepareTimeoutMs: 50, define: async context => {
      context.onCleanup(cleanup)
      await pending.promise
      context.register(task('late', { run }))
    } })
    const preparing = session.prepare()
    await vi.advanceTimersByTimeAsync(50)
    expect((await preparing).issue?.code).toBe('SCENE_PREPARE_TIMEOUT')
    expect(cleanup).toHaveBeenCalledOnce()
    pending.resolve(); await flushScenePromises()
    expect(run).not.toHaveBeenCalled()
    expect(session.getSnapshot().phase).toBe('failed')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('有限任务的墙钟完成期限包含受阻等待，超时取消剩余任务', async () => {
    const pending = deferred(), cleanup = vi.fn()
    const session = scene([task('voice', { run: context => {
      context.onCleanup(cleanup); context.setBlocked('buffering'); return pending.promise
    } })], { completionTimeoutMs: 100 })
    await session.start()
    expect(session.getSnapshot().phase).toBe('blocked')
    await vi.advanceTimersByTimeAsync(100)
    expect((await session.finished).issue?.code).toBe('SCENE_COMPLETION_TIMEOUT')
    expect(cleanup).toHaveBeenCalledOnce()
    pending.reject(new Error('late')); await flushScenePromises()
    expect(session.getSnapshot().issue?.code).toBe('SCENE_COMPLETION_TIMEOUT')
  })

  it('启动失败立即终止，纯 ambient 运行失败不阻塞有限完成', async () => {
    const failed = scene([task('broken', { run() { throw new Error('start') } })])
    await failed.start()
    expect((await failed.finished).phase).toBe('failed')
    const pending = deferred()
    const session = scene([task('title', { run: () => pending.promise }), task('particle', { role: 'ambient', run() { throw new Error('decorative') } })])
    await session.start()
    expect(session.getSnapshot().phase).toBe('running')
    pending.resolve(); await flushScenePromises()
    expect((await session.finished).phase).toBe('completed')
    session.stop()
  })

  it('计时或手动页面无 blocking 可准备，scene_end 必须在 prepare 报错', async () => {
    for (const advanceMode of ['manual', 'timer'] as const) {
      const session = scene([], { advanceMode })
      expect((await session.start()).phase).toBe('completed')
      session.stop()
    }
    const session = scene([task('loop', { role: 'ambient', finite: false })])
    expect((await session.prepare()).issue?.code).toBe('SCENE_COMPLETION_REQUIRED')
  })

  it('监听方在准备期间重入或在启动时退出，不重复执行也不遗留期限', async () => {
    const run = vi.fn(), session = scene([task('title', { run })])
    session.subscribe(snapshot => {
      if (snapshot.phase === 'preparing') void session.prepare()
      if (snapshot.phase === 'running') session.stop()
    })
    expect((await session.start()).phase).toBe('stopped')
    expect(run).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
})
