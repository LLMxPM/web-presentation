/**
 * PDF导出功能相关的TypeScript类型定义
 */

// 导出模式枚举
export type ExportMode = 'current' | 'all'

// PDF 生成方式
export type ExportMethod = 'canvas-pdf' | 'browser-print'

// 导出状态枚举
export enum ExportStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// PDF页面格式类型
export type PDFFormat = 'a4' | 'a3' | 'letter'

// PDF页面方向类型
export type PDFOrientation = 'portrait' | 'landscape'

// 导出选项接口
export interface ExportOptions {
  mode: ExportMode                // 导出模式：当前页面或所有页面
  method?: ExportMethod           // 生成方式：截图生成PDF或浏览器打印
  filename?: string               // 自定义文件名
  quality?: number                // 图片质量 (0-1)
  format?: PDFFormat              // PDF页面格式
  orientation?: PDFOrientation    // PDF页面方向
}

// 导出进度接口
export interface ExportProgress {
  current: number                 // 当前处理的页面索引
  total: number                   // 总页面数
  percentage: number              // 完成百分比
  currentPageTitle: string        // 当前处理页面标题
  currentPageRoute: string        // 当前处理页面路由
}

// 页面捕获选项接口
export interface CaptureOptions {
  width?: number                  // 捕获宽度
  height?: number                 // 捕获高度
  scale?: number                  // 缩放比例
  useCORS?: boolean               // 是否启用CORS
  allowTaint?: boolean            // 是否允许跨域图片
  backgroundColor?: string        // 背景颜色
  timeout?: number                // 超时时间(毫秒)
  proxyUrl?: string               // 跨域资源代理前缀，例如 'https://corsproxy.io/?url='
  fullBleed?: boolean            // 是否移除容器的阴影、圆角、内边距等装饰以实现无边距捕获
  routePath?: string              // 指定要捕获的运行时页面路由，导出多页时用于避免截错过渡页
}

// 导出任务接口
export interface ExportTask {
  id: string                      // 任务ID
  mode: ExportMode                // 导出模式
  status: ExportStatus            // 任务状态
  progress: number                // 进度百分比
  filename: string                // 文件名
  totalPages: number              // 总页面数
  completedPages: number          // 已完成页面数
  createdAt: Date                 // 创建时间
  updatedAt: Date                 // 更新时间
  error?: string                  // 错误信息
}

// 页面捕获数据接口
export interface PageCapture {
  id: string                      // 捕获ID
  taskId: string                  // 任务ID
  pageTitle: string               // 页面标题
  pageRoute: string               // 页面路由
  captureCanvas: HTMLCanvasElement // 捕获的画布元素
  order: number                   // 页面顺序
  capturedAt: Date                // 捕获时间
  dimensions: {
    width: number                 // 页面宽度
    height: number                // 页面高度
  }
}

// 导出配置接口
export interface ExportConfig {
  // PDF设置
  pdf: {
    format: PDFFormat             // 页面格式
    orientation: PDFOrientation   // 页面方向
    margin: {
      top: number                 // 上边距
      right: number               // 右边距
      bottom: number              // 下边距
      left: number                // 左边距
    }
  }
  
  // 捕获设置
  capture: {
    quality: number               // 图片质量
    scale: number                 // 缩放比例
    timeout: number               // 超时时间
    waitForImages: boolean        // 是否等待图片加载
    useCORS: boolean              // 是否启用CORS
    backgroundColor: string       // 背景颜色
    proxyUrl?: string             // 跨域资源代理前缀，例如 'https://corsproxy.io/?url='
  }
  
  // 文件设置
  file: {
    nameTemplate: string          // 文件名模板
    includeTimestamp: boolean     // 是否包含时间戳
    compression: boolean          // 是否压缩
  }
}

// 页面信息接口
export interface PageInfo {
  route: string                   // 页面路由
  title: string                   // 页面标题
  order: number                   // 页面顺序
  meta?: {
    pageNumber?: number           // 页码
    level?: number               // 层级
    hidden?: boolean             // 是否隐藏
    speakerNotes?: string | null  // 演讲者备注
    [key: string]: unknown       // 其他元数据
  }
}

// 导出事件类型
export type ExportEventType = 'start' | 'progress' | 'complete' | 'error' | 'cancel'

// 导出事件接口
export interface ExportEvent {
  type: ExportEventType           // 事件类型
  taskId: string                  // 任务ID
  data?: unknown                  // 事件数据
  timestamp: Date                 // 事件时间
}

// 导出结果接口
export interface ExportResult {
  success: boolean                // 是否成功
  taskId: string                  // 任务ID
  method?: ExportMethod           // 生成方式
  filename?: string               // 生成的文件名
  fileSize?: number               // 文件大小(字节)
  pageCount?: number              // 页面数量
  duration?: number               // 导出耗时(毫秒)
  message?: string                // 结果提示文案
  error?: string                  // 错误信息
}



