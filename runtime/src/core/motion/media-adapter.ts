/**
 * 文件功能：实现音视频同步适配器。
 *
 * 真媒体只负责 decode/seek/play；裁切、重复、rate 与时间映射由 transport 的
 * 逻辑位置换算。实时播放不在每帧写 currentTime，只在漂移超过阈值或重复跨边界时校正。
 */
import type { MotionAdapterContext, MotionTrackAdapter } from './adapters'
import {
  MOTION_ERROR_BUFFER_TIMEOUT,
  MOTION_ERROR_DURATION_UNRESOLVED,
  MOTION_ERROR_MEDIA_BLOCKED,
  MOTION_ERROR_TARGET_INVALID,
  MotionError,
} from './errors'
import { digestMotionStateProof } from './sampling'
import type { CompiledMediaTrack, MotionStateProof, MotionVisualMode } from './types'

const DEFAULT_MEDIA_DEADLINE_MS = 15_000
const DRIFT_CORRECTION_THRESHOLD_MS = 120
const VIDEO_FRAME_TIMEOUT_MS = 1_000

export interface MediaMotionAdapterOptions {
  /** metadata、seek 与视频帧确认的总期限。 */
  deadlineMs?: number
}

/** 计算逻辑位置对应的真实媒体时间；供适配器与测试共用。 */
export function mapMediaTimelinePosition(
  track: Pick<CompiledMediaTrack, 'startMs' | 'endMs' | 'durationMs' | 'inMs' | 'outMs' | 'rate' | 'repeat'>,
  positionMs: number,
): { sourceTimeMs: number; cycleIndex: number; finished: boolean; beforeStart: boolean } {
  if (positionMs < track.startMs) {
    return { sourceTimeMs: track.inMs, cycleIndex: 0, finished: false, beforeStart: true }
  }
  const local = Math.min(positionMs - track.startMs, track.durationMs)
  const cycleDurationMs = (track.outMs - track.inMs) / track.rate
  const finished = local >= track.durationMs - 0.5
  if (finished) {
    return { sourceTimeMs: track.outMs, cycleIndex: track.repeat - 1, finished: true, beforeStart: false }
  }
  const cycleIndex = Math.min(Math.floor(local / cycleDurationMs), track.repeat - 1)
  const cycleOffsetMs = local - cycleIndex * cycleDurationMs
  return {
    sourceTimeMs: Math.min(track.inMs + cycleOffsetMs * track.rate, track.outMs),
    cycleIndex,
    finished: false,
    beforeStart: false,
  }
}

/**
 * 在当前页面根内查找媒体元素。
 * 优先使用轨道 selector；否则按 AssetAudio/AssetVideo 根节点的 data-runtime-asset-name 定位。
 */
export function resolveMediaElement(root: ParentNode, track: CompiledMediaTrack): HTMLMediaElement | null {
  if (track.selector) {
    const selected = root.querySelector<HTMLElement>(track.selector)
    if (selected && (selected.tagName === 'AUDIO' || selected.tagName === 'VIDEO')) {
      return selected as HTMLMediaElement
    }
    const nested = root.querySelector<HTMLMediaElement>(`${track.selector} audio, ${track.selector} video`)
    if (nested) return nested
  }
  const candidates = Array.from(root.querySelectorAll<HTMLMediaElement>('audio, video'))
  return candidates.find(element => {
    const owner = element.closest('[data-runtime-asset-name]') as HTMLElement | null
    return owner?.dataset.runtimeAssetName === track.asset
  }) ?? null
}

