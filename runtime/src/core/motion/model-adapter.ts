/**
 * 文件功能：实现三维动作适配器。
 *
 * 适配器只做逻辑位置→片段时刻、裁切/重复与整体变换插值，再调用 ModelViewer
 * 注册的动作句柄；不持有 Mixer、Object3D 或原始动画片段。
 */
import type { MotionAdapterContext, MotionTrackAdapter } from './adapters'
import {
  MOTION_ERROR_BUFFER_TIMEOUT,
  MOTION_ERROR_MODEL_REFERENCE_STALE,
  MOTION_ERROR_TARGET_INVALID,
  MotionError,
} from './errors'
import { digestMotionStateProof } from './sampling'
import type {
  CompiledModelTrack,
  ModelMotionTransformState,
  MotionStateProof,
  MotionVisualMode,
} from './types'
import {
  readModelMotionHandle,
  type ModelMotionHandle,
  type ModelMotionStateDetails,
} from '@/runtime-kit/internal/renderers/model3d/motion/motion-contract'

const DEFAULT_MODEL_DEADLINE_MS = 15_000

export interface ModelMotionAdapterOptions {
  deadlineMs?: number
}

/** 计算逻辑位置对应的片段时刻与循环序号。 */
export function mapModelMotionPosition(
  track: Pick<CompiledModelTrack, 'startMs' | 'durationMs' | 'inMs' | 'outMs' | 'rate' | 'repeat'>,
  positionMs: number,
): { clipTimeMs: number; cycleIndex: number; finished: boolean; beforeStart: boolean } {
  if (positionMs < track.startMs) {
    return { clipTimeMs: track.inMs, cycleIndex: 0, finished: false, beforeStart: true }
  }
  const local = Math.min(positionMs - track.startMs, track.durationMs)
  const cycleDurationMs = (track.outMs - track.inMs) / track.rate
  const finished = local >= track.durationMs - 0.5
  if (finished) {
    return { clipTimeMs: track.outMs, cycleIndex: track.repeat - 1, finished: true, beforeStart: false }
  }
  const cycleIndex = Math.min(Math.floor(local / cycleDurationMs), track.repeat - 1)
  const offset = local - cycleIndex * cycleDurationMs
  return {
    clipTimeMs: Math.min(track.inMs + offset * track.rate, track.outMs),
    cycleIndex,
    finished: false,
    beforeStart: false,
  }
}

/** power2.out 缓动；与 DOM 适配器保持同一视觉节奏。 */
export function easeModelProgress(progress: number): number {
  const clamped = Math.min(Math.max(progress, 0), 1)
  return 1 - (1 - clamped) ** 3
}

/** 在整体变换轨道上插值；任意顺序采样都从同一 from/to 计算。 */
export function interpolateModelTransform(
  from: ModelMotionTransformState,
  to: ModelMotionTransformState,
  progress: number,
): Required<ModelMotionTransformState> {
  const eased = easeModelProgress(progress)
  return {
    x: (from.x ?? 0) + ((to.x ?? 0) - (from.x ?? 0)) * eased,
    y: (from.y ?? 0) + ((to.y ?? 0) - (from.y ?? 0)) * eased,
    z: (from.z ?? 0) + ((to.z ?? 0) - (from.z ?? 0)) * eased,
    scale: (from.scale ?? 1) + ((to.scale ?? 1) - (from.scale ?? 1)) * eased,
    rotationY: (from.rotationY ?? 0) + ((to.rotationY ?? 0) - (from.rotationY ?? 0)) * eased,
  }
}

/** 在当前页面根内查找模型根元素。 */
export function resolveModelElement(root: ParentNode, track: CompiledModelTrack): HTMLElement | null {
  const isModel = (element: Element | null): boolean => (
    Boolean(element && element.getAttribute('data-runtime-kit-media-kind') === 'model3d')
  )
  if (track.selector) {
    const selected = root.querySelector<HTMLElement>(track.selector)
    if (isModel(selected)) return selected
    const nested = selected?.querySelector<HTMLElement>('[data-runtime-kit-media-kind="model3d"]') ?? null
    if (nested) return nested
  }
  const candidates: HTMLElement[] = []
  if (isModel(root as Element)) candidates.push(root as HTMLElement)
  candidates.push(...Array.from(root.querySelectorAll<HTMLElement>('[data-runtime-kit-media-kind="model3d"]')))
  return candidates.find(element => {
    const owner = element.closest('[data-runtime-asset-name]') as HTMLElement | null
    return (owner ?? element).dataset.runtimeAssetName === track.asset
  }) ?? null
}

