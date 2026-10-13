/**
 * 文件用途：可编辑 PPTX 导出编排服务，协调离屏 1:1 页面舞台（OffscreenPageStage）、DOM 采集器（PPTXDomConverter）与 PPTX 文档写入器（PptxPackageWriter）。
 */

import type PptxGenJS from 'pptxgenjs'
import { appendEditablePptxPage, appendRasterizedPptxPage, PptxPageExtractionError } from './pptx/PptxPageAssembler'
import { runWithExportDeadline } from './export/ExportCancellation'
import { nextTick } from 'vue'
import type { Router } from 'vue-router'
import { elementRasterizer } from '@/core/services/export/ElementRasterizer'
import { ExportTaskRunner } from '@/core/services/export/ExportTaskRunner'
import {
  pickExportTitle,
  resolveCurrentPageTitle,
  resolveExportFilename,
} from '@/core/services/export/export-filename'
import {
  createOffscreenPageStage,
  type OffscreenPageStage,
} from '@/core/services/export/OffscreenPageStage'
import {
  createEmptyPptxReport,
  mergePptxReportPage,
} from '@/core/services/pptx/ir/PptxReportBuilder'
import {
  PPTXDomConverter,
  type PptxGradientFillInstruction,
} from '@/core/services/pptx/PPTXDomConverter'
import {
  PptxPackageWriter,
  type PptxSlideLayout,
} from '@/core/services/pptx/writer/PptxPackageWriter'
import type { PptxGroupInstruction } from '@/core/services/pptx/writer/OoxmlGroupPatcher'
import {
  PptxThemeResolver,
  type PptxPresentationTheme,
} from '@/core/services/pptx/theme/PptxThemeResolver'
import {
  ExportStatus,
  type ExportProgress,
  type ExportTask,
  type PageInfo,
} from '@/core/types/export-common'
import type {
  PptxExportOptions,
  PptxExportReportPage,
  PptxExportResult,
} from '@/core/types/pptx-export'
import { appConfig as runtimeAppConfig, appPageConfig } from '@/core/utils/config'
import { findRuntimePageSource } from '@/core/utils/export-dom'
import { collectAllExportPages } from '@/core/utils/export-pages'
import { PptxResourceSession, type PptxCanvasSnapshot } from '@/core/services/pptx/session/PptxResourceSession'
import { waitForFiniteDocumentAnimations } from '@/core/utils/visual-assets'

const DEFAULT_CAPTURE_TIMEOUT = 15000
const DEFAULT_RASTER_SCALE = 2
const PPTX_FILE_EXTENSION = '.pptx'

/**
 * 可编辑 PPTX 导出服务。
 */
export class PPTXExportService {
  private static instance: PPTXExportService
  private router: Router | null = null
  private readonly converter = new PPTXDomConverter()
  private readonly packageWriter = new PptxPackageWriter()
  private readonly themeResolver = new PptxThemeResolver()
  private readonly taskRunner = new ExportTaskRunner({
    taskIdPrefix: 'pptx-export',
    busyErrorMessage: '已有导出任务正在进行中',
    retainLockOnCancel: true,
  })

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
   * 遵循方案 A：在平台项目路由（meta.runtimeProject）下使用离屏 1:1 舞台采集，非项目或单测环境回退当前 DOM。
   * @param options 导出选项
   */
  async exportCurrentPage(options?: PptxExportOptions): Promise<PptxExportResult> {
    const filename = resolveExportFilename('current', this.router, PPTX_FILE_EXTENSION, options?.filename)
    const task = this.taskRunner.beginTask('current', filename)
    const currentRoute = this.router?.currentRoute.value
    const routePath = currentRoute?.path
    const routeLocation = currentRoute?.fullPath || routePath
    const pageInfo: PageInfo = {
      route: routePath || '', title: resolveCurrentPageTitle(this.router), order: 1,
      meta: { speakerNotes: this.pickSpeakerNotes(currentRoute?.meta?.speakerNotes) },
    }
    let offscreenStage: OffscreenPageStage | undefined
    let cleanupPreparedPage: (() => void) | undefined

    const resourceSession = new PptxResourceSession(task.id, this.taskRunner.getSignal(task.id) ?? undefined, this.snapshotCanvas())
    const rasterScale = options?.rasterScale ?? DEFAULT_RASTER_SCALE

    try {
      const startedAt = Date.now()
      let pageElement: HTMLElement | null = null

      if (currentRoute?.meta?.runtimeProject && routeLocation) {
        const stage = createOffscreenPageStage()
        offscreenStage = stage
        const prepared = await stage.preparePage(routeLocation, { signal: this.taskRunner.getSignal(task.id) ?? undefined })
        pageElement = prepared.element
        cleanupPreparedPage = prepared.cleanup
      } else {
        await runWithExportDeadline(() => this.waitForPageReady(routePath, task.id), resourceSession.signal, 30000)
        pageElement = findRuntimePageSource(routePath)
      }

      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消导出')
      }

      if (!pageElement) {
        throw new Error('未找到可导出的页面内容')
      }

      const prepDuration = Date.now() - startedAt
      const convStart = Date.now()
      const theme = this.themeResolver.resolveTheme(pageElement)
      const pptx = this.createPresentation(theme, undefined, resourceSession.canvas)
      const report = createEmptyPptxReport()
      const gradientFills: PptxGradientFillInstruction[] = []
      const groupInstructions: PptxGroupInstruction[] = []

      let pageReport: PptxExportReportPage
      try {
        pageReport = await this.addPageToPresentation(
          pptx,
          pageElement,
          pageInfo,
          1,
          gradientFills,
          groupInstructions,
          resourceSession,
          rasterScale,
        )
      } catch (pageError) {
        if (this.taskRunner.isTaskCancelled(task.id)) {
          throw pageError
        }
        if (options?.pageErrorStrategy === 'rasterize-ready-page' && pageError instanceof PptxPageExtractionError) {
          pageReport = await this.rasterizeFallbackPage(
            pptx,
            pageElement,
            pageInfo,
            1,
            pageError,
            resourceSession,
            rasterScale,
          )
        } else {
          throw pageError
        }
      }

      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消导出')
      }

