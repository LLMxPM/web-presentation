/**
 * 文件用途：为 Runtime 诊断与正式构建提供有界、加权且可关闭的进程内任务调度。
 */

export type RuntimeViteTaskKind = 'diagnostics' | 'project'

export interface RuntimeViteTaskSchedulerOptions {
  concurrency?: number
  maxQueueSize?: number
  queueWaitTimeoutMs?: number
  diagnosticsWeight?: number
}

interface QueuedTask<T> {
  id: number
  kind: RuntimeViteTaskKind
  run: () => Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
  reject: (reason?: unknown) => void
  timeoutHandle: ReturnType<typeof setTimeout>
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
 * 在同一并发预算中调度交互诊断和正式构建。
 * 关键约束：只限制尚未开始的排队任务；正在执行的任务关闭时会自然收尾。
 */
export class RuntimeViteTaskScheduler {
  private readonly concurrency: number
  private readonly maxQueueSize: number
  private readonly queueWaitTimeoutMs: number
  private readonly diagnosticsWeight: number
  private readonly queues: Record<RuntimeViteTaskKind, Array<QueuedTask<unknown>>> = {
    diagnostics: [],
    project: [],
  }
  private activeCount = 0
  private diagnosticsStreak = 0
  private nextTaskId = 1
  private closed = false

  constructor(options: RuntimeViteTaskSchedulerOptions = {}) {
    this.concurrency = normalizePositiveInteger(
      options.concurrency,
      process.env.RUNTIME_VITE_TASK_CONCURRENCY,
      DEFAULT_CONCURRENCY,
    )
    this.maxQueueSize = normalizePositiveInteger(
      options.maxQueueSize,
      process.env.RUNTIME_VITE_TASK_QUEUE_SIZE,
      DEFAULT_MAX_QUEUE_SIZE,
    )
    this.queueWaitTimeoutMs = normalizePositiveInteger(
      options.queueWaitTimeoutMs,
      process.env.RUNTIME_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS,
      DEFAULT_QUEUE_WAIT_TIMEOUT_MS,
    )
    this.diagnosticsWeight = normalizePositiveInteger(
      options.diagnosticsWeight,
      process.env.RUNTIME_VITE_DIAGNOSTICS_WEIGHT,
      DEFAULT_DIAGNOSTICS_WEIGHT,
    )
  }

  /**
   * 提交一个任务，并在任务真正执行完成后返回结果。
   * @param kind 任务种类，用于实施诊断优先的加权公平调度
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
    if (this.queuedCount >= this.maxQueueSize) {
      return Promise.reject(new RuntimeViteTaskSchedulerError(
        429,
        'RUNTIME_VITE_QUEUE_FULL',
        `Runtime Vite 等待队列已满（上限 ${this.maxQueueSize}）。`,
      ))
    }

    return new Promise<T>((resolve, reject) => {
      const id = this.nextTaskId++
      const task: QueuedTask<T> = {
        id,
        kind,
        run,
        resolve,
        reject,
        timeoutHandle: setTimeout(() => this.expireTask(kind, id), this.queueWaitTimeoutMs),
      }
      this.queues[kind].push(task as QueuedTask<unknown>)
      this.dispatch()
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
    for (const queue of Object.values(this.queues)) {
      for (const task of queue.splice(0)) {
        clearTimeout(task.timeoutHandle)
        task.reject(error)
      }
    }
  }

  /**
   * 返回当前运行态，供健康检查和结构化日志使用。
   */
  snapshot(): { active: number; queuedDiagnostics: number; queuedProject: number; concurrency: number } {
    return {
      active: this.activeCount,
      queuedDiagnostics: this.queues.diagnostics.length,
      queuedProject: this.queues.project.length,
      concurrency: this.concurrency,
    }
  }

  private get queuedCount(): number {
    return this.queues.diagnostics.length + this.queues.project.length
  }

  /**
   * 填满可用执行槽；任务完成后继续驱动队列。
   */
  private dispatch(): void {
    while (!this.closed && this.activeCount < this.concurrency) {
      const task = this.takeNextTask()
      if (!task) {
        return
      }
      clearTimeout(task.timeoutHandle)
      this.activeCount += 1
      void this.execute(task)
    }
  }

  /**
   * 按诊断:构建权重取出下一个任务，确保正式构建不会永久饥饿。
   */
  private takeNextTask(): QueuedTask<unknown> | undefined {
    const hasDiagnostics = this.queues.diagnostics.length > 0
    const hasProject = this.queues.project.length > 0
    if (!hasDiagnostics && !hasProject) {
      return undefined
    }
    if (hasProject && (!hasDiagnostics || this.diagnosticsStreak >= this.diagnosticsWeight)) {
      this.diagnosticsStreak = 0
      return this.queues.project.shift()
    }
    this.diagnosticsStreak += 1
    return this.queues.diagnostics.shift()
  }

  /**
   * 执行已取得的任务；槽位只在异步函数真实结束后释放。
   */
  private async execute(task: QueuedTask<unknown>): Promise<void> {
    try {
      task.resolve(await task.run())
    } catch (error) {
      task.reject(error)
    } finally {
      this.activeCount -= 1
      this.dispatch()
    }
  }

  /**
   * 仅移除仍处于等待态的超时任务，运行中的任务不受排队超时影响。
   */
  private expireTask(kind: RuntimeViteTaskKind, taskId: number): void {
    const queue = this.queues[kind]
    const index = queue.findIndex(task => task.id === taskId)
    if (index < 0) {
      return
    }
    const [task] = queue.splice(index, 1)
    task.reject(new RuntimeViteTaskSchedulerError(
      429,
      'RUNTIME_VITE_QUEUE_TIMEOUT',
      `Runtime Vite 任务排队超过 ${this.queueWaitTimeoutMs}ms。`,
    ))
  }
}

/**
 * 从显式配置、环境变量和默认值中解析正整数。
 */
function normalizePositiveInteger(explicit: number | undefined, rawEnv: string | undefined, fallback: number): number {
  const candidates = [explicit, Number(String(rawEnv || '').trim())]
  for (const candidate of candidates) {
    if (Number.isInteger(candidate) && Number(candidate) > 0) {
      return Number(candidate)
    }
  }
  return fallback
}
