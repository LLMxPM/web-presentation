/**
 * 文件功能：覆盖 WP03 transport 的状态机、主媒体时钟交接、暂停/缓冲、定位与释放。
 */
import { describe, expect, it } from 'vitest'

import type { MotionScheduler, MotionTrackAdapter } from './adapters'
import { compilePageTimeline } from './compile'
import { MotionError, MOTION_ERROR_MEDIA_BLOCKED } from './errors'
import { MotionTargetRegistry } from './target-registry'
import { createMotionTransport } from './transport'
import type { CompiledMotionPlan, MotionStateProof, PageTimelineDefinition } from './types'

class ManualScheduler implements MotionScheduler {
  private callbacks = new Map<number, () => void>()
  private sequence = 0

  request(callback: () => void): number {
    const handle = ++this.sequence
    this.callbacks.set(handle, callback)
    return handle
  }

  cancel(handle: number): void {
    this.callbacks.delete(handle)
  }

  get size(): number {
    return this.callbacks.size
  }

  async runNext(): Promise<void> {
    const first = this.callbacks.entries().next()
    if (first.done) return
    const [handle, callback] = first.value
    this.callbacks.delete(handle)
    callback()
    await flush()
  }
}

async function flush(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 等待受控回执真正进入适配器，避免依赖微任务顺序。 */
async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return
    await new Promise(resolve => setTimeout(resolve, 0))
  }
  throw new Error('等待条件超时')
}

interface FakeState {
  applied: Array<{ id: string; positionMs: number; visualMode: string }>
  paused: string[]
  disposed: string[]
  blockOnPlay: boolean
  playCalls: number
  clock: { positionMs: number; ended: boolean; blocked: boolean; buffering: boolean } | null
  clocks: Record<string, { positionMs: number; ended: boolean; blocked: boolean; buffering: boolean }>
  failOn: Partial<Record<'prepare' | 'apply' | 'play' | 'freeze', string>>
  /** 受控回执：用于模拟异步结果在定位/暂停/卸载之后才返回。 */
  prepareGate: Deferred | null
  playGate: Deferred | null
  applyGate: Deferred | null
}

interface Deferred {
  promise: Promise<void>
  resolve: () => void
  reject: (error: unknown) => void
}

