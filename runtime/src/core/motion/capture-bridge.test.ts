// @vitest-environment jsdom
/** 文件功能：验证静帧捕获选择器解析、无副作用采样回执与缺失时间轴的明确失败。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { compilePageTimeline } from './compile'
import {
  applyCaptureMotionSnapshot,
  installCaptureMotionBridge,
  resolveCaptureMotionTime,
} from './capture-bridge'
import type { PageMotionHandle } from './page-motion-contract'
import { PAGE_MOTION_ATTR, PAGE_MOTION_HANDLE_KEY } from './page-motion-contract'
import type { MotionSampleResult } from './sampling'
import type { MotionTransportSnapshot } from './types'
import { initializeRenderReadyHost } from '@/core/utils/render-ready'

const PLAN = compilePageTimeline({
  schemaVersion: 1,
  timelineId: 'intro',
  poster: { atMs: 250 },
  tracks: [
    {
      id: 'fade',
      label: 'detail',
      type: 'dom',
      target: 'h1',
      startMs: 0,
      durationMs: 1000,
      from: { opacity: 0 },
      to: { opacity: 1 },
    },
  ],
})

/** 在文档页根注册可控时间轴句柄。 */
function attachHandle(options: { missing?: boolean } = {}) {
  const root = document.createElement('div')
  root.className = 'runtime-page-print-source'
  root.dataset.runtimeRoutePath = '/a'
  document.body.append(root)
  const sampleAt = vi.fn(async (positionMs: number, visualMode: 'full' | 'reduced' = 'full'): Promise<MotionSampleResult> => ({
    timelineId: PLAN.timelineId,
    planDigest: PLAN.planDigest,
    sampledTimeMs: positionMs,
    visualMode,
    stateDigest: `state-${positionMs}-${visualMode}`,
    proofs: [],
  }))
  const snapshot: MotionTransportSnapshot = {
    timelineId: PLAN.timelineId,
    planDigest: PLAN.planDigest,
    pagePath: '/a',
    generation: 1,
    intent: 'stopped',
    phase: 'ready',
    positionMs: 0,
    durationMs: PLAN.durationMs,
    revision: 0,
    completedTrackIds: [],
    errorCode: null,
    errorMessage: '',
  }
  const pause = vi.fn(() => true)
  const setMuted = vi.fn()
  const handle = {
    plan: PLAN,
    ownership: { isElementClaimed: () => false },
    isElementClaimed: () => false,
    getSnapshot: () => snapshot,
    prepare: vi.fn(async () => {}),
    play: vi.fn(async () => true),
    pause,
    resume: vi.fn(async () => true),
    seek: vi.fn(async () => {}),
    restart: vi.fn(async () => true),
    setMuted,
    sampleAt,
    subscribe: () => () => {},
    dispose: vi.fn(),
  } as unknown as PageMotionHandle
  if (!options.missing) {
    ;(root as unknown as Record<string, unknown>)[PAGE_MOTION_HANDLE_KEY] = handle
    root.setAttribute(PAGE_MOTION_ATTR, 'v1')
  }
  return { root, handle, sampleAt, pause, setMuted }
}

afterEach(() => {
  document.body.innerHTML = ''
  delete window.__RUNTIME_APPLY_MOTION_SNAPSHOT__
  delete window.__RENDER_READY__
})

describe('capture motion bridge', () => {
  it('atMs 采样会暂停、静音并写入状态回执', async () => {
    const { sampleAt, pause, setMuted } = attachHandle()
    initializeRenderReadyHost()
    installCaptureMotionBridge()

    const receipt = await window.__RUNTIME_APPLY_MOTION_SNAPSHOT__!({ atMs: 400, visualMode: 'reduced' })

    expect(sampleAt).toHaveBeenCalledWith(400, 'reduced')
    expect(pause).toHaveBeenCalledTimes(1)
    expect(setMuted).toHaveBeenCalledWith(true)
    expect(receipt).toMatchObject({
      status: 'applied',
      timelineId: 'intro',
      planDigest: PLAN.planDigest,
      sampledTimeMs: 400,
      stateDigest: 'state-400-reduced',
      visualMode: 'reduced',
    })
    expect(window.__RENDER_READY__?.motion).toMatchObject({ status: 'applied', sampledTimeMs: 400 })
  })

  it('标签偏移与默认 poster 使用计划标签解析', async () => {
    const { sampleAt } = attachHandle()
    expect(resolveCaptureMotionTime({ plan: PLAN } as PageMotionHandle, { atLabel: 'detail', offsetMs: 600 })).toBe(600)
    expect(resolveCaptureMotionTime({ plan: PLAN } as PageMotionHandle, null)).toBe(250)

    await applyCaptureMotionSnapshot({ atLabel: 'detail', offsetMs: 600 })
    expect(sampleAt).toHaveBeenLastCalledWith(600, 'full')
  })

  it('缺失标签、越界时间或错误时间轴明确失败', async () => {
    attachHandle()
    await expect(applyCaptureMotionSnapshot({ atLabel: 'missing' })).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
    await expect(applyCaptureMotionSnapshot({ atMs: PLAN.durationMs + 1 })).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
    await expect(applyCaptureMotionSnapshot({ timelineId: 'other' })).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
  })

  it('旧页面默认采样返回 skipped，显式选择器返回失败', async () => {
    attachHandle({ missing: true })
    await expect(applyCaptureMotionSnapshot({})).resolves.toMatchObject({ status: 'skipped' })
    await expect(applyCaptureMotionSnapshot({ timelineId: 'intro' })).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
  })

  it('渲染桥拒绝非对象和非法 visualMode', async () => {
    attachHandle()
    installCaptureMotionBridge()
    await expect(window.__RUNTIME_APPLY_MOTION_SNAPSHOT__!('bad')).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
    await expect(window.__RUNTIME_APPLY_MOTION_SNAPSHOT__!({ atMs: 100, visualMode: 'fast' })).rejects.toMatchObject({
      code: 'TIMELINE_SNAPSHOT_UNAVAILABLE',
    })
  })
})
