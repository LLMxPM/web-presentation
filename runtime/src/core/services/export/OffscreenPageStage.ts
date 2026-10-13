/**
 * 文件用途：在独立同源 1:1 离屏 iframe 中加载并投影项目页面，供 PPTX DOM 采集与 PDF 整页截图共用，不改变主窗口路由。
 */

import { pageCaptureService } from '@/core/services/PageCaptureService'
import type { CaptureOptions } from '@/core/types/export-common'
import { appPageConfig } from '@/core/utils/config'
import { copyCanvasContents } from '@/core/utils/export-dom'

/**
 * 规范化后的离屏捕获路由信息。
 */
export interface RuntimeCaptureRoute {
  path: string
  hash: string
}

/**
 * 已投影到宿主文档的 1:1 离屏页面句柄；调用方使用完毕后必须执行 cleanup()。
 */
export interface OffscreenPreparedPage {
  element: HTMLElement
  cleanup: () => void
}

/**
 * 离屏页面舞台实例接口，同时支持 DOM 提取（preparePage）与整页光栅化（capture）。
 */
export interface OffscreenPageStage {
  /** 加载目标路由并在宿主文档构建 1:1 投影节点，供 PPTX DOM 转换器测量与提取 */
  preparePage: (route: string) => Promise<OffscreenPreparedPage>
  /** 加载目标路由并捕获为整页 HTMLCanvasElement，供 PDF 导出使用 */
  capture: (route: string, options?: CaptureOptions) => Promise<HTMLCanvasElement>
  /** 销毁离屏 iframe 并终止内部脚本与媒体资源 */
  dispose: () => void
}

/**
 * 将 Vue Router 的完整地址转换为 Runtime 捕获 hash。
 * @param route 页面路径，可包含 query
 * @param baseHref 当前 Runtime 地址，用于解析相对路径
 * @returns 规范化页面路径和带捕获标记的 hash
 */
export function resolveRuntimeCaptureRoute(
  route: string,
  baseHref = window.location.href,
): RuntimeCaptureRoute {
  const routeUrl = new URL(route, baseHref)
  const path = routeUrl.pathname || '/'
  const searchParams = new URLSearchParams(routeUrl.search)
  searchParams.set('runtimeMode', 'normal')
  searchParams.set('runtimeCapture', '1')

  return {
    path,
    hash: `${path}?${searchParams.toString()}`,
  }
}

/**
 * 冻结文档中的所有有限动画到最终状态，避免截图或几何测量采到动画起始帧或重新开始。
 * @param doc 目标文档
 */
export async function freezeDocumentAnimationsToFinalState(doc?: Document | null): Promise<void> {
  if (!doc || typeof doc.getAnimations !== 'function') {
    return
  }
  try {
    const animations = doc.getAnimations()
    for (const anim of animations) {
      const timing = anim.effect?.getTiming()
      const iterations = timing?.iterations ?? 1
      if (Number.isFinite(iterations) && iterations > 0) {
        if (typeof anim.finish === 'function') {
          try {
            anim.finish()
          } catch {
            // 忽略只读或已完成动画异常
          }
        }
      }
    }
  } catch {
    // 忽略不受支持环境异常
  }
}

/**
 * 创建单任务离屏 1:1 页面渲染舞台；调用方必须在 finally 中调用 dispose() 释放。
 * 退出条件保障：原生在真实 iframe 内部提取和截图，移除 PPTX 宿主投影，无遗留舞台或投影节点。
 * @returns OffscreenPageStage 实例
 */