      mergePptxReportPage(report, pageReport)
      const convDuration = Date.now() - convStart
      const packStart = Date.now()

      if (typeof this.packageWriter.generatePresentationBytes === 'function') {
        const bytes = await this.packageWriter.generatePresentationBytes(pptx, gradientFills, groupInstructions)
        if (this.taskRunner.isTaskCancelled(task.id)) {
          throw new Error('用户取消导出')
        }
        this.packageWriter.savePptxBlob?.(filename, bytes)
      } else {
        await this.packageWriter.writePresentationFile(pptx, filename, gradientFills, groupInstructions)
      }
      const packDuration = Date.now() - packStart
      const totalDuration = Date.now() - startedAt

      report.timings = {
        preparationTimeMs: prepDuration,
        conversionTimeMs: convDuration,
        packagingTimeMs: packDuration,
        totalDurationMs: totalDuration,
      }
      report.metrics = resourceSession.getMetrics()

      this.taskRunner.updateStatus(ExportStatus.COMPLETED, undefined, task.id)

      return {
        success: true,
        taskId: task.id,
        method: 'pptx-editable',
        filename,
        pageCount: 1,
        duration: totalDuration,
        message: report.metrics?.rasterizedPageIndices?.length ? '已导出 PPTX，部分页面已降级为整页图片' : '已导出可编辑 PPTX',
        report,
      }
    } catch (error) {
      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw error
      }
      this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败', task.id)
      throw error
    } finally {
      resourceSession.dispose()
      cleanupPreparedPage?.()
      offscreenStage?.dispose()
      this.taskRunner.finish(task.id)
    }
  }

  /**
   * 导出所有页面为可编辑 PPTX。
   * 关键约束：通过离屏 1:1 舞台（OffscreenPageStage）逐页渲染与采集，不篡改主窗口路由。
   * @param options 导出选项
   * @param onProgress 进度回调
   */
  async exportAllPages(
    options?: PptxExportOptions,
    onProgress?: (progress: ExportProgress) => void,
  ): Promise<PptxExportResult> {
    if (this.taskRunner.isRunning()) {
      throw new Error('已有导出任务正在进行中')
    }
    if (!this.router) {
      throw new Error('未设置路由实例，无法导出所有页面')
    }

    const filename = resolveExportFilename('all', this.router, PPTX_FILE_EXTENSION, options?.filename)
    const task = this.taskRunner.beginTask('all', filename, onProgress)
    let offscreenStage: OffscreenPageStage | undefined

    const resourceSession = new PptxResourceSession(task.id, this.taskRunner.getSignal(task.id) ?? undefined, this.snapshotCanvas())
    const rasterScale = options?.rasterScale ?? DEFAULT_RASTER_SCALE

    try {
      const stage = createOffscreenPageStage()
      offscreenStage = stage
      const startedAt = Date.now()
      const pages = await this.getAllPages()
      if (pages.length === 0) {
        throw new Error('未找到可导出的页面')
      }

      task.totalPages = pages.length
      const theme = this.themeResolver.resolveTheme(null)
      const pptx = this.createPresentation(theme, undefined, resourceSession.canvas)
      const report = createEmptyPptxReport()
      const gradientFills: PptxGradientFillInstruction[] = []
      const groupInstructions: PptxGroupInstruction[] = []
      let exportedPages = 0
      const prepDuration = Date.now() - startedAt
      const convStart = Date.now()

      for (let index = 0; index < pages.length; index += 1) {
        if (this.taskRunner.isTaskCancelled(task.id)) {
          throw new Error('用户取消导出')
        }

        const page = pages[index]
        this.taskRunner.reportProgress(index, pages.length, page.title, page.route, task.id)

        const prepared = await stage.preparePage(page.route, { signal: this.taskRunner.getSignal(task.id) ?? undefined })
        try {
          if (this.taskRunner.isTaskCancelled(task.id)) {
            throw new Error('用户取消导出')
          }
          let pageReport: PptxExportReportPage
          try {
            pageReport = await this.addPageToPresentation(
              pptx,
              prepared.element,
              page,
              index + 1,
              gradientFills,
              groupInstructions,
              resourceSession,
              rasterScale,
            )
          } catch (pageError) {
            if (this.taskRunner.isTaskCancelled(task.id)) {
              throw pageError
            }
            if (options?.pageErrorStrategy === 'rasterize-ready-page' && pageError instanceof PptxPageExtractionError) {
              pageReport = await this.rasterizeFallbackPage(
                pptx,
                prepared.element,
                page,
                index + 1,
                pageError,
                resourceSession,
                rasterScale,
              )
            } else {
              throw pageError
            }
          }

          mergePptxReportPage(report, pageReport)
          exportedPages += 1
          task.completedPages = exportedPages
        } finally {
          prepared.cleanup()
        }
      }

      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw new Error('用户取消导出')
      }

      if (exportedPages === 0) {
        throw new Error('没有成功导出任何页面')
      }

      const convDuration = Date.now() - convStart
      const packStart = Date.now()

      if (typeof this.packageWriter.generatePresentationBytes === 'function') {
        const bytes = await this.packageWriter.generatePresentationBytes(pptx, gradientFills, groupInstructions)
        if (this.taskRunner.isTaskCancelled(task.id)) {
          throw new Error('用户取消导出')
        }
        this.packageWriter.savePptxBlob?.(filename, bytes)
      } else {
        await this.packageWriter.writePresentationFile(pptx, filename, gradientFills, groupInstructions)
      }
      const packDuration = Date.now() - packStart
      const totalDuration = Date.now() - startedAt

      report.timings = {
        preparationTimeMs: prepDuration,
        conversionTimeMs: convDuration,
        packagingTimeMs: packDuration,
        totalDurationMs: totalDuration,
      }
      report.metrics = resourceSession.getMetrics()

      this.taskRunner.updateStatus(ExportStatus.COMPLETED, undefined, task.id)

      return {
        success: true,
        taskId: task.id,
        method: 'pptx-editable',
        filename,
        pageCount: exportedPages,
        duration: totalDuration,
        message: report.metrics?.rasterizedPageIndices?.length ? '已导出 PPTX，部分页面已降级为整页图片' : '已导出可编辑 PPTX',
        report,
      }
    } catch (error) {
      if (this.taskRunner.isTaskCancelled(task.id)) {
        throw error
      }
      this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败', task.id)
      throw error
    } finally {
      resourceSession.dispose()
      offscreenStage?.dispose()
      this.taskRunner.finish(task.id)
    }
  }

  /**
   * 取消当前 PPTX 导出任务。
   */
  cancelExport(taskId?: string): void {
    this.taskRunner.cancel(taskId)
  }

  /**
   * 获取当前任务。
   */
  getCurrentTask(): ExportTask | null {
    return this.taskRunner.getCurrentTask()
  }

  /**
   * 判断是否正在导出。
   */
  isCurrentlyExporting(): boolean {
    return this.taskRunner.isRunning()
  }

  /**
   * 判断指定任务是否已被取消。
   * @param taskId 任务 ID
   */
  isTaskCancelled(taskId?: string): boolean {
    return this.taskRunner.isTaskCancelled(taskId)
  }

  /**
   * 创建 PPTX 文件对象（委托给 PptxPackageWriter）。
   */
  private createPresentation(
    theme?: PptxPresentationTheme,
    masterProps?: Record<string, unknown>,
    canvas?: PptxCanvasSnapshot,
  ): PptxGenJS {
    const snapshot = canvas ?? this.snapshotCanvas()
    return this.packageWriter.createPresentation(snapshot.title, snapshot, theme, masterProps)
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
    groupInstructions?: PptxGroupInstruction[],
    resourceSession?: PptxResourceSession,
    rasterScale = DEFAULT_RASTER_SCALE,
  ): Promise<PptxExportReportPage> {
    return appendEditablePptxPage(pptx, this.converter, this.createPageExtractOptions(
      pptx, pageElement, page, pageIndex, resourceSession, rasterScale,
    ), gradientFills, groupInstructions)
  }

  /** 仅在页面提取失败后调用，完整图片取得后再创建备用幻灯片。 */
  private async rasterizeFallbackPage(
    pptx: PptxGenJS,
    pageElement: HTMLElement,
    page: PageInfo,
    pageIndex: number,
    error: unknown,
    resourceSession?: PptxResourceSession,
    rasterScale = DEFAULT_RASTER_SCALE,
  ): Promise<PptxExportReportPage> {
    return appendRasterizedPptxPage(pptx, this.createPageExtractOptions(
      pptx, pageElement, page, pageIndex, resourceSession, rasterScale,
    ), page, error)
  }

  /** 构造单页提取上下文，截图和资源读取沿用本任务的取消信号。 */
  private createPageExtractOptions(
    pptx: PptxGenJS,
    pageElement: HTMLElement,
    page: PageInfo,
    pageIndex: number,
    resourceSession?: PptxResourceSession,
    rasterScale = DEFAULT_RASTER_SCALE,
  ) {
    const canvas = resourceSession?.canvas ?? this.snapshotCanvas()
    const signal = resourceSession?.signal
    return {
      pageElement, pageIndex,
      pageTitle: page.title || `页面 ${pageIndex}`,
      pageRoute: page.route,
      speakerNotes: this.pickSpeakerNotes(page.meta?.speakerNotes),
      pageWidthPx: canvas.widthPx,
      pageHeightPx: canvas.heightPx,
      slideWidthIn: canvas.widthIn,
      slideHeightIn: canvas.heightIn,
      shapeTypes: this.packageWriter.getShapeTypes(pptx),
      captureElementAsPng: (element: HTMLElement) => runWithExportDeadline(
        () => elementRasterizer.captureElementAsPng(element, { scale: rasterScale }), signal,
      ),
      resourceSession, signal,
    }
  }

  /**
   * 按页面比例计算 PPTX slide 尺寸。
   */
  private resolveSlideLayout(): PptxSlideLayout {
    return this.packageWriter.resolveSlideLayout(
      Number(appPageConfig.value.width) || 1920,
      Number(appPageConfig.value.height) || 1080,
    )
  }

  /** 固定本任务的画布尺寸和演示文稿标题。 */
  private snapshotCanvas(): PptxCanvasSnapshot {
    return {
      ...this.resolveSlideLayout(),
      widthPx: Number(appPageConfig.value.width) || 1920,
      heightPx: Number(appPageConfig.value.height) || 1080,
      title: pickExportTitle(runtimeAppConfig.value.app.title) ?? 'Runtime 导出',
    }
  }

  /**
   * 获取当前页演讲者备注。
   */
  private getCurrentPageSpeakerNotes(): string | null {
    return this.pickSpeakerNotes(this.router?.currentRoute.value.meta?.speakerNotes)
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
   * 获取所有按页码排序的页面。
   */
  private async getAllPages(): Promise<PageInfo[]> {
    return collectAllExportPages(this.router)
  }

  /**
   * 等待目标页面渲染、图片和字体就绪（用于非项目模式或单测当前 DOM 回退）。
   * @param expectedRoutePath 期望路由路径
   */
  private async waitForPageReady(expectedRoutePath?: string, taskId?: string): Promise<void> {
    const startedAt = Date.now()

    for (;;) {
      if (taskId && this.taskRunner.isTaskCancelled(taskId)) {
        return
      }

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

    if (taskId && this.taskRunner.isTaskCancelled(taskId)) {
      return
    }

    const pageElement = findRuntimePageSource(expectedRoutePath) ?? document.body
    await this.waitForImages(pageElement, taskId)

    if (taskId && this.taskRunner.isTaskCancelled(taskId)) {
      return
    }

    if (document.fonts?.ready) {
      try {
        await Promise.race([
          document.fonts.ready,
          new Promise(resolve => window.setTimeout(resolve, 5000)),
        ])
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
   * @param taskId 可选任务 ID
   */
  private async waitForImages(root: HTMLElement, taskId?: string): Promise<void> {
    const images = Array.from(root.querySelectorAll('img'))

    await Promise.all(images.map(img => {
      if (taskId && this.taskRunner.isTaskCancelled(taskId)) {
        return Promise.resolve()
      }
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
}

export const pptxExportService = PPTXExportService.getInstance()
