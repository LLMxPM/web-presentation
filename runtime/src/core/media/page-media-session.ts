/**
 * 文件功能：按活动放映页收集原生音视频，维护每页 generation 内的播放状态、完成集合与清理。
 *
 * 只处理当前页根节点内的 audio/video；循环媒体不参与完成判定，第三方 iframe 不跨文档。
 * 播放状态来自元素事件与 play() Promise，不根据 autoplay 属性推断成功。
 */

export type PageMediaEventType = 'targets' | 'play' | 'pause' | 'ended' | 'error' | 'blocked' | 'reset' | 'contract-error'

/** 页面媒体用途；未声明时按 content 兼容旧页面。 */
export type PageMediaPurpose = 'content' | 'narration'

export interface PageMediaTargetSnapshot {
  id: string
  purpose: PageMediaPurpose
  loop: boolean
  /** 是否参与 media_end 完成判定；loop 与冲突旁白不参与。 */
  participating: boolean
  /** 是否具备放映自动播放资格；内容音频只允许用户手势播放。 */
  autoplayEligible: boolean
  playing: boolean
  ended: boolean
  error: string | null
}

export interface PageMediaSnapshot {
  generation: number
  targets: PageMediaTargetSnapshot[]
  /** 至少有一个目标且全部目标已结束；没有目标时由调度器回退停留时间。 */
  allEnded: boolean
  /** play() 被浏览器策略阻止；等待用户手势或重试。 */
  blocked: boolean
  /** 同一页面多个旁白或旁白循环等运行期契约冲突；进入后不自动播放并交由宿主报错。 */
  contractError: string | null
}

export interface PageMediaEvent {
  type: PageMediaEventType
  generation: number
  targetId?: string
  message?: string
  targetIds?: string[]
}

export interface PageMediaPlayAttempt {
  targetId: string
  outcome: 'played' | 'blocked' | 'error'
  message?: string
}

export interface PageMediaPlayResult {
  attempts: PageMediaPlayAttempt[]
  blocked: boolean
  failed: boolean
}

export interface PageMediaSessionOptions {
  /** 当前放映页根节点；查询不跨越 iframe。 */
  root: ParentNode
  /** 页面/尝试 generation；旧会话 dispose 后的事件不再上报。 */
  generation: number
  /** 执行上下文是否允许自动媒体播放；false 时 play() 不触碰元素。 */
  allowPlayback?: boolean
  onEvent?: (event: PageMediaEvent) => void
  observeMutations?: boolean
}

export interface PageMediaSession {
  readonly generation: number
  getSnapshot(): PageMediaSnapshot
  /** 重新收集活动目标的动态增删，MutationObserver 也会自动调用。 */
  refresh(): void
  /** 播放当前页全部未结束参与目标；返回真实 Promise 结果。 */
  play(): Promise<PageMediaPlayResult>
  /** 只播放具备自动播放资格的旁白目标；内容音频保持手动。 */
  playAutoplay(): Promise<PageMediaPlayResult>
  /** 单页循环重播：已结束目标归零后重新播放全部目标。 */
  restart(): Promise<PageMediaPlayResult>
  /** 暂停当前页目标，返回实际暂停数量。 */
  pause(): number
  /** 记录本会话正在播放的目标并全部暂停。 */
  suspend(): number
  /** 只恢复本会话 suspend() 记录且仍在文档中的目标。 */
  resume(): number
  /** 设置会话级静音；新加入的媒体继承当前状态。 */
  setMuted(muted: boolean): void
  isMuted(): boolean
  isSuspended(): boolean
  dispose(): void
}

interface MediaState {
  element: HTMLMediaElement
  id: string
  purpose: PageMediaPurpose
  loop: boolean
  playing: boolean
  ended: boolean
  error: string | null
  /** 非循环媒体参与完成判定；循环背景只参与暂停、恢复与清理。 */
  participating: boolean
  /** 旁白具备自动播放资格；内容音频保持手动。 */
  autoplayEligible: boolean
  /** 会话静音前的元素 muted 值；解除会话静音时恢复。 */
  baseMuted: boolean
}

