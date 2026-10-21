// @vitest-environment jsdom
/**
 * 文件功能：验证预览控制桥的命令解析、无时间轴兜底与播放/定位/偏好语义。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  PAGE_MOTION_ATTR,
  PAGE_MOTION_HANDLE_KEY,
  type PageMotionHandle,
} from './page-motion-contract'
import {
  executePreviewMotionCommand,
  installPreviewMotionBridge,
  parsePreviewMotionCommand,
  PREVIEW_MOTION_REQUEST_TYPE,
  readPreviewMotionState,
} from './preview-bridge'
import { compilePageTimeline } from './compile'
import type { MotionTransportSnapshot } from './types'

const PLAN = compilePageTimeline({
  schemaVersion: 1,
  timelineId: 'intro',
  poster: { atMs: 250 },
  tracks: [{ type: 'dom', id: 'title', target: 'h1', preset: 'fade', durationMs: 1000 }],
})

function attachHandle(overrides: Partial<Record<string, unknown>> = {}) {
  const snapshot: MotionTransportSnapshot = {
    timelineId: 'intro',
    planDigest: PLAN.planDigest,
    pagePath: '/cover',
    generation: 1,
    intent: 'stopped',
    phase: 'ready',
    positionMs: 250,
    durationMs: 1000,
    revision: 2,
    completedTrackIds: [],
    errorCode: null,
    errorMessage: '',
  }
  const prepare = vi.fn(async () => {})
  const play = vi.fn(async () => true)
  const pause = vi.fn(() => true)
  const resume = vi.fn(async () => true)
  const restart = vi.fn(async () => true)
  const seek = vi.fn(async () => {})
  const setVisualMode = vi.fn()
  const handle = {
    plan: PLAN,
    ownership: { isElementClaimed: () => false },
    visualMode: 'reduced',
    isElementClaimed: () => false,
    getSnapshot: () => snapshot,
    prepare,
    play,
    pause,
    resume,
    seek,
    restart,
    setMuted: vi.fn(),
    setVisualMode,
    sampleAt: vi.fn(),
    subscribe: () => () => {},
    dispose: vi.fn(),
    ...overrides,
  } as unknown as PageMotionHandle
  const root = document.createElement('div')
  root.setAttribute(PAGE_MOTION_ATTR, 'v1')
  ;(root as unknown as Record<string, unknown>)[PAGE_MOTION_HANDLE_KEY] = handle
  document.body.appendChild(root)
  return { root, handle, snapshot, prepare, play, pause, resume, restart, seek, setVisualMode }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('preview motion bridge', () => {
  it('无时间轴时返回稳定空状态且命令不伪造成功', async () => {
    expect(readPreviewMotionState()).toMatchObject({ hasTimeline: false, timelineId: null, positionMs: 0 })
    await expect(executePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'play',
    })).resolves.toBe(false)
  })

  it('读取句柄计划、位置与视觉偏好', () => {
    attachHandle()
    expect(readPreviewMotionState()).toMatchObject({
      hasTimeline: true,
      timelineId: 'intro',
      planDigest: PLAN.planDigest,
      posterTimeMs: 250,
      positionMs: 250,
      visualMode: 'reduced',
      phase: 'ready',
    })
  })

  it('停止态播放从起点重播，暂停态继续，定位与偏好透传句柄', async () => {
    const fake = attachHandle()
    await executePreviewMotionCommand({ type: PREVIEW_MOTION_REQUEST_TYPE, version: 1, action: 'play' })
    expect(fake.prepare).toHaveBeenCalled()
    expect(fake.restart).toHaveBeenCalled()
    expect(fake.play).not.toHaveBeenCalled()

    fake.resume.mockClear()
    fake.snapshot.intent = 'paused'
    await executePreviewMotionCommand({ type: PREVIEW_MOTION_REQUEST_TYPE, version: 1, action: 'play' })
    expect(fake.resume).toHaveBeenCalledTimes(1)
    expect(fake.restart).toHaveBeenCalledTimes(1)

    await executePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'seek',
      positionMs: 640,
    })
    expect(fake.seek).toHaveBeenCalledWith(640)

    await executePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'set-visual-mode',
      visualMode: 'full',
    })
    expect(fake.setVisualMode).toHaveBeenCalledWith('full')
  })

  it('解析只接受已知动作与合法参数', () => {
    expect(parsePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'seek',
      positionMs: 500,
    })).toMatchObject({ action: 'seek', positionMs: 500 })
    expect(parsePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'seek',
      positionMs: Number.POSITIVE_INFINITY,
    })).toBeNull()
    expect(parsePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 1,
      action: 'delete',
    })).toBeNull()
    expect(parsePreviewMotionCommand({
      type: PREVIEW_MOTION_REQUEST_TYPE,
      version: 2,
      action: 'play',
    })).toBeNull()
  })

  it('独立窗口不安装跨窗口监听', () => {
    const cleanup = installPreviewMotionBridge()
    expect(typeof cleanup).toBe('function')
    cleanup()
  })
})
