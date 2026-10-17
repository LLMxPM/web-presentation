/** 文件功能：用虚拟时钟验证放映调度状态机、剩余时间、旧回调作废与边界推进。 */
import { describe, expect, it } from 'vitest'
import { PlaybackController, type PlaybackClock, type PlaybackPage } from './playback-controller'

/** 可手动推进的单调时钟；到期计时按时间与创建顺序依次触发。 */
class ManualClock implements PlaybackClock {
  private current = 0
  private sequence = 0
  private readonly timers = new Map<number, { at: number; callback: () => void }>()

  now(): number {
    return this.current
  }

  setTimeout(callback: () => void, delayMs: number): unknown {
    const handle = ++this.sequence
    this.timers.set(handle, { at: this.current + Math.max(0, delayMs), callback })
    return handle
  }

  clearTimeout(handle: unknown): void {
    this.timers.delete(handle as number)
  }

  get pending(): number {
    return this.timers.size
  }

  advance(ms: number): void {
    const target = this.current + ms
    for (;;) {
      let next: [number, { at: number; callback: () => void }] | undefined
      for (const entry of this.timers) {
        if (entry[1].at > target) continue
        if (!next || entry[1].at < next[1].at || (entry[1].at === next[1].at && entry[0] < next[0])) {
          next = entry
        }
      }
      if (!next) break
      this.timers.delete(next[0])
      this.current = next[1].at
      next[1].callback()
    }
    this.current = target
  }
}

const TIMER_PAGES: PlaybackPage[] = [
  { path: '/one', advance: { mode: 'timer', delayMs: 5000 } },
  { path: '/two', advance: { mode: 'timer', delayMs: 7000 } },
  { path: '/manual', advance: { mode: 'manual', delayMs: 5000 } },
  { path: '/hidden', advance: { mode: 'timer', delayMs: 1000 }, hidden: true },
]

/** 创建带虚拟时钟与导航记录的控制器；navigate 可被单个用例覆盖。 */
function createController(options: {
  pages?: PlaybackPage[]
  loop?: boolean
  initialPath?: string
  navigate?: (path: string) => void | Promise<void>
} = {}) {
  const clock = new ManualClock()
  const navigations: string[] = []
  const controller = new PlaybackController({
    pages: options.pages ?? TIMER_PAGES,
    loop: options.loop,
    initialPath: options.initialPath ?? '/one',
    clock,
    navigate: options.navigate ?? (path => { navigations.push(path) }),
  })
  return { clock, navigations, controller }
}

/** 开始并完成当前页就绪，返回当前 generation。 */
function startReady(controller: PlaybackController, path?: string): number {
  controller.start(path)
  const generation = controller.getSnapshot().generation
  expect(controller.reportReady(controller.getSnapshot().path, generation)).toBe(true)
  return generation
}

