/** 文件用途：在同源固定画布 iframe 中准备真实页面，按本次捕获票据和资源状态校验就绪，供 PPTX 与 PDF 共用。 */
import { pageCaptureService } from '@/core/services/PageCaptureService'
import type { CaptureOptions } from '@/core/types/export-common'
import { appPageConfig } from '@/core/utils/config'
import { runWithExportDeadline, throwIfExportAborted } from './ExportCancellation'
import { ModelStaticFrameCache, cleanupModelStaticFrames, prepareModelStaticFrames, type ModelStaticFramesHandle } from './model-static-frames'
import { STATIC_PRESENTATION_UNAVAILABLE } from '@/core/static-presentation/types'

export interface RuntimeCaptureRoute { path: string; hash: string }
export interface OffscreenPreparedPage { element: HTMLElement; cleanup: () => void }
export interface OffscreenPrepareOptions {
  signal?: AbortSignal
  timeoutMs?: number
  pageLabel?: string
}
export interface OffscreenPageStage {
  preparePage: (route: string, options?: OffscreenPrepareOptions) => Promise<OffscreenPreparedPage>
  capture: (route: string, options?: CaptureOptions) => Promise<HTMLCanvasElement>
  dispose: () => void
}

/** 保留页面查询参数并固定捕获模式，不改变宿主页面地址。 */
export function resolveRuntimeCaptureRoute(route: string, baseHref = window.location.href): RuntimeCaptureRoute {
  const routeUrl = new URL(route, baseHref)
  const searchParams = new URLSearchParams(routeUrl.search)
  searchParams.set('runtimeMode', 'normal')
  searchParams.set('runtimeCapture', '1')
  return { path: routeUrl.pathname || '/', hash: `${routeUrl.pathname || '/'}?${searchParams.toString()}` }
}

/**
 * 暂停离屏页面内的原生媒体，避免隐藏舞台在导出期间继续播放或产生声音。
 * 只暂停，不改变播放进度，也不重置 poster/首帧。
 * @param root 离屏页面根节点
 */
export function pauseOffscreenMedia(root: HTMLElement): void {
  for (const element of Array.from(root.querySelectorAll('video, audio'))) {
    const media = element as HTMLMediaElement
    try {
      media.pause()
      media.removeAttribute('autoplay')
    } catch {
      // 忽略未实现播放控制的宿主
    }
  }
}


