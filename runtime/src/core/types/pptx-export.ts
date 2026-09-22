/**
 * 文件用途：定义可编辑 PPTX 导出相关的独立类型，避免污染 PDF 导出类型定义。
 */

import type { ExportMode } from '@/core/types/pdf-export'

export type PptxExportMethod = 'pptx-editable'

export type PptxReportItemResult =
  | 'editable-text'
  | 'editable-shape'
  | 'editable-table'
  | 'image'
  | 'svg'
  | 'screenshot'
  | 'skipped'

export type PptxReportSourceType =
  | 'title'
  | 'body'
  | 'number'
  | 'shape'
  | 'table'
  | 'image'
  | 'svg'
  | 'mermaid'
  | 'drawio'
  | 'formula'
  | 'chart'
  | 'canvas'
  | 'video'
  | 'complex-css'
  | 'unknown'

export interface PptxExportOptions {
  /** 导出范围：当前页面或全部页面 */
  mode: ExportMode
  /** 自定义文件名 */
  filename?: string
  /** 局部截图质量，当前用于 PNG 兜底 */
  quality?: number
}

export interface PptxExportReportSummary {
  /** 可编辑文本对象数量 */
  editableText: number
  /** 可编辑形状对象数量 */
  editableShape: number
  /** 可编辑表格对象数量 */
  editableTable: number
  /** 普通图片块数量 */
  imageBlock: number
  /** SVG 图片块数量 */
  svgBlock: number
  /** 局部截图降级块数量 */
  screenshotBlock: number
  /** 跳过对象数量 */
  skipped: number
}

export interface PptxExportReportItem {
  /** 页码索引，从 1 开始 */
  pageIndex: number
  /** 页面标题 */
  pageTitle: string
  /** 页面路由 */
  pageRoute: string
  /** 源对象类型 */
  sourceType: PptxReportSourceType
  /** 导出结果 */
  result: PptxReportItemResult
  /** 是否为 PPT 可编辑对象 */
  editable: boolean
  /** 对象文本或元素摘要 */
  label: string
  /** 降级或跳过原因 */
  reason?: string
  /** 同一 HTML 容器展开出的对象组合 ID */
  groupId?: string
  /** 父级 HTML 容器组合 ID */
  parentGroupId?: string
  /** HTML 容器组合嵌套深度 */
  groupDepth?: number
  /** HTML 容器摘要 */
  groupLabel?: string
}

export interface PptxExportReportPage {
  /** 页码索引，从 1 开始 */
  pageIndex: number
  /** 页面标题 */
  pageTitle: string
  /** 页面路由 */
  pageRoute: string
  /** 当前页对象明细 */
  items: PptxExportReportItem[]
}

export interface PptxExportReport {
  /** 导出汇总 */
  summary: PptxExportReportSummary
  /** 按页对象明细 */
  pages: PptxExportReportPage[]
}

export interface PptxExportResult {
  /** 是否成功 */
  success: boolean
  /** 任务 ID */
  taskId: string
  /** 导出方法，固定为 pptx-editable */
  method: PptxExportMethod
  /** 生成文件名 */
  filename?: string
  /** 页面数量 */
  pageCount?: number
  /** 导出耗时 */
  duration?: number
  /** 成功或提示文案 */
  message?: string
  /** 错误信息 */
  error?: string
  /** 导出报告 */
  report?: PptxExportReport
}
