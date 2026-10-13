/**
 * 文件用途：提供通用的导出任务状态机、进度上报与取消控制，供 PPTX、PDF、浏览器打印服务复用。
 *
 * 文件名与页面标题推导不属于任务生命周期，见同目录 export-filename.ts。
 */

import {
  ExportStatus,
  type ExportMode,
  type ExportProgress,
  type ExportTask,
} from '@/core/types/export-common'

/**
 * 导出任务生命周期管理器的构造配置。
 */
export interface ExportTaskRunnerConfig {
  /** 任务 ID 前缀，如 'pptx-export' / 'task' / 'browser-print' */
  taskIdPrefix: string
  /** 重复触发时的错误提示文案 */
  busyErrorMessage: string
  /** 取消后保持占用直到 finally 清理，适用于持有共享转换状态的 PPTX 导出。 */
  retainLockOnCancel?: boolean
}

/**
 * 通用导出任务状态机与文件名/标题解析工具。
 */
export class ExportTaskRunner {
  private currentTask: ExportTask | null = null
  private active = false
  private progressCallback: ((progress: ExportProgress) => void) | null = null
  private readonly config: ExportTaskRunnerConfig
  private readonly cancelledTaskIds = new Set<string>()
  private abortController: AbortController | null = null

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
   * 判断指定任务是否已被取消。
   * @param taskId 目标任务 ID
   */
  isTaskCancelled(taskId: string): boolean {
    return this.cancelledTaskIds.has(taskId) ||
      (this.currentTask?.id === taskId && this.currentTask.status === ExportStatus.CANCELLED)
  }

  /**
   * 判断指定任务是否仍处于活跃执行中（非过期、未取消且当前匹配）。
   * @param taskId 目标任务 ID
   */
  isTaskActive(taskId: string): boolean {
    return this.active && this.currentTask?.id === taskId && !this.isTaskCancelled(taskId)
  }

  /**
   * 获取指定任务的 AbortSignal，用于取消在途网络请求与等待。
   * @param taskId 可选任务 ID
   */
  getSignal(taskId?: string): AbortSignal | null {
    if (taskId && this.currentTask?.id !== taskId) {
      return null
    }
    return this.abortController?.signal ?? null
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
    this.abortController = typeof AbortController !== 'undefined' ? new AbortController() : null
    return task
  }

  /**
   * 更新任务状态。
   * @param status 新状态
   * @param error 可选错误信息
   * @param taskId 可选任务 ID，传入时校验归属
   */
  updateStatus(status: ExportStatus, error?: string, taskId?: string): void {
    if (!this.currentTask) {
      return
    }

    if (taskId && this.currentTask.id !== taskId) {
      return
    }

    if (taskId && this.isTaskCancelled(taskId) && status !== ExportStatus.CANCELLED) {
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
   * @param taskId 可选任务 ID，传入时校验归属
   */
  reportProgress(index: number, total: number, title: string, route = '', taskId?: string): void {
    if (taskId && this.currentTask?.id !== taskId) {
      return
    }

    if (taskId && this.isTaskCancelled(taskId)) {
      return
    }

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
   * @param taskId 可选指定取消的任务 ID
   * @returns 是否实际取消了正在运行的任务
   */
  cancel(taskId?: string): boolean {
    if (!this.active && !this.currentTask) {
      return false
    }

    if (taskId && this.currentTask?.id !== taskId) {
      return false
    }

    const currentId = this.currentTask?.id
    if (currentId) {
      this.cancelledTaskIds.add(currentId)
    }

    try {
      this.abortController?.abort()
    } catch {
      // 忽略已终止报错
    }

    this.updateStatus(ExportStatus.CANCELLED, undefined, currentId)
    if (!this.config.retainLockOnCancel) this.finish(currentId)
    // 仅保留有界的取消记录，避免单例随使用次数增长。
    while (this.cancelledTaskIds.size > 32) {
      this.cancelledTaskIds.delete(this.cancelledTaskIds.values().next().value!)
    }
    return true
  }

  /**
   * 清理当前任务的运行态引用（通常在 finally 中调用）。
   * @param taskId 可选任务 ID，传入时校验归属，旧任务无法清理新任务
   */
  finish(taskId?: string): void {
    if (taskId && this.currentTask?.id !== taskId) {
      return
    }

    this.active = false
    this.currentTask = null
    this.progressCallback = null
    this.abortController = null
  }
}
