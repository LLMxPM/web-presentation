/**
 * 文件用途：浏览器打印 PDF 服务，负责构建专用打印文档并调用浏览器打印。
 */

import { nextTick } from 'vue'
import type { Router } from 'vue-router'
import { ExportTaskRunner } from '@/core/services/export/ExportTaskRunner'
import {
  createOffscreenPageStage,
  freezeDocumentAnimationsToFinalState,
  type OffscreenPageStage,
} from '@/core/services/export/OffscreenPageStage'
import {
  ExportStatus,
  type ExportProgress,
  type ExportTask,
  type PageInfo,
} from '@/core/types/export-common'
import type {
  ExportOptions,
  ExportResult,
} from '@/core/types/pdf-export'
import { appPageConfig } from '@/core/utils/config'
import { collectAllExportPages } from '@/core/utils/export-pages'
import { cleanupModelStaticFrames, prepareModelStaticFrames } from '@/core/services/export/model-static-frames'

const PRINT_IFRAME_ID = 'runtime-browser-print-frame'
const PRINT_READY_DELAY = 100

/**
 * 浏览器打印服务。
 * 关键约束：浏览器打印只能打开系统打印对话框，无法强制保存文件名或判断用户是否完成保存。
 */
export class BrowserPrintService {
  private static instance: BrowserPrintService
  private router: Router | null = null
  private activeIframe: HTMLIFrameElement | null = null
  private readonly taskRunner = new ExportTaskRunner({
    taskIdPrefix: 'browser-print',
    busyErrorMessage: '已有打印任务正在进行中',
    // 取消后保持占用到 finally 释放离屏舞台，避免新旧任务共用捕获窗口。
    retainLockOnCancel: true,
  })

  /**
   * 获取单例实例。
   */
  static getInstance(): BrowserPrintService {
    if (!BrowserPrintService.instance) {
      BrowserPrintService.instance = new BrowserPrintService()
    }
    return BrowserPrintService.instance
  }

  /**
   * 设置路由实例。
   * @param router Vue Router 实例
   */
  setRouter(router: Router): void {
    this.router = router
  }

  /**
   * 通过浏览器打印当前页面。
   * @param options 打印选项
   * @returns 打印调用结果
   */
  async printCurrentPage(options?: ExportOptions): Promise<ExportResult> {
    const task = this.taskRunner.beginTask('current', '')
    let offscreenStage: OffscreenPageStage | undefined
    let cleanupPreparedPage: (() => void) | undefined

    try {
      const startedAt = Date.now()
      const signal = this.taskRunner.getSignal(task.id) ?? undefined
      const currentRoute = this.router?.currentRoute.value
      let pageElement: HTMLElement | null = null

      if (currentRoute?.meta?.runtimeProject && currentRoute.fullPath) {
        // 放映中打印当前页也走离屏静态舞台，避免主画布在采集期间被计时器翻页。
        const stage = createOffscreenPageStage()
        offscreenStage = stage
        const prepared = await stage.preparePage(currentRoute.fullPath, { signal })
        pageElement = prepared.element
        cleanupPreparedPage = prepared.cleanup
      } else {
        await this.waitForPageReady()
        pageElement = this.getCurrentPageElement()
        if (pageElement) await freezeDocumentAnimationsToFinalState(pageElement.ownerDocument)
      }

      if (!pageElement) {
        throw new Error('未找到可打印的页面内容')
      }
      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消打印')
      }

      const iframe = this.createPrintIframe()
      this.preparePrintDocument(iframe)
      this.appendPrintPage(iframe, pageElement)
      await this.flushPrintDocument(iframe)

      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消打印')
      }
      this.invokePrint(iframe)

      this.taskRunner.updateStatus(ExportStatus.COMPLETED, undefined, task.id)

