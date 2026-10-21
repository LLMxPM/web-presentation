/**
 * 文件功能：覆盖 WP02 计划编译的确定性、依赖、属性所有权与字段边界。
 */
import { describe, expect, it } from 'vitest'

import {
  compilePageTimeline,
  digestMotionPayload,
  primaryClockTrack,
  stableMotionStringify,
} from './compile'
import { MotionError } from './errors'
import type { PageTimelineDefinition } from './types'

function definition(overrides: Partial<PageTimelineDefinition> = {}): PageTimelineDefinition {
  return {
    schemaVersion: 1,
    timelineId: 'product-intro',
    tracks: [
      { type: 'dom', id: 'title', target: '.title', preset: 'fade-up', durationMs: 400 },
      { type: 'video', id: 'demo', asset: 'demo-video', outMs: 3000, muted: true, afterTrack: 'title', offsetMs: 100 },
      { type: 'model3d', id: 'product', asset: 'product', clip: { index: 0, durationMs: 2000 }, afterTrack: 'title' },
    ],
    ...overrides,
  }
}

function expectMotionError(run: () => unknown, code: string): MotionError {
  try {
    run()
  } catch (error) {
    expect(error).toBeInstanceOf(MotionError)
    expect((error as MotionError).code).toBe(code)
    return error as MotionError
  }
  throw new Error(`期望抛出 ${code}`)
}

