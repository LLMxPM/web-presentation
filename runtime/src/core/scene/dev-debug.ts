/** 文件功能：在开发服务器提供显式 Scene 播放调试，复用现有会话与取消域，不增加放映调度内核。 */
import type { Router } from 'vue-router'
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { findPageMotionHandle } from '@/core/motion/page-motion-contract'
import { isStaticExecution } from '@/core/static-presentation/types'
import { waitForEditorVisualAssets } from '@/core/utils/visual-assets'
import { findPageSceneDefinition } from './page-scene-definition'
import { createPageSceneSlot } from './page-scene-slot'
import { SceneSessionError, type SceneSnapshot } from './types'

export interface SceneDebugApi {
  /** 当前 frame 只有一份 Scene 时可省略 scope；多画布时传根元素或选择器。 */
  play(scope?: string | Element): Promise<SceneSnapshot | null>
  stop(): SceneSnapshot | null
  read(): SceneSnapshot | null
}

declare global {
  interface Window { __RUNTIME_SCENE_DEBUG__?: SceneDebugApi }
}

let disposePrevious: (() => void) | null = null

/** 开发安装幂等替换；生产不登记全局入口，静态执行不创建会话。 */
export function installPageSceneDebug(router?: Pick<Router, 'beforeEach'>): () => void {
  if (!import.meta.env.DEV || typeof window === 'undefined') return () => {}
  disposePrevious?.()
  const slot = createPageSceneSlot()
  let disposed = false

  /** 退出、切页和重复播放都先使旧 generation 失效，迟到结果不能继续创建任务。 */
  function stop(): SceneSnapshot | null {
    const session = slot.getCurrent()
    slot.stop()
    return session?.getSnapshot() ?? null
  }

  /** 开发预览只启动选中画布；正式全屏放映的所有权留给放映宿主。 */
  async function play(scope?: string | Element): Promise<SceneSnapshot | null> {
    stop()
    if (disposed || isStaticExecution(getRuntimeExecutionPolicy().kind)) return null
    if (document.fullscreenElement) throw new SceneSessionError('SCENE_DEBUG_PRESENTING', '请先退出全屏放映，再使用 Scene 开发调试。')
    const target = typeof scope === 'string' ? document.querySelector(scope) : scope ?? document
    if (!target) throw new SceneSessionError('SCENE_DEBUG_SCOPE_MISSING', '没有找到指定的 Scene 调试画布。')
    const definition = findPageSceneDefinition(target), root = definition?.root()
    if (!definition || !root?.isConnected) throw new SceneSessionError('SCENE_DEBUG_DEFINITION_MISSING', '当前画布没有已挂载的 usePageScene.v1 声明。')
    if (isStaticRoot(root)) return null
    if (findPageMotionHandle(root)) throw new SceneSessionError('SCENE_DEBUG_LEGACY_CONFLICT', '同一画布不能同时播放 Scene 和旧时间轴，请分别放在不同页面调试。')
    const session = await slot.prepare({ execution: 'interactive-preview', advanceMode: 'manual', define: async context => {
      const observer = new MutationObserver(() => {
        if (!context.signal.aborted && (!root.isConnected || isStaticRoot(root))) stop()
      })
      observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-runtime-execution'] })
      context.onCleanup(() => observer.disconnect())
      const assets = await waitForEditorVisualAssets({ root, includeAnimations: false, signal: context.signal })
      if (context.signal.aborted) return
      if (!root.isConnected || definition.root() !== root || findPageSceneDefinition(root) !== definition) {
        throw new SceneSessionError('SCENE_PAGE_REPLACED', '准备期间页面已经替换，请在新页面重新播放。')
      }
      if (!assets.ok) throw new SceneSessionError('SCENE_PAGE_ASSETS_FAILED', '页面资源未就绪，无法开始调试播放。')
      await definition.define(context)
    } })
    if (!session) return null
    return session.start()
  }

  const api: SceneDebugApi = { play, stop, read: () => slot.getCurrent()?.getSnapshot() ?? null }
  const removeNavigationGuard = router?.beforeEach(() => { stop() })
  /** 进入正式放映立即释放调试任务，两个宿主不同时持有当前页。 */
  const onFullscreen = () => { if (document.fullscreenElement) stop() }
  document.addEventListener('fullscreenchange', onFullscreen)
  window.__RUNTIME_SCENE_DEBUG__ = api
  /** 卸载只移除自己的全局入口；旧 HMR 清理不能删掉新安装。 */
  function dispose(): void {
    if (disposed) return
    disposed = true
    removeNavigationGuard?.()
    document.removeEventListener('fullscreenchange', onFullscreen)
    window.removeEventListener('beforeunload', dispose)
    stop()
    if (window.__RUNTIME_SCENE_DEBUG__ === api) delete window.__RUNTIME_SCENE_DEBUG__
    if (disposePrevious === dispose) disposePrevious = null
  }
  disposePrevious = dispose
  window.addEventListener('beforeunload', dispose, { once: true })
  return dispose
}

/** 任一祖先静态作用域都禁止调试播放，不能用全局 presentation 策略绕过缩略图限制。 */
function isStaticRoot(root: HTMLElement): boolean {
  return Boolean(root.closest('[data-runtime-execution="capture"], [data-runtime-execution="export"], [data-runtime-execution="thumbnail"]'))
}