export function createOffscreenPageStage(): OffscreenPageStage {
  const frame = document.createElement('iframe')
  frame.title = 'Runtime 导出捕获'
  frame.setAttribute('aria-hidden', 'true')
  frame.inert = true
  Object.assign(frame.style, {
    position: 'fixed',
    left: '-100000px',
    top: '0',
    border: '0',
    width: `${appPageConfig.value.width}px`,
    height: `${appPageConfig.value.height}px`,
  })
  document.body.appendChild(frame)
  let disposed = false
  let lastCapturedElement: HTMLElement | null = null

  /**
   * 确保 iframe 文档与 body 结构初始化完成。
   */
  function ensureFrameDocument(): void {
    const doc = frame.contentDocument
    if (doc && !doc.body) {
      try {
        doc.write('<!DOCTYPE html><html><head></head><body></body></html>')
        doc.close()
      } catch {
        // 忽略跨域写异常
      }
    }
  }

  /**
   * 重载独立运行时并等待目标页面、字体与动画最终态就绪，直接返回真实 iframe 节点。
   * @param route 目标页面路由
   * @returns 真实 iframe 中的 1:1 页面元素及清理句柄
   */
  async function preparePage(route: string): Promise<OffscreenPreparedPage> {
    const ticket = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const captureRoute = resolveRuntimeCaptureRoute(route)
    const url = new URL(window.location.href)
    const [pathPart, queryPart] = captureRoute.hash.split('?')
    const searchParams = new URLSearchParams(queryPart || '')
    searchParams.set('runtimeCaptureTicket', ticket)
    url.hash = `${pathPart}?${searchParams.toString()}`

    // 重置已挂载窗口的就绪标记，防止多页切换时上一页就绪标记引起残余 DOM 误判
    if (frame.contentWindow && '__EDITOR_RUNTIME_PREVIEW_READY__' in frame.contentWindow) {
      try {
        frame.contentWindow.__EDITOR_RUNTIME_PREVIEW_READY__ = false
      } catch {
        // 忽略跨域写标记异常
      }
    }

    // 优先通过 contentWindow.location.hash 触发单页内部路由更新，避免重复整页重载
    if (frame.contentWindow?.location && frame.src) {
      try {
        frame.contentWindow.location.hash = url.hash
      } catch {
        frame.src = url.href
      }
    } else {
      frame.src = url.href
    }

    ensureFrameDocument()

    const started = Date.now()
    while (!disposed && Date.now() - started < 30000) {
      ensureFrameDocument()
      const targetWindow = frame.contentWindow
      const doc = frame.contentDocument
      const target = doc?.querySelector<HTMLElement>('.runtime-page-print-source')
      const isRouteMatched = target?.dataset.runtimeRoutePath === captureRoute.path
      const isNewElement = !lastCapturedElement || target !== lastCapturedElement || !lastCapturedElement.isConnected

      if (
        targetWindow?.__EDITOR_RUNTIME_PREVIEW_READY__ &&
        isRouteMatched &&
        isNewElement &&
        !doc?.querySelector('[role="alert"]')
      ) {
        await doc?.fonts?.ready
        await freezeDocumentAnimationsToFinalState(doc)
        lastCapturedElement = target
        return {
          element: target,
          cleanup: () => {
            // 原生在 iframe 内运行，不污染宿主文档，无须移除宿主投影
          },
        }
      }
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    throw new Error(disposed ? '截图任务已释放' : `等待导出页面超时：${route}`)
  }

  /**
   * 准备离屏页面并捕获为整页 Canvas。
   * @param route 目标页面路由
   * @param options 捕获选项
   */
  async function capture(route: string, options?: CaptureOptions): Promise<HTMLCanvasElement> {
    const projection = await preparePage(route)
    try {
      return await pageCaptureService.captureElement(projection.element, options)
    } finally {
      projection.cleanup()
    }
  }

  /**
   * 释放 iframe，同时终止页面脚本与媒体资源。
   */
  function dispose(): void {
    disposed = true
    lastCapturedElement = null
    frame.remove()
  }

  return {
    preparePage,
    capture,
    dispose,
  }
}

/**
 * 将 iframe 页面投影到宿主文档，确保宿主的样式表、CSS 变量、SVG defs 与 canvas 位图完整可用。
 * @param sourceElement iframe 中的页面源节点
 * @param sourceDocument iframe 文档
 * @returns 宿主文档中的捕获节点和清理函数
 */
function projectIframeTarget(
  sourceElement: HTMLElement,
  sourceDocument: Document,
): OffscreenPreparedPage {
  const host = document.createElement('div')
  const styleNodes = copyIframeStyles(sourceDocument)
  host.setAttribute('aria-hidden', 'true')
  host.setAttribute('data-runtime-capture-projection', 'true')
  Object.assign(host.style, {
    position: 'fixed',
    left: '-100000px',
    top: '0',
    width: `${appPageConfig.value.width}px`,
    height: `${appPageConfig.value.height}px`,
    overflow: 'visible',
    pointerEvents: 'none',
    zIndex: '-1',
  })
  host.innerHTML = sourceElement.outerHTML
  const projectedElement = host.firstElementChild as HTMLElement | null
  if (!projectedElement) {
    styleNodes.forEach(style => style.remove())
    throw new Error('导出页面缺少可捕获的页面源节点')
  }

  const cleanup = () => {
    host.remove()
    styleNodes.forEach(style => style.remove())
  }

  try {
    appendExternalSvgDefinitions(sourceElement, sourceDocument, host)
    document.body.appendChild(host)
    copyIframeCssVariables(sourceElement, sourceDocument, projectedElement)
    copyCanvasContents(sourceElement, projectedElement)
  } catch (error) {
    cleanup()
    throw error
  }

  return {
    element: projectedElement,
    cleanup,
  }
}

/**
 * 复制 iframe 的运行时样式到宿主文档，确保伪元素和页面组件样式可被宿主读取。
 * @param sourceDocument iframe 文档
 * @returns 临时样式节点
 */
function copyIframeStyles(sourceDocument: Document): HTMLStyleElement[] {
  const styleTexts = new Set<string>()
  const styleNodes: HTMLStyleElement[] = []
  const parentStyleSheetHrefs = new Set(
    Array.from(document.styleSheets)
      .map(styleSheet => styleSheet.href)
      .filter((href): href is string => Boolean(href)),
  )

  sourceDocument.querySelectorAll('style').forEach(sourceStyle => {
    const cssText = sourceStyle.textContent?.trim()
    if (!cssText || styleTexts.has(cssText)) {
      return
    }

    const style = document.createElement('style')
    style.textContent = cssText
    if (sourceStyle.media) {
      style.media = sourceStyle.media
    }
    document.head.appendChild(style)
    styleTexts.add(cssText)
    styleNodes.push(style)
  })

  Array.from(sourceDocument.styleSheets).forEach(sourceSheet => {
    const ownerNode = (sourceSheet as CSSStyleSheet).ownerNode as Element | null
    if (ownerNode?.tagName.toLowerCase() === 'style') {
      return
    }

    const sourceHref = sourceSheet.href
    if (sourceHref && parentStyleSheetHrefs.has(sourceHref)) {
      return
    }

    try {
      const cssText = Array.from((sourceSheet as CSSStyleSheet).cssRules)
        .map(rule => rule.cssText)
        .join('\n')
        .trim()
      if (!cssText || styleTexts.has(cssText)) {
        return
      }

      const style = document.createElement('style')
      style.textContent = cssText
      document.head.appendChild(style)
      styleTexts.add(cssText)
      styleNodes.push(style)
    } catch {
      // 跨域样式表无法读取 cssRules 时，宿主 Runtime 自身的公共样式仍可继续参与捕获。
    }
  })

  return styleNodes
}

/**
 * 把 iframe 根节点和祖先链上的 CSS 变量写入投影根，避免宿主页面的主题变量覆盖导出页面。
 * @param sourceElement iframe 页面源节点
 * @param sourceDocument iframe 文档
 * @param projectedElement 宿主投影根节点
 */
function copyIframeCssVariables(
  sourceElement: HTMLElement,
  sourceDocument: Document,
  projectedElement: HTMLElement,
): void {
  const sourceWindow = sourceDocument.defaultView
  if (!sourceWindow) {
    return
  }

  const ancestors: Element[] = [sourceElement]
  let ancestor = sourceElement.parentElement
  while (ancestor) {
    ancestors.push(ancestor)
    ancestor = ancestor.parentElement
  }
  if (sourceDocument.body && !ancestors.includes(sourceDocument.body)) {
    ancestors.push(sourceDocument.body)
  }
  if (sourceDocument.documentElement && !ancestors.includes(sourceDocument.documentElement)) {
    ancestors.push(sourceDocument.documentElement)
  }

  const variableValues = new Map<string, string>()
  ancestors.reverse().forEach(element => {
    const computedStyle = sourceWindow.getComputedStyle(element)
    for (let index = 0; index < computedStyle.length; index += 1) {
      const propertyName = computedStyle[index]
      if (!propertyName?.startsWith('--')) {
        continue
      }

      const propertyValue = computedStyle.getPropertyValue(propertyName).trim()
      if (propertyValue) {
        variableValues.set(propertyName, propertyValue)
      }
    }
  })

  variableValues.forEach((value, name) => {
    projectedElement.style.setProperty(name, value)
  })
}

/**
 * 把页面源节点之外的 SVG defs 临时放入宿主文档，供 SVG use 等引用解析。
 * @param sourceElement iframe 页面源节点
 * @param sourceDocument iframe 文档
 * @param host 宿主投影容器
 */
function appendExternalSvgDefinitions(
  sourceElement: HTMLElement,
  sourceDocument: Document,
  host: HTMLElement,
): void {
  sourceDocument.querySelectorAll('svg').forEach(sourceSvg => {
    if (sourceElement.contains(sourceSvg) || !sourceSvg.querySelector('defs')) {
      return
    }

    const definitionHost = document.createElement('div')
    definitionHost.setAttribute('aria-hidden', 'true')
    Object.assign(definitionHost.style, {
      position: 'absolute',
      left: '0',
      top: '0',
      width: '0',
      height: '0',
      overflow: 'hidden',
      pointerEvents: 'none',
    })
    definitionHost.innerHTML = sourceSvg.outerHTML
    host.appendChild(definitionHost)
  })
}
