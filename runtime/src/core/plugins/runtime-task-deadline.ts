/**
 * 文件用途：为 Runtime 诊断与正式构建提供可传递的端到端 deadline 和 AbortSignal。
 */

export type RuntimeTaskDeadlineKind = 'diagnostics' | 'project'

export interface RuntimeTaskDeadline {
  signal: AbortSignal
  remainingMs: () => number
  throwIfExpired: () => void
}

/**
 * Runtime 任务超过其执行预算时返回的可重试基础设施错误。
 */
export class RuntimeTaskDeadlineError extends Error {
  statusCode = 504
  code: 'RUNTIME_DIAGNOSTICS_TASK_TIMEOUT' | 'RUNTIME_BUILD_TASK_TIMEOUT'

  constructor(kind: RuntimeTaskDeadlineKind, timeoutMs: number) {
    super(kind === 'diagnostics'
      ? `Runtime 单页诊断超过 ${timeoutMs}ms 执行时限。`
      : `Runtime 正式构建超过 ${timeoutMs}ms 执行时限。`)
    this.name = 'RuntimeTaskDeadlineError'
    this.code = kind === 'diagnostics'
      ? 'RUNTIME_DIAGNOSTICS_TASK_TIMEOUT'
      : 'RUNTIME_BUILD_TASK_TIMEOUT'
  }
}

/**
 * 在任务实际取得调度槽位后建立 deadline；超时时中止所有接收 signal 的网络操作。
 * @param kind 诊断或正式构建
 * @param timeoutMs 本次任务允许的总执行时长
 * @param execute 任务实现；应在不可中断的本地慢操作前后调用 throwIfExpired
 */
export async function runWithRuntimeTaskDeadline<T>(
  kind: RuntimeTaskDeadlineKind,
  timeoutMs: number,
  execute: (deadline: RuntimeTaskDeadline) => Promise<T>,
): Promise<T> {
  const normalizedTimeoutMs = normalizeTimeoutMs(timeoutMs)
  const controller = new AbortController()
  const deadlineAt = Date.now() + normalizedTimeoutMs
  const timeoutError = new RuntimeTaskDeadlineError(kind, normalizedTimeoutMs)
  const timeoutHandle = setTimeout(() => controller.abort(timeoutError), normalizedTimeoutMs)
  const deadline: RuntimeTaskDeadline = {
    signal: controller.signal,
    remainingMs: () => {
      const remaining = deadlineAt - Date.now()
      if (remaining <= 0 || controller.signal.aborted) {
        throw timeoutError
      }
      return Math.max(1, Math.ceil(remaining))
    },
    throwIfExpired: () => {
      if (controller.signal.aborted || Date.now() >= deadlineAt) {
        throw timeoutError
      }
    },
  }

  try {
    const result = await execute(deadline)
    deadline.throwIfExpired()
    return result
  } catch (error) {
    if (controller.signal.aborted) {
      throw timeoutError
    }
    throw error
  } finally {
    clearTimeout(timeoutHandle)
  }
}

/**
 * 将异常配置收敛为最小正整数，防止 setTimeout 的非法输入破坏任务生命周期。
 */
function normalizeTimeoutMs(value: number): number {
  const normalized = Math.floor(Number(value))
  return Number.isFinite(normalized) && normalized > 0 ? normalized : 1
}
