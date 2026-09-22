/**
 * 文件用途：浏览器打印 PDF 服务，负责构建专用打印文档并调用浏览器打印。
 */

import { nextTick } from 'vue'
import type { Router } from 'vue-router'
import { appPageConfig } from '@/core/utils/config'
import { collectAllExportPages } from '@/core/utils/export-pages'
import type {
  ExportOptions,
  ExportProgress,
  ExportResult,
  ExportTask,
  PageInfo,
} from '@/core/types/pdf-export'
import { ExportStatus } from '@/core/types/pdf-export'

const PRINT_IFRAME_ID = 'runtime-browser-print-frame'
const PRINT_READY_DELAY = 100

/**
 * 浏览器打印服务。
 * 关键约束：浏览器打印只能打开系统打印对话框，无法强制保存文件名或判断用户是否完成保存。
 */
export class BrowserPrintService {
  private static instance: BrowserPrintService
  private router: Router | null = null
  private currentTask: ExportTask | null = null
  private isPrinting = false
  private progressCallback: ((progress: ExportProgress) => void) | null = null
  private activeIframe: HTMLIFrameElement | null = null

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
    if (this.isPrinting) {
      throw new Error('已有打印任务正在进行中')
    }

    const task = this.createTask('current')
    this.currentTask = task
    this.isPrinting = true

    try {
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)
      const startedAt = Date.now()
      await this.waitForPageReady()

      const pageElement = this.getCurrentPageElement()
      if (!pageElement) {
        throw new Error('未找到可打印的页面内容')
      }

      const iframe = this.createPrintIframe()
      this.preparePrintDocument(iframe)
      this.appendPrintPage(iframe, pageElement)
      await this.flushPrintDocument(iframe)
      this.invokePrint(iframe)

      this.updateTaskStatus(ExportStatus.COMPLETED)

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
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '打印失败')
      this.cleanupPrintIframe()
      throw error
    } finally {
      this.isPrinting = false
      this.currentTask = null
      this.progressCallback = null
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
    if (this.isPrinting) {
      throw new Error('已有打印任务正在进行中')
    }

    if (!this.router) {
      throw new Error('未设置路由实例，无法打印所有页面')
    }

    const task = this.createTask('all')
    const originalRoute = this.router.currentRoute.value.fullPath
    this.currentTask = task
    this.isPrinting = true
    this.progressCallback = onProgress ?? null

    try {
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)
      const startedAt = Date.now()
      const pages = await this.getAllPages()

      if (pages.length === 0) {
        throw new Error('未找到可打印的页面')
      }

      task.totalPages = pages.length
      const iframe = this.createPrintIframe()
      this.preparePrintDocument(iframe)
      let printedPages = 0

      for (let index = 0; index < pages.length; index += 1) {
        const page = pages[index]
        this.updateProgress(index, pages.length, page)
        await this.navigateToPage(page.route)
        await this.waitForPageReady(page.route)

        const pageElement = this.getCurrentPageElement(page.route)
        if (!pageElement) {
          console.warn(`页面 ${page.title} 未找到可打印内容，已跳过`)
          continue
        }

        this.appendPrintPage(iframe, pageElement)
        printedPages += 1
        task.completedPages = printedPages
      }

      if (printedPages === 0) {
        throw new Error('没有成功收集任何可打印页面')
      }

      await this.flushPrintDocument(iframe)
      this.invokePrint(iframe)
      this.updateTaskStatus(ExportStatus.COMPLETED)

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
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '打印失败')
      this.cleanupPrintIframe()
      throw error
    } finally {
      await this.restoreRoute(originalRoute)
      this.isPrinting = false
      this.currentTask = null
      this.progressCallback = null
    }
  }

  /**
   * 取消当前打印任务并清理临时 iframe。
   */
  cancelPrint(): void {
    if (!this.isPrinting) {
      return
    }

    this.updateTaskStatus(ExportStatus.CANCELLED)
    this.cleanupPrintIframe()
    this.isPrinting = false
    this.currentTask = null
    this.progressCallback = null
  }

  /**
   * 获取当前打印任务。
   */
  getCurrentTask(): ExportTask | null {
    return this.currentTask
  }

  /**
   * 检查是否正在打印。
   */
  isCurrentlyPrinting(): boolean {
    return this.isPrinting
  }

  /**
   * 创建打印任务。
   * @param mode 打印范围
   */
  private createTask(mode: 'current' | 'all'): ExportTask {
    const now = new Date()
    return {
      id: `browser-print-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
      mode,
      status: ExportStatus.PENDING,
      progress: 0,
      filename: '',
      totalPages: mode === 'current' ? 1 : 0,
      completedPages: 0,
      createdAt: now,
      updatedAt: now,
    }
  }

  /**
   * 更新任务状态。
   * @param status 新状态
   * @param error 错误信息
   */
  private updateTaskStatus(status: ExportStatus, error?: string): void {
    if (!this.currentTask) {
      return
    }

    this.currentTask.status = status
    this.currentTask.updatedAt = new Date()
    if (error) {
      this.currentTask.error = error
    }
  }

  /**
   * 更新打印进度。
   * @param index 当前页面索引
   * @param total 总页面数量
   * @param page 当前页面信息
   */
  private updateProgress(index: number, total: number, page: PageInfo): void {
    if (this.currentTask) {
      this.currentTask.progress = Math.round((index / total) * 100)
    }

    this.progressCallback?.({
      current: index + 1,
      total,
      percentage: Math.round((index / total) * 100),
      currentPageTitle: page.title,
      currentPageRoute: page.route,
    })
  }

  /**
   * 获取所有按页码排序的页面。
   */
  private async getAllPages(): Promise<PageInfo[]> {
    return collectAllExportPages(this.router)
  }

  /**
   * 导航到指定页面。
   * @param route 页面路由
   */
  private async navigateToPage(route: string): Promise<void> {
    if (!this.router) {
      throw new Error('路由实例未设置')
    }

    await this.router.push(route)
  }

  /**
   * 恢复打印前的路由位置。
   * @param route 原始路由
   */
  private async restoreRoute(route: string): Promise<void> {
    if (!this.router || !route || this.router.currentRoute.value.fullPath === route) {
      return
    }

    try {
      await this.router.push(route)
      await this.waitForPageReady(this.router.currentRoute.value.path)
    } catch (error) {
      console.warn('恢复打印前路由失败:', error)
    }
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

    const sourceStyle = window.getComputedStyle(sourceCanvas)
    if (!clonedCanvas.style.width && sourceStyle.width && sourceStyle.width !== 'auto') {
      clonedCanvas.style.width = sourceStyle.width
    }
    if (!clonedCanvas.style.height && sourceStyle.height && sourceStyle.height !== 'auto') {
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
