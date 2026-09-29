/**
 * 文件用途：为 Runtime 诊断、正式构建与轻量内部工具提供有界、按类别隔离容量且可关闭的进程内任务调度。
 * 关键约束：diagnostics/project/light 各自持有独立并发与队列，长编译不得占用轻量工具或另一类别的执行槽。
 */

import {
  getRuntimeRole,
  resolveRuntimeKindBudget,
  type RuntimeTaskBudget,
  type RuntimeViteTaskKind,
} from './runtime-role'

export type { RuntimeTaskBudget, RuntimeViteTaskKind }

export interface RuntimeViteTaskKindBudgetOptions {
  concurrency?: number
  maxQueueSize?: number
  queueWaitTimeoutMs?: number
}

export interface RuntimeViteTaskSchedulerOptions {
  /** 角色：决定 RUNTIME_{ROLE}_VITE_TASK_* 覆盖优先级；缺省读环境变量 RUNTIME_ROLE。 */
  role?: ReturnType<typeof getRuntimeRole>
  /** diagnostics/project 两类未单独配置时的共享默认预算。 */
  concurrency?: number
  maxQueueSize?: number
  queueWaitTimeoutMs?: number
  /** 兼容字段：类别隔离后不再参与跨类调度，仅保留在快照中供观测。 */
  diagnosticsWeight?: number
  /** 按类别覆盖执行预算。 */
  kinds?: Partial<Record<RuntimeViteTaskKind, RuntimeViteTaskKindBudgetOptions>>
}

interface QueuedTask<T> {
  id: number
  run: () => Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
  reject: (reason?: unknown) => void
  timeoutHandle: ReturnType<typeof setTimeout>
  enqueuedAt: number
}

interface KindLane {
  budget: RuntimeTaskBudget
  queue: Array<QueuedTask<unknown>>
  active: number
}

export interface RuntimeViteTaskKindSnapshot extends RuntimeTaskBudget {
  active: number
  queued: number
  /** 当前类别最久排队任务的等待毫秒数；无排队时为 0 */
  oldestQueuedAgeMs: number
}

export interface RuntimeViteTaskSchedulerSnapshot {
  /** 所有类别合计的执行中任务数 */
  active: number
  queuedPreview: number
  queuedDiagnostics: number
  queuedProject: number
  queuedLight: number
  /** 兼容字段：diagnostics 类别预算，诊断工作区池据此定容 */
  concurrency: number
  maxQueueSize: number
  queueWaitTimeoutMs: number
  /** 当前最久排队任务的等待毫秒数；无排队时为 0 */
  oldestQueuedAgeMs: number
  diagnosticsWeight: number
  closed: boolean
  kinds: Record<RuntimeViteTaskKind, RuntimeViteTaskKindSnapshot>
}

const DEFAULT_CONCURRENCY = 1
const DEFAULT_MAX_QUEUE_SIZE = 16
const DEFAULT_QUEUE_WAIT_TIMEOUT_MS = 30000
const DEFAULT_DIAGNOSTICS_WEIGHT = 3

/**
 * Runtime Vite 任务排队失败。
 */
export class RuntimeViteTaskSchedulerError extends Error {
  statusCode: number
  code: 'RUNTIME_VITE_QUEUE_FULL' | 'RUNTIME_VITE_QUEUE_TIMEOUT' | 'RUNTIME_VITE_SCHEDULER_CLOSED'

  constructor(
    statusCode: number,
    code: RuntimeViteTaskSchedulerError['code'],
    message: string,
  ) {
    super(message)
    this.name = 'RuntimeViteTaskSchedulerError'
    this.statusCode = statusCode
    this.code = code
  }
}

/**
 * 按任务类别隔离容量的进程内调度器。
 * 关键约束：只限制尚未开始的排队任务；正在执行的任务关闭时会自然收尾。
 */
export class RuntimeViteTaskScheduler {
  private readonly lanes: Record<RuntimeViteTaskKind, KindLane>
  private readonly diagnosticsWeight: number
  private nextTaskId = 1
  private closed = false

