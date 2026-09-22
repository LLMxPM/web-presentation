/**
 * 文件用途：可编辑 PPTX 导出服务，负责路由遍历、页面等待、DOM 转换和 PPTX 文件生成。
 */

import PptxGenJS from 'pptxgenjs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { nextTick } from 'vue'
import type { Router } from 'vue-router'
import { pageCaptureService } from '@/core/services/PageCaptureService'
import { ExportStatus, type ExportProgress, type ExportTask, type PageInfo } from '@/core/types/pdf-export'
import type {
  PptxExportOptions,
  PptxExportReport,
  PptxExportReportPage,
  PptxExportResult,
} from '@/core/types/pptx-export'
import { appConfig as runtimeAppConfig, appPageConfig } from '@/core/utils/config'
import { findRuntimePageSource } from '@/core/utils/export-dom'
import { collectAllExportPages } from '@/core/utils/export-pages'
import { generateFilename } from '@/core/utils/file'
import { waitForFiniteDocumentAnimations } from '@/core/utils/visual-assets'
import { PPTXDomConverter, type PptxGradientFillInstruction } from '@/core/services/pptx/PPTXDomConverter'

const PPTX_LAYOUT_NAME = 'RUNTIME_PPTX_LAYOUT'
const DEFAULT_CAPTURE_SCALE = 2
const DEFAULT_CAPTURE_TIMEOUT = 15000

interface PptxSlideLayout {
  widthIn: number
  heightIn: number
}

/**
 * 可编辑 PPTX 导出服务。
 */
export class PPTXExportService {
  private static instance: PPTXExportService
  private router: Router | null = null
  private currentTask: ExportTask | null = null
  private isExporting = false
  private progressCallback: ((progress: ExportProgress) => void) | null = null
  private readonly converter = new PPTXDomConverter()

  /**
   * 获取单例实例。
   */
  static getInstance(): PPTXExportService {
    if (!PPTXExportService.instance) {
      PPTXExportService.instance = new PPTXExportService()
    }
    return PPTXExportService.instance
  }

  /**
   * 设置路由实例。
   * @param router Vue Router 实例
   */
  setRouter(router: Router): void {
    this.router = router
  }

