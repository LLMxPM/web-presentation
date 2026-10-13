/**
 * 文件用途：提供通用的导出任务状态机、进度上报、取消控制与默认文件名生成能力，供 PPTX、PDF、浏览器打印服务复用。
 */

import type { Router } from 'vue-router'
import {
  ExportStatus,
  type ExportMode,
  type ExportProgress,
  type ExportTask,
} from '@/core/types/export-common'
import { appConfig as runtimeAppConfig } from '@/core/utils/config'
import { generateFilename } from '@/core/utils/file'

/**
 * 导出任务生命周期管理器的构造配置。
 */
export interface ExportTaskRunnerConfig {
  /** 任务 ID 前缀，如 'pptx-export' / 'task' / 'browser-print' */
  taskIdPrefix: string
  /** 重复触发时的错误提示文案 */
  busyErrorMessage: string
  /** 默认文件扩展名（如 '.pdf' 或 '.pptx'，为空则不生成默认文件名） */
  fileExtension?: string
}

/**
 * 通用导出任务状态机与文件名/标题解析工具。
 */
export class ExportTaskRunner {
  private currentTask: ExportTask | null = null
  private active = false
  private progressCallback: ((progress: ExportProgress) => void) | null = null
  private readonly config: ExportTaskRunnerConfig

  constructor(config: ExportTaskRunnerConfig) {
    this.config = config
  }

  /**
   * 判断当前是否有任务正在执行。
   */
  isRunning(): boolean {
    return this.active
  }

  /**
   * 获取当前任务快照。
   */
  getCurrentTask(): ExportTask | null {
    return this.currentTask
  }

  /**
   * 启动一个导出任务并设为 IN_PROGRESS 状态。
   * @param mode 导出范围
   * @param filename 最终文件名
   * @param onProgress 可选进度回调
   * @returns 创建并启动的 ExportTask
   */
  beginTask(
    mode: ExportMode,
    filename: string,
    onProgress?: (progress: ExportProgress) => void,
  ): ExportTask {
    if (this.active) {
      throw new Error(this.config.busyErrorMessage)
    }

    const now = new Date()
    const task: ExportTask = {
      id: `${this.config.taskIdPrefix}-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
      mode,
      status: ExportStatus.IN_PROGRESS,
      progress: 0,
      filename,
      totalPages: mode === 'current' ? 1 : 0,
      completedPages: 0,
      createdAt: now,
      updatedAt: now,
    }

    this.currentTask = task
    this.active = true
    this.progressCallback = onProgress ?? null
    return task
  }

  /**
   * 更新任务状态。
   * @param status 新状态
   * @param error 可选错误信息
   */
  updateStatus(status: ExportStatus, error?: string): void {
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
   * 上报当前页面的处理进度。
   * @param index 当前页面索引（从 0 开始）
   * @param total 总页面数
   * @param title 当前页面标题
   * @param route 当前页面路由，未参与上报时留空
   */
  reportProgress(index: number, total: number, title: string, route = ''): void {
    const percentage = Math.round((index / total) * 100)
    if (this.currentTask) {
      this.currentTask.progress = percentage
    }

    this.progressCallback?.({
      current: index + 1,
      total,
      percentage,
      currentPageTitle: title,
      currentPageRoute: route,
    })
  }

  /**
   * 取消当前任务并重置活动标记。
   * @returns 是否实际取消了正在运行的任务
   */
  cancel(): boolean {
    if (!this.active) {
      return false
    }

    this.updateStatus(ExportStatus.CANCELLED)
    this.finish()
    return true
  }

  /**
   * 清理当前任务的运行态引用（通常在 finally 中调用）。
   */
  finish(): void {
    this.active = false
    this.currentTask = null
    this.progressCallback = null
  }

  /**
   * 生成带时间戳和扩展名的导出文件名。
   * @param mode 导出范围
   * @param router 当前路由器
   * @param customFilename 用户自定义文件名
   * @returns 最终文件名
   */
  resolveFilename(mode: ExportMode, router: Router | null, customFilename?: string): string {
    if (!this.config.fileExtension) {
      return customFilename ?? ''
    }
    const baseName = this.getDefaultFilenameBase(mode, router)
    return generateFilename(customFilename, `${baseName}-{timestamp}`, true, this.config.fileExtension)
  }

  /**
   * 获取默认文件名主体（全部页面用项目标题，单页用当前页标题）。
   * @param mode 导出范围
   * @param router 当前路由器
   */
  getDefaultFilenameBase(mode: ExportMode, router: Router | null): string {
    if (mode === 'all') {
      return this.pickTitle(runtimeAppConfig.value.app.title) ?? '项目'
    }
    return this.getCurrentPageTitle(router)
  }

  /**
   * 获取当前页面标题（按路由 meta.title -> document.title -> 项目标题 -> '页面' 顺序回退）。
   * @param router 当前路由器
   */
  getCurrentPageTitle(router: Router | null): string {
    const routeTitle = this.pickTitle(router?.currentRoute.value.meta?.title)
    const documentTitle = typeof document === 'undefined' ? undefined : this.pickTitle(document.title)
    return routeTitle ?? documentTitle ?? this.pickTitle(runtimeAppConfig.value.app.title) ?? '页面'
  }

  /**
   * 规范化非空标题字符串。
   * @param title 候选标题
   */
  pickTitle(title: unknown): string | undefined {
    if (typeof title !== 'string') {
      return undefined
    }
    const normalized = title.trim()
    return normalized.length > 0 ? normalized : undefined
  }
}