  constructor(options: RuntimeViteTaskSchedulerOptions = {}) {
    const role = options.role ?? getRuntimeRole()
    const sharedProvided = {
      concurrency: options.concurrency !== undefined,
      maxQueueSize: options.maxQueueSize !== undefined,
      queueWaitTimeoutMs: options.queueWaitTimeoutMs !== undefined,
    }
    const sharedDefaults: RuntimeTaskBudget = {
      concurrency: normalizePositiveInteger(
        options.concurrency,
        process.env.RUNTIME_VITE_TASK_CONCURRENCY,
        DEFAULT_CONCURRENCY,
      ),
      maxQueueSize: normalizePositiveInteger(
        options.maxQueueSize,
        process.env.RUNTIME_VITE_TASK_QUEUE_SIZE,
        DEFAULT_MAX_QUEUE_SIZE,
      ),
      queueWaitTimeoutMs: normalizePositiveInteger(
        options.queueWaitTimeoutMs,
        process.env.RUNTIME_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS,
        DEFAULT_QUEUE_WAIT_TIMEOUT_MS,
      ),
    }
    this.diagnosticsWeight = normalizePositiveInteger(
      options.diagnosticsWeight,
      process.env.RUNTIME_VITE_DIAGNOSTICS_WEIGHT,
      DEFAULT_DIAGNOSTICS_WEIGHT,
    )
    this.lanes = {
      // preview 独立容量：HTML/模块转换不得被长编译诊断或构建挤占。
      preview: createLane('preview', options.kinds?.preview, sharedDefaults, { concurrency: false, maxQueueSize: false, queueWaitTimeoutMs: false }, role),
      diagnostics: createLane('diagnostics', options.kinds?.diagnostics, sharedDefaults, sharedProvided, role),
      project: createLane('project', options.kinds?.project, sharedDefaults, sharedProvided, role),
      // 轻量工具独立容量：不继承诊断/构建的共享默认预算，避免被长编译配置拖大或挤占。
      light: createLane('light', options.kinds?.light, sharedDefaults, { concurrency: false, maxQueueSize: false, queueWaitTimeoutMs: false }, role),
    }
  }

  /**
   * 提交一个任务，并在任务真正执行完成后返回结果。
   * @param kind 任务类别；各类别使用独立并发槽与排队预算，互不挤占
   * @param run 不得同步阻塞事件循环的异步任务
   */
  schedule<T>(kind: RuntimeViteTaskKind, run: () => Promise<T>): Promise<T> {
    if (this.closed) {
      return Promise.reject(new RuntimeViteTaskSchedulerError(
        503,
        'RUNTIME_VITE_SCHEDULER_CLOSED',
        'Runtime Vite 任务调度器已关闭。',
      ))
    }
    const lane = this.lanes[kind]
    if (lane.queue.length >= lane.budget.maxQueueSize) {
      return Promise.reject(new RuntimeViteTaskSchedulerError(
        429,
        'RUNTIME_VITE_QUEUE_FULL',
        `Runtime Vite ${kind} 等待队列已满（上限 ${lane.budget.maxQueueSize}）。`,
      ))
    }

    return new Promise<T>((resolve, reject) => {
      const id = this.nextTaskId++
      const task: QueuedTask<T> = {
        id,
        run,
        resolve,
        reject,
        timeoutHandle: setTimeout(
          () => this.expireTask(kind, id),
          lane.budget.queueWaitTimeoutMs,
        ),
        enqueuedAt: Date.now(),
      }
      lane.queue.push(task as QueuedTask<unknown>)
      this.dispatch(kind)
    })
  }

  /**
   * 拒绝尚未开始的任务，并阻止继续提交。
   */
  close(): void {
    if (this.closed) {
      return
    }
    this.closed = true
    const error = new RuntimeViteTaskSchedulerError(
      503,
      'RUNTIME_VITE_SCHEDULER_CLOSED',
      'Runtime Vite 任务调度器已关闭。',
    )
    for (const lane of Object.values(this.lanes)) {
      for (const task of lane.queue.splice(0)) {
        clearTimeout(task.timeoutHandle)
        task.reject(error)
      }
    }
  }

  /**
   * 返回当前运行态，供健康检查和结构化日志使用。
   * 含各类别排队年龄与容量上限，便于判断压力来自 Check、Build 还是轻量工具。
   */
  snapshot(): RuntimeViteTaskSchedulerSnapshot {
    const kinds = {} as Record<RuntimeViteTaskKind, RuntimeViteTaskKindSnapshot>
    for (const kind of Object.keys(this.lanes) as RuntimeViteTaskKind[]) {
      const lane = this.lanes[kind]
      kinds[kind] = {
        ...lane.budget,
        active: lane.active,
        queued: lane.queue.length,
        oldestQueuedAgeMs: computeOldestQueuedAgeMs(lane.queue),
      }
    }
    return {
      active: kinds.preview.active + kinds.diagnostics.active + kinds.project.active + kinds.light.active,
      queuedPreview: kinds.preview.queued,
      queuedDiagnostics: kinds.diagnostics.queued,
      queuedProject: kinds.project.queued,
      queuedLight: kinds.light.queued,
      concurrency: kinds.diagnostics.concurrency,
      maxQueueSize: kinds.diagnostics.maxQueueSize,
      queueWaitTimeoutMs: kinds.diagnostics.queueWaitTimeoutMs,
      oldestQueuedAgeMs: Math.max(
        kinds.preview.oldestQueuedAgeMs,
        kinds.diagnostics.oldestQueuedAgeMs,
        kinds.project.oldestQueuedAgeMs,
        kinds.light.oldestQueuedAgeMs,
      ),
      diagnosticsWeight: this.diagnosticsWeight,
      closed: this.closed,
      kinds,
    }
  }

