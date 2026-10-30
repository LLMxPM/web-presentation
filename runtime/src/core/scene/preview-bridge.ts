/** 文件功能：向 Editor 父窗口提供正式 Scene 预览桥，验证来源并推送原子状态，不保留时间轴定位协议。 */
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticExecution } from '@/core/static-presentation/types'
import { createPageScenePreview } from './page-scene-preview'
import { parsePreviewSceneCommand, PREVIEW_SCENE_PROTOCOL_VERSION, PREVIEW_SCENE_STATE_TYPE } from './preview-protocol'

/** 嵌入式交互预览才安装；静态执行和顶层窗口不创建预览会话或消息监听。 */
export function installPreviewSceneBridge(): () => void {
  if (typeof window === 'undefined' || window.parent === window || isStaticExecution(getRuntimeExecutionPolicy().kind)) return () => {}
  const preview = createPageScenePreview()
  let origin: string | null = null, disposed = false
  /** 单次消息包含完整当前状态，不逐帧广播位置。 */
  function publish(requestId?: string): void {
    if (disposed || !origin) return
    window.parent.postMessage({ type: PREVIEW_SCENE_STATE_TYPE, version: PREVIEW_SCENE_PROTOCOL_VERSION,
      ...(requestId ? { requestId } : {}), state: preview.read() }, origin)
  }
  const unsubscribe = preview.subscribe(() => publish())
  /** 首次 sync 固定父窗口 origin；旧协议、跨窗口和来源变更均不执行。 */
  function message(event: MessageEvent): void {
    if (disposed || event.source !== window.parent || !event.origin || event.origin === 'null') return
    const command = parsePreviewSceneCommand(event.data)
    if (!command || (origin && origin !== event.origin)) return
    if (command.action === 'sync') { origin = event.origin; publish(command.requestId); return }
    if (origin !== event.origin) return
    if (command.action === 'unsync') { origin = null; preview.stop(); return }
    if (command.action === 'stop') { preview.stop(); publish(command.requestId); return }
    void preview.play().catch(() => false).then(() => publish(command.requestId))
  }
  /** 页面退出时先终止任务，再移除属于本桥的监听。 */
  function dispose(): void {
    if (disposed) return
    disposed = true; origin = null; unsubscribe(); preview.dispose()
    window.removeEventListener('message', message)
    window.removeEventListener('beforeunload', dispose)
  }
  window.addEventListener('message', message)
  window.addEventListener('beforeunload', dispose, { once: true })
  return dispose
}
