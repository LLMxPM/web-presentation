/**
 * 文件用途：定义 PPTX、PDF、浏览器打印等所有导出服务共享的公共生命周期、进度、页面元信息与截图选项类型。
 */

/**
 * 导出范围模式：当前页面或全部页面。
 */
export type ExportMode = 'current' | 'all'

/**
 * 导出任务状态枚举。
 */
export enum ExportStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * 导出进度回调数据。
 */
export interface ExportProgress {
  /** 当前处理的页面序号（从 1 开始） */
  current: number
  /** 总页面数 */
  total: number
  /** 完成百分比（0-100） */
  percentage: number
  /** 当前处理页面标题 */
  currentPageTitle: string
  /** 当前处理页面路由 */
  currentPageRoute: string
}

/**
 * 页面或局部元素捕获选项接口。
 */
export interface CaptureOptions {
  /** 捕获宽度 */
  width?: number
  /** 捕获高度 */
  height?: number
  /** 缩放比例 */
  scale?: number
  /** 是否启用 CORS */
  useCORS?: boolean
  /** 是否允许跨域图片污染画布 */
  allowTaint?: boolean
  /** 背景颜色 */
  backgroundColor?: string
  /** 超时时间（毫秒） */
  timeout?: number
  /** 跨域资源代理前缀，例如 Runtime 同源 snapDOM 代理地址 */
  proxyUrl?: string
  /** 是否移除容器的阴影、圆角、内边距等装饰以实现无边距捕获 */
  fullBleed?: boolean
  /** 指定要捕获的运行时页面路由，导出多页时用于避免截错过渡页 */
  routePath?: string
  /** 取消信号：中止离屏页面准备与截图等待 */
  signal?: AbortSignal
  /** 当目标所在页面已确认加载完成时跳过全局页面就绪与 500ms 固定等待（用于 PPTX 局部元素光栅化） */
  skipPageWait?: boolean
}

/**
 * 导出任务运行时实体。
 */
export interface ExportTask {
  /** 任务 ID */
  id: string
  /** 导出模式 */
  mode: ExportMode
  /** 任务状态 */
  status: ExportStatus
  /** 进度百分比 */
  progress: number
  /** 文件名 */
  filename: string
  /** 总页面数 */
  totalPages: number
  /** 已完成页面数 */
  completedPages: number
  /** 创建时间 */
  createdAt: Date
  /** 更新时间 */
  updatedAt: Date
  /** 错误信息 */
  error?: string
}

/**
 * 待导出页面的路由与元信息。
 */
export interface PageInfo {
  /** 页面路由 */
  route: string
  /** 页面标题 */
  title: string
  /** 页面顺序 */
  order: number
  /** 路由元信息 */
  meta?: {
    pageNumber?: number
    level?: number
    hidden?: boolean
    speakerNotes?: string | null
    [key: string]: unknown
  }
}