  /**
   * 填满该类别的可用执行槽；任务完成后继续驱动同类别队列。
   */
  private dispatch(kind: RuntimeViteTaskKind): void {
    const lane = this.lanes[kind]
    while (!this.closed && lane.active < lane.budget.concurrency) {
      const task = lane.queue.shift()
      if (!task) {
        return
      }
      clearTimeout(task.timeoutHandle)
      lane.active += 1
      void this.execute(kind, task)
    }
  }

  /**
   * 执行已取得的任务；槽位只在异步函数真实结束后释放。
   */
  private async execute(kind: RuntimeViteTaskKind, task: QueuedTask<unknown>): Promise<void> {
    const lane = this.lanes[kind]
    try {
      task.resolve(await task.run())
    } catch (error) {
      task.reject(error)
    } finally {
      lane.active -= 1
      this.dispatch(kind)
    }
  }

  /**
   * 仅移除仍处于等待态的超时任务，运行中的任务不受排队超时影响。
   */
  private expireTask(kind: RuntimeViteTaskKind, taskId: number): void {
    const lane = this.lanes[kind]
    const index = lane.queue.findIndex(task => task.id === taskId)
    if (index < 0) {
      return
    }
    const [task] = lane.queue.splice(index, 1)
    task.reject(new RuntimeViteTaskSchedulerError(
      429,
      'RUNTIME_VITE_QUEUE_TIMEOUT',
      `Runtime Vite ${kind} 任务排队超过 ${lane.budget.queueWaitTimeoutMs}ms。`,
    ))
  }
}

/**
 * 构建单个类别的调度通道；优先级：类别显式配置 → 构造参数共享默认 → 角色/类别环境变量。
 */
function createLane(
  kind: RuntimeViteTaskKind,
  overrides: RuntimeViteTaskKindBudgetOptions | undefined,
  sharedDefaults: RuntimeTaskBudget,
  sharedProvided: { concurrency: boolean; maxQueueSize: boolean; queueWaitTimeoutMs: boolean },
  role: NonNullable<RuntimeViteTaskSchedulerOptions['role']>,
): KindLane {
  const envBudget = resolveRuntimeKindBudget(kind, role)
  return {
    budget: {
      concurrency: firstPositive(
        overrides?.concurrency,
        sharedProvided.concurrency ? sharedDefaults.concurrency : undefined,
        envBudget.concurrency,
      ),
      maxQueueSize: firstPositive(
        overrides?.maxQueueSize,
        sharedProvided.maxQueueSize ? sharedDefaults.maxQueueSize : undefined,
        envBudget.maxQueueSize,
      ),
      queueWaitTimeoutMs: firstPositive(
        overrides?.queueWaitTimeoutMs,
        sharedProvided.queueWaitTimeoutMs ? sharedDefaults.queueWaitTimeoutMs : undefined,
        envBudget.queueWaitTimeoutMs,
      ),
    },
    queue: [],
    active: 0,
  }
}

/**
 * 依次返回第一个合法正整数；全部无效时返回最后一个兜底值。
 */
function firstPositive(...candidates: Array<number | undefined>): number {
  let last = 0
  for (const candidate of candidates) {
    if (Number.isInteger(candidate) && Number(candidate) > 0) {
      return Number(candidate)
    }
    if (candidate !== undefined) {
      last = Number(candidate)
    }
  }
  return last > 0 ? last : 1
}

/**
 * 计算指定队列中最久排队任务已等待的毫秒数。
 */
function computeOldestQueuedAgeMs(queue: Array<QueuedTask<unknown>>): number {
  const now = Date.now()
  let oldest = 0
  for (const task of queue) {
    oldest = Math.max(oldest, now - task.enqueuedAt)
  }
  return oldest
}

/**
 * 从显式配置、环境变量和默认值中解析正整数；均缺失时返回 fallback。
 */
function normalizePositiveInteger(
  explicit: number | undefined,
  rawEnv: string | undefined,
  fallback: number,
): number {
  const candidates = [explicit, Number(String(rawEnv || '').trim())]
  for (const candidate of candidates) {
    if (Number.isInteger(candidate) && Number(candidate) > 0) {
      return Number(candidate)
    }
  }
  return fallback
}
