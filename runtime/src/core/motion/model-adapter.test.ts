/**
 * 文件功能：覆盖 WP06 模型片段映射、整体变换插值与动作句柄校验。
 */
import { describe, expect, it, vi } from 'vitest'

import type { MotionAdapterContext } from './adapters'
import { compilePageTimeline } from './compile'
import { MOTION_ERROR_MODEL_REFERENCE_STALE } from './errors'
import {
  createModelMotionAdapter,
  interpolateModelTransform,
  mapModelMotionPosition,
  resolveModelElement,
} from './model-adapter'
import { MotionTargetRegistry } from './target-registry'
import type { CompiledModelTrack, MotionVisualMode } from './types'
import {
  MODEL_MOTION_HANDLE_KEY,
  type ModelMotionApplyRequest,
  type ModelMotionHandle,
} from '@/runtime-kit/internal/renderers/model3d/motion/motion-contract'

function modelTrack(overrides: Partial<CompiledModelTrack> = {}): CompiledModelTrack {
  return {
    type: 'model3d',
    id: 'product',
    label: 'product',
    asset: 'product',
    clip: { index: 0, name: 'Spin', durationMs: 2000 },
    inMs: 200,
    outMs: 1200,
    rate: 1,
    repeat: 1,
    endBehavior: 'hold',
    startMs: 500,
    endMs: 1500,
    durationMs: 1000,
    required: true,
    role: 'content',
    transform: { from: { rotationY: 0 }, to: { rotationY: 90 } },
    ...overrides,
  }
}

function makeContext(root: HTMLElement, track: CompiledModelTrack, visualMode: MotionVisualMode = 'full'): MotionAdapterContext {
  return {
    plan: compilePageTimeline({
      schemaVersion: 1,
      timelineId: 'model-test',
      tracks: [{
        type: 'model3d',
        id: track.id,
        asset: track.asset,
        clip: track.clip,
        inMs: track.inMs,
        outMs: track.outMs,
        rate: track.rate,
        repeat: track.repeat,
        startMs: track.startMs,
        transform: track.transform,
      }],
    }),
    track,
    root,
    signal: new AbortController().signal,
    visualMode,
    allowMediaPlayback: false,
    muted: false,
    generation: 1,
    ownership: new MotionTargetRegistry(),
  }
}

function installFakeHandle(element: HTMLElement, requests: ModelMotionApplyRequest[], signature = 'current-signature'): void {
  const handle: ModelMotionHandle = {
    listAnimations: () => [{ index: 0, name: 'Spin', durationMs: 2000, channelCount: 3, signature }],
    applyAt: (request) => {
      requests.push(request)
      return {
        clipIndex: request.clipIndex,
        clipName: 'Spin',
        clipTimeMs: request.clipTimeMs,
        clipDurationMs: request.clipDurationMs,
        actionTimeMs: request.clipTimeMs,
        actionWeight: 1,
        transform: request.transform,
      }
    },
  }
  ;(element as unknown as Record<string, unknown>)[MODEL_MOTION_HANDLE_KEY] = handle
}

describe('mapModelMotionPosition', () => {
  it('处理起点前、裁切、重复与结束', () => {
    const track = modelTrack()
    expect(mapModelMotionPosition(track, 0)).toMatchObject({ clipTimeMs: 200, beforeStart: true })
    expect(mapModelMotionPosition(track, 500)).toMatchObject({ clipTimeMs: 200 })
    expect(mapModelMotionPosition(track, 1000)).toMatchObject({ clipTimeMs: 700, cycleIndex: 0 })
    expect(mapModelMotionPosition(track, 1500)).toMatchObject({ clipTimeMs: 1200, finished: true })

    const repeated = modelTrack({ repeat: 2, durationMs: 2000, endMs: 2500 })
    expect(mapModelMotionPosition(repeated, 1999)).toMatchObject({ cycleIndex: 1 })
  })
})