describe('compilePageTimeline', () => {
  it('解析绝对起点、依赖与裁切并生成稳定计划', () => {
    const plan = compilePageTimeline(definition())
    const title = plan.tracks.find(track => track.id === 'title')
    const demo = plan.tracks.find(track => track.id === 'demo')
    const product = plan.tracks.find(track => track.id === 'product')

    expect(title?.startMs).toBe(0)
    expect(demo?.startMs).toBe(500)
    expect(demo?.endMs).toBe(3500)
    expect(product?.startMs).toBe(400)
    expect(plan.durationMs).toBe(3500)
    expect(plan.labels.title).toBe(0)
    expect(plan.labels.demo).toBe(500)
    expect(plan.labels.product).toBe(400)
    expect(plan.planDigest).toMatch(/^[0-9a-f]{16}$/)
  })

  it('轨道顺序不同但语义相同的定义得到相同摘要', () => {
    const forward = compilePageTimeline(definition())
    const reversed = compilePageTimeline(definition({ tracks: [...definition().tracks].reverse() }))
    expect(reversed.planDigest).toBe(forward.planDigest)
    expect(stableMotionStringify(reversed.tracks)).toBe(stableMotionStringify(forward.tracks))
  })

  it('解析主媒体时钟并默认从逻辑 0 开始', () => {
    const plan = compilePageTimeline(definition({
      tracks: [
        { type: 'video', id: 'main', asset: 'main-video', outMs: 5000, role: 'primary' },
        { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 400 },
      ],
    }))
    expect(plan.primaryClockTrackId).toBe('main')
    expect(primaryClockTrack(plan)?.durationMs).toBe(5000)
    expect(plan.durationMs).toBe(5000)
  })

  it('拒绝循环依赖与缺失前驱', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'a', target: '.a', preset: 'fade', durationMs: 100, afterTrack: 'b' },
        { type: 'dom', id: 'b', target: '.b', preset: 'fade', durationMs: 100, afterTrack: 'a' },
      ],
    })), 'TIMELINE_DEPENDENCY_CYCLE')

    const missing = expectMotionError(() => compilePageTimeline(definition({
      tracks: [{ type: 'dom', id: 'a', target: '.a', preset: 'fade', durationMs: 100, afterTrack: 'ghost' }],
    })), 'TIMELINE_TARGET_INVALID')
    expect(missing.fieldPath).toBe('timeline.tracks[0].afterTrack')
  })

  it('拒绝重复 id、非法数值与海报越界', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'title', target: '.a', preset: 'fade', durationMs: 100 },
        { type: 'dom', id: 'title', target: '.b', preset: 'fade', durationMs: 100 },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({
      tracks: [{ type: 'dom', id: 'title', target: '.a', preset: 'fade', durationMs: -1 }],
    })), 'TIMELINE_DURATION_UNRESOLVED')

    expectMotionError(() => compilePageTimeline(definition({ poster: { atMs: 4000 } })), 'TIMELINE_SCHEMA_INVALID')
  })

  it('拒绝同一 DOM 目标上的重叠属性', () => {
    const error = expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'a', target: '.title', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 600 },
        { type: 'dom', id: 'b', target: '.title', from: { opacity: 1 }, to: { opacity: 0.5 }, durationMs: 600, startMs: 300 },
      ],
    })), 'TIMELINE_PROPERTY_CONFLICT')
    expect(error.trackId).toBe('b')
  })

  it('允许同一目标上互不重叠或互不冲突的轨道', () => {
    const plan = compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'a', target: '.title', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 300 },
        { type: 'dom', id: 'b', target: '.title', from: { y: 20 }, to: { y: 0 }, durationMs: 300, startMs: 300 },
      ],
    }))
    expect(plan.tracks).toHaveLength(2)
  })

  it('主媒体限制：唯一、从 0 开始、速率 1 且只播放一次', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'video', id: 'main', asset: 'main', outMs: 1000, role: 'primary', startMs: 100 },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'video', id: 'main', asset: 'main', outMs: 1000, role: 'primary', repeat: 2 },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'video', id: 'main', asset: 'main', outMs: 1000, role: 'primary' },
        { type: 'audio', id: 'second', asset: 'second', outMs: 1000, role: 'primary' },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')
  })

  it('辅助同步视频非静音时拒绝，旁白唯一且不可重复', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'video', id: 'main', asset: 'main', outMs: 1000, role: 'primary' },
        { type: 'video', id: 'aux', asset: 'aux', outMs: 1000, muted: false },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'audio', id: 'n1', asset: 'voice-a', outMs: 1000, role: 'narration' },
        { type: 'audio', id: 'n2', asset: 'voice-b', outMs: 1000, role: 'narration', muted: true },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'audio', id: 'n1', asset: 'voice-a', outMs: 1000, role: 'narration', repeat: 2 },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')
  })

  it('资源时长未提供时明确失败，不伪造 duration', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [{ type: 'video', id: 'demo', asset: 'demo' } as unknown as PageTimelineDefinition['tracks'][number]],
    })), 'TIMELINE_DURATION_UNRESOLVED')

    const error = expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'model3d', id: 'model', asset: 'model', clip: { index: 0 } as unknown as { index: number; durationMs: number } },
      ],
    })), 'TIMELINE_DURATION_UNRESOLVED')
    expect(error.fieldPath).toContain('clip.durationMs')
  })

  it('海报支持标签并拒绝互斥字段', () => {
    const plan = compilePageTimeline(definition({ poster: { atLabel: 'demo' } }))
    expect(plan.posterTimeMs).toBe(500)

    expectMotionError(() => compilePageTimeline(definition({
      poster: { atLabel: 'demo', atMs: 0 },
    })), 'TIMELINE_SCHEMA_INVALID')

    expectMotionError(() => compilePageTimeline(definition({ poster: { atLabel: 'ghost' } })), 'TIMELINE_TARGET_INVALID')
  })

  it('标签不得与其它轨道 id 冲突', () => {
    expectMotionError(() => compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'title', target: '.a', preset: 'fade', durationMs: 100 },
        { type: 'dom', id: 'subtitle', target: '.b', preset: 'fade', durationMs: 100, label: 'title' },
      ],
    })), 'TIMELINE_SCHEMA_INVALID')
  })

  it('装饰轨道默认不参与完成与总时长', () => {
    const plan = compilePageTimeline(definition({
      tracks: [
        { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 500 },
        { type: 'dom', id: 'glow', target: '.glow', preset: 'fade', durationMs: 2000, role: 'decoration' },
      ],
    }))
    expect(plan.durationMs).toBe(500)
    expect(plan.requiredTrackIds).toEqual(['title'])
  })

  it('摘要实现可跨进程稳定', () => {
    expect(digestMotionPayload({ b: 2, a: [1, { d: 4, c: 3 }] }))
      .toBe(digestMotionPayload({ a: [1, { c: 3, d: 4 }], b: 2 }))
  })
})
