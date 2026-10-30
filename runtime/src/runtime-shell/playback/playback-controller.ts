/** 文件功能：观众窗口唯一 Deck 调度，复用页级 Scene 聚合，只维护自动翻页的一次性计时。 */
import { SceneSessionError, type PageSceneSession, type SceneIssue, type SceneSnapshot } from '@/core/scene/types'
import type { DeckClock, DeckOptions, DeckPage, DeckSnapshot, DeckState } from './deck-types'

const defaultClock: DeckClock = {
  now: () => performance.now(),
  setTimeout: (callback, delay) => setTimeout(callback, delay),
  clearTimeout: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
}

/** 原放映控制器就地收敛；不持有动画、媒体的帧时钟，也不提供 Scene 暂停或定位。 */
export class DeckPlaybackSession {
  private readonly pages: DeckPage[]
  private readonly clock: DeckClock
  private readonly listeners = new Set<(value: DeckSnapshot) => void>()
  private scene: PageSceneSession | null = null
  private unsubscribe: (() => void) | null = null
  private state: DeckState = 'stopped'
  private path: string
  private issue: SceneIssue | null = null
  private held = false
  private suspended = false
  private completed = false
  private disposed = false
  private request = 0
  private timer: unknown
  private deadline = 0
  private remaining = 0

  constructor(private readonly options: DeckOptions) {
    this.clock = options.clock ?? defaultClock
    const paths = new Set<string>()
    this.pages = options.pages.filter(page => {
      if (page.hidden || !page.path || paths.has(page.path)) return false
      paths.add(page.path); return true
    }).map(page => ({ ...page, advance: { ...page.advance } }))
    this.path = options.initialPath ?? this.pages[0]?.path ?? ''
  }

  /** 快照不公开内部实例，Scene generation 由唯一 slot 分配。 */
  getSnapshot(): DeckSnapshot {
    const index = this.pages.findIndex(page => page.path === this.path), page = this.pages[index]
    return { state: this.state, path: this.path, index, total: this.pages.length, loop: Boolean(this.options.loop),
      held: this.held, suspended: this.suspended, advanceMode: page?.advance.mode ?? 'manual',
      remainingMs: this.timer === undefined ? this.remaining : Math.max(0, this.deadline - this.clock.now()),
      waitingForScene: page?.advance.mode === 'scene_end' && !this.completed,
      scene: this.scene?.getSnapshot() ?? null, issue: this.issue ? { ...this.issue } : null }
  }