      return {
        success: true,
        taskId: task.id,
        method: 'browser-print',
        filename: options?.filename,
        pageCount: 1,
        duration: Date.now() - startedAt,
        message: '已打开浏览器打印对话框，请选择“保存为 PDF”。',
      }
    } catch (error) {
      if (!this.taskRunner.isTaskCancelled(task.id)) {
        this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '打印失败', task.id)
      }
      this.cleanupPrintIframe()
      throw error
    } finally {
      cleanupPreparedPage?.()
      offscreenStage?.dispose()
      this.taskRunner.finish()
    }
  }

  /**
   * 通过浏览器打印所有页面。
   * @param options 打印选项
   * @param onProgress 页面处理进度回调
   * @returns 打印调用结果
   */
  async printAllPages(
    options?: ExportOptions,
    onProgress?: (progress: ExportProgress) => void,
  ): Promise<ExportResult> {
    if (this.taskRunner.isRunning()) {
      throw new Error('已有打印任务正在进行中')
    }

    if (!this.router) {
      throw new Error('未设置路由实例，无法打印所有页面')
    }

    const task = this.taskRunner.beginTask('all', '', onProgress)
    let offscreenStage: OffscreenPageStage | undefined

    try {
      const startedAt = Date.now()
      const pages = await this.getAllPages()

      if (pages.length === 0) {
        throw new Error('未找到可打印的页面')
      }

      task.totalPages = pages.length
      const stage = createOffscreenPageStage()
      offscreenStage = stage
      const signal = this.taskRunner.getSignal(task.id) ?? undefined
      const iframe = this.createPrintIframe()
      this.preparePrintDocument(iframe)
      let printedPages = 0

      // 每页都在独立离屏舞台渲染，不导航正在放映的主画布。
      for (let index = 0; index < pages.length; index += 1) {
        if (this.taskRunner.isTaskCancelled(task.id)) {
          throw new Error('用户取消打印')
        }

        const page = pages[index]
        this.taskRunner.reportProgress(index, pages.length, page.title, page.route, task.id)

        const prepared = await stage.preparePage(page.route, { signal })
        try {
          if (this.taskRunner.isTaskCancelled(task.id)) {
            throw new Error('用户取消打印')
          }
          this.appendPrintPage(iframe, prepared.element)
          printedPages += 1
          task.completedPages = printedPages
        } finally {
          prepared.cleanup()
        }
      }

      if (printedPages === 0) {
        throw new Error('没有成功收集任何可打印页面')
      }

      await this.flushPrintDocument(iframe)

      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消打印')
      }
      this.invokePrint(iframe)
      this.taskRunner.updateStatus(ExportStatus.COMPLETED, undefined, task.id)

      return {
        success: true,
        taskId: task.id,
        method: 'browser-print',
        filename: options?.filename,
        pageCount: printedPages,
        duration: Date.now() - startedAt,
        message: '已打开浏览器打印对话框，请选择“保存为 PDF”。',
      }
    } catch (error) {
      if (!this.taskRunner.isTaskCancelled(task.id)) {
        this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '打印失败', task.id)
      }
      this.cleanupPrintIframe()
      throw error
    } finally {
      offscreenStage?.dispose()
      this.taskRunner.finish()
    }
  }

  /**
   * 取消当前打印任务并清理临时 iframe。
   */
  cancelPrint(): void {
    if (this.taskRunner.cancel()) {
      this.cleanupPrintIframe()
    }
  }

  /**
   * 获取当前打印任务。
   */
  getCurrentTask(): ExportTask | null {
    return this.taskRunner.getCurrentTask()
  }

  /**
   * 检查是否正在打印。
   */
  isCurrentlyPrinting(): boolean {
    return this.taskRunner.isRunning()
  }

  /**
   * 获取所有按页码排序的页面。
   */
  private async getAllPages(): Promise<PageInfo[]> {
    return collectAllExportPages(this.router)
  }

  /**
   * 等待当前页面渲染、图片和字体就绪。
   */
  private async waitForPageReady(expectedRoutePath?: string): Promise<void> {
    const startedAt = Date.now()

    for (;;) {
      await nextTick()
      await this.waitForAnimationFrame()

      const hasRouteMarkers = !!document.querySelector('.runtime-page-print-source')

      if (!expectedRoutePath || this.getCurrentPageElement(expectedRoutePath) || !hasRouteMarkers) {
        break
      }

      if (Date.now() - startedAt > 8000) {
        console.warn(`等待页面 ${expectedRoutePath} 渲染超时，将尝试使用当前页面内容`)
        break
      }

      await new Promise(resolve => window.setTimeout(resolve, 50))
    }

    await this.waitForImages(document)

    if (document.fonts?.ready) {
      try {
        await document.fonts.ready
      } catch (error) {
        console.warn('等待字体加载失败:', error)
      }
    }

    await new Promise(resolve => setTimeout(resolve, PRINT_READY_DELAY))
  }

  /**
   * 等待一次浏览器绘制帧。
   */
  private async waitForAnimationFrame(): Promise<void> {
    await new Promise(resolve => {
      if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(() => resolve(undefined))
        return
      }
      window.setTimeout(resolve, 16)
    })
  }

  /**
   * 等待指定文档或元素中的图片加载完成。
   * @param root 文档或元素
   */
  private async waitForImages(root: Document | HTMLElement): Promise<void> {
    const images = Array.from(root.querySelectorAll('img'))

    await Promise.all(images.map(img => {
      if (img.complete && img.naturalWidth > 0) {
        return Promise.resolve()
      }

      return new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, 5000)
        const finish = () => {
          window.clearTimeout(timer)
          resolve()
        }

        img.addEventListener('load', finish, { once: true })
        img.addEventListener('error', finish, { once: true })
      })
    }))
  }

  /**
   * 查找当前真实演示页面节点。
   */
  private getCurrentPageElement(expectedRoutePath?: string): HTMLElement | null {
    if (expectedRoutePath) {
      const routeElement = Array.from(document.querySelectorAll<HTMLElement>('.runtime-page-print-source'))
        .find(element => element.dataset.runtimeRoutePath === expectedRoutePath && this.isVisiblePageElement(element))

      if (routeElement) {
        return routeElement
      }

      return null
    }

    const currentRoutePath = this.router?.currentRoute.value.path
    if (currentRoutePath) {
      const routeElement = Array.from(document.querySelectorAll<HTMLElement>('.runtime-page-print-source'))
        .find(element => element.dataset.runtimeRoutePath === currentRoutePath && this.isVisiblePageElement(element))

      if (routeElement) {
        return routeElement
      }
    }

    const container = document.querySelector('.page-content-wrapper .fixed-ratio-container, main .fixed-ratio-container, .fixed-ratio-container') as HTMLElement | null
    if (!container) {
      return null
    }

    const child = container.firstElementChild as HTMLElement | null
    return child ?? container
  }

  /**
   * 判断页面节点是否已进入可打印状态。
   * @param element 页面节点
   */
  private isVisiblePageElement(element: HTMLElement): boolean {
    const style = window.getComputedStyle(element)

    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      Number(style.opacity) !== 0
  }

  /**
   * 创建隐藏打印 iframe。
   */
  private createPrintIframe(): HTMLIFrameElement {
    this.cleanupPrintIframe()

    const iframe = document.createElement('iframe')
    iframe.id = PRINT_IFRAME_ID
    iframe.setAttribute('aria-hidden', 'true')
    iframe.style.position = 'fixed'
    iframe.style.right = '0'
    iframe.style.bottom = '0'
    iframe.style.width = '0'
    iframe.style.height = '0'
    iframe.style.border = '0'
    iframe.style.opacity = '0'
    iframe.style.pointerEvents = 'none'

    document.body.appendChild(iframe)
    this.activeIframe = iframe
    return iframe
  }

  /**
   * 初始化打印文档结构和样式。
   * @param iframe 打印 iframe
   */
  private preparePrintDocument(iframe: HTMLIFrameElement): void {
    const iframeDocument = this.getIframeDocument(iframe)
    iframeDocument.open()
    iframeDocument.write(`<!doctype html><html><head><meta charset="utf-8"><title>Print</title></head><body><div id="print-root"></div></body></html>`)
    iframeDocument.close()

    const base = iframeDocument.createElement('base')
    base.href = document.baseURI
    iframeDocument.head.appendChild(base)
    this.copyDocumentStyles(iframeDocument)

    const style = iframeDocument.createElement('style')
    style.setAttribute('data-runtime-print-style', 'true')
    style.textContent = this.createPrintCss()
    iframeDocument.head.appendChild(style)

    const runtimeVariables = iframeDocument.createElement('style')
    runtimeVariables.setAttribute('data-runtime-print-variables', 'true')
    runtimeVariables.textContent = this.createRuntimeVariableCss()
    iframeDocument.head.appendChild(runtimeVariables)
  }

  /**
   * 将当前页面样式复制到打印文档。
   * @param targetDocument iframe 文档
   */
  private copyDocumentStyles(targetDocument: Document): void {
    document.querySelectorAll('link[rel="stylesheet"], style').forEach(node => {
      targetDocument.head.appendChild(node.cloneNode(true))
    })
  }

  /**
   * 生成打印 CSS。
   */
  private createPrintCss(): string {
    const pageWidth = appPageConfig.value.width || 1920
    const pageHeight = appPageConfig.value.height || 1080
    const ratio = pageWidth / pageHeight
    const longEdge = 11.69
    const shortEdge = longEdge / ratio
    const widthInches = ratio >= 1 ? longEdge : longEdge * ratio
    const heightInches = ratio >= 1 ? shortEdge : longEdge
    const contentScale = (widthInches * 96) / pageWidth

    return `
      @page {
        size: ${widthInches.toFixed(4)}in ${heightInches.toFixed(4)}in;
        margin: 0;
      }

      html,
      body {
        width: ${widthInches.toFixed(4)}in;
        min-height: ${heightInches.toFixed(4)}in;
        margin: 0;
        padding: 0;
        background: #fff;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }

      *,
      *::before,
      *::after {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
        box-sizing: border-box;
      }

      #print-root {
        margin: 0;
        padding: 0;
      }

      .print-page {
        position: relative;
        width: ${widthInches.toFixed(4)}in;
        height: ${heightInches.toFixed(4)}in;
        margin: 0;
        padding: 0;
        overflow: hidden;
        background: #fff;
        break-after: page;
        page-break-after: always;
      }

      .print-page:last-child {
        break-after: auto;
        page-break-after: auto;
      }

      .print-page__content {
        position: absolute;
        inset: 0;
        width: ${pageWidth}px;
        height: ${pageHeight}px;
        overflow: hidden;
        zoom: ${contentScale};
        transform: none !important;
        transform-origin: top left;
        box-shadow: none !important;
        border-radius: 0 !important;
      }

      .print-page__content > * {
        width: ${pageWidth}px !important;
        height: ${pageHeight}px !important;
        min-width: ${pageWidth}px !important;
        min-height: ${pageHeight}px !important;
        max-width: none !important;
        max-height: none !important;
        overflow: hidden !important;
      }

      .runtime-page-print-source,
      .runtime-page-print-source > * {
        width: ${pageWidth}px !important;
        height: ${pageHeight}px !important;
        min-width: ${pageWidth}px !important;
        min-height: ${pageHeight}px !important;
        max-width: none !important;
        max-height: none !important;
        overflow: hidden !important;
      }

      .fixed-ratio-container,
      .page-content-wrapper,
      .main-content {
        transform: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
      }
    `
  }

  /**
   * 生成当前运行时 CSS 变量快照，确保打印文档的主题色与预览一致。
   */
  private createRuntimeVariableCss(): string {
    const variables = this.collectRuntimeCssVariables()
    if (variables.length === 0) {
      return ''
    }

    const cssText = variables.map(([name, value]) => `${name}: ${value};`).join('\n')

    return `
      :root,
      body,
      #print-root,
      .print-page,
      .print-page__content {
        ${cssText}
      }
    `
  }

  /**
   * 收集主题、Tailwind 和运行时布局相关 CSS 变量。
   */
  private collectRuntimeCssVariables(): Array<[string, string]> {
    const variableMap = new Map<string, string>()
    const sources = [
      document.documentElement,
      document.body,
      document.querySelector('.responsive-layout'),
      document.querySelector('.runtime-page-print-source'),
    ].filter((element): element is Element => Boolean(element))

    sources.forEach(element => {
      const style = window.getComputedStyle(element)
      for (let index = 0; index < style.length; index += 1) {
        const propertyName = style[index]
        if (!this.isRuntimeCssVariable(propertyName)) {
          continue
        }

        const propertyValue = style.getPropertyValue(propertyName).trim()
        if (propertyValue) {
          variableMap.set(propertyName, propertyValue)
        }
      }
    })

    return Array.from(variableMap.entries())
  }

  /**
   * 判断 CSS 变量是否属于打印所需的运行时变量。
   * @param propertyName CSS 属性名
   */
  private isRuntimeCssVariable(propertyName: string): boolean {
    return propertyName.startsWith('--theme-') ||
      propertyName.startsWith('--tw-color-') ||
      propertyName.startsWith('--tw-font-') ||
      propertyName.startsWith('--bottom-preview-')
  }

  /**
   * 追加一页打印内容。
   * @param iframe 打印 iframe
   * @param sourceElement 当前页面节点
   */
  private appendPrintPage(iframe: HTMLIFrameElement, sourceElement: HTMLElement): void {
    const iframeDocument = this.getIframeDocument(iframe)
    const root = iframeDocument.getElementById('print-root')
    if (!root) {
      throw new Error('打印文档初始化失败')
    }

    // 静态帧必须在 clone 前准备：克隆的 WebGL 画布没有像素缓冲，打印文档里只能靠 PNG 覆盖图。
    const staticFrames = prepareModelStaticFrames(sourceElement)
    try {
      const page = iframeDocument.createElement('section')
      page.className = 'print-page'

      const content = iframeDocument.createElement('div')
      content.className = 'print-page__content'

      const clone = sourceElement.cloneNode(true) as HTMLElement
      this.copyCanvasContents(sourceElement, clone)
      clone.style.transform = 'none'
      clone.style.transformOrigin = 'top left'
      clone.style.width = `${appPageConfig.value.width || 1920}px`
      clone.style.height = `${appPageConfig.value.height || 1080}px`
      clone.style.minWidth = `${appPageConfig.value.width || 1920}px`
      clone.style.minHeight = `${appPageConfig.value.height || 1080}px`
      clone.style.overflow = 'hidden'
      content.appendChild(clone)
      page.appendChild(content)
      root.appendChild(page)
    } finally {
      cleanupModelStaticFrames(staticFrames)
    }
  }

  /**
   * 将源页面中 canvas 的位图内容同步到克隆节点。
   *
   * @param sourceRoot 源页面节点
   * @param clonedRoot 克隆后的页面节点
   */
  private copyCanvasContents(sourceRoot: HTMLElement, clonedRoot: HTMLElement): void {
    const sourceCanvases = this.collectCanvasElements(sourceRoot)
    const clonedCanvases = this.collectCanvasElements(clonedRoot)

    sourceCanvases.forEach((sourceCanvas, index) => {
      const clonedCanvas = clonedCanvases[index]
      if (!clonedCanvas) {
        return
      }

      this.copyCanvasBitmap(sourceCanvas, clonedCanvas)
    })
  }

  /**
   * 按 DOM 顺序收集节点自身和子级中的 canvas。
   *
   * @param root 查询根节点
   * @returns canvas 节点列表
   */
  private collectCanvasElements(root: HTMLElement): HTMLCanvasElement[] {
    const canvases = Array.from(root.querySelectorAll<HTMLCanvasElement>('canvas'))

    if (root.tagName.toLowerCase() === 'canvas') {
      return [root as HTMLCanvasElement, ...canvases]
    }

    return canvases
  }

  /**
   * 复制单个 canvas 的像素缓冲；cloneNode 不会复制这部分浏览器内部状态。
   *
   * @param sourceCanvas 源 canvas
   * @param clonedCanvas 克隆 canvas
   */
  private copyCanvasBitmap(sourceCanvas: HTMLCanvasElement, clonedCanvas: HTMLCanvasElement): void {
    if (sourceCanvas.width <= 0 || sourceCanvas.height <= 0) {
      return
    }

    clonedCanvas.width = sourceCanvas.width
    clonedCanvas.height = sourceCanvas.height

    // 离屏舞台中的画布属于 iframe 文档，必须使用其自身 window 解析计算样式。
    const styleWindow = sourceCanvas.ownerDocument.defaultView
    const sourceStyle = styleWindow?.getComputedStyle(sourceCanvas)
    if (!clonedCanvas.style.width && sourceStyle?.width && sourceStyle.width !== 'auto') {
      clonedCanvas.style.width = sourceStyle.width
    }
    if (!clonedCanvas.style.height && sourceStyle?.height && sourceStyle.height !== 'auto') {
      clonedCanvas.style.height = sourceStyle.height
    }

    try {
      const context = clonedCanvas.getContext('2d')
      context?.clearRect(0, 0, clonedCanvas.width, clonedCanvas.height)
      context?.drawImage(sourceCanvas, 0, 0)
    } catch (error) {
      console.warn('复制打印 canvas 位图失败，相关图表可能无法出现在浏览器打印结果中:', error)
    }
  }

  /**
   * 等待打印文档中的图片和字体就绪。
   * @param iframe 打印 iframe
   */
  private async flushPrintDocument(iframe: HTMLIFrameElement): Promise<void> {
    const iframeDocument = this.getIframeDocument(iframe)
    await this.waitForImages(iframeDocument)

    if (iframeDocument.fonts?.ready) {
      try {
        await iframeDocument.fonts.ready
      } catch (error) {
        console.warn('等待打印文档字体加载失败:', error)
      }
    }

    await new Promise(resolve => setTimeout(resolve, PRINT_READY_DELAY))
  }

  /**
   * 调用浏览器打印对话框。
   * @param iframe 打印 iframe
   */
  private invokePrint(iframe: HTMLIFrameElement): void {
    const printWindow = iframe.contentWindow
    if (!printWindow) {
      throw new Error('无法访问打印窗口')
    }

    const cleanup = () => this.cleanupPrintIframe()
    printWindow.addEventListener('afterprint', cleanup, { once: true })
    printWindow.focus()
    printWindow.print()
    window.setTimeout(cleanup, 60000)
  }

  /**
   * 获取 iframe 文档。
   * @param iframe 打印 iframe
   */
  private getIframeDocument(iframe: HTMLIFrameElement): Document {
    const iframeDocument = iframe.contentDocument || iframe.contentWindow?.document
    if (!iframeDocument) {
      throw new Error('无法创建打印文档')
    }

    return iframeDocument
  }

  /**
   * 清理临时打印 iframe。
   */
  private cleanupPrintIframe(): void {
    const iframe = this.activeIframe || document.getElementById(PRINT_IFRAME_ID)
    if (iframe?.parentNode) {
      iframe.parentNode.removeChild(iframe)
    }
    this.activeIframe = null
  }
}

// 导出单例实例
export const browserPrintService = BrowserPrintService.getInstance()