function deferred(): Deferred {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function createFactory(state: FakeState, primaryId: string | null) {
  return ({ track }: { track: { id: string; type: MotionTrackAdapter['type'] } }): MotionTrackAdapter => ({
    type: track.type,
    async prepare() {
      if (state.prepareGate) await state.prepareGate.promise
      if (state.failOn.prepare === track.id) throw new Error(`准备失败: ${track.id}`)
    },
    async applyAt(options) {
      if (state.applyGate) await state.applyGate.promise
      if (state.failOn.apply === track.id) throw new Error(`采样失败: ${track.id}`)
      state.applied.push({ id: track.id, positionMs: options.positionMs, visualMode: options.visualMode })
    },
    async play() {
      state.playCalls += 1
      if (state.playGate) await state.playGate.promise
      if (state.failOn.play === track.id) throw new Error(`播放失败: ${track.id}`)
      if (state.blockOnPlay) {
        throw new MotionError(MOTION_ERROR_MEDIA_BLOCKED, '浏览器阻止了媒体播放。', { trackId: track.id })
      }
    },
    pause() {
      state.paused.push(track.id)
    },
    getClock: () => state.clocks[track.id] ?? (track.id === primaryId ? state.clock : null),
    async freeze(positionMs): Promise<MotionStateProof> {
      if (state.failOn.freeze === track.id) throw new Error(`固化失败: ${track.id}`)
      return { trackId: track.id, type: track.type, positionMs, digest: `state-${track.id}` }
    },
    dispose() {
      state.disposed.push(track.id)
    },
  } satisfies MotionTrackAdapter)
}

function createHarness(definition: PageTimelineDefinition, primaryId: string | null = null) {
  const plan: CompiledMotionPlan = compilePageTimeline(definition)
  const scheduler = new ManualScheduler()
  const state: FakeState = {
    applied: [],
    paused: [],
    disposed: [],
    blockOnPlay: false,
    playCalls: 0,
    clock: primaryId ? { positionMs: 0, ended: false, blocked: false, buffering: false } : null,
    clocks: {},
    failOn: {},
    prepareGate: null,
    playGate: null,
    applyGate: null,
  }
  let wall = 0
  const transport = createMotionTransport({
    plan,
    root: document.createElement('div'),
    pagePath: '/intro',
    generation: 3,
    scheduler,
    now: () => wall,
    createAdapter: createFactory(state, primaryId),
  })
  return {
    plan,
    scheduler,
    state,
    transport,
    advance(ms: number) {
      wall += ms
    },
    get wall() {
      return wall
    },
  }
}

describe('createMotionTransport', () => {
  it('播放与暂停位置未变化时仍向订阅方发布意图', async () => {
    const { transport } = createHarness({
      schemaVersion: 1,
      timelineId: 'intent-notification',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 }],
    })
    const observed: string[] = []
    transport.subscribe(snapshot => observed.push(snapshot.intent))
    await transport.prepare()
    await transport.play()
    expect(observed.at(-1)).toBe('playing')
    transport.pause()
    expect(observed.at(-1)).toBe('paused')
  })

  it('准备、播放、暂停与自然完成保持单调位置', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'basic',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 }],
    })
    const { transport, scheduler, state } = harness

    await transport.prepare()
    expect(transport.getSnapshot().phase).toBe('ready')
    expect(transport.getSnapshot().positionMs).toBe(0)

    await transport.play()
    expect(transport.getSnapshot().intent).toBe('playing')

    harness.advance(400)
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(400)

    expect(transport.pause()).toBe(true)
    expect(transport.getSnapshot().intent).toBe('paused')
    harness.advance(500)
    expect(scheduler.size).toBe(0)
    expect(transport.getSnapshot().positionMs).toBe(400)

    await transport.resume()
    harness.advance(700)
    await scheduler.runNext()
    await flush()
    expect(transport.getSnapshot().phase).toBe('completed')
    expect(transport.getSnapshot().intent).toBe('stopped')
    expect(transport.getSnapshot().completedTrackIds).toEqual(['title'])
    expect(state.applied.some(entry => entry.positionMs === 1000)).toBe(true)
  })

  it('主媒体结束后交接单调时钟并继续剩余 required 轨道', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'handover',
      tracks: [
        { type: 'video', id: 'main', asset: 'main-video', outMs: 2000, role: 'primary' },
        { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 3000 },
      ],
    }, 'main')
    const { transport, scheduler, state } = harness

    await transport.prepare()
    await transport.play()
    state.clock!.positionMs = 800
    harness.advance(900)
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(800)

    state.clock!.positionMs = 2000
    state.clock!.ended = true
    harness.advance(100)
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(2000)

    harness.advance(500)
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(2500)

    harness.advance(600)
    await scheduler.runNext()
    await flush()
    expect(transport.getSnapshot().phase).toBe('completed')
    expect(transport.getSnapshot().completedTrackIds).toEqual(['main', 'title'])
  })

  it('缓冲不推进位置，用户暂停后缓冲结束也不会自动恢复', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'buffer',
      tracks: [
        { type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary' },
        { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 4000 },
      ],
    }, 'main')
    const { transport, scheduler, state } = harness

    await transport.prepare()
    await transport.play()
    state.clock!.buffering = true
    harness.advance(200)
    await scheduler.runNext()
    expect(transport.getSnapshot().phase).toBe('buffering')

    expect(transport.pause()).toBe(true)
    expect(transport.getSnapshot().intent).toBe('paused')
    state.clock!.buffering = false
    harness.advance(1000)
    expect(scheduler.size).toBe(0)
    expect(transport.getSnapshot().positionMs).toBe(0)
  })

  it('次要 required 媒体缓冲冻结主媒体，恢复后只从冻结位置继续', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'secondary-buffer',
      tracks: [
        { type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary', muted: true },
        { type: 'audio', id: 'voice', asset: 'voice', outMs: 4000, muted: true, required: true },
      ],
    }, 'main')
    const { transport, scheduler, state } = harness
    state.clocks.voice = { positionMs: 200, ended: false, blocked: false, buffering: false }
    await transport.prepare()
    await transport.play()
    state.clock!.positionMs = 200
    state.clocks.voice.buffering = true
    harness.advance(200)
    await scheduler.runNext()
    expect(transport.getSnapshot()).toMatchObject({ phase: 'buffering', positionMs: 200 })
    expect(state.paused).toContain('main')
    harness.advance(500)
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(200)

    state.clocks.voice.buffering = false
    await scheduler.runNext()
    expect(transport.getSnapshot().phase).toBe('ready')
    state.clock!.positionMs = 350
    await scheduler.runNext()
    expect(transport.getSnapshot().positionMs).toBe(350)
  })

  it('optional 媒体缓冲跳过且不冻结主时钟，required 超时则有界失败', async () => {
    const optional = createHarness({
      schemaVersion: 1,
      timelineId: 'optional-buffer',
      tracks: [
        { type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary', muted: true },
        { type: 'audio', id: 'decoration', asset: 'decoration', outMs: 4000, role: 'decoration', muted: true },
      ],
    }, 'main')
    optional.state.clocks.decoration = { positionMs: 0, ended: false, blocked: false, buffering: true }
    await optional.transport.prepare()
    await optional.transport.play()
    optional.state.clock!.positionMs = 300
    await optional.scheduler.runNext()
    expect(optional.transport.getSnapshot()).toMatchObject({ phase: 'ready', positionMs: 300 })
    expect(optional.state.applied.filter(entry => entry.id === 'decoration' && entry.positionMs === 300)).toEqual([])

    const required = createHarness({
      schemaVersion: 1,
      timelineId: 'required-timeout',
      tracks: [{ type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary' }],
    }, 'main')
    await required.transport.prepare()
    await required.transport.play()
    required.state.clock!.buffering = true
    await required.scheduler.runNext()
    required.advance(15_100)
    await required.scheduler.runNext()
    expect(required.transport.getSnapshot()).toMatchObject({ phase: 'error', errorCode: 'TIMELINE_BUFFER_TIMEOUT' })
  })

  it.each(['prepare', 'apply', 'play', 'freeze'] as const)(
    'optional 媒体 %s 失败只释放本轨道，主媒体继续播放与采样',
    async stage => {
      const harness = createHarness({
        schemaVersion: 1,
        timelineId: `optional-${stage}-failure`,
        tracks: [
          { type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary', muted: true },
          { type: 'audio', id: 'decoration', asset: 'decoration', outMs: 4000, role: 'decoration', muted: true },
        ],
      }, 'main')
      const { transport, state } = harness
      if (stage === 'prepare') state.failOn.prepare = 'decoration'
      await transport.prepare()
      if (stage === 'apply') state.failOn.apply = 'decoration'
      if (stage === 'play') state.failOn.play = 'decoration'
      expect(await transport.play()).toBe(true)
      if (stage === 'freeze') state.failOn.freeze = 'decoration'
      const sampled = await transport.sampleAt(300)
      expect(sampled.degradedTrackIds).toEqual(['decoration'])
      expect(transport.getSnapshot()).toMatchObject({ phase: 'ready', positionMs: 300, errorCode: null })
      expect(state.disposed.filter(id => id === 'decoration')).toHaveLength(1)
      expect(state.disposed).not.toContain('main')
      state.clock!.positionMs = 600
      expect(await transport.play()).toBe(true)
      await harness.scheduler.runNext()
      expect(transport.getSnapshot().phase).toBe('ready')
      expect(state.disposed.filter(id => id === 'decoration')).toHaveLength(1)
    },
  )

  it('required 媒体准备失败仍阻止播放并暴露错误', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'required-prepare-failure',
      tracks: [{ type: 'video', id: 'main', asset: 'main-video', outMs: 4000, role: 'primary' }],
    }, 'main')
    harness.state.failOn.prepare = 'main'
    await expect(harness.transport.prepare()).rejects.toThrow('准备失败: main')
    expect(harness.transport.getSnapshot()).toMatchObject({ phase: 'error', intent: 'stopped' })
  })

  it('浏览器阻止播放进入 blocked 并允许用户手势重试', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'blocked',
      tracks: [{ type: 'video', id: 'main', asset: 'main-video', outMs: 2000, role: 'primary' }],
    }, 'main')
    const { transport, state } = harness
    state.blockOnPlay = true

    await transport.prepare()
    await transport.play()
    expect(transport.getSnapshot().phase).toBe('blocked')
    expect(transport.getSnapshot().intent).toBe('playing')

    state.blockOnPlay = false
    await transport.play()
    expect(transport.getSnapshot().phase).toBe('ready')
  })

  it('暂停后迟到的 play 回执不留在播放集合，并再次暂停适配器', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'late-play',
      tracks: [{ type: 'video', id: 'main', asset: 'main-video', outMs: 2000, role: 'primary' }],
    }, 'main')
    const { transport, state } = harness

    await transport.prepare()
    state.playGate = deferred()
    const playing = transport.play()
    // play 回执已进入适配器并挂起，此时用户暂停；迟到的成功回执不能把适配器留在播放集合。
    await waitFor(() => state.playCalls === 1)
    expect(transport.pause()).toBe(true)
    state.playGate.resolve()
    expect(await playing).toBe(true)

    expect(transport.getSnapshot().intent).toBe('paused')
    expect(transport.getSnapshot().phase).toBe('ready')
    // 一次来自用户暂停，一次来自迟到回执后的自愈暂停。
    expect(state.paused.filter(id => id === 'main')).toHaveLength(2)
  })

  it('旧 revision 的定位回执不提交位置或完成状态', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'late-apply',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 300 }],
    })
    const { transport, scheduler, state } = harness

    await transport.prepare()
    await transport.play()
    state.applyGate = deferred()
    harness.advance(400)
    // tick 在 400ms 发起定位，回执被挂起；此后用户定位到 100ms。
    await scheduler.runNext()
    const seeking = transport.seek(100)
    await Promise.resolve()
    state.applyGate.resolve()
    state.applyGate = null
    await seeking

    expect(transport.getSnapshot().positionMs).toBe(100)
    // 400ms 的回执已越过 300ms 轨道末尾，若被提交会污染完成集合。
    expect(transport.getSnapshot().completedTrackIds).toEqual([])
  })

  it('卸载后迟到的准备失败不把已释放会话改成错误', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'late-prepare',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 500 }],
    })
    const { transport, state } = harness

    state.prepareGate = deferred()
    const preparing = transport.prepare()
    transport.dispose()
    state.prepareGate.reject(new Error('迟到的准备失败'))
    await preparing

    expect(transport.getSnapshot().phase).toBe('disposed')
    expect(transport.getSnapshot().errorCode).toBeNull()
  })

  it('定位提交最终位置并保留播放意图', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'seek',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 2000 }],
    })
    const { transport, state } = harness

    await transport.prepare()
    await transport.seek(750)
    expect(transport.getSnapshot().positionMs).toBe(750)
    expect(state.applied.at(-1)?.positionMs).toBe(750)

    await transport.seek(9999)
    expect(transport.getSnapshot().positionMs).toBe(2000)
    expect(transport.getSnapshot().revision).toBe(2)

    await transport.play()
    await transport.seek(500)
    expect(transport.getSnapshot().intent).toBe('playing')
    expect(transport.getSnapshot().phase).toBe('ready')
  })

  it('setVisualMode 在准备后按当前位置重新应用且不改变播放意图', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'visual-mode',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 }],
    })
    const { transport, state } = harness
    await transport.prepare()
    await transport.seek(400)
    const intentBefore = transport.getSnapshot().intent

    transport.setVisualMode('reduced')
    await flush()

    expect(state.applied.at(-1)?.positionMs).toBe(400)
    expect(state.applied.at(-1)?.visualMode).toBe('reduced')
    expect(transport.getSnapshot().intent).toBe(intentBefore)
  })

  it('相同计划的指定状态采样摘要稳定且不启动播放', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'sample',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 2000 }],
    })
    const { transport } = harness
    await transport.prepare()
    const first = await transport.sampleAt(800, 'full')
    const second = await transport.sampleAt(800, 'full')
    const reduced = await transport.sampleAt(800, 'reduced')
    const earlier = await transport.sampleAt(400, 'full')

    expect(first.stateDigest).toBe(second.stateDigest)
    expect(reduced.stateDigest).not.toBe(first.stateDigest)
    // 不同动作时刻必须得到不同状态摘要，截图身份才能区分同一资源的两个时间点。
    expect(earlier.stateDigest).not.toBe(first.stateDigest)
    expect(first.sampledTimeMs).toBe(800)
    expect(transport.getSnapshot().intent).toBe('stopped')
  })

  it('dispose 后释放目标与适配器且不再提交状态', async () => {
    const harness = createHarness({
      schemaVersion: 1,
      timelineId: 'dispose',
      tracks: [{ type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 }],
    })
    const { transport, state } = harness
    await transport.prepare()
    await transport.play()
    transport.dispose()
    transport.dispose()

    expect(state.disposed).toEqual(['title'])
    expect(transport.getSnapshot().phase).toBe('disposed')
    expect(transport.pause()).toBe(false)
    expect(await transport.play()).toBe(false)
  })
})

describe('MotionTargetRegistry', () => {
  it('同一 generation 内独占目标并按代际失效', () => {
    const registry = new MotionTargetRegistry()
    registry.beginGeneration(1)
    const element = document.createElement('video')
    const claim = registry.claim('video', 'demo', element)

    expect(registry.isElementClaimed(element)).toBe(true)
    expect(() => registry.claim('video', 'demo', null)).toThrow(MotionError)

    registry.beginGeneration(2)
    expect(registry.isElementClaimed(element)).toBe(false)
    expect(registry.hasClaim('video', 'demo')).toBe(false)

    claim.release()
    registry.dispose()
    expect(registry.isElementClaimed(element)).toBe(false)
  })
})
