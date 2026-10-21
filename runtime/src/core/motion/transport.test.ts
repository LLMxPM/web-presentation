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

interface FakeState {
  applied: Array<{ id: string; positionMs: number }>
  paused: string[]
  disposed: string[]
  blockOnPlay: boolean
  clock: { positionMs: number; ended: boolean; blocked: boolean; buffering: boolean } | null
}

function createFactory(state: FakeState, primaryId: string | null) {
  return ({ track }: { track: { id: string; type: MotionTrackAdapter['type'] } }): MotionTrackAdapter => ({
    type: track.type,
    async prepare() {},
    async applyAt(options) {
      state.applied.push({ id: track.id, positionMs: options.positionMs })
    },
    async play() {
      if (state.blockOnPlay) {
        throw new MotionError(MOTION_ERROR_MEDIA_BLOCKED, '浏览器阻止了媒体播放。', { trackId: track.id })
      }
    },
    pause() {
      state.paused.push(track.id)
    },
    getClock: track.id === primaryId ? () => state.clock : undefined,
    async freeze(positionMs): Promise<MotionStateProof> {
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
    clock: primaryId ? { positionMs: 0, ended: false, blocked: false, buffering: false } : null,
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

    expect(first.stateDigest).toBe(second.stateDigest)
    expect(reduced.stateDigest).not.toBe(first.stateDigest)
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