  /** 观察方异常不破坏执行和清理；返回取消订阅函数。 */
  subscribe(listener: (value: DeckSnapshot) => void): () => void {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  /** 显式开始；活跃页不重启，失败后的重试由 retry 表达。 */
  start(path = this.path): boolean {
    if (this.disposed || this.active()) return false
    const page = this.pages.find(entry => entry.path === path) ?? this.pages[0]
    if (!page) return false
    this.enter(page)
    return true
  }

  /** 手动导航沿用同一准备流程，目录边界不绕回；循环只控制自动推进。 */
  go(offset: -1 | 1): boolean {
    if (this.disposed || this.state === 'stopped') return false
    const target = this.pages[this.pages.findIndex(page => page.path === this.path) + offset]
    if (!target) return false
    this.enter(target); return true
  }

  /** 页内链接或路由导航使旧准备立即失效；自身导航提交不重复创建会话。 */
  visit(path: string): boolean {
    if (this.disposed || this.state === 'stopped' || path === this.path) return false
    const page = this.pages.find(entry => entry.path === path)
    if (!page) { this.stop(); return false }
    this.enter(page); return true
  }

  /** 保持当前页仅取消翻页计时，Scene 和媒体继续，不改变推进配置。 */
  hold(): boolean {
    if (this.disposed || this.held || !this.active()) return false
    this.held = true; this.clearTimer(); this.remaining = this.fullDelay(); this.emit(); return true
  }

  /** 释放后重算当前页完整停留，忽略 hold 期间已经过期的计时。 */
  release(): boolean {
    if (this.disposed || !this.held || !this.active()) return false
    this.held = false; this.schedule(this.fullDelay()); this.emit(); return true
  }

  /** 内部冻结暂停 Scene 和推进预算；恢复按剩余值重新计时，不补发过期翻页。 */
  setSuspended(value: boolean): void {
    if (this.disposed || this.suspended === value) return
    this.suspended = value
    if (value) {
      if (this.timer !== undefined) this.remaining = Math.max(0, this.deadline - this.clock.now())
      this.clearTimer()
    }
    this.scene?.setSuspended(value)
    if (!value) this.schedule(this.remaining)
    this.emit()
  }

  /** 只重试失败页；blocking 的本地播放许可恢复由资源适配器处理。 */
  retry(): boolean {
    if (this.disposed || this.state !== 'failed') return false
    const page = this.pages.find(entry => entry.path === this.path)
    if (!page) return false
    this.enter(page); return true
  }

  /** 退出立即停止所有页级任务与准备，不等媒体或 Promise 自行结束。 */
  stop(): boolean {
    if (this.disposed || this.state === 'stopped') return false
    const token = ++this.request
    this.clearPage()
    if (token !== this.request) return true
    this.state = 'stopped'; this.issue = null; this.remaining = 0; this.held = false
    this.emit(); return true
  }

  /** 宿主卸载后永远不能再次启动。 */
  dispose(): void {
    if (this.disposed) return
    this.disposed = true; this.request += 1; this.clearPage(); this.state = 'stopped'; this.remaining = 0; this.listeners.clear()
  }

  /** 一次进页复用 Stage 的导航/过渡/资源共享准备期限，旧清理重入不能覆盖新请求。 */
  private enter(page: DeckPage): void {
    const token = ++this.request
    this.clearPage()
    if (token !== this.request || this.disposed) return
    this.path = page.path; this.state = 'preparing'; this.issue = null; this.completed = false; this.remaining = 0
    try {
      if (!['manual', 'timer', 'scene_end'].includes(page.advance.mode)) throw new SceneSessionError('DECK_ADVANCE_UNSUPPORTED', '当前推进配置已不支持，请改为 manual、timer 或 scene_end。')
      if (!Number.isFinite(page.advance.delayMs) || page.advance.delayMs < 0 || page.advance.delayMs > 3600000
        || (page.advance.mode === 'timer' && page.advance.delayMs === 0)
        || (page.advance.completionDelayMs !== undefined && (!Number.isFinite(page.advance.completionDelayMs) || page.advance.completionDelayMs < 0 || page.advance.completionDelayMs > 3600000))) {
        throw new SceneSessionError('DECK_ADVANCE_INVALID', '页面停留必须是有限毫秒值，定时停留须为正数。')
      }
      const preparing = this.options.stage.prepare({ path: page.path, execution: 'presentation', advanceMode: page.advance.mode })
      this.scene = this.options.stage.getCurrent()
      const scene = this.scene
      if (!scene) throw new SceneSessionError('DECK_SCENE_MISSING', '当前执行策略不能创建放映会话。')
      this.unsubscribe = scene.subscribe(value => { if (token === this.request) this.onScene(value) })
      this.emit()
      void preparing.then(async ready => {
        if (token !== this.request || this.disposed || ready !== this.scene) return
        if (ready?.getSnapshot().phase !== 'ready') { this.onScene(scene.getSnapshot()); return }
        this.state = 'playing'; this.emit()
        if (token !== this.request || this.disposed) return
        scene.setSuspended(this.suspended)
        await scene.start()
        if (token !== this.request || this.disposed) return
        if (page.advance.mode === 'timer') this.schedule(page.advance.delayMs)
      }).catch(error => { if (token === this.request && !this.disposed) this.fail(error) })
    } catch (error) { this.fail(error) }
  }

  /** 聚合真实完成；timer 不因 blocking 受阻而等待，scene_end 只在完成后计时。 */
  private onScene(value: SceneSnapshot): void {
    if (value.phase === 'failed') { this.fail(value.issue); return }
    if (value.phase === 'stopped') { this.fail(new SceneSessionError('DECK_SCENE_STOPPED', '页面声明已经卸载，播放已停止。')); return }
    if (value.phase === 'blocked') this.state = 'blocked'
    else if (value.phase === 'running' || value.phase === 'completed') this.state = 'playing'
    if (value.phase === 'completed' && !this.completed) {
      this.completed = true
      if (this.getSnapshot().advanceMode === 'scene_end') this.schedule(this.fullDelay())
    }
    this.emit()
  }

  /** 一次性翻页计时；冻结、hold、准备或完成目标未满足时不持有句柄。 */
  private schedule(delay: number): void {
    this.clearTimer(); this.remaining = delay
    if (!['playing', 'blocked'].includes(this.state) || this.held || this.suspended) return
    const mode = this.getSnapshot().advanceMode
    if (mode === 'manual' || (mode === 'scene_end' && !this.completed)) return
    const token = this.request
    this.deadline = this.clock.now() + Math.max(1, delay)
    this.timer = this.clock.setTimeout(() => {
      this.timer = undefined
      if (token !== this.request || !this.active() || this.held || this.suspended) return
      if (this.clock.now() - this.deadline > 3000) { this.held = true; this.remaining = this.fullDelay(); this.emit(); return }
      const index = this.pages.findIndex(page => page.path === this.path)
      const next = this.pages[index + 1] ?? (this.options.loop ? this.pages[0] : undefined)
      if (next) this.enter(next)
      else {
        const ended = ++this.request
        this.clearPage()
        if (ended !== this.request) return
        this.state = 'ended'; this.remaining = 0; this.emit()
      }
    }, Math.max(1, delay))
  }

  /** release 和迟到守卫都使用完整当前页停留，不累计遗漏的翻页次数。 */
  private fullDelay(): number {
    const advance = this.pages.find(page => page.path === this.path)?.advance
    return advance?.mode === 'timer' ? advance.delayMs : advance?.mode === 'scene_end' && this.completed ? advance.completionDelayMs ?? 300 : 0
  }

  /** 先退订再取消，防止离页清理的 stopped 被误识别成当前页失败。 */
  private clearPage(): void { this.clearTimer(); this.unsubscribe?.(); this.unsubscribe = null; this.scene = null; this.options.stage.stop() }
  /** 统一撤销唯一计时句柄。 */
  private clearTimer(): void { if (this.timer !== undefined) this.clock.clearTimeout(this.timer); this.timer = undefined }
  /** 失败立即释放当前页，摘要有界且不会暴露任意异常堆栈。 */
  private fail(error: unknown): void {
    const known = error instanceof SceneSessionError ? error : error && typeof error === 'object' && 'code' in error ? error as SceneIssue : null
    const issue = { code: String(known?.code ?? 'DECK_PLAYBACK_FAILED').slice(0, 128), message: String(known?.message ?? '页面播放失败。').slice(0, 240) }
    const token = ++this.request
    this.clearPage()
    if (token !== this.request || this.disposed) return
    this.issue = issue; this.state = 'failed'; this.remaining = 0; this.emit()
  }
  /** 只有活跃状态允许保持/释放；ended 不再拥有页面资源。 */
  private active(): boolean { return ['preparing', 'playing', 'blocked'].includes(this.state) }
  /** 订阅回调可以重入停止或切页，不传播观察方错误。 */
  private emit(): void { for (const listener of this.listeners) { try { listener(this.getSnapshot()) } catch { /* 继续通知其他观察方。 */ } } }
}