/** 刷新已排队的 Promise 拒绝回调。 */
async function flushMicrotasks(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

describe('PlaybackController 就绪与计时', () => {
  it('就绪前不计时，就绪后只建立一个句柄并在完整停留后推进', () => {
    const { clock, navigations, controller } = createController()
    expect(controller.getSnapshot()).toMatchObject({ state: 'stopped', path: '/one', generation: 0 })

    expect(controller.start()).toBe(true)
    expect(controller.getSnapshot()).toMatchObject({ state: 'preparing', remainingMs: 5000 })
    clock.advance(20_000)
    expect(navigations).toEqual([])
    expect(clock.pending).toBe(0)

    expect(controller.reportReady('/one', controller.getSnapshot().generation)).toBe(true)
    expect(controller.getSnapshot().state).toBe('playing')
    expect(clock.pending).toBe(1)

    clock.advance(4_999)
    expect(navigations).toEqual([])
    clock.advance(1)
    expect(navigations).toEqual(['/two'])
    expect(controller.getSnapshot()).toMatchObject({ state: 'preparing', path: '/one' })

    controller.notifyPageChange('/two')
    expect(clock.pending).toBe(0)
    expect(controller.reportReady('/two', controller.getSnapshot().generation)).toBe(true)
    clock.advance(6_999)
    expect(navigations).toEqual(['/two'])
    clock.advance(1)
    expect(navigations).toEqual(['/two', '/manual'])
  })

  it('重复开始与重复就绪不会创建第二个句柄', () => {
    const { clock, navigations, controller } = createController()
    expect(controller.start()).toBe(true)
    expect(controller.start()).toBe(false)
    const generation = controller.getSnapshot().generation
    expect(controller.reportReady('/one', generation)).toBe(true)
    expect(controller.reportReady('/one', generation)).toBe(false)
    expect(clock.pending).toBe(1)
    clock.advance(5_000)
    expect(navigations).toEqual(['/two'])
  })

  it('暂停保留剩余时间，继续后补足剩余部分且重复命令无效', () => {
    const { clock, navigations, controller } = createController()
    startReady(controller)
    clock.advance(1_200)

    expect(controller.pause()).toBe(true)
    expect(controller.pause()).toBe(false)
    expect(controller.getSnapshot()).toMatchObject({ state: 'paused', remainingMs: 3_800 })
    expect(clock.pending).toBe(0)
    clock.advance(60_000)
    expect(navigations).toEqual([])

    expect(controller.resume()).toBe(true)
    expect(controller.resume()).toBe(false)
    expect(clock.pending).toBe(1)
    clock.advance(3_799)
    expect(navigations).toEqual([])
    clock.advance(1)
    expect(navigations).toEqual(['/two'])
  })

  it('同路径导航不打断停留计时', () => {
    const { clock, navigations, controller } = createController()
    startReady(controller)
    clock.advance(1_000)
    expect(controller.notifyPageChange('/one')).toBe(false)
    expect(controller.getSnapshot().remainingMs).toBe(4_000)
    clock.advance(4_000)
    expect(navigations).toEqual(['/two'])
  })
})

describe('PlaybackController 手动页与边界', () => {
  it('手动页等待用户操作并跳过隐藏页', () => {
    const { clock, navigations, controller } = createController({ initialPath: '/manual' })
    expect(controller.getSnapshot().total).toBe(3)
    startReady(controller)
    expect(controller.getSnapshot()).toMatchObject({ state: 'playing', delayMs: null, remainingMs: 0 })
    clock.advance(60_000)
    expect(navigations).toEqual([])

    const hiddenStart = createController({ initialPath: '/hidden' }).controller
    expect(hiddenStart.start()).toBe(true)
    expect(hiddenStart.getSnapshot()).toMatchObject({ state: 'preparing', path: '/one', total: 3 })
  })

  it('末页手动边界不自动绕回', () => {
    const pages: PlaybackPage[] = [
      { path: '/one', advance: { mode: 'timer', delayMs: 5000 } },
      { path: '/last', advance: { mode: 'manual', delayMs: 5000 } },
    ]
    const { clock, navigations, controller } = createController({ pages, loop: true, initialPath: '/last' })
    startReady(controller)
    expect(controller.getSnapshot().state).toBe('playing')
    clock.advance(60_000)
    expect(navigations).toEqual([])
    expect(controller.getSnapshot().state).toBe('playing')
  })

  it('末页结束后停止，重新开始从当前页完整计时', () => {
    const pages: PlaybackPage[] = [
      { path: '/one', advance: { mode: 'timer', delayMs: 5000 } },
      { path: '/two', advance: { mode: 'timer', delayMs: 7000 } },
    ]
    const { clock, navigations, controller } = createController({ pages, initialPath: '/two' })
    startReady(controller)
    clock.advance(7_000)
    expect(controller.getSnapshot()).toMatchObject({ state: 'ended', path: '/two', remainingMs: 0 })
    expect(navigations).toEqual([])
    expect(clock.pending).toBe(0)
    clock.advance(60_000)
    expect(navigations).toEqual([])

    expect(controller.start()).toBe(true)
    expect(controller.getSnapshot()).toMatchObject({ state: 'playing', path: '/two' })
    clock.advance(6_999)
    expect(controller.getSnapshot().state).toBe('playing')
    clock.advance(1)
    expect(controller.getSnapshot().state).toBe('ended')
  })

  it('多页循环回到第一个可见页', () => {
    const pages: PlaybackPage[] = [
      { path: '/one', advance: { mode: 'timer', delayMs: 5000 } },
      { path: '/two', advance: { mode: 'timer', delayMs: 7000 } },
    ]
    const { clock, navigations, controller } = createController({ pages, initialPath: '/two', loop: true })
    startReady(controller)
    clock.advance(7_000)
    expect(navigations).toEqual(['/one'])
    controller.notifyPageChange('/one')
    expect(controller.reportReady('/one', controller.getSnapshot().generation)).toBe(true)
    clock.advance(5_000)
    expect(navigations).toEqual(['/one', '/two'])
  })

  it('单页循环每轮都有完整停留周期且不触发导航', () => {
    const pages: PlaybackPage[] = [{ path: '/only', advance: { mode: 'timer', delayMs: 5000 } }]
    const { clock, navigations, controller } = createController({ pages, loop: true, initialPath: '/only' })
    const firstGeneration = startReady(controller)
    clock.advance(4_999)
    expect(controller.getSnapshot().remainingMs).toBe(1)
    clock.advance(1)
    expect(controller.getSnapshot()).toMatchObject({ state: 'playing', generation: firstGeneration + 1 })
    expect(clock.pending).toBe(1)
    clock.advance(5_000)
    expect(controller.getSnapshot().generation).toBe(firstGeneration + 2)
    expect(clock.pending).toBe(1)
    expect(navigations).toEqual([])
  })

  it('停止保留当前页且作废旧计时，重新开始重新计时', () => {
    const { clock, navigations, controller } = createController()
    startReady(controller)
    clock.advance(1_000)
    expect(controller.stop()).toBe(true)
    expect(controller.stop()).toBe(false)
    expect(controller.getSnapshot()).toMatchObject({ state: 'stopped', path: '/one', remainingMs: 0 })
    expect(clock.pending).toBe(0)
    clock.advance(60_000)
    expect(navigations).toEqual([])

    expect(controller.start()).toBe(true)
    expect(controller.getSnapshot().state).toBe('playing')
    clock.advance(5_000)
    expect(navigations).toEqual(['/two'])
  })

  it('没有可见页时开始无效', () => {
    const { controller } = createController({ pages: [], initialPath: '' })
    expect(controller.start()).toBe(false)
    expect(controller.getSnapshot()).toMatchObject({ state: 'stopped', total: 0 })
  })
})

describe('PlaybackController 手动介入与 generation', () => {
  it('播放中手动跳页作废旧计时，新页就绪后完整计时', () => {
    const { clock, navigations, controller } = createController()
    const oldGeneration = startReady(controller)
    clock.advance(2_000)

    controller.notifyPageChange('/two')
    const generation = controller.getSnapshot().generation
    expect(generation).toBeGreaterThan(oldGeneration)
    expect(controller.getSnapshot()).toMatchObject({ state: 'preparing', path: '/two', remainingMs: 7000 })
    expect(clock.pending).toBe(0)
    clock.advance(60_000)
    expect(navigations).toEqual([])

    expect(controller.reportReady('/two', oldGeneration)).toBe(false)
    expect(controller.reportReady('/one', generation)).toBe(false)
    expect(controller.reportReady('/two', generation)).toBe(true)
    clock.advance(7_000)
    expect(navigations).toEqual(['/manual'])
  })

  it('快速连跳只接受最新页面与 generation 的就绪信号', () => {
    const { clock, navigations, controller } = createController()
    startReady(controller)
    controller.notifyPageChange('/two')
    const stale = controller.getSnapshot().generation
    controller.notifyPageChange('/manual')
    const current = controller.getSnapshot().generation
    expect(current).toBeGreaterThan(stale)
    expect(controller.reportReady('/two', stale)).toBe(false)
    expect(controller.reportReady('/manual', stale)).toBe(false)
    expect(controller.reportReady('/manual', current)).toBe(true)
    expect(controller.getSnapshot()).toMatchObject({ state: 'playing', path: '/manual' })
    clock.advance(60_000)
    expect(navigations).toEqual([])
  })

  it('暂停中手动跳页保持暂停，恢复后按新页完整周期计时', () => {
    const { clock, navigations, controller } = createController()
    startReady(controller)
    clock.advance(1_000)
    controller.pause()
    expect(controller.getSnapshot().remainingMs).toBe(4_000)

    controller.notifyPageChange('/two')
    expect(controller.getSnapshot()).toMatchObject({ state: 'paused', path: '/two', remainingMs: 7000 })
    expect(clock.pending).toBe(0)
    expect(controller.resume()).toBe(true)
    expect(controller.getSnapshot().state).toBe('preparing')
    expect(controller.reportReady('/two', controller.getSnapshot().generation)).toBe(true)
    clock.advance(6_999)
    expect(navigations).toEqual([])
    clock.advance(1)
    expect(navigations).toEqual(['/manual'])
  })

  it('暂停时到达的就绪信号被记录，恢复后不再等待', () => {
    const { clock, navigations, controller } = createController()
    controller.start()
    controller.pause()
    expect(controller.getSnapshot().state).toBe('paused')
    expect(controller.reportReady('/one', controller.getSnapshot().generation)).toBe(true)
    expect(controller.getSnapshot().state).toBe('paused')
    expect(controller.resume()).toBe(true)
    expect(controller.getSnapshot().state).toBe('playing')
    clock.advance(5_000)
    expect(navigations).toEqual(['/two'])
  })
})

describe('PlaybackController 失败恢复与清理', () => {
  it('资源失败进入错误态并停止计时，重试后等待新就绪', () => {
    const { clock, navigations, controller } = createController()
    const generation = startReady(controller)
    clock.advance(1_000)
    expect(controller.reportError('/one', generation, '资源加载失败')).toBe(true)
    expect(controller.getSnapshot()).toMatchObject({ state: 'error', message: '资源加载失败', remainingMs: 0 })
    expect(clock.pending).toBe(0)
    clock.advance(60_000)
    expect(navigations).toEqual([])

    expect(controller.retry()).toBe(true)
    expect(controller.getSnapshot().state).toBe('preparing')
    expect(controller.reportReady('/one', controller.getSnapshot().generation)).toBe(true)
    clock.advance(5_000)
    expect(navigations).toEqual(['/two'])
  })

  it('受阻态可重试，旧 generation 的失败信号被丢弃', () => {
    const { controller } = createController()
    const generation = startReady(controller)
    expect(controller.reportBlocked('/two', generation)).toBe(false)
    expect(controller.reportBlocked('/one', generation)).toBe(true)
    expect(controller.getSnapshot().state).toBe('blocked')
    expect(controller.retry()).toBe(true)
    expect(controller.getSnapshot().state).toBe('preparing')
  })

  it('自动翻页被拒绝时进入错误态', async () => {
    const { clock, controller } = createController({
      navigate: () => Promise.reject(new Error('router failed')),
    })
    startReady(controller)
    clock.advance(5_000)
    await flushMicrotasks()
    expect(controller.getSnapshot()).toMatchObject({ state: 'error', path: '/one' })
    expect(clock.pending).toBe(0)
  })

  it('旧导航拒绝不覆盖用户已跳转到的新页面', async () => {
    let rejectNavigation: ((error: unknown) => void) | undefined
    const { clock, controller } = createController({
      navigate: () => new Promise<void>((_resolve, reject) => { rejectNavigation = reject }),
    })
    startReady(controller)
    clock.advance(5_000)
    expect(controller.getSnapshot().state).toBe('preparing')
    controller.notifyPageChange('/manual')
    rejectNavigation?.(new Error('late failure'))
    await flushMicrotasks()
    expect(controller.getSnapshot()).toMatchObject({ state: 'preparing', path: '/manual' })
    expect(controller.reportReady('/manual', controller.getSnapshot().generation)).toBe(true)
    expect(controller.getSnapshot().state).toBe('playing')
  })

  it('释放后清除计时与监听器，所有输入无效', () => {
    const { clock, navigations, controller } = createController()
    let notifications = 0
    controller.subscribe(() => { notifications += 1 })
    const generation = startReady(controller)
    const beforeDispose = notifications
    controller.dispose()
    expect(clock.pending).toBe(0)
    expect(notifications).toBe(beforeDispose)
    expect(controller.reportReady('/one', generation)).toBe(false)
    expect(controller.start()).toBe(false)
    controller.notifyPageChange('/two')
    clock.advance(60_000)
    expect(navigations).toEqual([])
    expect(controller.getSnapshot()).toMatchObject({ state: 'stopped', path: '/one' })
  })
})
