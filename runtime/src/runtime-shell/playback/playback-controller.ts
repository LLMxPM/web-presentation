/**
 * 文件功能：与路由和 DOM 解耦的单窗口放映调度核心。
 * 负责播放状态迁移、单调时钟下的剩余时间、一次性计时句柄、页面 generation
 * 以及末页结束/循环；就绪、错误和页面切换由外部适配层上报。
 */
import type { PageAdvanceConfig } from '@/core/types/page-transition'

export type PlaybackState =
  | 'stopped'
  | 'preparing'
  | 'playing'
  | 'paused'
  | 'ended'
  | 'blocked'
  | 'error'

/** 参与自动序列的可见叶子页；隐藏页由构造器过滤。 */
export interface PlaybackPage {
  path: string
  advance: PageAdvanceConfig
  hidden?: boolean
}

/** 单调时钟与一次性计时注入点，测试使用虚拟时钟获得确定性断言。 */
export interface PlaybackClock {
  now(): number
  setTimeout(callback: () => void, delayMs: number): unknown
  clearTimeout(handle: unknown): void
}

export interface PlaybackSnapshot {
  state: PlaybackState
  path: string
  generation: number
  remainingMs: number
  delayMs: number | null
  index: number
  total: number
  loop: boolean
  message: string
}

export type PlaybackListener = (snapshot: PlaybackSnapshot) => void
export type PlaybackNavigate = (path: string) => void | Promise<void>

export interface PlaybackOptions {
  pages: readonly PlaybackPage[]
  loop?: boolean
  clock?: PlaybackClock
  navigate: PlaybackNavigate
  initialPath?: string
}

const defaultClock: PlaybackClock = {
  now: () => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: handle => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
}

const NAVIGATION_ERROR_MESSAGE = '页面切换失败，请重试或手动翻页。'
const READY_ERROR_MESSAGE = '页面加载或资源准备失败，请重试。'
const BLOCKED_MESSAGE = '播放被浏览器阻止，请手动开始。'

/**
 * 单窗口放映控制器。
 * 所有外部输入（页面切换、就绪、错误）均携带/核对 generation，旧回调只被丢弃；
 * 任意时刻最多持有一个推进计时句柄。
 */
export class PlaybackController {
  private readonly pages: PlaybackPage[]
  private readonly loop: boolean
  private readonly clock: PlaybackClock
  private readonly navigate: PlaybackNavigate
  private readonly listeners = new Set<PlaybackListener>()

  private state: PlaybackState = 'stopped'
  private path: string
  private generation = 0
  private pageReady = false
  private readyPath = ''
  private timer: unknown
  private deadline = 0
  private remaining = 0
  private message = ''
  private disposed = false

  constructor(options: PlaybackOptions) {
    this.clock = options.clock ?? defaultClock
    this.navigate = options.navigate
    this.loop = Boolean(options.loop)
    this.pages = dedupeVisiblePages(options.pages)
    this.path = options.initialPath ?? this.pages[0]?.path ?? ''
  }

