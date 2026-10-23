/**
 * 文件功能：覆盖 WP05 媒体时间映射与资源目标定位。
 */
import { describe, expect, it, vi } from 'vitest'

import { compilePageTimeline } from './compile'
import { createMediaMotionAdapter, mapMediaTimelinePosition, resolveMediaElement } from './media-adapter'
import type { MotionAdapterContext } from './adapters'
import type { CompiledMediaTrack } from './types'

function mediaTrack(overrides: Partial<CompiledMediaTrack> = {}): CompiledMediaTrack {
  return {
    type: 'video',
    id: 'demo',
    label: 'demo',
    asset: 'demo-video',
    inMs: 500,
    outMs: 1500,
    rate: 1,
    repeat: 1,
    muted: false,
    volume: 1,
    endBehavior: 'hold',
    startMs: 1000,
    endMs: 2000,
    durationMs: 1000,
    required: true,
    role: 'content',
    primary: false,
    ...overrides,
  }
}

describe('mapMediaTimelinePosition', () => {
  it('处理起点前、裁切区间与结束保持', () => {
    const track = mediaTrack()
    expect(mapMediaTimelinePosition(track, 0)).toMatchObject({ sourceTimeMs: 500, beforeStart: true })
    expect(mapMediaTimelinePosition(track, 1000)).toMatchObject({ sourceTimeMs: 500, beforeStart: false })
    expect(mapMediaTimelinePosition(track, 1500)).toMatchObject({ sourceTimeMs: 1000, cycleIndex: 0 })
    expect(mapMediaTimelinePosition(track, 2000)).toMatchObject({ sourceTimeMs: 1500, finished: true })
    expect(mapMediaTimelinePosition(track, 9000)).toMatchObject({ sourceTimeMs: 1500, finished: true })
  })

  it('处理有限重复与速率', () => {
    const repeated = mediaTrack({ repeat: 2, durationMs: 2000, endMs: 3000 })
    expect(mapMediaTimelinePosition(repeated, 2499)).toMatchObject({ sourceTimeMs: 999, cycleIndex: 1 })

    const fast = mediaTrack({ rate: 2, durationMs: 500, endMs: 1500 })
    expect(mapMediaTimelinePosition(fast, 1250)).toMatchObject({ sourceTimeMs: 1000, cycleIndex: 0 })
  })
})

describe('resolveMediaElement', () => {
  it('按资源逻辑名定位资产根内的媒体元素', () => {
    const root = document.createElement('div')
    root.innerHTML = '<section data-runtime-asset-name="demo-video"><video></video></section>'
    const track = mediaTrack()
    expect(resolveMediaElement(root, track)?.tagName).toBe('VIDEO')
  })

  it('优先使用显式选择器并支持直接选中媒体元素', () => {
    const root = document.createElement('div')
    root.innerHTML = '<section data-runtime-asset-name="demo-video"><video></video></section><video class="target"></video>'
    const track = mediaTrack({ selector: '.target' })
    expect(resolveMediaElement(root, track)?.className).toBe('target')
  })

  it('资源未渲染时返回 null', () => {
    const root = document.createElement('div')
    expect(resolveMediaElement(root, mediaTrack())).toBeNull()
  })
})

describe('媒体轨道编译边界', () => {
  it('显式拒绝超过真实裁切语义的重复与速率组合', () => {
    const plan = compilePageTimeline({
      schemaVersion: 1,
      timelineId: 'media',
      tracks: [{ type: 'audio', id: 'voice', asset: 'voice', outMs: 1000, inMs: 200, rate: 2, repeat: 2 }],
    })
    const track = plan.tracks[0] as CompiledMediaTrack
    expect(track.durationMs).toBe(800)
    expect(mapMediaTimelinePosition(track, 700).sourceTimeMs).toBeCloseTo(800)
  })
})

describe('媒体重复回绕', () => {
  it('循环到下一段时恢复播放，用户暂停后保持暂停', async () => {
    const listeners = new Map<string, Set<() => void>>()
    let currentTime = 0
    const media = {
      tagName: 'AUDIO',
      isConnected: true,
      readyState: 4,
      duration: 0.7,
      paused: true,
      ended: false,
      muted: false,
      preload: 'auto',
      volume: 1,
      playbackRate: 1,
      error: null,
      playCalls: 0,
      addEventListener(type: string, handler: () => void) {
        if (!listeners.has(type)) listeners.set(type, new Set())
        listeners.get(type)!.add(handler)
      },
      removeEventListener(type: string, handler: () => void) {
        listeners.get(type)?.delete(handler)
      },
      emit(type: string) {
        for (const handler of listeners.get(type) ?? []) handler()
      },
      async play() {
        this.playCalls += 1
        this.paused = false
        this.ended = false
      },
      pause() {
        this.paused = true
      },
      get currentTime() {
        return currentTime
      },
      set currentTime(value: number) {
        currentTime = value
        this.emit('seeked')
      },
    }
    const track = mediaTrack({
      selector: '.a15-audio',
      outMs: 700, inMs: 0, repeat: 500,
      startMs: 0, endMs: 350_000, durationMs: 350_000,
    })
    const context = {
      track,
      root: { querySelector: () => media } as unknown as ParentNode,
      ownership: { claim: () => ({ release: vi.fn() }) },
      generation: 1,
      visualMode: 'full',
      muted: false,
      allowMediaPlayback: true,
    } as unknown as MotionAdapterContext
    const adapter = createMediaMotionAdapter(context, { deadlineMs: 100 })
    await adapter.prepare()
    await adapter.play!()
    expect(media.paused).toBe(false)

    // 模拟首段自然结束：时间轴进入下一循环后必须重新播放。
    media.paused = true
    media.ended = true
    currentTime = 0.7
    await adapter.applyAt({ positionMs: 750, visualMode: 'full' })
    expect(media.paused).toBe(false)
    expect(media.playCalls).toBe(2)
    expect(currentTime).toBeCloseTo(0.05)

    // 用户暂停后，同一回绕逻辑不得擅自恢复。
    adapter.pause!()
    media.paused = true
    media.ended = true
    currentTime = 0.7
    await adapter.applyAt({ positionMs: 1_450, visualMode: 'full' })
    expect(media.paused).toBe(true)
    expect(media.playCalls).toBe(2)
    adapter.dispose()
  })
})
