/** 文件功能：把路由提交、过渡完成和资源就绪串入同一次 Scene prepare，不创建第二套翻页控制器。 */
import { nextTick, watch } from 'vue'
import type { Router } from 'vue-router'
import type { ExecutionContextKind } from '@/core/execution/execution-policy'
import type { TransitionSettledEvent } from '@/core/types/page-transition'
import { getRuntimeSession, navigateRuntimePage } from '@/core/router/runtime-session'
import { findPageSceneDefinition } from '@/core/scene/page-scene-definition'
import { isStaticSceneRoot } from '@/core/scene/scene-scope'
import { createPageSceneSlot } from '@/core/scene/page-scene-slot'
import { SceneSessionError, type PageSceneOptions, type SceneAdvanceMode } from '@/core/scene/types'
import { createVisualAssetWaitScope } from '@/core/utils/visual-asset-wait'
import { waitForEditorVisualAssets } from '@/core/utils/visual-assets'
import { findPlaybackPageElement } from './playback-page-root'

interface SceneStageInput extends Pick<PageSceneOptions, 'prepareTimeoutMs' | 'completionTimeoutMs'> {
  path: string
  execution: ExecutionContextKind
  advanceMode: SceneAdvanceMode
  /** 开始当前稳定页时可以复用最近的过渡完成；重新进页可强制等待新事件。 */
  acceptCurrentSettled?: boolean
}

/** 一个宿主只持有一个 slot；generation、取消和准备期限继续由 PageSceneSession 管理。 */
export function createPageSceneStage(router: Router) {
  const slot = createPageSceneSlot()
  /** 静态策略在创建前拦截；没有 Scene 的普通页仍支持 manual/timer。 */
  function prepare(input: SceneStageInput) {
    return slot.prepare({ ...input, define: async context => {
      const root = await prepareScenePage(router, input, context.signal)
      if (context.signal.aborted) return
      await findPageSceneDefinition(root, element => !isStaticSceneRoot(element))?.define(context)
    } })
  }
  return { prepare, stop: slot.stop, getCurrent: slot.getCurrent }
}

/** 只做页面准备；不自动 start，也不提供暂停、定位或新的放映时钟。 */
async function prepareScenePage(router: Router, input: SceneStageInput, signal: AbortSignal): Promise<HTMLElement> {
  const scope = createVisualAssetWaitScope(signal)
  const session = getRuntimeSession(router)
  const previous = session.transitionSettled.value
  const canReuse = input.acceptCurrentSettled !== false && router.currentRoute.value.path === input.path
    && previous?.path === input.path
  try {
    scope.check()
    const settled = waitForPageTransition(router, input.path, previous, canReuse, scope.signal)
    const navigation = scope.wait(navigateRuntimePage(router, input.path)).then(() => {
      scope.check()
      if (router.currentRoute.value.path !== input.path) throw navigationError()
    }, error => {
      scope.check()
      throw error instanceof SceneSessionError ? error : navigationError()
    })
    await Promise.all([settled, navigation])
    await scope.wait(nextTick())
    scope.check()
    const root = findPlaybackPageElement(input.path)
    if (!root?.isConnected) throw new SceneSessionError('SCENE_PAGE_ROOT_MISSING', '页面节点未就绪，无法开始播放。')
    const assets = await scope.wait(waitForEditorVisualAssets({ root, includeAnimations: false, timeoutMs: 25000, signal: scope.signal }))
    scope.check()
    if (router.currentRoute.value.path !== input.path || findPlaybackPageElement(input.path) !== root || !root.isConnected) {
      throw new SceneSessionError('SCENE_PAGE_REPLACED', '准备期间页面已经切换，请重新开始当前页。')
    }
    if (!assets.ok) throw new SceneSessionError('SCENE_PAGE_ASSETS_FAILED', '页面资源未就绪，无法开始播放。')
    return root
  } finally { scope.dispose() }
}

/** 先监听再导航，既不漏掉同步过渡，也不复用快速往返留下的旧完成事件。 */
function waitForPageTransition(router: Router, path: string, previous: TransitionSettledEvent | null, reuse: boolean,
  signal: AbortSignal): Promise<void> {
  const session = getRuntimeSession(router), initialError = session.navigationError.value
  return new Promise((resolve, reject) => {
    /** 每条结算路径都撤销 watcher 和取消监听，离页不遗留响应式观察。 */
    const cleanup = () => { stopWatch(); signal.removeEventListener('abort', cancel) }
    const cancel = () => { cleanup(); reject(new DOMException('页面准备已取消。', 'AbortError')) }
    /** 过渡层已经丢弃旧 generation；这里只拒绝原回执，允许宿主重挂后重新编号。 */
    const probe = () => {
      if (session.navigationError.value && session.navigationError.value !== initialError) {
        cleanup(); reject(navigationError()); return
      }
      const event = session.transitionSettled.value
      if (router.currentRoute.value.path !== path || event?.path !== path) return
      if (!reuse && event === previous) return
      cleanup(); resolve()
    }
    const stopWatch = watch([() => router.currentRoute.value.path, session.transitionSettled, session.navigationError], probe, { flush: 'sync' })
    signal.addEventListener('abort', cancel, { once: true })
    if (signal.aborted) cancel()
    else probe()
  })
}

/** 路由异常不把任意组件异常或资源地址放入 Scene 状态。 */
function navigationError(): SceneSessionError {
  return new SceneSessionError('SCENE_PAGE_NAVIGATION_FAILED', '页面切换失败，请重新开始或选择其它页面。')
}