const MEDIA_SELECTOR = 'audio, video'
/** HTMLMediaElement.NETWORK_NO_SOURCE；失败后再次 play() 会直接拒绝，必须先 load() 重新选源。 */
const NETWORK_NO_SOURCE = 3
const MEDIA_PURPOSE_ATTRIBUTE = 'data-runtime-media-purpose'
const NARRATION_CONFLICT_MESSAGE = '同一页面最多只能有一个页面旁白目标，已停止自动播放。'
const NARRATION_LOOP_MESSAGE = '页面旁白不允许循环播放。'

/**
 * 创建单个活动页面的媒体会话。
 * 会话只监听实际媒体元素，不依赖 ended 冒泡；同一元素替换 src 时通过 loadstart/emptied 重置完成态。
 */
export function createPageMediaSession(options: PageMediaSessionOptions): PageMediaSession {
  const { root, generation, onEvent } = options
  const allowPlayback = options.allowPlayback ?? true
  const media = new Map<string, MediaState>()
  const ids = new WeakMap<HTMLMediaElement, string>()
  const listeners = new Map<HTMLMediaElement, Record<string, EventListener>>()
  let sequence = 0
  let disposed = false
  let blocked = false
  let suspended = false
  let muted = false
  let contractError: string | null = null
  let recorded: HTMLMediaElement[] = []
  let observer: MutationObserver | null = null

  function emit(event: Omit<PageMediaEvent, 'generation'>): void {
    if (disposed) return
    onEvent?.({ ...event, generation })
  }

  /** 从媒体元素或页面祖先读取用途；未声明按 content 兼容旧页面。 */
  function resolvePurpose(element: Element): PageMediaPurpose {
    let current: Element | null = element
    while (current) {
      const value = current.getAttribute?.(MEDIA_PURPOSE_ATTRIBUTE)
      if (value === 'narration') return 'narration'
      if (value === 'content') return 'content'
      if (current === root) break
      current = current.parentElement
    }
    return 'content'
  }

  /** 计算单目标的参与完成、自动播放与契约状态。 */
  function resolveMediaState(element: HTMLMediaElement): { purpose: PageMediaPurpose; loop: boolean; participating: boolean; autoplayEligible: boolean } {
    const purpose = resolvePurpose(element)
    const loop = Boolean(element.loop)
    return {
      purpose,
      loop,
      // 循环媒体不参与完成；旁白循环属于契约错误，同样不能参与。
      participating: !loop,
      autoplayEligible: purpose === 'narration' && !loop,
    }
  }

  /** 重算旁白数量与契约错误，返回有界文案并只在变化时上报。 */
  function refreshContractError(): void {
    const narrationStates = [...media.values()].filter(state => state.purpose === 'narration')
    const invalidLoop = narrationStates.some(state => state.loop)
    let nextError: string | null = null
    if (invalidLoop) nextError = NARRATION_LOOP_MESSAGE
    else if (narrationStates.length > 1) nextError = NARRATION_CONFLICT_MESSAGE

    if (nextError === contractError) return
    contractError = nextError
    // 冲突时所有旁白都不参与完成与自动播放，避免同时说话或无限等待。
    const conflicted = nextError !== null
    for (const state of media.values()) {
      if (state.purpose !== 'narration') continue
      state.participating = conflicted ? false : !state.loop
      state.autoplayEligible = !conflicted && !state.loop
      if (conflicted) state.ended = false
    }
    if (nextError) {
      emit({ type: 'contract-error', message: nextError })
    }
  }

  function targetId(element: HTMLMediaElement): string {
    const existing = ids.get(element)
    if (existing) return existing
    const next = `media-${++sequence}`
    ids.set(element, next)
    return next
  }

  function snapshot(): PageMediaSnapshot {
    const states = [...media.values()].filter(state => state.participating)
    return {
      generation,
      targets: states.map(state => ({
        id: state.id,
        purpose: state.purpose,
        loop: state.loop,
        participating: state.participating,
        autoplayEligible: state.autoplayEligible,
        playing: state.playing,
        ended: state.ended,
        error: state.error,
      })),
      allEnded: states.length > 0 && states.every(state => state.ended),
      blocked,
      contractError,
    }
  }

  function bind(state: MediaState): void {
    const element = state.element
    if (listeners.has(element)) return
    const handler = (event: Event): void => {
      if (disposed) return
      switch (event.type) {
        case 'play':
        case 'playing':
          state.playing = true
          if (event.type === 'playing') state.ended = false
          emit({ type: 'play', targetId: state.id })
          break
        case 'pause':
          state.playing = false
          emit({ type: 'pause', targetId: state.id })
          break
        case 'ended':
          state.playing = false
          if (!state.participating) break
          state.ended = true
          emit({ type: 'ended', targetId: state.id })
          break
        case 'error':
          state.playing = false
          state.error = mediaErrorMessage(element)
          emit({ type: 'error', targetId: state.id, message: state.error })
          break
        case 'loadstart':
        case 'emptied':
          state.playing = false
          state.ended = false
          state.error = null
          if (state.participating) emit({ type: 'reset', targetId: state.id })
          break
      }
    }
    const entries: Record<string, EventListener> = {}
    for (const type of ['play', 'playing', 'pause', 'ended', 'error', 'loadstart', 'emptied']) {
      const bound = handler as EventListener
      entries[type] = bound
      element.addEventListener(type, bound)
    }
    listeners.set(element, entries)
  }

  function unbind(element: HTMLMediaElement): void {
    const entries = listeners.get(element)
    if (!entries) return
    for (const [type, handler] of Object.entries(entries)) {
      element.removeEventListener(type, handler)
    }
    listeners.delete(element)
  }

  function refresh(): void {
    if (disposed) return
    const found = new Set([...root.querySelectorAll<HTMLMediaElement>(MEDIA_SELECTOR)])
    let changed = false

    for (const [id, state] of media) {
      if (!found.has(state.element)) {
        unbind(state.element)
        if (!state.element.paused) state.element.pause()
        media.delete(id)
        changed = true
        continue
      }
      const resolved = resolveMediaState(state.element)
      if (
        state.purpose !== resolved.purpose
        || state.loop !== resolved.loop
        || state.participating !== resolved.participating
        || state.autoplayEligible !== resolved.autoplayEligible
      ) {
        state.purpose = resolved.purpose
        state.loop = resolved.loop
        state.participating = resolved.participating
        state.autoplayEligible = resolved.autoplayEligible
        if (!state.participating) state.ended = false
        changed = true
      }
    }

    for (const element of found) {
      if ([...media.values()].some(state => state.element === element)) continue
      const resolved = resolveMediaState(element)
      const state: MediaState = {
        element,
        id: targetId(element),
        purpose: resolved.purpose,
        loop: resolved.loop,
        playing: !element.paused,
        ended: element.ended,
        error: null,
        participating: resolved.participating,
        autoplayEligible: resolved.autoplayEligible,
        baseMuted: element.muted,
      }
      // 会话静音是覆盖层；新加入媒体继承静音，但不丢弃页面自身声明的 muted。
      if (muted) element.muted = true
      media.set(state.id, state)
      bind(state)
      changed = true
    }

    refreshContractError()
    if (changed) {
      emit({
        type: 'targets',
        targetIds: [...media.values()].filter(state => state.participating).map(state => state.id),
      })
    }
  }

  function pauseTargets(): number {
    refresh()
    let paused = 0
    for (const state of media.values()) {
      if (!state.element.paused) {
        state.element.pause()
        state.playing = false
        paused += 1
      }
    }
    return paused
  }

  function suspend(): number {
    refresh()
    if (suspended) return recorded.length
    recorded = [...media.values()]
      .map(state => state.element)
      .filter(element => !element.paused && !element.ended)
    for (const element of recorded) element.pause()
    suspended = true
    return recorded.length
  }

  function resume(): number {
    if (!suspended) return 0
    const elements = recorded
    recorded = []
    suspended = false
    let resumed = 0
    for (const element of elements) {
      if (!element.isConnected || element.ended) continue
      resumed += 1
      try {
        void Promise.resolve(element.play()).catch(() => {})
      } catch {
        // 恢复被同步拒绝时等待用户手动继续。
      }
    }
    return resumed
  }

  async function playStates(states: MediaState[]): Promise<PageMediaPlayResult> {
    blocked = false
    const attempts: PageMediaPlayAttempt[] = []
    const results = await Promise.allSettled(
      states.map(async state => {
        state.error = null
        try {
          // 失败的媒体元素保留错误且无法直接重播；先重新选源，服务恢复后重试才能成功。
          if (state.element.error || state.element.networkState === NETWORK_NO_SOURCE) {
            state.element.load()
          }
          await state.element.play()
          if (disposed) {
            // 会话在 play() Promise 返回前已销毁：立即停播，避免旧 generation 幽灵声音。
            state.element.pause()
            return { state, outcome: 'error' as const, message: '页面媒体会话已结束。' }
          }
          state.playing = true
          return { state, outcome: 'played' as const }
        } catch (error) {
          if (isNotAllowedError(error)) {
            blocked = true
            return { state, outcome: 'blocked' as const, message: '浏览器阻止了自动播放，请点击页面继续。' }
          }
          const message = error instanceof Error ? error.message : '媒体播放失败。'
          state.error = message
          emit({ type: 'error', targetId: state.id, message })
          return { state, outcome: 'error' as const, message }
        }
      }),
    )
    for (const result of results) {
      if (result.status !== 'fulfilled') continue
      const attempt: PageMediaPlayAttempt = {
        targetId: result.value.state.id,
        outcome: result.value.outcome,
      }
      if ('message' in result.value && result.value.message) attempt.message = result.value.message
      attempts.push(attempt)
    }
    if (blocked) emit({ type: 'blocked' })
    return {
      attempts,
      blocked,
      failed: attempts.some(attempt => attempt.outcome === 'error'),
    }
  }

  async function play(): Promise<PageMediaPlayResult> {
    if (disposed || !allowPlayback) {
      return { attempts: [], blocked: false, failed: false }
    }
    refresh()
    return playStates([...media.values()].filter(state => state.participating && !state.ended))
  }

  async function playAutoplay(): Promise<PageMediaPlayResult> {
    if (disposed || !allowPlayback || contractError) {
      return { attempts: [], blocked: false, failed: false }
    }
    refresh()
    return playStates(
      [...media.values()].filter(state => state.participating && state.autoplayEligible && !state.ended),
    )
  }

  async function restart(): Promise<PageMediaPlayResult> {
    for (const state of media.values()) {
      if (!state.participating) continue
      const wasEnded = state.ended || state.element.ended
      state.ended = false
      state.error = null
      if (wasEnded) {
        try {
          state.element.currentTime = 0
        } catch {
          // 元数据尚未就绪时无法归零，保留 play() 的真实结果。
        }
      }
    }
    return play()
  }

  function dispose(): void {
    if (disposed) return
    disposed = true
    observer?.disconnect()
    observer = null
    for (const state of media.values()) {
      unbind(state.element)
      if (!state.element.paused) state.element.pause()
      try {
        // 离页释放时归零，返回同一页面实例时不继承旧播放位置。
        state.element.currentTime = 0
      } catch {
        // 元数据未就绪的元素可能拒绝写入 currentTime；不影响释放。
      }
    }
    media.clear()
    recorded = []
    suspended = false
    blocked = false
    contractError = null
  }

  /** 设置会话级静音；只覆盖元素 muted，解除时恢复页面自身声明。 */
  function setMuted(nextMuted: boolean): void {
    if (muted === nextMuted) return
    muted = nextMuted
    for (const state of media.values()) {
      if (nextMuted) {
        state.baseMuted = state.element.muted
        state.element.muted = true
      } else {
        state.element.muted = state.baseMuted
      }
    }
  }

  refresh()
  if (options.observeMutations !== false && typeof MutationObserver !== 'undefined') {
    observer = new MutationObserver(() => refresh())
    observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['loop', MEDIA_PURPOSE_ATTRIBUTE],
    })
  }

  return {
    generation,
    getSnapshot: snapshot,
    refresh,
    play,
    playAutoplay,
    restart,
    pause: pauseTargets,
    suspend,
    resume,
    setMuted,
    isMuted: () => muted,
    isSuspended: () => suspended,
    dispose,
  }
}

/** 把媒体错误转换为可读文本；没有 MediaError 时使用兜底文案。 */
function mediaErrorMessage(element: HTMLMediaElement): string {
  const code = element.error?.code
  if (code === 1) return '媒体加载被中止。'
  if (code === 2) return '媒体网络错误。'
  if (code === 3) return '媒体解码失败。'
  if (code === 4) return '媒体格式不受支持或资源不可用。'
  return '媒体播放失败。'
}

/** 区分浏览器自动播放策略拒绝与其他媒体错误。 */
function isNotAllowedError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === 'NotAllowedError'
    : Boolean(error && typeof error === 'object' && (error as { name?: unknown }).name === 'NotAllowedError')
}
