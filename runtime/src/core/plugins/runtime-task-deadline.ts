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
 * 租约失守等外部中止：调用方应停止投入更多计算，不得当作超时重试同一 attempt。
 */
export class RuntimeTaskAbortedError extends Error {
  statusCode = 409
  code = 'RUNTIME_BUILD_LEASE_LOST'

  constructor(message: string) {
    super(message)
    this.name = 'RuntimeTaskAbortedError'
    this.code = 'RUNTIME_BUILD_LEASE_LOST'
  }
}

/**
 * 在任务实际取得调度槽位后建立 deadline；超时时中止所有接收 signal 的网络操作。
 * @param kind 诊断或正式构建
 * @param timeoutMs 本次任务允许的总执行时长
 * @param execute 任务实现；应在不可中断的本地慢操作前后调用 throwIfExpired
 * @param externalAbort 可选外部中止信号（如租约失守）；触发后与超时同样中断任务
 */
export async function runWithRuntimeTaskDeadline<T>(
  kind: RuntimeTaskDeadlineKind,
  timeoutMs: number,
  execute: (deadline: RuntimeTaskDeadline) => Promise<T>,
  externalAbort?: AbortSignal,
): Promise<T> {
  const normalizedTimeoutMs = normalizeTimeoutMs(timeoutMs)
  const controller = new AbortController()
  const deadlineAt = Date.now() + normalizedTimeoutMs
  const timeoutError = new RuntimeTaskDeadlineError(kind, normalizedTimeoutMs)
  let abortError: Error = timeoutError
  const abortWith = (error: Error) => {
    abortError = error
    if (!controller.signal.aborted) {
      controller.abort(error)
    }
  }
  const timeoutHandle = setTimeout(() => abortWith(timeoutError), normalizedTimeoutMs)
  const onExternalAbort = () => {
    const reason = externalAbort?.reason
    abortWith(
      reason instanceof Error && reason.name === 'RuntimeTaskAbortedError'
        ? reason
        : new RuntimeTaskAbortedError(String(reason || '任务被外部中止。')),
    )
  }
  if (externalAbort) {
    if (externalAbort.aborted) {
      onExternalAbort()
    } else {
      externalAbort.addEventListener('abort', onExternalAbort, { once: true })
    }
  }
  const deadline: RuntimeTaskDeadline = {
    signal: controller.signal,
    remainingMs: () => {
      const remaining = deadlineAt - Date.now()
      if (remaining <= 0 || controller.signal.aborted) {
        throw abortError
      }
      return Math.max(1, Math.ceil(remaining))
    },
    throwIfExpired: () => {
      if (controller.signal.aborted || Date.now() >= deadlineAt) {
        throw abortError
      }
    },
  }

  try {
    const result = await execute(deadline)
    deadline.throwIfExpired()
    return result
  } catch (error) {
    if (controller.signal.aborted) {
      throw abortError
    }
    throw error
  } finally {
    clearTimeout(timeoutHandle)
    externalAbort?.removeEventListener('abort', onExternalAbort)
  }
}

/**
 * 将异常配置收敛为最小正整数，防止 setTimeout 的非法输入破坏任务生命周期。
 */
function normalizeTimeoutMs(value: number): number {
  const normalized = Math.floor(Number(value))
  return Number.isFinite(normalized) && normalized > 0 ? normalized : 1
}
