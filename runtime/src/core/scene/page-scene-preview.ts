/** 文件功能：为正式单页预览和开发调试复用页级 Scene 播放、就绪等待、状态和释放域。 */
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticExecution } from '@/core/static-presentation/types'
import { waitForEditorVisualAssets } from '@/core/utils/visual-assets'
import { findPageSceneDefinition, subscribePageSceneDefinitions, type RegisteredPageScene } from './page-scene-definition'
import { createPageSceneSlot } from './page-scene-slot'
import { SceneSessionError, type SceneSnapshot } from './types'
import type { PreviewSceneState } from './preview-protocol'
import { isStaticSceneRoot } from './scene-scope'

/** 一个预览宿主只持有一个 slot；不自动播放、不自动翻页、不提供 seek 或暂停。 */
export function createPageScenePreview(scope: () => ParentNode | null = () => document) {
  const slot = createPageSceneSlot(), listeners = new Set<() => void>()
  let active: RegisteredPageScene | null = null, previous: SceneSnapshot | null = null
  let unsubscribe: (() => void) | null = null, disposed = false

  /** 只发现当前画布，静态上下文不披露可播放声明。 */
  function definition(): RegisteredPageScene | null {
    if (disposed || isStaticExecution(getRuntimeExecutionPolicy().kind)) return null
    const target = scope(), entry = target ? findPageSceneDefinition(target, root => !isStaticSceneRoot(root)) : null, root = entry?.root()
    return root?.isConnected && !isStaticSceneRoot(root) ? entry : null
  }

  /** 只读取有界状态；无实例时仍能显示已经挂载的声明与播放按钮。 */
  function read(): PreviewSceneState {
    try {
      const entry = definition(), snapshot = entry && entry === active ? slot.getCurrent()?.getSnapshot() ?? previous : null
      return { hasScene: Boolean(entry), generation: snapshot?.generation ?? null, phase: snapshot?.phase ?? (entry ? 'idle' : null),
        hasBlocking: snapshot?.hasBlocking ?? false, blockedTaskIds: snapshot?.blockedTaskIds ?? [], issue: snapshot?.issue ?? null }
    } catch (error) {
      return { hasScene: false, generation: null, phase: 'failed', hasBlocking: false, blockedTaskIds: [], issue: {
        code: error instanceof SceneSessionError ? error.code : 'SCENE_PREVIEW_FAILED',
        message: error instanceof SceneSessionError ? error.message : '页面声明读取失败。',
      } }
    }
  }

  /** 状态只在变化时通知，预览不创建轮询或第二只播放时钟。 */
  function emit(): void { if (!disposed) for (const listener of listeners) { try { listener() } catch { /* 观察方不控制任务。 */ } } }

  /** 退出立即撤销准备和播放；保留停止快照供正式预览显示。 */
  function stop(): SceneSnapshot | null {
    const session = slot.getCurrent()
    unsubscribe?.(); unsubscribe = null
    slot.stop(); previous = session?.getSnapshot() ?? previous
    emit()
    return session?.getSnapshot() ?? null
  }

  /** 用户播放时才等待资源与执行 define；重复播放创建新 generation。 */
  async function play(): Promise<boolean> {
    stop()
    const entry = definition(), root = entry?.root()
    if (!entry || !root) return false
    if (document.fullscreenElement) throw new SceneSessionError('SCENE_PREVIEW_PRESENTING', '请退出正式全屏放映后使用单页预览。')
    active = entry; previous = null
    const preparing = slot.prepare({ execution: 'interactive-preview', advanceMode: 'manual', define: async context => {
      const observer = new MutationObserver(() => {
        if (!context.signal.aborted && (!root.isConnected || isStaticSceneRoot(root))) stop()
      })
      observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-runtime-execution'] })
      context.onCleanup(() => observer.disconnect())
      const assets = await waitForEditorVisualAssets({ root, includeAnimations: false, signal: context.signal })
      if (context.signal.aborted) return
      if (!root.isConnected || entry.root() !== root || findPageSceneDefinition(root, element => !isStaticSceneRoot(element)) !== entry) throw new SceneSessionError('SCENE_PAGE_REPLACED', '准备期间页面已经替换，请重新播放。')
      if (!assets.ok) throw new SceneSessionError('SCENE_PAGE_ASSETS_FAILED', '页面资源未就绪，无法开始预览。')
      await entry.define(context)
    } })
    const current = slot.getCurrent()
    unsubscribe = current?.subscribe(emit) ?? null
    emit()
    const session = await preparing
    if (!session || session !== slot.getCurrent()) return false
    const started = await session.start()
    return ['running', 'blocked', 'completed'].includes(started.phase)
  }

  const unsubscribeDefinitions = subscribePageSceneDefinitions(() => {
    let current: RegisteredPageScene | null = null
    try { current = definition() } catch { /* read 会给出有界原因。 */ }
    if (active && current !== active) { stop(); active = null; previous = null }
    emit()
  })

  /** 组件/iframe 卸载撤销监听、实例和所有迟到准备，不依赖 Promise 合作取消。 */
  function dispose(): void { if (disposed) return; disposed = true; unsubscribeDefinitions(); stop(); listeners.clear() }
  return { play, stop, read, dispose, getSnapshot: () => slot.getCurrent()?.getSnapshot() ?? null,
    setSuspended(value: boolean) { slot.getCurrent()?.setSuspended(value) },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
  }
}