/** 创建单轨道三维动作适配器。 */
export function createModelMotionAdapter(
  context: MotionAdapterContext,
  options: ModelMotionAdapterOptions = {},
): MotionTrackAdapter {
  const track = context.track as CompiledModelTrack
  if (track.type !== 'model3d') {
    throw new MotionError(MOTION_ERROR_TARGET_INVALID, '模型适配器只接受 model3d 轨道。', { trackId: track.id })
  }
  const deadlineMs = options.deadlineMs ?? DEFAULT_MODEL_DEADLINE_MS
  let element: HTMLElement | null = null
  let handle: ModelMotionHandle | null = null
  let claim: { release(): void } | null = null
  let disposed = false
  let visualMode: MotionVisualMode = context.visualMode

  function ensureElement(): HTMLElement {
    if (element?.isConnected) return element
    const found = resolveModelElement(context.root, track)
    if (!found) {
      throw new MotionError(MOTION_ERROR_TARGET_INVALID, `三维资源 ${track.asset} 未在当前页面渲染。`, {
        fieldPath: `timeline.tracks.${track.id}.asset`,
        trackId: track.id,
      })
    }
    element = found
    return found
  }

  /** 等待模型首次真实绘制；错误态直接失败，不无限等待。 */
  async function waitForReady(target: HTMLElement): Promise<void> {
    const start = Date.now()
    while (!disposed) {
      const state = target.getAttribute('data-runtime-model-state')
      if (state === 'ready') return
      if (state === 'error') {
        const message = target.getAttribute('data-runtime-model-message') || '三维模型加载失败。'
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, message, { trackId: track.id })
      }
      if (Date.now() - start > deadlineMs) {
        throw new MotionError(MOTION_ERROR_BUFFER_TIMEOUT, '等待三维模型就绪超时。', { trackId: track.id })
      }
      await new Promise(resolve => setTimeout(resolve, 25))
    }
  }

  function validateClip(target: HTMLElement): void {
    const current = readModelMotionHandle(target)
    if (!current) {
      throw new MotionError(MOTION_ERROR_MODEL_REFERENCE_STALE, '三维资源没有可用的动作句柄。', {
        trackId: track.id,
      })
    }
    handle = current
    const summaries = current.listAnimations()
    const summary = summaries.find(item => item.index === track.clip.index)
    if (!summary) {
      throw new MotionError(
        MOTION_ERROR_MODEL_REFERENCE_STALE,
        `动画片段索引 ${track.clip.index} 不存在，请重新查询资源动作。`,
        { fieldPath: `timeline.tracks.${track.id}.clip.index`, trackId: track.id },
      )
    }
    if (track.clip.name && summary.name && track.clip.name !== summary.name) {
      throw new MotionError(
        MOTION_ERROR_MODEL_REFERENCE_STALE,
        `动画片段名称已变化：期望 ${track.clip.name}，实际 ${summary.name}。`,
        { fieldPath: `timeline.tracks.${track.id}.clip.name`, trackId: track.id },
      )
    }
    if (track.clip.signature && track.clip.signature !== summary.signature) {
      throw new MotionError(MOTION_ERROR_MODEL_REFERENCE_STALE, '动画片段内容已变化，请重新查询资源动作。', {
        fieldPath: `timeline.tracks.${track.id}.clip.signature`, trackId: track.id,
      })
    }
    if (Math.abs(summary.durationMs - track.clip.durationMs) > 2) {
      throw new MotionError(
        MOTION_ERROR_MODEL_REFERENCE_STALE,
        `动画片段时长已变化：期望 ${track.clip.durationMs}ms，实际 ${summary.durationMs.toFixed(0)}ms。`,
        { fieldPath: `timeline.tracks.${track.id}.clip.durationMs`, trackId: track.id },
      )
    }
    if (track.outMs > summary.durationMs + 2) {
      throw new MotionError(
        MOTION_ERROR_MODEL_REFERENCE_STALE,
        '动画裁切终点超过片段真实时长。',
        { fieldPath: `timeline.tracks.${track.id}.outMs`, trackId: track.id },
      )
    }
  }

  function applyPosition(positionMs: number, mode: MotionVisualMode): ModelMotionStateDetails {
    if (!handle) {
      throw new MotionError(MOTION_ERROR_MODEL_REFERENCE_STALE, '三维动作尚未准备。', { trackId: track.id })
    }
    visualMode = mode
    const mapping = mapModelMotionPosition(track, positionMs)
    const reduced = mode === 'reduced'
    const clipTimeMs = reduced ? track.outMs : mapping.clipTimeMs
    const progress = reduced
      ? 1
      : mapping.beforeStart
        ? 0
        : mapping.finished
          ? 1
          : Math.min((positionMs - track.startMs) / track.durationMs, 1)
    const transform = track.transform
      ? interpolateModelTransform(track.transform.from, track.transform.to, progress)
      : interpolateModelTransform({}, {}, 0)
    return handle.applyAt({
      clipIndex: track.clip.index,
      clipName: track.clip.name,
      clipDurationMs: track.clip.durationMs,
      clipTimeMs,
      transform,
    })
  }

  return {
    type: 'model3d',
    async prepare() {
      const target = ensureElement()
      claim = context.ownership.claim('model3d', track.selector ?? track.asset, target, context.generation)
      await waitForReady(target)
      validateClip(target)
      applyPosition(track.startMs, context.visualMode)
    },
    async applyAt({ positionMs, visualMode: mode }) {
      applyPosition(positionMs, mode)
    },
    getClock() {
      return null
    },
    async freeze(positionMs): Promise<MotionStateProof> {
      const details = applyPosition(positionMs, visualMode)
      return {
        trackId: track.id,
        type: 'model3d',
        positionMs,
        digest: digestMotionStateProof(track.id, 'model3d', positionMs, {
          clipIndex: details.clipIndex,
          clipTimeMs: details.clipTimeMs,
          transform: details.transform,
          visualMode,
        }),
        details: {
          clipIndex: details.clipIndex,
          clipTimeMs: details.clipTimeMs,
          actionWeight: details.actionWeight,
          transform: details.transform,
          visualMode,
        },
      }
    },
    dispose() {
      if (disposed) return
      disposed = true
      claim?.release()
      claim = null
      handle = null
      element = null
    },
  }
}
