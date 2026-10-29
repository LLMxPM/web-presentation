/** 文件功能：管理 Scene 取消信号、逆序清理与有界异步准备，隔离任务的迟到结果。 */
import { SceneSessionError } from './types'

/** 创建一个会话的释放域；任意清理异常不能阻止后续清理。 */
export function createSceneLifetime() {
  const controller = new AbortController()
  const cleanups: Array<() => void> = []
  /** 取消后登记的资源立即释放；页面自行产生的外部副作用不作回滚承诺。 */
  function onCleanup(cleanup: () => void): void {
    if (controller.signal.aborted) { safely(cleanup); return }
    cleanups.push(cleanup)
  }
  /** 单个清理失败不会破坏停止的幂等性。 */
  function safely(cleanup: () => void): void { try { cleanup() } catch { /* 继续释放其它资源。 */ } }
  /** 信号先取消，再按资源登记的逆序清理。 */
  function stop(): void {
    if (controller.signal.aborted) return
    controller.abort()
    for (const cleanup of cleanups.splice(0).reverse()) safely(cleanup)
  }
  return { signal: controller.signal, onCleanup, stop }
}

/** 等待整个 prepare；取消或超时立即结算，迟到的原 Promise 仍有失败处理器。 */
export function waitForScenePrepare(work: () => Promise<void>, signal: AbortSignal, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => finish(new SceneSessionError('SCENE_STOPPED', '页面会话已停止。'), true)
    const timer = setTimeout(() => finish(new SceneSessionError('SCENE_PREPARE_TIMEOUT', '页面任务准备超时。'), true), timeoutMs)
    /** 任一路径完成都撤销监听与定时器，不等待不合作的任务 Promise。 */
    function finish(error?: unknown, failed = false): void {
      clearTimeout(timer)
      signal.removeEventListener('abort', abort)
      if (failed) reject(error)
      else resolve()
    }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) { abort(); return }
    Promise.resolve().then(() => { if (!signal.aborted) return work() }).then(() => finish(), error => finish(error, true))
  })
}
