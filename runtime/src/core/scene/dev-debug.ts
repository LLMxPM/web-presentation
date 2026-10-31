/** 文件功能：在 Vite DEV 提供 Scene 控制台，复用正式单页预览实现，不另建执行器。 */
import type { Router } from 'vue-router'
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticExecution } from '@/core/static-presentation/types'
import { findPageSceneDefinition } from './page-scene-definition'
import { createPageScenePreview } from './page-scene-preview'
import { isStaticSceneRoot } from './scene-scope'
import { SceneSessionError, type SceneSnapshot } from './types'

export interface SceneDebugApi {
  play(scope?: string | Element): Promise<SceneSnapshot | null>
  stop(): SceneSnapshot | null
  read(): SceneSnapshot | null
}
declare global { interface Window { __RUNTIME_SCENE_DEBUG__?: SceneDebugApi } }
let disposePrevious: (() => void) | null = null

/** 开发入口幂等替换；生产不安装，路由/全屏交接立即停止当前预览。 */
export function installPageSceneDebug(router?: Pick<Router, 'beforeEach'>): () => void {
  if (!import.meta.env.DEV || typeof window === 'undefined') return () => {}
  disposePrevious?.()
  let scope: ParentNode = document, disposed = false
  const preview = createPageScenePreview(() => scope)
  /** 使用正式预览播放逻辑，同时给控制台提供可操作的选画布错误。 */
  async function play(input?: string | Element): Promise<SceneSnapshot | null> {
    preview.stop()
    if (disposed || isStaticExecution(getRuntimeExecutionPolicy().kind)) return null
    if (document.fullscreenElement) throw new SceneSessionError('SCENE_DEBUG_PRESENTING', '请先退出全屏放映，再使用 Scene 开发调试。')
    const target = typeof input === 'string' ? document.querySelector(input) : input ?? document
    if (!target) throw new SceneSessionError('SCENE_DEBUG_SCOPE_MISSING', '没有找到指定的 Scene 调试画布。')
    if (target instanceof HTMLElement && isStaticSceneRoot(target)) return null
    const definition = findPageSceneDefinition(target, element => !isStaticSceneRoot(element)), root = definition?.root()
    if (!root?.isConnected) throw new SceneSessionError('SCENE_DEBUG_DEFINITION_MISSING', '当前画布没有已挂载的 usePageScene.v1 声明。')
    if (isStaticSceneRoot(root)) return null
    scope = target
    await preview.play()
    return preview.getSnapshot()
  }
  const api: SceneDebugApi = { play, stop: preview.stop, read: preview.getSnapshot }
  const removeNavigationGuard = router?.beforeEach(() => { preview.stop() })
  /** 正式全屏拥有页面播放权，开发调试不得继续运行。 */
  const onFullscreen = () => { if (document.fullscreenElement) preview.stop() }
  document.addEventListener('fullscreenchange', onFullscreen)
  window.__RUNTIME_SCENE_DEBUG__ = api
  /** 旧 HMR 清理不能删除新安装，监听与预览所有权统一释放。 */
  function dispose(): void {
    if (disposed) return
    disposed = true; removeNavigationGuard?.(); preview.dispose()
    document.removeEventListener('fullscreenchange', onFullscreen); window.removeEventListener('beforeunload', dispose)
    if (window.__RUNTIME_SCENE_DEBUG__ === api) delete window.__RUNTIME_SCENE_DEBUG__
    if (disposePrevious === dispose) disposePrevious = null
  }
  disposePrevious = dispose
  window.addEventListener('beforeunload', dispose, { once: true })
  return dispose
}
