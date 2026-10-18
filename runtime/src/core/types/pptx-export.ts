/**
 * 文件用途：定义可编辑 PPTX 导出相关的独立类型，避免污染 PDF 导出类型定义。
 */

import type { ExportMode } from '@/core/types/export-common'

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
  | 'audio'
  | 'model3d'
  | 'complex-css'
  | 'unknown'

export interface PptxExportOptions {
  /** 导出范围：当前页面或全部页面 */
  mode: ExportMode
  /** 自定义文件名 */
  filename?: string
  /**
   * @deprecated 早期 PNG 质量参数，PNG 格式下无损压缩无效，建议使用 rasterScale
   */
  quality?: number
  /**
   * 局部与整页截图清晰度倍率（默认 2）
   */
  rasterScale?: number
  /**
   * 页面错误处理策略：
   * - 'fail-fast': 任意页面发生错误立即中止并抛出错误（默认）
   * - 'rasterize-ready-page': 页面就绪后若原生 DOM 提取失败，采用整页高清截图容错交付
   */
  pageErrorStrategy?: 'fail-fast' | 'rasterize-ready-page'
}

/**
 * PPTX 导出各阶段耗时统计（毫秒）。
 */
export interface PptxExportTimingMetrics {
  /** 准备与环境初始化耗时 (ms) */
  preparationTimeMs?: number
  /** DOM 遍历与原生转换耗时 (ms) */
  conversionTimeMs?: number
  /** 打包与 OOXML 处理耗时 (ms) */
  packagingTimeMs?: number
  /** 总耗时 (ms) */
  totalDurationMs?: number
}

/**
 * PPTX 导出任务级资源与截图性能指标。
 */
export interface PptxExportResourceMetrics {
  /** 缓存命中的资源读取次数 */
  cacheHits: number
  /** 真实发起的网络/DataURL 读取次数 */
  fetchCount: number
  /** 资源总字节数（字节） */
  totalResourceBytes: number
  /** 局部或整页截图次数 */
  screenshotCount: number
  /** 采用整页截图容错降级的页面序号列表（从 1 开始） */
  rasterizedPageIndices?: number[]
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

export type PptxReportSeverity = 'info' | 'warning' | 'error'

export type PptxReportFallbackScope = 'none' | 'element' | 'subtree' | 'page'

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
  /** 源 DOM 节点或选择器标识 */
  sourceId?: string
  /** 关联的 PPTX 真实图元 ID 列表 */
  primitiveIds?: string[]
  /** 诊断严重级别 */
  severity?: PptxReportSeverity
  /** 稳定原因码 */
  code?: string
  /** 处理阶段 */
  stage?: string
  /** 元素在幻灯片中的边界盒（inch） */
  bounds?: { x: number; y: number; w: number; h: number }
  /** 降级影响范围 */
  fallbackScope?: PptxReportFallbackScope
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
  /** 阶段耗时统计 */
  timings?: PptxExportTimingMetrics
  /** 任务级资源与性能指标 */
  metrics?: PptxExportResourceMetrics
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
