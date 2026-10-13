/** 文件用途：为导出等待提供可取消的期限控制，确保超时覆盖异步读取的整个生命周期。 */

/** 抛出统一取消错误，调用方据此阻止截图容错与下载。 */
export function throwIfExportAborted(signal?: AbortSignal | null): void {
  if (signal?.aborted) throw new Error('用户取消导出')
}

/**
 * 执行有界异步操作；子信号同时覆盖请求和响应正文，结束时清理监听与计时器。
 * 不支持取消的底层操作可以自然结束，但迟到结果不再交给调用方。
 */
export async function runWithExportDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  signal?: AbortSignal | null,
  timeoutMs = 15000,
): Promise<T> {
  throwIfExportAborted(signal)
  const controller = new AbortController()
  let rejectDeadline!: (error: Error) => void
  const deadline = new Promise<never>((_, reject) => { rejectDeadline = reject })
  const abort = () => {
    rejectDeadline(new Error('用户取消导出'))
    controller.abort()
  }
  signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => {
    rejectDeadline(new Error('导出操作超时'))
    controller.abort()
  }, timeoutMs)
  try {
    return await Promise.race([operation(controller.signal), deadline])
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