/** 创建可复用捕获舞台，调用方必须在 finally 中释放。 */
export function createOffscreenPageStage(): OffscreenPageStage {
  const frame = document.createElement('iframe')
  frame.title = 'Runtime 导出捕获'
  frame.setAttribute('aria-hidden', 'true')
  frame.inert = true
  Object.assign(frame.style, {
    // 预览处于跨源嵌套 iframe 时，屏幕外子框架会被 Chromium 暂停 rAF，导致挂载永不就绪。
    // 保持几何区域在视口内，以透明和禁止交互隐藏舞台，仍按固定画布尺寸完成真实布局。
    position: 'fixed', left: '0', top: '0', border: '0', opacity: '0', pointerEvents: 'none', zIndex: '-1',
    width: `${appPageConfig.value.width}px`, height: `${appPageConfig.value.height}px`,
  })
  document.body.appendChild(frame)
  let disposed = false
  // 任务级静态帧缓存：同一导出任务内按实例视角复用，dispose 时统一释放。
  const staticFrameCache = new ModelStaticFrameCache()
  // 上一页的静态帧句柄：同路径 hash 导航复用 DOM 时元素不变，
  // 若旧句柄未清理，preparedModelRoots 标记会让新一轮 prepare 跳过补帧。先清旧再备新。
  let activeStaticFrameHandle: ModelStaticFramesHandle | null = null

  /** 验证当前票据对应的页面，再等待该文档的资源和动画；允许同路径更新复用 DOM。 */
  async function preparePage(route: string, options?: OffscreenPrepareOptions): Promise<OffscreenPreparedPage> {
    if (options && 'motionSnapshot' in options) throw new Error('不再支持指定动画时刻导出；请声明独立静态呈现。')
    const captureRoute = resolveRuntimeCaptureRoute(route)
    const ticket = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const url = new URL(window.location.href)
    // 执行策略只读取 location.search；捕获标记必须同时写入 search 与 hash 路由。
    url.searchParams.set('runtimeMode', 'normal')
    url.searchParams.set('runtimeCapture', '1')
    const query = new URLSearchParams(captureRoute.hash.slice(captureRoute.hash.indexOf('?') + 1))
    query.set('runtimeCaptureTicket', ticket)
    url.hash = `${captureRoute.path}?${query.toString()}`
    // hash 导航复用运行时；不清掉只在应用启动时写入的全局 mounted 标记。
    frame.src = url.href
    return runWithExportDeadline(async signal => {
      while (!disposed) {
        throwIfExportAborted(signal)
        const win = frame.contentWindow
        const doc = frame.contentDocument
        const target = doc?.querySelector<HTMLElement>('.runtime-page-print-source')
        if (win?.__RENDER_READY__?.initFailed) throw new Error(win.__RENDER_READY__.message || '导出页面初始化失败')
        const matchesTicket = target?.dataset.runtimeRoutePath === captureRoute.path && target?.dataset.runtimeCaptureTicket === ticket
        const receipt = matchesTicket && win?.__RENDER_READY__?.mounted ? win.__RENDER_READY__.staticPresentation : null
        const pageLabel = options?.pageLabel || captureRoute.path
        if (receipt?.status === 'unsupported') throw new Error(`${pageLabel}：${STATIC_PRESENTATION_UNAVAILABLE}：${receipt.message}`)
        if (receipt?.status === 'failed') throw new Error(`${pageLabel}：${receipt.code}：${receipt.message}`)
        if (win?.__EDITOR_RUNTIME_PREVIEW_READY__ && target?.dataset.runtimeRoutePath === captureRoute.path &&
          target.dataset.runtimeCaptureTicket === ticket && !doc?.querySelector('[role="alert"]')) {
          if (receipt?.status !== 'ready') throw new Error(`${pageLabel}：导出页面缺少独立静态呈现回执`)
          await doc?.fonts?.ready
          const probe = win.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__
          if (probe) {
            const result = await probe({ timeoutMs: options?.timeoutMs ?? 15000, includeAnimations: false, staticMedia: true, root: target })
            if (!result.ok) throw new Error(`${pageLabel}：导出页面视觉资源未就绪：${[...result.failed, ...result.pending].map(issue => issue.message).slice(0, 3).join('；')}`)
          }
          throwIfExportAborted(signal)
          pauseOffscreenMedia(target)
          // 页面就绪后逐实例准备静态帧：克隆与转换阶段看到的是 PNG 覆盖图，而不是空白 WebGL 画布。
          cleanupModelStaticFrames(activeStaticFrameHandle)
          let staticFrames: ModelStaticFramesHandle
          try { staticFrames = prepareModelStaticFrames(target, { cache: staticFrameCache, required: true }) }
          catch (error) { throw new Error(`${pageLabel}：${error instanceof Error ? error.message : '模型静态帧采集失败'}`) }
          activeStaticFrameHandle = staticFrames
          return { element: target, cleanup: () => cleanupModelStaticFrames(staticFrames) }
        }
        await new Promise(resolve => setTimeout(resolve, 25))
      }
      throw new Error('截图任务已释放')
    }, options?.signal, options?.timeoutMs ?? 30000)
  }

  /** 在已就绪页面节点上捕获，截图完成后归还页面句柄。 */
  async function capture(route: string, options?: CaptureOptions): Promise<HTMLCanvasElement> {
    if (options && 'motionSnapshot' in options) throw new Error('不再支持指定动画时刻导出；请声明独立静态呈现。')
    const prepared = await preparePage(route, {
      signal: options?.signal,
    })
    try { return await pageCaptureService.captureElement(prepared.element, options) }
    finally { prepared.cleanup() }
  }

  /** 移除 iframe，终止其页面脚本和资源占用，并释放任务级静态帧缓存。 */
  function dispose(): void {
    disposed = true
    cleanupModelStaticFrames(activeStaticFrameHandle)
    activeStaticFrameHandle = null
    staticFrameCache.clear()
    frame.remove()
  }
  return { preparePage, capture, dispose }
}
