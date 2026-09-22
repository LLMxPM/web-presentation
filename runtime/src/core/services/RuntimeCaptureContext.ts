/** 文件功能：在独立同源 iframe 中捕获项目页面，不改变交互窗口路由或频道。 */
import { appPageConfig } from '../utils/config'
import type { CaptureOptions } from '../types/pdf-export'
import { copyCanvasContents } from '../utils/export-dom'
import { pageCaptureService } from './PageCaptureService'

interface RuntimeCaptureRoute {
  path: string
  hash: string
}

interface ParentCaptureProjection {
  element: HTMLElement
  cleanup: () => void
}

/**
 * 将 Vue Router 的完整地址转换为 Runtime 捕获 hash。
 * @param route 页面路径，可包含 query
 * @param baseHref 当前 Runtime 地址，用于解析相对路径
 * @returns 规范化页面路径和带捕获标记的 hash
 */
export function resolveRuntimeCaptureRoute(route: string, baseHref = window.location.href): RuntimeCaptureRoute {
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

/** 创建单任务截图窗口；调用方必须在 finally 中释放。 */
export function createRuntimeCaptureContext() {
  const frame = document.createElement('iframe')
  frame.title = 'Runtime 导出捕获'
  frame.setAttribute('aria-hidden', 'true')
  frame.inert = true
  Object.assign(frame.style, { position: 'fixed', left: '-100000px', top: '0', border: '0', width: `${appPageConfig.value.width}px`, height: `${appPageConfig.value.height}px` })
  document.body.appendChild(frame)
  let disposed = false

  /** 重载独立运行时并等待目标页面与启动就绪标记，失败不捕获错误页面。 */
  async function capture(route: string, options?: CaptureOptions): Promise<HTMLCanvasElement> {
    const captureRoute = resolveRuntimeCaptureRoute(route)
    const url = new URL(window.location.href)
    url.hash = captureRoute.hash
    frame.src = url.href
    const started = Date.now()
    while (!disposed && Date.now() - started < 30000) {
      const targetWindow = frame.contentWindow
      const doc = frame.contentDocument
      const target = doc?.querySelector<HTMLElement>('.runtime-page-print-source')
      if (targetWindow?.__EDITOR_RUNTIME_PREVIEW_READY__ && target?.dataset.runtimeRoutePath === captureRoute.path && !doc?.querySelector('[role="alert"]')) {
        await doc?.fonts?.ready
        const projection = projectIframeTarget(target, doc)
        try {
          return await pageCaptureService.captureElement(projection.element, options)
        } finally {
          projection.cleanup()
        }
      }
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    throw new Error(disposed ? '截图任务已释放' : `等待导出页面超时：${route}`)
  }

  /** 释放 iframe，同时终止页面脚本与媒体资源。 */
  function dispose(): void { disposed = true; frame.remove() }
  return { capture, dispose }
}

/**
 * 将 iframe 页面投影到宿主文档，再交给宿主的 snapdom 实例捕获。
 * snapdom 会从宿主全局 document 读取样式和 SVG defs，直接传入 iframe 元素会丢失伪元素、SVG 引用和部分画布内容。
 * @param sourceElement iframe 中的页面源节点
 * @param sourceDocument iframe 文档
 * @returns 宿主文档中的捕获节点和清理函数
 */
function projectIframeTarget(sourceElement: HTMLElement, sourceDocument: Document): ParentCaptureProjection {
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
 * 复制 iframe 的运行时样式到宿主文档，确保伪元素和页面组件样式可被 snapdom 解析。
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
function copyIframeCssVariables(sourceElement: HTMLElement, sourceDocument: Document, projectedElement: HTMLElement): void {
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
function appendExternalSvgDefinitions(sourceElement: HTMLElement, sourceDocument: Document, host: HTMLElement): void {
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