/** 创建单轨道音视频适配器。 */
export function createMediaMotionAdapter(
  context: MotionAdapterContext,
  options: MediaMotionAdapterOptions = {},
): MotionTrackAdapter {
  const track = context.track as CompiledMediaTrack
  if (track.type !== 'audio' && track.type !== 'video') {
    throw new MotionError(MOTION_ERROR_TARGET_INVALID, '媒体适配器只接受音视频轨道。', { trackId: track.id })
  }
  const deadlineMs = options.deadlineMs ?? DEFAULT_MEDIA_DEADLINE_MS
  let element: HTMLMediaElement | null = null
  let claim: { release(): void } | null = null
  let originalMuted = false
  let originalPreload: HTMLMediaElement['preload'] = 'metadata'
  let disposed = false
  let buffering = false
  let blocked = false
  let sessionMuted = context.muted
  let visualMode: MotionVisualMode = context.visualMode
  let lastSourceTimeMs = Number.NaN
  let listeners: Array<() => void> = []

  function ensureElement(): HTMLMediaElement {
    if (element?.isConnected) return element
    const found = resolveMediaElement(context.root, track)
    if (!found) {
      throw new MotionError(
        MOTION_ERROR_TARGET_INVALID,
        `媒体资源 ${track.asset} 未在当前页面渲染。`,
        { fieldPath: `timeline.tracks.${track.id}.asset`, trackId: track.id },
      )
    }
    element = found
    return found
  }

  function applyMuted(): void {
    if (!element) return
    element.muted = sessionMuted || track.muted
  }

  /** 等待媒体 metadata；超时进入可重试的缓冲错误而不是伪造时长。 */
  async function waitForMetadata(): Promise<void> {
    const media = ensureElement()
    if (media.readyState >= 1 && Number.isFinite(media.duration) && media.duration > 0) {
      // metadata 已缓存时也必须继续核对裁切边界。
    } else {
      await waitForEvent(media, ['loadedmetadata', 'canplay'], 'error', deadlineMs, () => {
        return media.readyState >= 1 && Number.isFinite(media.duration) && media.duration > 0
      })
    }
    if (!Number.isFinite(media.duration) || media.duration <= 0) {
      throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, `媒体资源 ${track.asset} 没有可用时长。`, {
        trackId: track.id,
      })
    }
    if (track.outMs > media.duration * 1000 + 1) {
      throw new MotionError(
        MOTION_ERROR_DURATION_UNRESOLVED,
        `轨道 ${track.id} 的裁切终点超过媒体真实时长。`,
        { fieldPath: `timeline.tracks.${track.id}.outMs`, trackId: track.id },
      )
    }
  }

  /** 定位真实媒体并等待 seeked；视频额外等待一帧，无法确认时退回 seeked。 */
  async function seekTo(sourceTimeMs: number, mode: MotionVisualMode): Promise<void> {
    const media = ensureElement()
    const seconds = Math.max(0, sourceTimeMs / 1000)
    if (Math.abs(media.currentTime - seconds) <= 0.002) {
      lastSourceTimeMs = sourceTimeMs
      return
    }
    await waitForEvent(media, ['seeked'], 'error', deadlineMs, () => {
      return Math.abs(media.currentTime - seconds) <= 0.005
    }, () => {
      media.currentTime = seconds
    })
    lastSourceTimeMs = sourceTimeMs
    if (track.type === 'video') {
      await waitForVideoFrame(media as HTMLVideoElement)
    }
  }

  function shouldCorrectDrift(sourceTimeMs: number, force: boolean): boolean {
    if (!element) return true
    if (force) return true
    if (!Number.isFinite(lastSourceTimeMs)) return true
    const currentMs = element.currentTime * 1000
    return Math.abs(currentMs - sourceTimeMs) > DRIFT_CORRECTION_THRESHOLD_MS
  }

  async function applyPosition(positionMs: number, mode: MotionVisualMode, forceSeek = false): Promise<void> {
    if (disposed) return
    visualMode = mode
    const mapping = mapMediaTimelinePosition(track, positionMs)
    const media = ensureElement()
    if (mapping.beforeStart || mapping.finished) {
      if (!media.paused) media.pause()
    }
    if (mapping.beforeStart) {
      if (shouldCorrectDrift(mapping.sourceTimeMs, true)) await seekTo(mapping.sourceTimeMs, mode)
      return
    }
    if (mapping.finished) {
      if (track.endBehavior === 'restore') {
        if (shouldCorrectDrift(track.inMs, true)) await seekTo(track.inMs, mode)
      } else if (shouldCorrectDrift(mapping.sourceTimeMs, true)) {
        await seekTo(mapping.sourceTimeMs, mode)
      }
      return
    }
    if (shouldCorrectDrift(mapping.sourceTimeMs, forceSeek)) {
      await seekTo(mapping.sourceTimeMs, mode)
    } else {
      lastSourceTimeMs = mapping.sourceTimeMs
    }
  }

  function bindStateEvents(): void {
    const media = ensureElement()
    const onWaiting = () => {
      if (!media.paused) buffering = true
    }
    const onPlaying = () => {
      buffering = false
    }
    const onError = () => {
      buffering = false
    }
    media.addEventListener('waiting', onWaiting)
    media.addEventListener('stalled', onWaiting)
    media.addEventListener('playing', onPlaying)
    media.addEventListener('canplay', onPlaying)
    media.addEventListener('error', onError)
    listeners.push(
      () => media.removeEventListener('waiting', onWaiting),
      () => media.removeEventListener('stalled', onWaiting),
      () => media.removeEventListener('playing', onPlaying),
      () => media.removeEventListener('canplay', onPlaying),
      () => media.removeEventListener('error', onError),
    )
  }

  return {
    type: track.type,
    async prepare() {
      const media = ensureElement()
      claim = context.ownership.claim(track.type, track.selector ?? track.asset, media, context.generation)
      originalMuted = media.muted
      originalPreload = media.preload
      applyMuted()
      media.playbackRate = track.rate
      media.volume = track.volume
      if (media.preload !== 'auto') media.preload = 'auto'
      bindStateEvents()
      await waitForMetadata()
      await applyPosition(track.startMs, context.visualMode, true)
    },
    async applyAt({ positionMs, visualMode: mode, forceSeek }) {
      await applyPosition(positionMs, mode, forceSeek)
    },
    async play() {
      if (disposed || !context.allowMediaPlayback) return
      const media = ensureElement()
      blocked = false
      if (!media.paused) return
      applyMuted()
      try {
        await media.play()
      } catch (error) {
        if (isNotAllowedError(error)) {
          blocked = true
          throw new MotionError(MOTION_ERROR_MEDIA_BLOCKED, '浏览器阻止了媒体播放，请点击页面后重试。', {
            trackId: track.id,
          })
        }
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, mediaErrorMessage(error), { trackId: track.id })
      }
    },
    pause() {
      if (element && !element.paused) element.pause()
    },
    setMuted(nextMuted: boolean) {
      sessionMuted = nextMuted
      applyMuted()
    },
    getClock() {
      if (!element) return null
      const positionMs = element.currentTime * 1000
      return {
        positionMs,
        ended: element.ended || positionMs >= track.outMs - 0.5,
        blocked,
        buffering: buffering || (!element.paused && element.readyState < 3),
      }
    },
    async freeze(positionMs): Promise<MotionStateProof> {
      if (!element) {
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, '媒体目标尚未准备。', { trackId: track.id })
      }
      element.pause()
      await applyPosition(positionMs, visualMode, true)
      const details = {
        asset: track.asset,
        sourceTimeMs: element.currentTime * 1000,
        muted: element.muted,
        paused: element.paused,
        repeatIndex: mapMediaTimelinePosition(track, positionMs).cycleIndex,
      }
      return {
        trackId: track.id,
        type: track.type,
        positionMs,
        digest: digestMotionStateProof(track.id, track.type, positionMs, details),
        details,
      }
    },
    dispose() {
      if (disposed) return
      disposed = true
      for (const unbind of listeners) unbind()
      listeners = []
      if (element) {
        try {
          element.pause()
          element.currentTime = 0
          element.muted = originalMuted
          element.preload = originalPreload
        } catch {
          // 已销毁的媒体元素无需恢复。
        }
      }
      claim?.release()
      claim = null
      element = null
      buffering = false
    },
  }
}

