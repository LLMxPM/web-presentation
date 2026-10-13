/**
 * PDF导出服务
 * 负责协调页面捕获和PDF生成
 */

import jsPDF from 'jspdf'
import type { Router } from 'vue-router'
import { pageCaptureService } from './PageCaptureService'
import {
  createOffscreenPageStage,
  type OffscreenPageStage,
} from '@/core/services/export/OffscreenPageStage'
import { resolveSnapdomProxyUrl as resolveSharedSnapdomProxyUrl } from '@/core/services/export/ElementRasterizer'
import { ExportTaskRunner } from '@/core/services/export/ExportTaskRunner'
import { resolveExportFilename } from '@/core/services/export/export-filename'
import {
  ExportStatus,
  type CaptureOptions,
  type ExportProgress,
  type ExportTask,
  type PageInfo,
} from '@/core/types/export-common'
import type {
  ExportConfig,
  ExportOptions,
  ExportResult,
  PageCapture,
} from '@/core/types/pdf-export'
import { appPageConfig } from '@/core/utils/config'
import { collectAllExportPages } from '@/core/utils/export-pages'

const PDF_FILE_EXTENSION = '.pdf'

export class PDFExportService {
  private static instance: PDFExportService
  private router: Router | null = null
  private readonly taskRunner = new ExportTaskRunner({
    taskIdPrefix: 'task',
    busyErrorMessage: '已有导出任务正在进行中',
  })

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
    const filename = resolveExportFilename('current', this.router, PDF_FILE_EXTENSION, options?.filename)
    const task = this.taskRunner.beginTask('current', filename)
    let offscreenStage: OffscreenPageStage | undefined

    try {
      // 捕获当前页面
      const currentRoute = this.router?.currentRoute.value
      const routePath = currentRoute?.path
      const routeLocation = currentRoute?.fullPath || routePath
      const stage = currentRoute?.meta?.runtimeProject ? createOffscreenPageStage() : undefined
      offscreenStage = stage
      const canvas = stage && routeLocation
        ? await stage.capture(routeLocation, this.buildCaptureOptions(routePath))
        : await pageCaptureService.captureCurrentPage(this.buildCaptureOptions(routePath))

      // 生成PDF
      const pdf = await this.createPDF()
      this.addCanvasToPDF(pdf, canvas, 0)

      // 下载文件
      pdf.save(filename)

      // 更新任务状态
      this.taskRunner.updateStatus(ExportStatus.COMPLETED)

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
      this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      offscreenStage?.dispose()
      this.taskRunner.finish()
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
    if (this.taskRunner.isRunning()) {
      throw new Error('已有导出任务正在进行中')
    }

    if (!this.router) {
      throw new Error('未设置路由实例，无法导出所有页面')
    }

    const filename = resolveExportFilename('all', this.router, PDF_FILE_EXTENSION, options?.filename)
    const task = this.taskRunner.beginTask('all', filename, onProgress)
    let offscreenStage: OffscreenPageStage | undefined

    try {
      const stage = createOffscreenPageStage()
      offscreenStage = stage

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
        // 取消检查必须放在逐页 try 之外：内层 catch 会吞掉单页错误并继续，取消需要真正中断整个导出。
        if (!this.taskRunner.isRunning()) {
          throw new Error('用户取消导出')
        }

        const page = pages[i]

        try {
          // 更新进度
          this.taskRunner.reportProgress(i, pages.length, page.title)

          // 在独立窗口中捕获，不导航用户当前的演示窗口。
          const canvas = await stage.capture(page.route, this.buildCaptureOptions(page.route))

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
      pdf.save(filename)

      // 更新任务状态
      this.taskRunner.updateStatus(ExportStatus.COMPLETED)

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
      this.taskRunner.updateStatus(ExportStatus.FAILED, error instanceof Error ? error.message : '导出失败')
      throw error
    } finally {
      offscreenStage?.dispose()
      this.taskRunner.finish()
    }
  }

  /**
   * 取消导出
   */
  cancelExport(): void {
    this.taskRunner.cancel()
  }

  /**
   * 获取当前导出任务
   */
  getCurrentTask(): ExportTask | null {
    return this.taskRunner.getCurrentTask()
  }

  /**
   * 检查是否正在导出
   */
  isCurrentlyExporting(): boolean {
    return this.taskRunner.isRunning()
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
    return resolveSharedSnapdomProxyUrl(this.defaultConfig.capture.proxyUrl)
  }
}

// 导出单例实例
export const pdfExportService = PDFExportService.getInstance()
