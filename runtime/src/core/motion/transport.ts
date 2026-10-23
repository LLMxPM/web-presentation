/**
 * 文件功能：实现页内编排的唯一播放所有者与确定性状态机。
 *
 * 播放意图（stopped/playing/paused）与运行阶段分离；位置由真实主媒体时钟或
 * 单调时钟推进。所有异步准备、播放与定位都核对 generation、revision 和 disposed，
 * 旧回执只清理自己，不提交状态。
 */
import { deriveSampledState, type MotionSampleResult } from './sampling'
import {
  MOTION_ERROR_BUFFER_TIMEOUT,
  MOTION_ERROR_MEDIA_BLOCKED,
  MOTION_ERROR_SNAPSHOT_UNAVAILABLE,
  MotionError,
  isMotionError,
  toMotionError,
} from './errors'
import {
  createMotionScheduler,
  type MotionAdapterApplyOptions,
  type MotionAdapterFactory,
  type MotionScheduler,
  type MotionTrackAdapter,
} from './adapters'
import { MotionTargetRegistry } from './target-registry'
import {
  type CompiledMediaTrack,
  type CompiledMotionPlan,
  type CompiledMotionTrack,
  type MotionPlaybackIntent,
  type MotionRunPhase,
  type MotionStateProof,
  type MotionTransportSnapshot,
  type MotionVisualMode,
} from './types'

/** 连续 tick 的最小位置提交差；避免同一毫秒重复通知。 */
const POSITION_EPSILON_MS = 0.5
/** 播放中恢复缓冲的上限；避免网络永久挂起使时间轴无限停留。 */
const BUFFER_RECOVERY_TIMEOUT_MS = 15_000

export interface MotionTransportOptions {
  plan: CompiledMotionPlan
  root: ParentNode
  pagePath: string
  generation: number
  createAdapter: MotionAdapterFactory
  /** 页面宿主共享的目标注册表；缺省由 transport 创建并负责释放。 */
  ownership?: MotionTargetRegistry
  visualMode?: MotionVisualMode
  allowMediaPlayback?: boolean
  muted?: boolean
  scheduler?: MotionScheduler
  now?: () => number
  onState?: (snapshot: MotionTransportSnapshot) => void
  /** 由原生创作入口构造，仍由本 transport 统一采样和释放。 */
  visualAdapter?: MotionTrackAdapter
}

export interface MotionTransport {
  readonly plan: CompiledMotionPlan
  readonly ownership: MotionTargetRegistry
  readonly visualMode: MotionVisualMode
  getSnapshot(): MotionTransportSnapshot
  prepare(): Promise<void>
  play(): Promise<boolean>
  pause(): boolean
  resume(): Promise<boolean>
  restart(): Promise<boolean>
  seek(positionMs: number): Promise<void>
  stop(): Promise<void>
  setMuted(muted: boolean): void
  /** 切换视觉映射偏好；已准备时立即重放当前状态。 */
  setVisualMode(mode: MotionVisualMode): void
  /** 无播放副作用的指定状态采样；供捕获与诊断使用。 */
  sampleAt(positionMs: number, visualMode?: MotionVisualMode): Promise<MotionSampleResult>
  subscribe(listener: (snapshot: MotionTransportSnapshot) => void): () => void
  dispose(): void
}

interface AdapterEntry {
  track: Pick<CompiledMotionTrack, 'id' | 'type' | 'startMs' | 'endMs' | 'required'>
  adapter: MotionTrackAdapter
}

/**
 * 创建页内时间轴 transport。
 * 构造阶段不读取 DOM、不播放媒体；第一次 prepare 才创建并准备适配器。
 */
