/** 文件功能：定义正向 Scene 会话与受管任务契约；不包含采样、全局计划或静态截图字段。 */
export type SceneTaskRole = 'blocking' | 'ambient'
export type ScenePhase = 'idle' | 'preparing' | 'ready' | 'running' | 'blocked' | 'completed' | 'failed' | 'stopped'
export type SceneAdvanceMode = 'manual' | 'timer' | 'scene_end'

export interface SceneIssue {
  code: string
  message: string
  taskId?: string
}

export interface SceneSnapshot {
  generation: number
  phase: ScenePhase
  hasBlocking: boolean
  blockedTaskIds: string[]
  issue: SceneIssue | null
}

export interface SceneTaskContext {
  generation: number
  signal: AbortSignal
  /** 登记离页清理；取消后才登记的清理立即执行，避免迟到 Promise 泄漏。 */
  onCleanup(cleanup: () => void): void
  /** 仅 blocking 任务的受阻会冻结后续调度；恢复传 null。 */
  setBlocked(reason: string | null): void
}

export interface SceneTask {
  id: string
  role: SceneTaskRole
  /** 默认有限；无限任务只能是 ambient，且不能作为依赖前驱。 */
  finite?: boolean
  startMs?: number
  afterTrack?: string
  /** 仅允许 afterTrack 的非负延时，以前驱实际完成时刻为基准。 */
  offsetMs?: number
  prepare?(context: SceneTaskContext): void | Promise<void>
  /** Promise 完成表示任务实际结束；回调返回 void 表示同步完成。 */
  run(context: SceneTaskContext): void | Promise<void>
  /** 内部冻结或 blocking 受阻时通知已启动任务；不是公开的暂停控制。 */
  setSuspended?(suspended: boolean): void
}

export interface SceneRegistration {
  generation: number
  signal: AbortSignal
  register(task: SceneTask): void
  onCleanup(cleanup: () => void): void
}

export interface PageSceneOptions {
  generation: number
  advanceMode: SceneAdvanceMode
  define(context: SceneRegistration): void | Promise<void>
  /** 整个注册与准备阶段共用期限，最多 25 秒。 */
  prepareTimeoutMs?: number
  /** 从 start 起的墙钟期限，含受阻等待；最多一小时。ambient 不受此完成期限约束。 */
  completionTimeoutMs?: number
  now?: () => number
  isCurrent?: () => boolean
}

export interface PageSceneSession {
  getSnapshot(): SceneSnapshot
  prepare(): Promise<SceneSnapshot>
  start(): Promise<SceneSnapshot>
  /** 完成、失败或停止只结算一次；completed 后 ambient 持续到 stop。 */
  finished: Promise<SceneSnapshot>
  stop(): void
  /** 只供宿主 freeze/恢复使用，不作为页面控制 API 暴露。 */
  setSuspended(suspended: boolean): void
  subscribe(listener: (snapshot: SceneSnapshot) => void): () => void
}

/** 有界错误；不得把任意任务对象、资源地址或栈直接塞进宿主状态。 */
export class SceneSessionError extends Error {
  readonly code: string
  readonly taskId?: string
  constructor(code: string, message: string, taskId?: string) {
    super(message.slice(0, 240))
    this.code = code.slice(0, 128)
    this.taskId = taskId?.slice(0, 128)
  }
}