  /**
   * 导出当前页面为可编辑 PPTX。
   * @param options 导出选项
   */
  async exportCurrentPage(options?: PptxExportOptions): Promise<PptxExportResult> {
    if (this.isExporting) {
      throw new Error('已有导出任务正在进行中')
    }

    const task = this.createTask('current', options)
    this.currentTask = task
    this.isExporting = true

    try {
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)
      const startedAt = Date.now()
      await this.waitForPageReady(this.router?.currentRoute.value.path)

      const routePath = this.router?.currentRoute.value.path
      const pageElement = findRuntimePageSource(routePath)
      if (!pageElement) {
        throw new Error('未找到可导出的页面内容')
      }

      const pptx = this.createPresentation()
      const report = this.createEmptyReport()
      const gradientFills: PptxGradientFillInstruction[] = []
      const pageTitle = this.getCurrentPageTitle()
      const pageReport = await this.addPageToPresentation(pptx, pageElement, {
        route: routePath || '',
        title: pageTitle,
        order: 1,
        meta: {
          speakerNotes: this.getCurrentPageSpeakerNotes(),
        },
      }, 1, gradientFills)
      this.appendReportPage(report, pageReport)

      const filename = task.filename
      await this.writePresentationFile(pptx, filename, gradientFills)
      this.updateTaskStatus(ExportStatus.COMPLETED)

      return {
        success: true,
        taskId: task.id,
        method: 'pptx-editable',
        filename,
        pageCount: 1,
        duration: Date.now() - startedAt,
        message: '已导出可编辑 PPTX',
        report,
      }
    } catch (error) {
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      this.isExporting = false
      this.currentTask = null
      this.progressCallback = null
    }
  }

  /**
   * 导出所有页面为可编辑 PPTX。
   * @param options 导出选项
   * @param onProgress 进度回调
   */
  async exportAllPages(
    options?: PptxExportOptions,
    onProgress?: (progress: ExportProgress) => void,
  ): Promise<PptxExportResult> {
    if (this.isExporting) {
      throw new Error('已有导出任务正在进行中')
    }
    if (!this.router) {
      throw new Error('未设置路由实例，无法导出所有页面')
    }

    const task = this.createTask('all', options)
    const originalRoute = this.router.currentRoute.value.fullPath
    this.currentTask = task
    this.isExporting = true
    this.progressCallback = onProgress ?? null

    try {
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)
      const startedAt = Date.now()
      const pages = await this.getAllPages()
      if (pages.length === 0) {
        throw new Error('未找到可导出的页面')
      }

      task.totalPages = pages.length
      const pptx = this.createPresentation()
      const report = this.createEmptyReport()
      const gradientFills: PptxGradientFillInstruction[] = []
      let exportedPages = 0

      for (let index = 0; index < pages.length; index += 1) {
        if (!this.isExporting) {
          throw new Error('用户取消导出')
        }

        const page = pages[index]
        this.updateProgress(index, pages.length, page)
        await this.navigateToPage(page.route)
        await this.waitForPageReady(page.route)

        const pageElement = findRuntimePageSource(page.route)
        if (!pageElement) {
          console.warn(`页面 ${page.title} 未找到可导出内容，已跳过`)
          continue
        }

        const pageReport = await this.addPageToPresentation(pptx, pageElement, page, index + 1, gradientFills)
        this.appendReportPage(report, pageReport)
        exportedPages += 1
        task.completedPages = exportedPages
      }

      if (exportedPages === 0) {
        throw new Error('没有成功导出任何页面')
      }

      const filename = task.filename
      await this.writePresentationFile(pptx, filename, gradientFills)
      this.updateTaskStatus(ExportStatus.COMPLETED)

      return {
        success: true,
        taskId: task.id,
        method: 'pptx-editable',
        filename,
        pageCount: exportedPages,
        duration: Date.now() - startedAt,
        message: '已导出可编辑 PPTX',
        report,
      }
    } catch (error) {
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      await this.restoreRoute(originalRoute)
      this.isExporting = false
      this.currentTask = null
      this.progressCallback = null
    }
  }

  /**
   * 取消当前 PPTX 导出任务。
   */
  cancelExport(): void {
    if (!this.isExporting) {
      return
    }

    this.updateTaskStatus(ExportStatus.CANCELLED)
    this.isExporting = false
    this.currentTask = null
    this.progressCallback = null
  }

  /**
   * 获取当前任务。
   */
  getCurrentTask(): ExportTask | null {
    return this.currentTask
  }

  /**
   * 判断是否正在导出。
   */
  isCurrentlyExporting(): boolean {
    return this.isExporting
  }

  /**
   * 创建 PPTX 文件对象。
   */
  private createPresentation(): PptxGenJS {
    const pptx = new PptxGenJS()
    const layout = this.resolveSlideLayout()

    pptx.defineLayout({
      name: PPTX_LAYOUT_NAME,
      width: layout.widthIn,
      height: layout.heightIn,
    })
    pptx.layout = PPTX_LAYOUT_NAME
    pptx.author = 'web-runtime-vue'
    pptx.company = 'web-runtime-vue'
    pptx.subject = 'Runtime editable PPTX export'
    pptx.title = this.pickTitle(runtimeAppConfig.value.app.title) ?? 'Runtime 导出'
    pptx.theme = {
      headFontFace: 'Microsoft YaHei',
      bodyFontFace: 'Microsoft YaHei',
    }

    return pptx
  }

  /**
   * 添加一页到 PPTX。
   * @param pptx PPTX 对象
   * @param pageElement 页面源节点
   * @param page 页面信息
   * @param pageIndex 页码索引
   * @param gradientFills 需要写入 PPTX XML 的渐变填充指令
   */
  private async addPageToPresentation(
    pptx: PptxGenJS,
    pageElement: HTMLElement,
    page: PageInfo,
    pageIndex: number,
    gradientFills: PptxGradientFillInstruction[],
  ): Promise<PptxExportReportPage> {
    const slide = pptx.addSlide()
    const layout = this.resolveSlideLayout()
    const pageWidthPx = appPageConfig.value.width || 1920
    const pageHeightPx = appPageConfig.value.height || 1080
    const speakerNotes = this.pickSpeakerNotes(page.meta?.speakerNotes)

    if (speakerNotes) {
      slide.addNotes(speakerNotes)
    }

    return this.converter.convertPage({
      slide,
      pageElement,
      pageIndex,
      pageTitle: page.title || `页面 ${pageIndex}`,
      pageRoute: page.route,
      pageWidthPx,
      pageHeightPx,
      slideWidthIn: layout.widthIn,
      slideHeightIn: layout.heightIn,
      shapeTypes: {
        rect: pptx.ShapeType.rect,
        roundRect: pptx.ShapeType.roundRect,
        ellipse: pptx.ShapeType.ellipse,
        line: pptx.ShapeType.line,
      },
      captureElementAsPng: element => this.captureElementAsPng(element),
      gradientFillCollector: instruction => gradientFills.push(instruction),
    })
  }

  /**
   * 写出 PPTX 文件，必要时先把单色兜底填充替换为原生渐变填充。
   * @param pptx PPTX 对象
   * @param filename 文件名
   * @param gradientFills 渐变填充指令
   */
  private async writePresentationFile(
    pptx: PptxGenJS,
    filename: string,
    gradientFills: PptxGradientFillInstruction[],
  ): Promise<void> {
    if (gradientFills.length === 0) {
      await pptx.writeFile({ fileName: filename, compression: true })
      return
    }

    const rawPptx = await pptx.write({ outputType: 'uint8array', compression: true }) as Uint8Array
    const patchedPptx = this.patchGradientFills(rawPptx, gradientFills)
    this.savePptxBlob(filename, patchedPptx)
  }

  /**
   * 将 PPTX zip 内指定形状的填充替换为 OOXML 原生渐变。
   * @param data PPTX zip 字节
   * @param gradientFills 渐变填充指令
   */
  private patchGradientFills(
    data: Uint8Array,
    gradientFills: PptxGradientFillInstruction[],
  ): Uint8Array {
    const files = unzipSync(data)
    const fillsByPage = new Map<number, PptxGradientFillInstruction[]>()
    for (const instruction of gradientFills) {
      const pageFills = fillsByPage.get(instruction.pageIndex) ?? []
      pageFills.push(instruction)
      fillsByPage.set(instruction.pageIndex, pageFills)
    }

    for (const [pageIndex, pageFills] of fillsByPage) {
      const slidePath = `ppt/slides/slide${pageIndex}.xml`
      const slideFile = files[slidePath]
      if (!slideFile) {
        continue
      }

      let slideXml = strFromU8(slideFile)
      for (const instruction of pageFills) {
        slideXml = this.patchGradientFillInSlideXml(slideXml, instruction)
      }
      files[slidePath] = strToU8(slideXml)
    }

    return zipSync(files, { level: 6 })
  }

  /**
   * 替换单个 slide XML 内目标形状的 fill 节点。
   * @param slideXml slide XML 内容
   * @param instruction 渐变填充指令
   */
  private patchGradientFillInSlideXml(
    slideXml: string,
    instruction: PptxGradientFillInstruction,
  ): string {
    const objectName = this.escapeRegExp(this.escapeXmlAttribute(instruction.objectName))
    const shapeRegex = new RegExp(
      `(<p:sp>[\\s\\S]*?<p:cNvPr[^>]*\\bname="${objectName}"[^>]*>[\\s\\S]*?<p:spPr[^>]*>[\\s\\S]*?)(<a:solidFill>[\\s\\S]*?<\\/a:solidFill>|<a:noFill\\s*\\/>)`,
    )

    return slideXml.replace(shapeRegex, `$1${this.buildGradientFillXml(instruction)}`)
  }

  /**
   * 构造 OOXML 渐变填充片段。
   * @param instruction 渐变填充指令
   */
  private buildGradientFillXml(instruction: PptxGradientFillInstruction): string {
    const stopsXml = instruction.stops
      .map(stop => {
        const position = Math.round(Math.max(0, Math.min(1, stop.position)) * 100000)
        const alpha = Math.round(Math.max(0, Math.min(1, stop.color.alpha)) * 100000)
        return `<a:gs pos="${position}"><a:srgbClr val="${stop.color.hex}"><a:alpha val="${alpha}"/></a:srgbClr></a:gs>`
      })
      .join('')
    const angle = this.gradientDirectionToPptAngle(instruction.direction) * 60000
    return `<a:gradFill rotWithShape="1"><a:gsLst>${stopsXml}</a:gsLst><a:lin ang="${angle}" scaled="0"/></a:gradFill>`
  }

  /**
   * 将 CSS 线性渐变方向映射为 PPT 角度。
   * @param direction CSS 目标方向
   */
  private gradientDirectionToPptAngle(direction: PptxGradientFillInstruction['direction']): number {
    switch (direction) {
      case 'left':
        return 180
      case 'bottom':
        return 90
      case 'top':
        return 270
      case 'right':
      default:
        return 0
    }
  }

  /**
   * 下载内存中的 PPTX 字节。
   * @param filename 文件名
   * @param data PPTX 文件字节
   */
  private savePptxBlob(filename: string, data: Uint8Array): void {
    const arrayBuffer = new ArrayBuffer(data.byteLength)
    new Uint8Array(arrayBuffer).set(data)
    const blob = new Blob([arrayBuffer], {
      type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => window.URL.revokeObjectURL(url), 100)
  }

  /**
   * 转义正则特殊字符。
   * @param value 原始文本
   */
  private escapeRegExp(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  /**
   * 转义 XML 属性值。
   * @param value 原始属性值
   */
  private escapeXmlAttribute(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  /**
   * 局部截图并返回 PNG data URL。
   * 说明：PPTX 局部截图需要保留透明区域，避免圆角、阴影和叠层被白底污染。
   * @param element 目标元素
   */
  private async captureElementAsPng(element: HTMLElement): Promise<string> {
    const canvas = await pageCaptureService.captureElement(element, {
      scale: DEFAULT_CAPTURE_SCALE,
      backgroundColor: 'transparent',
      timeout: DEFAULT_CAPTURE_TIMEOUT,
    })
    return canvas.toDataURL('image/png')
  }

  /**
   * 按页面比例计算 PPTX slide 尺寸。
   */
  private resolveSlideLayout(): PptxSlideLayout {
    const pageWidth = Number(appPageConfig.value.width) || 1920
    const pageHeight = Number(appPageConfig.value.height) || 1080
    const aspectRatio = pageWidth / pageHeight
    const longEdge = 13.333

    if (aspectRatio >= 1) {
      return {
        widthIn: longEdge,
        heightIn: longEdge / aspectRatio,
      }
    }

    return {
      widthIn: longEdge * aspectRatio,
      heightIn: longEdge,
    }
  }

  /**
   * 创建导出任务。
   * @param mode 导出范围
   * @param options 导出选项
   */
  private createTask(mode: 'current' | 'all', options?: PptxExportOptions): ExportTask {
    const now = new Date()
    return {
      id: `pptx-export-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
      mode,
      status: ExportStatus.PENDING,
      progress: 0,
      filename: this.generateExportFilename(mode, options),
      totalPages: mode === 'current' ? 1 : 0,
      completedPages: 0,
      createdAt: now,
      updatedAt: now,
    }
  }

  /**
   * 生成 PPTX 文件名。
   * @param mode 导出范围
   * @param options 导出选项
   */
  private generateExportFilename(mode: 'current' | 'all', options?: PptxExportOptions): string {
    return generateFilename(options?.filename, `${this.getDefaultFilenameBase(mode)}-{timestamp}`, true, '.pptx')
  }

  /**
   * 获取默认文件名主体。
   * @param mode 导出范围
   */
  private getDefaultFilenameBase(mode: 'current' | 'all'): string {
    if (mode === 'all') {
      return this.pickTitle(runtimeAppConfig.value.app.title) ?? '项目'
    }

    return this.getCurrentPageTitle()
  }

  /**
   * 获取当前页标题。
   */
  private getCurrentPageTitle(): string {
    const routeTitle = this.pickTitle(this.router?.currentRoute.value.meta?.title)
    const documentTitle = typeof document === 'undefined' ? undefined : this.pickTitle(document.title)
    return routeTitle ?? documentTitle ?? this.pickTitle(runtimeAppConfig.value.app.title) ?? '页面'
  }

  /**
   * 获取当前页演讲者备注。
   */
  private getCurrentPageSpeakerNotes(): string | null {
    return this.pickSpeakerNotes(this.router?.currentRoute.value.meta?.speakerNotes)
  }

  /**
   * 规范化标题文本。
   * @param title 候选标题
   */
  private pickTitle(title: unknown): string | undefined {
    if (typeof title !== 'string') {
      return undefined
    }

    const normalizedTitle = title.trim()
    return normalizedTitle.length > 0 ? normalizedTitle : undefined
  }

  /**
   * 规范化演讲者备注，空白备注不写入 PPTX。
   * @param notes 候选备注
   */
  private pickSpeakerNotes(notes: unknown): string | null {
    if (typeof notes !== 'string') {
      return null
    }

    const normalizedNotes = notes.trim()
    return normalizedNotes.length > 0 ? normalizedNotes : null
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
   * 更新导出进度。
   * @param index 当前页面索引
   * @param total 页面总数
   * @param page 当前页面
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
   * 恢复导出前路由。
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
      console.warn('恢复 PPTX 导出前路由失败:', error)
    }
  }

  /**
   * 等待目标页面渲染、图片和字体就绪。
   * @param expectedRoutePath 期望路由路径
   */
  private async waitForPageReady(expectedRoutePath?: string): Promise<void> {
    const startedAt = Date.now()

    for (;;) {
      await nextTick()
      await this.waitForAnimationFrame()

      const hasRouteMarkers = !!document.querySelector('.runtime-page-print-source')
      if (!expectedRoutePath || findRuntimePageSource(expectedRoutePath) || !hasRouteMarkers) {
        break
      }

      if (Date.now() - startedAt > 8000) {
        console.warn(`等待页面 ${expectedRoutePath} 渲染超时，将尝试使用当前页面内容`)
        break
      }

      await new Promise(resolve => window.setTimeout(resolve, 50))
    }

    const pageElement = findRuntimePageSource(expectedRoutePath) ?? document.body
    await this.waitForImages(pageElement)

    if (document.fonts?.ready) {
      try {
        await document.fonts.ready
      } catch (error) {
        console.warn('等待字体加载失败:', error)
      }
    }

    await waitForFiniteDocumentAnimations(DEFAULT_CAPTURE_TIMEOUT)
    await this.waitForAnimationFrame()
    await this.waitForAnimationFrame()
  }

  /**
   * 等待一帧浏览器绘制。
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
   * 等待图片加载完成。
   * @param root 查询根节点
   */
  private async waitForImages(root: HTMLElement): Promise<void> {
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
   * 创建空报告。
   */
  private createEmptyReport(): PptxExportReport {
    return {
      summary: {
        editableText: 0,
        editableShape: 0,
        editableTable: 0,
        imageBlock: 0,
        svgBlock: 0,
        screenshotBlock: 0,
        skipped: 0,
      },
      pages: [],
    }
  }

  /**
   * 合并单页报告。
   * @param report 总报告
   * @param pageReport 单页报告
   */
  private appendReportPage(report: PptxExportReport, pageReport: PptxExportReportPage): void {
    report.pages.push(pageReport)

    pageReport.items.forEach(item => {
      switch (item.result) {
        case 'editable-text':
          report.summary.editableText += 1
          break
        case 'editable-shape':
          report.summary.editableShape += 1
          break
        case 'editable-table':
          report.summary.editableTable += 1
          break
        case 'image':
          report.summary.imageBlock += 1
          break
        case 'svg':
          report.summary.svgBlock += 1
          break
        case 'screenshot':
          report.summary.screenshotBlock += 1
          break
        case 'skipped':
          report.summary.skipped += 1
          break
      }
    })
  }
}

export const pptxExportService = PPTXExportService.getInstance()