export function createMotionTransport(options: MotionTransportOptions): MotionTransport {
  const { plan, root, pagePath, generation } = options
  let visualMode = options.visualMode ?? 'full'
  const scheduler = options.scheduler ?? createMotionScheduler()
  const now = options.now ?? (() => (typeof performance !== 'undefined' ? performance.now() : Date.now()))
  const ownsRegistry = options.ownership === undefined
  const ownership = options.ownership ?? new MotionTargetRegistry()
  if (ownsRegistry) ownership.beginGeneration(generation)

  let intent: MotionPlaybackIntent = 'stopped'
  let phase: MotionRunPhase = 'idle'
  let positionMs = 0
  let revision = 0
  let muted = options.muted === true
  const allowMediaPlayback = options.allowMediaPlayback !== false
  let errorCode: string | null = null
  let errorMessage = ''
  let lastError: MotionError | null = null
  let disposed = false
  let preparing = false
  let prepared = false
  let abortController: AbortController | null = null
  let tickHandle: number | null = null
  let anchorWallMs = 0
  let anchorPositionMs = 0
  let primaryHandover = false
  let bufferingStartedAtMs: number | null = null
  let bufferingTrackId: string | null = null
  const warnedOptionalBuffering = new Set<string>()
  const disabledOptionalAdapters = new Set<MotionTrackAdapter>()
  let seekChain: Promise<void> = Promise.resolve()
  let applyChain: Promise<void> = Promise.resolve()
  let pendingApplyPosition: number | null = null
  let lastEmittedPosition = -1
  let lastEmittedPhase: MotionRunPhase | null = null
  let lastEmittedIntent: MotionPlaybackIntent | null = null
  let entries: AdapterEntry[] = []
  const completedTrackIds = new Set<string>()
  const playingAdapters = new Set<MotionTrackAdapter>()
  const stateListeners = new Set<(snapshot: MotionTransportSnapshot) => void>()
  let primaryTrack: CompiledMediaTrack | null = null
  let primaryAdapter: MotionTrackAdapter | null = null

  function emit(): void {
    if (disposed) return
    const snapshot = getSnapshot()
    options.onState?.(snapshot)
    for (const listener of [...stateListeners]) {
      try {
        listener(snapshot)
      } catch (error) {
        console.error('[motion-transport] 状态监听失败', error)
      }
    }
  }

  /** 当前锚定位置；主媒体优先使用真实进度，交接后使用单调时钟。 */
  function currentPosition(): number {
    if (phase === 'buffering') return positionMs
    if (intent !== 'playing' || primaryHandover) {
      if (intent === 'playing' && primaryHandover) {
        return clampPosition(anchorPositionMs + (now() - anchorWallMs))
      }
      return positionMs
    }
    if (primaryTrack && primaryAdapter?.getClock) {
      const clock = primaryAdapter.getClock()
      if (clock && !clock.ended) {
        return clampPosition(primaryTrack.startMs + (clock.positionMs - primaryTrack.inMs) / primaryTrack.rate)
      }
    }
    return clampPosition(anchorPositionMs + (now() - anchorWallMs))
  }

  function clampPosition(value: number): number {
    if (!Number.isFinite(value)) return 0
    return Math.min(Math.max(value, 0), plan.durationMs)
  }

  function getSnapshot(): MotionTransportSnapshot {
    return {
      timelineId: plan.timelineId,
      planDigest: plan.planDigest,
      pagePath,
      generation,
      intent,
      phase,
      positionMs: currentPosition(),
      durationMs: plan.durationMs,
      revision,
      completedTrackIds: [...completedTrackIds].sort(),
      errorCode,
      errorMessage,
    }
  }

  function notifyIfChanged(): void {
    const position = currentPosition()
    if (phase === lastEmittedPhase && intent === lastEmittedIntent
      && Math.abs(position - lastEmittedPosition) < POSITION_EPSILON_MS) return
    lastEmittedPhase = phase
    lastEmittedIntent = intent
    lastEmittedPosition = position
    emit()
  }

  function setPhase(next: MotionRunPhase, error?: unknown): void {
    phase = next
    if (error === undefined) {
      errorCode = null
      errorMessage = ''
      lastError = null
    } else {
      const motionError = toMotionError(error)
      lastError = motionError
      errorCode = motionError.code
      errorMessage = motionError.message
    }
    notifyIfChanged()
  }

  function fail(error: unknown): void {
    const motionError = toMotionError(error)
    intent = 'stopped'
    cancelTick()
    pauseAdapters()
    setPhase('error', motionError)
  }

  function isErrorPhase(): boolean {
    return phase === 'error'
  }

  function cancelTick(): void {
    if (tickHandle !== null) {
      scheduler.cancel(tickHandle)
      tickHandle = null
    }
  }

  function scheduleTick(): void {
    if (disposed || tickHandle !== null || intent !== 'playing') return
    tickHandle = scheduler.request(() => {
      tickHandle = null
      void tick()
    })
  }

  function resetAnchor(position: number): void {
    anchorWallMs = now()
    anchorPositionMs = position
    positionMs = position
  }

  /** optional 轨道失败后只释放本轨道，避免重复调用失败适配器或阻断必需轨道。 */
  function disableOptional(entry: AdapterEntry, stage: string, error: unknown): void {
    if (disabledOptionalAdapters.has(entry.adapter)) return
    disabledOptionalAdapters.add(entry.adapter)
    playingAdapters.delete(entry.adapter)
    try { entry.adapter.pause?.() } catch { /* 继续释放失败轨道。 */ }
    try { entry.adapter.dispose() } catch { /* 其它轨道仍需继续。 */ }
    console.warn(`[motion-transport] optional 轨道 ${entry.track.id} 在 ${stage} 失败，已跳过。`, error)
  }

  /** 把位置应用到所有适配器；连续 tick 通过同一队列串行，避免乱序采样。 */
  function requestApply(position: number): Promise<void> {
    pendingApplyPosition = position
    const revisionAtRequest = revision
    applyChain = applyChain.then(async () => {
      if (disposed) return
      const target = pendingApplyPosition
      if (target === null) return
      pendingApplyPosition = null
      await applyAtPosition(target, revisionAtRequest)
    }).catch(error => {
      if (!disposed) fail(error)
    })
    return applyChain
  }

  async function applyAtPosition(position: number, revisionAtRequest: number, mode = visualMode, forceSeek = false): Promise<void> {
    const applyOptions: MotionAdapterApplyOptions = { positionMs: position, visualMode: mode, forceSeek }
    for (const entry of entries) {
      if (disposed || revisionAtRequest !== revision) return
      if (disabledOptionalAdapters.has(entry.adapter)) continue
      if (!entry.track.required && entry.adapter.getClock?.()?.buffering) continue
      try {
        await entry.adapter.applyAt(applyOptions)
      } catch (error) {
        if (entry.track.required) throw error
        disableOptional(entry, '采样', error)
      }
    }
    if (disposed || revisionAtRequest !== revision) return
    positionMs = position
    for (const entry of entries) {
      if (entry.track.required && position >= entry.track.endMs - POSITION_EPSILON_MS) {
        completedTrackIds.add(entry.track.id)
      }
    }
  }

  async function startAdapters(): Promise<void> {
    const playRevision = revision
    for (const entry of entries) {
      if (disposed || intent !== 'playing') return
      if (disabledOptionalAdapters.has(entry.adapter)) continue
      // 只有当前区间内的媒体才能播放；采样方法始终只负责状态写入。
      if (positionMs < entry.track.startMs || positionMs >= entry.track.endMs) {
        entry.adapter.pause?.()
        playingAdapters.delete(entry.adapter)
        continue
      }
      if (!entry.adapter.play || playingAdapters.has(entry.adapter)) continue
      try {
        await entry.adapter.play()
        if (disposed || intent !== 'playing' || playRevision !== revision) {
          entry.adapter.pause?.()
          return
        }
        playingAdapters.add(entry.adapter)
      } catch (error) {
        if (!entry.track.required) {
          disableOptional(entry, '播放', error)
          continue
        }
        if (isMotionError(error) && error.code === MOTION_ERROR_MEDIA_BLOCKED) {
          pauseAdapters()
          setPhase('blocked', error)
          cancelTick()
          return
        }
        throw error
      }
    }
  }

  function pauseAdapters(): void {
    playingAdapters.clear()
    for (const entry of entries) {
      if (disabledOptionalAdapters.has(entry.adapter)) continue
      try {
        entry.adapter.pause?.()
      } catch {
        // 暂停失败不阻断状态收敛；后续 applyAt/dispose 仍会尝试释放。
      }
    }
  }

  async function prepareInternal(): Promise<void> {
    if (disposed) return
    if (prepared) return
    if (preparing) {
      // 同一 transport 只有一个准备流程；重复调用等待现有流程完成。
      while (preparing && !disposed) {
        await new Promise(resolve => setTimeout(resolve, 0))
      }
      return
    }
    preparing = true
    setPhase('preparing')
    abortController = new AbortController()
    const signal = abortController.signal
    try {
      entries = plan.tracks.map(track => ({
        track,
        adapter: options.createAdapter({
          plan,
          track,
          root,
          signal,
          visualMode,
          allowMediaPlayback,
          muted,
          generation,
          ownership,
        }),
      }))
      if (options.visualAdapter && plan.visual) {
        entries.push({ track: { id: 'motion-visual', type: 'dom', startMs: 0, endMs: plan.visual.durationMs, required: true }, adapter: options.visualAdapter })
      }
      primaryTrack = plan.tracks.find((track): track is CompiledMediaTrack => (
        track.type !== 'dom' && track.type !== 'model3d' && track.id === plan.primaryClockTrackId
      )) ?? null
      primaryAdapter = entries.find(entry => entry.track.id === plan.primaryClockTrackId)?.adapter ?? null
      await Promise.all(entries.map(async entry => {
        try {
          await entry.adapter.prepare()
        } catch (error) {
          if (entry.track.required) throw error
          disableOptional(entry, '准备', error)
        }
      }))
      if (disposed || signal.aborted) return
      await applyAtPosition(positionMs, revision)
      prepared = true
      preparing = false
      setPhase('ready')
    } catch (error) {
      preparing = false
      if (disposed) return
      if (isMotionError(error) && error.code === MOTION_ERROR_MEDIA_BLOCKED) {
        setPhase('blocked', error)
        return
      }
      fail(error)
    }
  }

  async function tick(): Promise<void> {
    if (disposed || intent !== 'playing') return
    if (phase === 'completed' || phase === 'error' || phase === 'disposed') return
    // 一轮 tick 跨多个 await；期间可能发生定位、重播或换页，
    // 旧轮次不得在回执返回后继续提交位置、完成集合或再次排程。
    const tickRevision = revision
    try {
      // 所有正在播放的 required 媒体都属于同步集合；optional 卡顿则跳过并在恢复后追帧。
      let requiredBuffering: string | null = null
      for (const entry of entries) {
        if (disabledOptionalAdapters.has(entry.adapter)) continue
        if (positionMs < entry.track.startMs || positionMs >= entry.track.endMs) continue
        const clock = entry.adapter.getClock?.()
        if (!clock?.buffering) {
          warnedOptionalBuffering.delete(entry.track.id)
          continue
        }
        if (entry.track.required) requiredBuffering ??= entry.track.id
        else if (!warnedOptionalBuffering.has(entry.track.id)) {
          warnedOptionalBuffering.add(entry.track.id)
          console.warn(`[motion-transport] optional 媒体 ${entry.track.id} 缓冲中，按跳过策略继续播放。`)
        }
      }
      if (requiredBuffering) {
        if (phase !== 'buffering') {
          resetAnchor(currentPosition())
          bufferingStartedAtMs = now()
          bufferingTrackId = requiredBuffering
          pauseAdapters()
          setPhase('buffering')
        } else if (bufferingStartedAtMs !== null && now() - bufferingStartedAtMs >= BUFFER_RECOVERY_TIMEOUT_MS) {
          fail(new MotionError(MOTION_ERROR_BUFFER_TIMEOUT, '等待同步媒体恢复超时。', {
            trackId: bufferingTrackId ?? requiredBuffering,
          }))
          return
        }
        scheduleTick()
        return
      }
      if (phase === 'buffering') {
        bufferingStartedAtMs = null
        bufferingTrackId = null
        resetAnchor(positionMs)
        setPhase('ready')
      }
      if (primaryTrack && primaryAdapter && !primaryHandover) {
        const clock = primaryAdapter.getClock?.()
        if (clock?.blocked) {
          setPhase('blocked', new MotionError(MOTION_ERROR_MEDIA_BLOCKED, '浏览器阻止了媒体播放，请点击页面后重试。', {
            trackId: primaryTrack.id,
          }))
          return
        }
        if (clock?.ended || (clock && primaryTrack.startMs + (clock.positionMs - primaryTrack.inMs) / primaryTrack.rate >= primaryTrack.endMs)) {
          primaryHandover = true
          resetAnchor(primaryTrack.endMs)
        } else if (clock) {
          positionMs = clampPosition(primaryTrack.startMs + (clock.positionMs - primaryTrack.inMs) / primaryTrack.rate)
        }
      }

      if (!primaryTrack || primaryHandover) {
        positionMs = clampPosition(anchorPositionMs + (now() - anchorWallMs))
      }

      await requestApply(positionMs)
      if (disposed || intent !== 'playing' || tickRevision !== revision) return
      await startAdapters()
      if (disposed || intent !== 'playing' || tickRevision !== revision) return
      if (phase === 'blocked' || isErrorPhase()) return
      notifyIfChanged()

      if (disposed || intent !== 'playing') return
      if (positionMs >= plan.durationMs - POSITION_EPSILON_MS) {
        cancelTick()
        await requestApply(plan.durationMs)
        if (disposed || tickRevision !== revision) return
        completedTrackIds.clear()
        for (const entry of entries) {
          if (entry.track.required) completedTrackIds.add(entry.track.id)
        }
        intent = 'stopped'
        pauseAdapters()
        setPhase('completed')
        return
      }
      scheduleTick()
    } catch (error) {
      fail(error)
    }
  }

  async function playInternal(): Promise<boolean> {
    if (disposed || phase === 'error') return false
    if (phase === 'completed' || positionMs >= plan.durationMs - POSITION_EPSILON_MS) {
      await seekInternal(0)
    }
    intent = 'playing'
    if (!prepared) {
      await prepareInternal()
    }
    if (disposed || isErrorPhase()) {
      intent = 'stopped'
      return false
    }
    // 已准备的阻塞来自上一轮 play() 的浏览器拒绝；本轮可能由用户手势解除。
    if (prepared && phase === 'blocked') setPhase('ready')
    await requestApply(positionMs)
    try {
      await startAdapters()
    } catch (error) {
      fail(error)
      return false
    }
    if (disposed || intent !== 'playing') return !isErrorPhase()
    if (phase === 'blocked') return true
    completedTrackIds.clear()
    setPhase('ready')
    resetAnchor(positionMs)
    scheduleTick()
    return true
  }

  async function seekInternal(target: number): Promise<void> {
    if (disposed) return
    const clamped = clampPosition(target)
    revision += 1
    const requestRevision = revision
    cancelTick()
    pauseAdapters()
    setPhase('seeking')
    try {
      await applyChain
      await applyAtPosition(clamped, requestRevision, visualMode, true)
    } catch (error) {
      if (!disposed && requestRevision === revision) fail(error)
      return
    }
    if (disposed || requestRevision !== revision) return
    resetAnchor(clamped)
    primaryHandover = Boolean(primaryTrack && clamped >= primaryTrack.endMs)
    completedTrackIds.clear()
    if (intent === 'playing') {
      setPhase('ready')
      try {
        await startAdapters()
        if (phase !== 'blocked') scheduleTick()
      } catch (error) {
        if (requestRevision === revision) fail(error)
      }
    } else {
      setPhase('ready')
    }
  }

  function seek(position: number): Promise<void> {
    const run = () => seekInternal(position)
    seekChain = seekChain.then(run, run)
    return seekChain
  }

  async function prepare(): Promise<void> {
    await prepareInternal()
    if (phase === 'error' && lastError) throw lastError
  }

  async function play(): Promise<boolean> {
    return playInternal()
  }

  function pause(): boolean {
    if (disposed || (intent !== 'playing' && phase !== 'buffering' && phase !== 'preparing')) return false
    positionMs = currentPosition()
    intent = 'paused'
    cancelTick()
    pauseAdapters()
    if (phase !== 'error') setPhase('ready')
    return true
  }

  async function resume(): Promise<boolean> {
    if (disposed || intent !== 'paused') return false
    return playInternal()
  }

  async function restart(): Promise<boolean> {
    if (disposed) return false
    revision += 1
    positionMs = 0
    resetAnchor(0)
    completedTrackIds.clear()
    await seekInternal(0)
    if (disposed) return false
    intent = 'playing'
    return playInternal()
  }

  async function stop(): Promise<void> {
    if (disposed) return
    intent = 'stopped'
    cancelTick()
    pauseAdapters()
    await seekInternal(0)
    if (!disposed) setPhase('ready')
  }

  function setMuted(nextMuted: boolean): void {
    muted = nextMuted
    for (const entry of entries) {
      if (!disabledOptionalAdapters.has(entry.adapter)) entry.adapter.setMuted?.(nextMuted)
    }
  }

  /** 只改变视觉映射，不改变时钟与播放意图；准备后立即按当前位置重新应用。 */
  function setVisualMode(nextMode: MotionVisualMode): void {
    if (visualMode === nextMode) return
    visualMode = nextMode
    if (prepared && !disposed) void requestApply(getSnapshot().positionMs)
  }

  async function sampleAt(target: number, sampleVisualMode: MotionVisualMode = visualMode): Promise<MotionSampleResult> {
    if (disposed) {
      throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, '时间轴已释放，无法采样。')
    }
    if (!prepared && phase !== 'blocked') await prepareInternal()
    if (disposed || phase === 'error') {
      throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, errorMessage || '时间轴准备失败，无法采样。', {
        cause: errorCode,
      })
    }
    const clamped = clampPosition(target)
    const requestRevision = ++revision
    cancelTick()
    pauseAdapters()
    const previousIntent = intent
    intent = 'paused'
    try {
      await applyChain
      await applyAtPosition(clamped, requestRevision, sampleVisualMode, true)
      if (disposed || requestRevision !== revision) {
        throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, '采样已被更新的定位请求取代。')
      }
      positionMs = clamped
      const proofs: MotionStateProof[] = []
      for (const entry of entries) {
        if (disabledOptionalAdapters.has(entry.adapter)) continue
        if (!entry.adapter.freeze) continue
        try {
          proofs.push(await entry.adapter.freeze(clamped))
        } catch (error) {
          if (entry.track.required) throw error
          disableOptional(entry, '固化', error)
        }
      }
      const degradedTrackIds = entries
        .filter(entry => !entry.track.required && disabledOptionalAdapters.has(entry.adapter))
        .map(entry => entry.track.id)
      return deriveSampledState(plan, clamped, sampleVisualMode, proofs, degradedTrackIds)
    } finally {
      if (!disposed) {
        intent = previousIntent === 'playing' ? 'paused' : previousIntent
        setPhase('ready')
      }
    }
  }

  function dispose(): void {
    if (disposed) return
    disposed = true
    intent = 'stopped'
    cancelTick()
    abortController?.abort()
    abortController = null
    pauseAdapters()
    for (const entry of entries) {
      if (disabledOptionalAdapters.has(entry.adapter)) continue
      try {
        entry.adapter.dispose()
      } catch {
        // 释放失败不阻断其它资源；页面卸载后由文档销毁兜底。
      }
    }
    entries = []
    disabledOptionalAdapters.clear()
    // 尚未 prepare 就卸载时，原生视觉也已经创建，仍需释放作用域。
    options.visualAdapter?.dispose()
    primaryAdapter = null
    primaryTrack = null
    if (ownsRegistry) ownership.dispose()
    stateListeners.clear()
    phase = 'disposed'
    errorCode = null
    errorMessage = ''
  }

  // 初始海报状态：构造时立即应用一次，首次挂载不自动播放。
  return {
    plan,
    ownership,
    get visualMode() {
      return visualMode
    },
    getSnapshot,
    prepare,
    play,
    pause,
    resume,
    restart,
    seek,
    stop,
    setMuted,
    setVisualMode,
    sampleAt,
    subscribe(listener) {
      stateListeners.add(listener)
      return () => { stateListeners.delete(listener) }
    },
    dispose,
  }
}