describe('interpolateModelTransform', () => {
  it('从同一 from/to 重建任意进度且端点精确', () => {
    expect(interpolateModelTransform({}, {}, 0)).toEqual({ x: 0, y: 0, z: 0, scale: 1, rotationY: 0 })
    const middle = interpolateModelTransform({ rotationY: 0, scale: 1 }, { rotationY: 90, scale: 2 }, 0.5)
    expect(middle.rotationY).toBeGreaterThan(0)
    expect(middle.rotationY).toBeLessThan(90)
    expect(middle.scale).toBeGreaterThan(1)
    expect(interpolateModelTransform({ rotationY: 0 }, { rotationY: 90 }, 1).rotationY).toBe(90)
  })
})

describe('resolveModelElement', () => {
  it('按资源名定位模型根', () => {
    const root = document.createElement('div')
    root.innerHTML = '<div data-runtime-kit-media-kind="model3d" data-runtime-asset-name="product"></div>'
    expect(resolveModelElement(root, modelTrack())?.dataset.runtimeAssetName).toBe('product')
  })
})

describe('createModelMotionAdapter', () => {
  it('相同名称和时长的动作被替换后，旧签名明确失效', async () => {
    const root = document.createElement('div')
    root.innerHTML = '<div data-runtime-kit-media-kind="model3d" data-runtime-asset-name="product" data-runtime-model-state="ready"></div>'
    const element = root.firstElementChild as HTMLElement
    installFakeHandle(element, [])
    const stale = modelTrack({ clip: { index: 0, name: 'Spin', durationMs: 2000, signature: 'old-signature' } })
    const adapter = createModelMotionAdapter(makeContext(root, stale))
    await expect(adapter.prepare()).rejects.toMatchObject({ code: MOTION_ERROR_MODEL_REFERENCE_STALE })
    adapter.dispose()
    const valid = modelTrack({ clip: { ...stale.clip, signature: 'current-signature' } })
    const current = createModelMotionAdapter(makeContext(root, valid))
    await expect(current.prepare()).resolves.toBeUndefined()
    current.dispose()
  })
  it('准备后按逻辑位置应用片段与整体变换', async () => {
    const root = document.createElement('div')
    root.innerHTML = '<div data-runtime-kit-media-kind="model3d" data-runtime-asset-name="product" data-runtime-model-state="ready"><div data-runtime-model-state="ready"></div></div>'
    const modelElement = root.querySelector<HTMLElement>('[data-runtime-kit-media-kind="model3d"]')!
    const requests: ModelMotionApplyRequest[] = []
    installFakeHandle(modelElement, requests)

    const adapter = createModelMotionAdapter(makeContext(root, modelTrack()))
    await adapter.prepare()
    await adapter.applyAt({ positionMs: 1000, visualMode: 'full' })

    expect(requests).toHaveLength(2)
    expect(requests[0].clipTimeMs).toBe(200)
    expect(requests[1].clipTimeMs).toBe(700)
    expect(requests[1].transform.rotationY).toBeGreaterThan(0)
    adapter.dispose()
  })

  it('片段索引失效时返回可定位的 stale 错误', async () => {
    const root = document.createElement('div')
    root.innerHTML = '<div data-runtime-kit-media-kind="model3d" data-runtime-asset-name="product" data-runtime-model-state="ready"></div>'
    const modelElement = root.querySelector<HTMLElement>('[data-runtime-kit-media-kind="model3d"]')!
    installFakeHandle(modelElement, [])

    const stale = modelTrack({ clip: { index: 3, durationMs: 2000 } })
    const adapter = createModelMotionAdapter(makeContext(root, stale))
    await expect(adapter.prepare()).rejects.toMatchObject({ code: MOTION_ERROR_MODEL_REFERENCE_STALE })
    adapter.dispose()
  })

  it('reduced 直接应用结束姿态', async () => {
    const root = document.createElement('div')
    root.innerHTML = '<div data-runtime-kit-media-kind="model3d" data-runtime-asset-name="product" data-runtime-model-state="ready"></div>'
    const modelElement = root.querySelector<HTMLElement>('[data-runtime-kit-media-kind="model3d"]')!
    const requests: ModelMotionApplyRequest[] = []
    installFakeHandle(modelElement, requests)

    const adapter = createModelMotionAdapter(makeContext(root, modelTrack(), 'reduced'))
    await adapter.prepare()
    expect(requests.at(-1)?.clipTimeMs).toBe(1200)
    expect(requests.at(-1)?.transform.rotationY).toBe(90)
    adapter.dispose()
  })
})
