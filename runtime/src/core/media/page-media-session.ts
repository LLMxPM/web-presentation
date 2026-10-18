/**
 * 文件功能：按活动放映页收集原生音视频，维护每页 generation 内的播放状态、完成集合与清理。
 *
 * 只处理当前页根节点内的 audio/video；循环媒体不参与完成判定，第三方 iframe 不跨文档。
 * 播放状态来自元素事件与 play() Promise，不根据 autoplay 属性推断成功。
 */

export type PageMediaEventType = 'targets' | 'play' | 'pause' | 'ended' | 'error' | 'blocked' | 'reset'

export interface PageMediaTargetSnapshot {
  id: string
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
  /** 播放当前页全部未结束目标；返回真实 Promise 结果。 */
  play(): Promise<PageMediaPlayResult>
  /** 单页循环重播：已结束目标归零后重新播放全部目标。 */
  restart(): Promise<PageMediaPlayResult>
  /** 暂停当前页目标，返回实际暂停数量。 */
  pause(): number
  /** 记录本会话正在播放的目标并全部暂停。 */
  suspend(): number
  /** 只恢复本会话 suspend() 记录且仍在文档中的目标。 */
  resume(): number
  isSuspended(): boolean
  dispose(): void
}

interface MediaState {
  element: HTMLMediaElement
  id: string
  playing: boolean
  ended: boolean
  error: string | null
  /** 非循环媒体参与完成判定；循环背景只参与暂停、恢复与清理。 */
  participating: boolean
}

const MEDIA_SELECTOR = 'audio, video'
/** HTMLMediaElement.NETWORK_NO_SOURCE；失败后再次 play() 会直接拒绝，必须先 load() 重新选源。 */
const NETWORK_NO_SOURCE = 3

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
  let recorded: HTMLMediaElement[] = []
  let observer: MutationObserver | null = null

  function emit(event: Omit<PageMediaEvent, 'generation'>): void {
    if (disposed) return
    onEvent?.({ ...event, generation })
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
        playing: state.playing,
        ended: state.ended,
        error: state.error,
      })),
      allEnded: states.length > 0 && states.every(state => state.ended),
      blocked,
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
      const participating = !state.element.loop
      if (state.participating !== participating) {
        state.participating = participating
        if (!participating) state.ended = false
        changed = true
      }
    }

    for (const element of found) {
      if ([...media.values()].some(state => state.element === element)) continue
      const state: MediaState = {
        element,
        id: targetId(element),
        playing: !element.paused,
        ended: element.ended,
        error: null,
        participating: !element.loop,
      }
      media.set(state.id, state)
      bind(state)
      changed = true
    }

    if (changed) {
      emit({
        type: 'targets',
        targetIds: [...media.values()].filter(state => state.participating).map(state => state.id),
      })
    }
  }

  function pauseTargets(): number {
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

  async function play(): Promise<PageMediaPlayResult> {
    if (disposed || !allowPlayback) {
      return { attempts: [], blocked: false, failed: false }
    }
    refresh()
    blocked = false
    const attempts: PageMediaPlayAttempt[] = []
    const pending = [...media.values()].filter(state => state.participating && !state.ended)
    const results = await Promise.allSettled(
      pending.map(async state => {
        state.error = null
        try {
          // 失败的媒体元素保留错误且无法直接重播；先重新选源，服务恢复后重试才能成功。
          if (state.element.error || state.element.networkState === NETWORK_NO_SOURCE) {
            state.element.load()
          }
          await state.element.play()
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
    }
    media.clear()
    recorded = []
    suspended = false
    blocked = false
  }

  refresh()
  if (options.observeMutations !== false && typeof MutationObserver !== 'undefined') {
    observer = new MutationObserver(() => refresh())
    observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['loop'],
    })
  }

  return {
    generation,
    getSnapshot: snapshot,
    refresh,
    play,
    restart,
    pause: pauseTargets,
    suspend,
    resume,
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
