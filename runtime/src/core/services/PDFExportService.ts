/**
 * PDF导出服务
 * 负责协调页面捕获和PDF生成
 */

import jsPDF from 'jspdf'
import type { Router } from 'vue-router'
import { pageCaptureService } from './PageCaptureService'
import { createRuntimeCaptureContext } from './RuntimeCaptureContext'
import { ExportStatus } from '@/core/types/pdf-export'
import { appConfig as runtimeAppConfig, appPageConfig } from '@/core/utils/config'
import { collectAllExportPages } from '@/core/utils/export-pages'
import { getRuntimePreviewContext, getRuntimePreviewToken } from '@/core/utils/path'
import { RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH } from '@/core/shared/runtime-preview'
import { generateFilename } from '../utils/file'
import type {
  ExportOptions,
  ExportProgress,
  ExportTask,
  ExportResult,
  PageCapture,
  ExportConfig,
  PageInfo,
  CaptureOptions
} from '@/core/types/pdf-export'

export class PDFExportService {
  private static instance: PDFExportService
  private currentTask: ExportTask | null = null
  private isExporting = false
  private router: Router | null = null
  private progressCallback: ((progress: ExportProgress) => void) | null = null

  // 默认配置
  private defaultConfig: ExportConfig = {
    pdf: {
      format: 'a4',
      orientation: 'landscape',
      margin: {
        top: 0,
        right: 0,
        bottom: 0,
        left: 0
      }
    },
    capture: {
      quality: 0.95,
      scale: 2,
      timeout: 15000,
      waitForImages: true,
      useCORS: true,
      backgroundColor: '#ffffff', // 使用白色背景避免透明问题
      proxyUrl: undefined
    },
    file: {
      nameTemplate: 'export-{timestamp}',
      includeTimestamp: true,
      compression: true
    }
  }

  /**
   * 获取单例实例
   */
  static getInstance(): PDFExportService {
    if (!PDFExportService.instance) {
      PDFExportService.instance = new PDFExportService()
    }
    return PDFExportService.instance
  }

  /**
   * 设置路由实例
   * @param router Vue Router实例
   */
  setRouter(router: Router): void {
    this.router = router
  }

