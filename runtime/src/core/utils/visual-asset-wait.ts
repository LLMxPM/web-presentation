/** 文件功能：为视觉资源准备提供可取消的延时、绘制帧和 Promise 等待，统一释放临时句柄。 */
export interface VisualAssetWaitScope {
  signal: AbortSignal
  check(): void
  wait<T>(promise: PromiseLike<T>): Promise<T>
  delay(ms: number): Promise<void>
  frame(): Promise<void>
  dispose(): void
}

/** 取消只撤销观察与等待，不回滚页面资源加载，也不把退出伪装为资源失败。 */
export function createVisualAssetWaitScope(parent?: AbortSignal): VisualAssetWaitScope {
  const controller = new AbortController()
  const { signal } = controller
  const abort = () => controller.abort()
  parent?.addEventListener('abort', abort, { once: true })
  if (parent?.aborted) abort()

  /** 所有入口都拒绝已经取消的等待，不暴露外部任意 abort reason。 */
  function check(): void {
    if (signal.aborted) throw new DOMException('视觉资源等待已取消。', 'AbortError')
  }

  /** 单次观察在完成或取消后撤销监听；不能取消的原 Promise 始终有拒绝处理器。 */
  function wait<T>(promise: PromiseLike<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const cancel = () => { cleanup(); reject(new DOMException('视觉资源等待已取消。', 'AbortError')) }
      const cleanup = () => signal.removeEventListener('abort', cancel)
      signal.addEventListener('abort', cancel, { once: true })
      Promise.resolve(promise).then(value => { cleanup(); resolve(value) }, error => { cleanup(); reject(error) })
      if (signal.aborted) cancel()
    })
  }

  /** 延时结束或取消都释放原句柄，避免快速翻页留下长超时计时。 */
  function delay(ms: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', cancel) }
      const cancel = () => { cleanup(); reject(new DOMException('视觉资源等待已取消。', 'AbortError')) }
      const timer = setTimeout(() => { cleanup(); resolve() }, Math.max(0, ms))
      signal.addEventListener('abort', cancel, { once: true })
      if (signal.aborted) cancel()
    })
  }

  /** 绘制帧等待支持立即撤销，后台停止不必等待浏览器再次分配 RAF。 */
  function frame(): Promise<void> {
    if (typeof requestAnimationFrame !== 'function') return delay(16)
    return new Promise<void>((resolve, reject) => {
      const cleanup = () => { cancelAnimationFrame(handle); signal.removeEventListener('abort', cancel) }
      const cancel = () => { cleanup(); reject(new DOMException('视觉资源等待已取消。', 'AbortError')) }
      const handle = requestAnimationFrame(() => { cleanup(); resolve() })
      signal.addEventListener('abort', cancel, { once: true })
      if (signal.aborted) cancel()
    })
  }

  /** 正常完成同样撤销未胜出的超时观察，不取消宿主传入的父信号。 */
  function dispose(): void { parent?.removeEventListener('abort', abort); abort() }
  return { signal, check, wait, delay, frame, dispose }
}