  /** 订阅状态变化；返回取消订阅函数。 */
  subscribe(listener: PlaybackListener): () => void {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  /**
   * 当前快照。playing 且持有计时句柄时，剩余时间按单调时钟实时计算，
   * 不依赖定时器的触发精度。
   */
  getSnapshot(): PlaybackSnapshot {
    const page = this.currentPage()
    return {
      state: this.state,
      path: this.path,
      generation: this.generation,
      remainingMs: this.currentRemaining(),
      delayMs: page?.advance.mode === 'timer' ? page.advance.delayMs : null,
      index: this.indexOf(this.path),
      total: this.pages.length,
      loop: this.loop,
      message: this.message,
    }
  }

  /**
   * 开始放映。stopped/ended/blocked/error 可进入；preparing/playing/paused 重复调用无效。
   * 优先使用显式路径，其次当前页；当前页不在目录中时从第一个可见叶子页开始。
   */
  start(preferredPath?: string): boolean {
    if (this.disposed) return false
    if (this.state === 'preparing' || this.state === 'playing' || this.state === 'paused') return false
    const target = this.resolveStartPath(preferredPath)
    if (!target) return false
    if (target !== this.path) {
      this.path = target
      this.pageReady = false
      this.readyPath = ''
    }
    this.generation += 1
    this.message = ''
    this.remaining = this.pageDelay(this.currentPage())
    if (this.pageReady && this.readyPath === this.path) {
      // 停止/结束后当前页仍在画布中，重新开始只重置停留时钟。
      this.enterPlaying(this.remaining)
    } else {
      this.state = 'preparing'
      this.emit()
    }
    return true
  }

  /** 暂停等待或播放中的放映；保留当前页与剩余停留时间，重复调用无效。 */
  pause(): boolean {
    if (this.disposed) return false
    if (this.state !== 'preparing' && this.state !== 'playing') return false
    if (this.state === 'playing' && this.timer !== undefined) {
      this.remaining = this.currentRemaining()
      this.clearTimer()
    } else {
      this.remaining = this.pageDelay(this.currentPage())
    }
    this.state = 'paused'
    this.emit()
    return true
  }

  /**
   * 从暂停恢复：页面已就绪时按原剩余时间继续，否则回到 preparing 等待就绪信号。
   * 暂停期间发生手动跳页时，剩余时间已重置为新页完整停留周期。
   */
  resume(): boolean {
    if (this.disposed || this.state !== 'paused') return false
    if (!this.pageReady || this.readyPath !== this.path) {
      this.state = 'preparing'
      this.remaining = this.pageDelay(this.currentPage())
      this.emit()
      return true
    }
    this.enterPlaying(Math.max(0, this.remaining))
    return true
  }

  /** 停止放映并保留当前页；重复停止无效。 */
  stop(): boolean {
    if (this.disposed || this.state === 'stopped') return false
    this.clearTimer()
    this.generation += 1
    this.state = 'stopped'
    this.message = ''
    this.remaining = 0
    // 页面仍在画布中，保留 pageReady，重新开始时无需等待新的过渡信号。
    this.emit()
    return true
  }

  /** 错误/受阻后重试当前页，等待外部重新上报就绪。 */
  retry(): boolean {
    if (this.disposed || (this.state !== 'error' && this.state !== 'blocked')) return false
    this.clearTimer()
    this.generation += 1
    this.state = 'preparing'
    this.message = ''
    this.pageReady = false
    this.readyPath = ''
    this.remaining = this.pageDelay(this.currentPage())
    this.emit()
    return true
  }

  /** 外部适配层确认当前页已完成路由提交、DOM/资源就绪与过渡；旧 generation 被丢弃。 */
  reportReady(path: string, generation: number): boolean {
    if (this.disposed || path !== this.path || generation !== this.generation) return false
    if (this.pageReady) return false
    if (this.state !== 'preparing' && this.state !== 'paused') return false
    this.pageReady = true
    this.readyPath = path
    if (this.state === 'preparing') {
      this.enterPlaying(this.pageDelay(this.currentPage()))
    } else {
      this.emit()
    }
    return true
  }

  /** 页面加载或必要资源失败：清除计时并进入可见错误态，不无限等待就绪。 */
  reportError(path: string, generation: number, message = READY_ERROR_MESSAGE): boolean {
    return this.enterFailure('error', path, generation, message)
  }

  /** 播放被浏览器策略阻止：进入受阻态，由用户重试或手动翻页。 */
  reportBlocked(path: string, generation: number, message = BLOCKED_MESSAGE): boolean {
    return this.enterFailure('blocked', path, generation, message)
  }

  /**
   * 外部适配层观察到路由路径变化时调用（自动翻页、手动跳页、浏览器导航）。
   * 播放中回到 preparing，暂停中保持暂停；同路径的查询参数变化不打断停留计时。
   */
  notifyPageChange(path: string): boolean {
    if (this.disposed || !path || path === this.path) return false
    this.clearTimer()
    this.generation += 1
    this.path = path
    this.pageReady = false
    this.readyPath = ''
    this.message = ''
    const delay = this.pageDelay(this.currentPage())
    if (this.state === 'playing' || this.state === 'preparing') {
      this.state = 'preparing'
      this.remaining = delay
    } else if (this.state === 'paused') {
      this.remaining = delay
    } else if (this.state === 'error' || this.state === 'blocked') {
      this.state = 'stopped'
      this.remaining = 0
    } else {
      this.remaining = 0
    }
    this.emit()
    return true
  }

  /** 释放计时句柄与监听器；之后所有输入无效。 */
  dispose(): void {
    if (this.disposed) return
    this.clearTimer()
    this.disposed = true
    this.generation += 1
    this.state = 'stopped'
    this.pageReady = false
    this.readyPath = ''
    this.remaining = 0
    this.listeners.clear()
  }

  /** 计时到期：按末页/循环规则推进，或为单页循环开启完整的新周期。 */
  private handleTimer(token: number): void {
    if (this.disposed || token !== this.generation || this.state !== 'playing' || !this.pageReady) return
    this.timer = undefined
    const page = this.currentPage()
    if (!page || page.advance.mode !== 'timer') return
    const currentIndex = this.indexOf(this.path)
    if (currentIndex < 0) return
    const isLast = currentIndex === this.pages.length - 1

    if (isLast && !this.loop) {
      this.generation += 1
      this.state = 'ended'
      this.remaining = 0
      this.emit()
      return
    }
    if (isLast && this.pages.length === 1) {
      // 单页循环不产生路由切换，但每轮都必须有完整停留周期。
      this.generation += 1
      this.remaining = page.advance.delayMs
      this.armTimer(page.advance.delayMs)
      this.emit()
      return
    }

    const next = this.pages[isLast ? 0 : currentIndex + 1]
    const attempt = ++this.generation
    this.state = 'preparing'
    this.pageReady = false
    this.readyPath = ''
    this.remaining = this.pageDelay(next)
    this.emit()
    let result: void | Promise<void>
    try {
      result = this.navigate(next.path)
    } catch (error) {
      this.failNavigation(attempt, error)
      return
    }
    Promise.resolve(result).catch(error => this.failNavigation(attempt, error))
  }

  /** 自动翻页失败时只处理当前尝试，用户已跳页或被新状态覆盖的旧失败直接丢弃。 */
  private failNavigation(attempt: number, error: unknown): void {
    if (this.disposed || attempt !== this.generation) return
    console.error('[runtime-playback] 自动翻页失败', error)
    this.clearTimer()
    this.generation += 1
    this.state = 'error'
    this.message = NAVIGATION_ERROR_MESSAGE
    this.pageReady = false
    this.readyPath = ''
    this.remaining = 0
    this.emit()
  }

  private enterFailure(state: 'error' | 'blocked', path: string, generation: number, message: string): boolean {
    if (this.disposed || path !== this.path || generation !== this.generation) return false
    if (this.state !== 'preparing' && this.state !== 'playing' && this.state !== 'paused') return false
    this.clearTimer()
    this.generation += 1
    this.state = state
    this.message = message
    this.pageReady = false
    this.readyPath = ''
    this.remaining = 0
    this.emit()
    return true
  }

  /** 从就绪状态进入播放；手动页保持 playing 但不再创建推进计时。 */
  private enterPlaying(delayMs: number): void {
    this.state = 'playing'
    const page = this.currentPage()
    if (!page || page.advance.mode !== 'timer') {
      this.remaining = 0
      this.emit()
      return
    }
    this.remaining = delayMs
    this.armTimer(delayMs)
    this.emit()
  }

  /** 建立唯一推进句柄；覆盖前始终清理旧句柄。 */
  private armTimer(delayMs: number): void {
    this.clearTimer()
    const token = this.generation
    this.deadline = this.clock.now() + delayMs
    this.timer = this.clock.setTimeout(() => this.handleTimer(token), delayMs)
  }

  private clearTimer(): void {
    if (this.timer === undefined) return
    this.clock.clearTimeout(this.timer)
    this.timer = undefined
  }

  /** 播放中按单调时钟计算剩余毫秒，其余状态返回保存值。 */
  private currentRemaining(): number {
    if (this.state === 'playing' && this.timer !== undefined) {
      return Math.max(0, Math.round(this.deadline - this.clock.now()))
    }
    return this.remaining
  }

  private pageDelay(page: PlaybackPage | undefined): number {
    return page?.advance.mode === 'timer' ? page.advance.delayMs : 0
  }

  private currentPage(): PlaybackPage | undefined {
    const index = this.indexOf(this.path)
    return index >= 0 ? this.pages[index] : undefined
  }

  private indexOf(path: string): number {
    return this.pages.findIndex(page => page.path === path)
  }

  private resolveStartPath(preferredPath?: string): string | undefined {
    if (preferredPath && this.indexOf(preferredPath) >= 0) return preferredPath
    if (this.indexOf(this.path) >= 0) return this.path
    return this.pages[0]?.path
  }

  private emit(): void {
    if (this.disposed) return
    const snapshot = this.getSnapshot()
    for (const listener of [...this.listeners]) {
      try {
        listener(snapshot)
      } catch (error) {
        console.error('[runtime-playback] 状态监听失败', error)
      }
    }
  }
}

/** 过滤隐藏页并按路径去重，构造器保存的配置不再受外部数组修改影响。 */
function dedupeVisiblePages(pages: readonly PlaybackPage[]): PlaybackPage[] {
  const result: PlaybackPage[] = []
  const seen = new Set<string>()
  for (const page of pages) {
    if (page.hidden || seen.has(page.path)) continue
    seen.add(page.path)
    result.push({ path: page.path, advance: { ...page.advance } })
  }
  return result
}
