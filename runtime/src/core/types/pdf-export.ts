/**
 * 文件用途：PDF 导出功能相关的 TypeScript 类型定义；跨导出方式共享的生命周期类型见 export-common.ts。
 */

import type { ExportMode } from '@/core/types/export-common'

// PDF 生成方式
export type ExportMethod = 'canvas-pdf' | 'browser-print'

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