function isNotAllowedError(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && (error as { name?: unknown }).name === 'NotAllowedError')
}

function mediaErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '媒体播放失败。'
}

/**
 * 等待媒体事件；beforeWait 在挂载监听后执行，避免事件早于赋值。
 * 超时统一映射为 TIMELINE_BUFFER_TIMEOUT，由宿主显示可重试失败。
 */
function waitForEvent(
  media: HTMLMediaElement,
  successTypes: string[],
  errorType: string,
  timeoutMs: number,
  isReady: () => boolean,
  beforeWait?: () => void,
): Promise<void> {
  if (isReady()) return Promise.resolve()
  return new Promise<void>((resolve, reject) => {
    let settled = false
    const cleanup = () => {
      for (const type of successTypes) media.removeEventListener(type, onSuccess)
      media.removeEventListener(errorType, onError)
      clearTimeout(timer)
    }
    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      cleanup()
      if (error) reject(error)
      else resolve()
    }
    const onSuccess = () => {
      if (isReady()) finish()
    }
    const onError = () => {
      finish(new MotionError(MOTION_ERROR_TARGET_INVALID, mediaErrorMessage(media.error), {}))
    }
    for (const type of successTypes) media.addEventListener(type, onSuccess)
    media.addEventListener(errorType, onError)
    const timer = setTimeout(() => {
      finish(new MotionError(MOTION_ERROR_BUFFER_TIMEOUT, '等待媒体就绪超时。', {}))
    }, timeoutMs)
    try {
      beforeWait?.()
    } catch (error) {
      finish(error instanceof Error ? error : new Error(String(error)))
    }
  })
}

/** 等待视频目标帧；不支持 rVFC 或超时时按 seeked 状态继续。 */
function waitForVideoFrame(video: HTMLVideoElement): Promise<void> {
  const requestFrame = (video as unknown as {
    requestVideoFrameCallback?: (callback: () => void) => number
    cancelVideoFrameCallback?: (handle: number) => void
  }).requestVideoFrameCallback
  if (typeof requestFrame !== 'function') return Promise.resolve()
  return new Promise<void>(resolve => {
    let settled = false
    const timer = setTimeout(() => finish(), VIDEO_FRAME_TIMEOUT_MS)
    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve()
    }
    try {
      requestFrame.call(video, () => finish())
    } catch {
      finish()
    }
  })
}