  /**
   * 导出当前页面
   * @param options 导出选项
   * @returns Promise<ExportResult>
   */
  async exportCurrentPage(options?: ExportOptions): Promise<ExportResult> {
    if (this.isExporting) {
      throw new Error('已有导出任务正在进行中')
    }

    const task = this.createTask('current', options)
    this.currentTask = task
    this.isExporting = true
    const captureContext = this.router?.currentRoute.value.meta?.runtimeProject ? createRuntimeCaptureContext() : undefined

    try {
      // 更新任务状态
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)

      // 捕获当前页面
      const currentRoute = this.router?.currentRoute.value
      const routePath = currentRoute?.path
      const routeLocation = currentRoute?.fullPath || routePath
      const canvas = captureContext && routeLocation
        ? await captureContext.capture(routeLocation, this.buildCaptureOptions(routePath))
        : await pageCaptureService.captureCurrentPage(this.buildCaptureOptions(routePath))

      // 生成PDF
      const pdf = await this.createPDF()
      this.addCanvasToPDF(pdf, canvas, 0)

      // 下载文件
      const filename = task.filename
      pdf.save(filename)

      // 更新任务状态
      this.updateTaskStatus(ExportStatus.COMPLETED)

      const result: ExportResult = {
        success: true,
        taskId: task.id,
        method: 'canvas-pdf',
        filename,
        pageCount: 1,
        duration: Date.now() - task.createdAt.getTime()
      }

      return result
    } catch (error) {
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      captureContext?.dispose()
      this.isExporting = false
      this.currentTask = null
    }
  }

  /**
   * 导出所有页面
   * @param options 导出选项
   * @param onProgress 进度回调函数
   * @returns Promise<ExportResult>
   */
  async exportAllPages(
    options?: ExportOptions,
    onProgress?: (progress: ExportProgress) => void
  ): Promise<ExportResult> {
    if (this.isExporting) {
      throw new Error('已有导出任务正在进行中')
    }

    if (!this.router) {
      throw new Error('未设置路由实例，无法导出所有页面')
    }

    const task = this.createTask('all', options)
    const captureContext = createRuntimeCaptureContext()
    this.currentTask = task
    this.isExporting = true
    this.progressCallback = onProgress

    try {
      // 更新任务状态
      this.updateTaskStatus(ExportStatus.IN_PROGRESS)

      // 获取所有页面路由
      const pages = await this.getAllPages()
      if (pages.length === 0) {
        throw new Error('未找到可导出的页面')
      }

      // 更新任务总页面数
      task.totalPages = pages.length

      // 创建PDF实例
      const pdf = await this.createPDF()
      const captures: PageCapture[] = []

      // 逐页捕获和添加到PDF
      for (let i = 0; i < pages.length; i++) {
        const page = pages[i]

        try {
          // 更新进度
          this.updateProgress(i, pages.length, page.title)

          // 在独立窗口中捕获，不导航用户当前的演示窗口。
          const canvas = await captureContext.capture(page.route, this.buildCaptureOptions(page.route))

          // 添加到PDF（第一页不需要新建页面）
          if (captures.length > 0) {
            pdf.addPage()
          }
          this.addCanvasToPDF(pdf, canvas, i)

          // 记录捕获信息
          const capture: PageCapture = {
            id: `capture-${i}`,
            taskId: task.id,
            pageTitle: page.title,
            pageRoute: page.route,
            captureCanvas: canvas,
            order: i,
            capturedAt: new Date(),
            dimensions: {
              width: canvas.width,
              height: canvas.height
            }
          }
          captures.push(capture)

          // 更新已完成页面数
          task.completedPages = i + 1

        } catch (error) {
          console.error(`页面 ${page.title} 导出失败:`, error)
          // 继续处理下一页，不中断整个导出过程
        }
      }

      if (captures.length === 0) {
        throw new Error('没有成功捕获任何页面')
      }

      // 下载文件
      const filename = task.filename
      pdf.save(filename)

      // 更新任务状态
      this.updateTaskStatus(ExportStatus.COMPLETED)

      const result: ExportResult = {
        success: true,
        taskId: task.id,
        method: 'canvas-pdf',
        filename,
        pageCount: captures.length,
        duration: Date.now() - task.createdAt.getTime()
      }

      return result
    } catch (error) {
      this.updateTaskStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      captureContext.dispose()
      this.isExporting = false
      this.currentTask = null
      this.progressCallback = null
    }
  }

  /**
   * 取消导出
   */
  cancelExport(): void {
    if (this.currentTask && this.isExporting) {
      this.updateTaskStatus(ExportStatus.CANCELLED)
      this.isExporting = false
      this.currentTask = null
      this.progressCallback = null
    }
  }

  /**
   * 获取当前导出任务
   */
  getCurrentTask(): ExportTask | null {
    return this.currentTask
  }

  /**
   * 检查是否正在导出
   */
  isCurrentlyExporting(): boolean {
    return this.isExporting
  }

  /**
   * 创建导出任务
   * @param mode 导出模式
   * @param options 导出选项
   * @returns ExportTask
   */
  private createTask(mode: 'current' | 'all', options?: ExportOptions): ExportTask {
    const now = new Date()
    return {
      id: `task-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
      mode,
      status: ExportStatus.PENDING,
      progress: 0,
      filename: this.generateExportFilename(mode, options),
      totalPages: mode === 'current' ? 1 : 0,
      completedPages: 0,
      createdAt: now,
      updatedAt: now
    }
  }

  /**
   * 生成导出文件名。
   * @param mode 导出范围
   * @param options 导出选项
   */
  private generateExportFilename(mode: 'current' | 'all', options?: ExportOptions): string {
    return generateFilename(options?.filename, `${this.getDefaultFilenameBase(mode)}-{timestamp}`)
  }

  /**
   * 根据导出范围获取默认文件名主体。
   * @param mode 导出范围
   */
  private getDefaultFilenameBase(mode: 'current' | 'all'): string {
    if (mode === 'all') {
      return this.pickTitle(runtimeAppConfig.value.app.title) ?? '项目'
    }

    const routeTitle = this.pickTitle(this.router?.currentRoute.value.meta?.title)
    const documentTitle = typeof document === 'undefined' ? undefined : this.pickTitle(document.title)

    return routeTitle ?? documentTitle ?? this.pickTitle(runtimeAppConfig.value.app.title) ?? '页面'
  }

  /**
   * 规范化标题文本，空字符串不作为有效标题。
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
   * 更新任务状态
   * @param status 新状态
   * @param error 错误信息
   */
  private updateTaskStatus(status: ExportStatus, error?: string): void {
    if (this.currentTask) {
      this.currentTask.status = status
      this.currentTask.updatedAt = new Date()
      if (error) {
        this.currentTask.error = error
      }
    }
  }

  /**
   * 更新导出进度
   * @param current 当前页面索引
   * @param total 总页面数
   * @param currentPageTitle 当前页面标题
   */
  private updateProgress(current: number, total: number, currentPageTitle: string): void {
    if (this.currentTask) {
      const percentage = Math.round((current / total) * 100)
      this.currentTask.progress = percentage

      if (this.progressCallback) {
        this.progressCallback({
          current: current + 1,
          total,
          percentage,
          currentPageTitle,
          currentPageRoute: ''
        })
      }
    }
  }

  /**
   * 获取所有页面信息
   * @returns Promise<PageInfo[]>
   */
  private async getAllPages(): Promise<PageInfo[]> {
    return collectAllExportPages(this.router)
  }

  /**
   * 创建PDF实例
   * @returns jsPDF实例
   */
  private async createPDF(): Promise<jsPDF> {
    const pageConfigWidth = Number(appPageConfig.value.width) || 1920
    const pageConfigHeight = Number(appPageConfig.value.height) || 1080
    const aspectRatio = pageConfigWidth / pageConfigHeight
    const longEdge = 297
    const pageWidth = aspectRatio >= 1 ? longEdge : longEdge * aspectRatio
    const pageHeight = aspectRatio >= 1 ? longEdge / aspectRatio : longEdge

    return new jsPDF({
      orientation: pageWidth > pageHeight ? 'landscape' : 'portrait',
      unit: 'mm',
      format: [pageWidth, pageHeight],
      compress: this.defaultConfig.file.compression,
      putOnlyUsedFonts: true,
      floatPrecision: 16
    })
  }

  /**
   * 将Canvas添加到PDF
   * @param pdf PDF实例
   * @param canvas Canvas元素
   * @param pageIndex 页面索引
   */
  private addCanvasToPDF(pdf: jsPDF, canvas: HTMLCanvasElement, pageIndex: number): void {
    void pageIndex
    // 获取PDF页面尺寸
    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()

    // 项目需要，不需要边距，改为全幅铺满（cover），通过裁剪消除空白边距
    const availableWidth = pageWidth
    const availableHeight = pageHeight

    // 根据PDF页面的宽高比裁剪原始canvas，避免留白且不拉伸
    const pageRatio = availableWidth / availableHeight
    const canvasRatio = canvas.width / canvas.height

    // 计算裁剪区域（源矩形）以匹配页面宽高比
    let sx = 0
    let sy = 0
    let sWidth = canvas.width
    let sHeight = canvas.height

    if (canvasRatio > pageRatio) {
      // 原画面更宽，裁掉左右两侧
      sWidth = Math.round(canvas.height * pageRatio)
      sx = Math.round((canvas.width - sWidth) / 2)
    } else if (canvasRatio < pageRatio) {
      // 原画面更高，裁掉上下两侧
      sHeight = Math.round(canvas.width / pageRatio)
      sy = Math.round((canvas.height - sHeight) / 2)
    }

    // 使用一个中间画布进行裁剪，保持较高质量
    const cropCanvas = document.createElement('canvas')
    const cropCtx = cropCanvas.getContext('2d')
    if (!cropCtx) {
      throw new Error('无法创建裁剪Canvas上下文')
    }

    // 为减少再次缩放导致的失真，按照源裁剪区域的像素尺寸生成目标图
    cropCanvas.width = sWidth
    cropCanvas.height = sHeight
    cropCtx.imageSmoothingEnabled = true
    cropCtx.imageSmoothingQuality = 'high'
    cropCtx.drawImage(canvas, sx, sy, sWidth, sHeight, 0, 0, sWidth, sHeight)

    // 导出裁剪后的图像数据
    const quality = Math.min(this.defaultConfig.capture.quality, 0.95)
    const imgData = cropCanvas.toDataURL('image/jpeg', quality)

    // 将裁剪后的图片以铺满的方式添加到PDF页面（无留白）
    const x = 0
    const y = 0
    const imgWidth = availableWidth
    const imgHeight = availableHeight

    try {
      pdf.addImage(imgData, 'JPEG', x, y, imgWidth, imgHeight, '', 'FAST')
    } catch (error) {
      console.warn('添加高质量图片失败，尝试压缩图片:', error)
      const fallbackImgData = cropCanvas.toDataURL('image/jpeg', 0.7)
      pdf.addImage(fallbackImgData, 'JPEG', x, y, imgWidth, imgHeight)
    }
  }

  /**
   * 构造统一的截图参数。
   * @param routePath 目标路由路径
   */
  private buildCaptureOptions(routePath?: string): CaptureOptions {
    return {
      scale: this.defaultConfig.capture.scale,
      useCORS: this.defaultConfig.capture.useCORS,
      allowTaint: false,
      backgroundColor: this.defaultConfig.capture.backgroundColor,
      timeout: this.defaultConfig.capture.timeout,
      proxyUrl: this.resolveSnapdomProxyUrl(),
      routePath,
    }
  }

  /**
   * 解析 snapDOM 跨域资源代理地址。
   * 优先使用显式环境变量；SaaS 预览下自动回退到 Runtime 同源代理，避免远端图片缺少 CORS 时截图空白。
   */
  private resolveSnapdomProxyUrl(): string | undefined {
    const explicitProxyUrl = String(
      import.meta.env.VITE_SNAPDOM_PROXY_URL
      || this.defaultConfig.capture.proxyUrl
      || '',
    ).trim()
    if (explicitProxyUrl) {
      return explicitProxyUrl
    }

    if (typeof window === 'undefined') {
      return undefined
    }

    const previewContext = getRuntimePreviewContext()
    const previewToken = getRuntimePreviewToken()
    if (!previewContext?.artifactId || !previewToken) {
      return undefined
    }

    const runtimePublicBaseUrl = this.resolveRuntimePublicBaseUrl()
    const proxyBaseUrl = runtimePublicBaseUrl || window.location.origin
    const proxyUrl = new URL(
      RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH.replace(/^\/+/, ''),
      `${proxyBaseUrl.replace(/\/+$/, '')}/`,
    )
    proxyUrl.searchParams.set('artifactId', previewContext.artifactId)
    proxyUrl.searchParams.set('token', previewToken)
    proxyUrl.searchParams.set('url', '')

    return proxyUrl.href
  }

  /**
   * 读取预览 HTML 注入的 Runtime 公开基址。
   * @returns 规范化后的 Runtime 公开基址，缺失或非法时返回空串
   */
  private resolveRuntimePublicBaseUrl(): string {
    const runtimePublicBaseUrl = String(window.__RUNTIME_PUBLIC_BASE_URL__ || '').trim()
    if (!runtimePublicBaseUrl) {
      return ''
    }

    try {
      return new URL(runtimePublicBaseUrl, window.location.href).href.replace(/\/+$/, '')
    } catch {
      return ''
    }
  }


}

// 导出单例实例
export const pdfExportService = PDFExportService.getInstance()
