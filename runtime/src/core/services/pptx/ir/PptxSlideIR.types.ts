/**
 * 文件用途：定义 PPTX 单页导出的纯数据中间表示（PptxSlideIR），隔离 DOM 采集与 PptxGenJS/OOXML 写入。
 */

import type { PptxExportReportPage } from '@/core/types/pptx-export'
import type {
  PptxGradientFillInstruction,
  PptxShapeTypes,
  PptxTableRowLike,
  PptxTextContentLike,
} from '@/core/services/pptx/PPTXDomConverter.types'

/**
 * 幻灯片背景纯数据描述。
 */
export interface PptxSlideBackgroundIR {
  color: string
  transparency: number
}

/**
 * 文本框或带背景文本形状图元。
 */
export interface PptxTextPrimitiveIR {
  kind: 'text'
  id?: string
  text: PptxTextContentLike
  options?: Record<string, unknown>
}

/**
 * 几何形状或线条图元。
 */
export interface PptxShapePrimitiveIR {
  kind: 'shape'
  id?: string
  shapeType: string
  options?: Record<string, unknown>
}

/**
 * 位图、SVG 或局部截图图元。
 */
export interface PptxImagePrimitiveIR {
  kind: 'image'
  id?: string
  options: Record<string, unknown>
}

/**
 * 表格图元。
 */
export interface PptxTablePrimitiveIR {
  kind: 'table'
  id?: string
  rows: PptxTableRowLike[]
  options?: Record<string, unknown>
}

/**
 * 原生图表图元。
 */
export interface PptxChartPrimitiveIR {
  kind: 'chart'
  id?: string
  chartType: import('../PPTXRuntimeKitExportDom').PptxChartType
  data: Array<{ name: string; labels: string[]; values: number[] }>
  options?: Record<string, unknown>
}

/**
 * 幻灯片可序列化图元联合类型。
 */
export type PptxSlidePrimitiveIR =
  | PptxTextPrimitiveIR
  | PptxShapePrimitiveIR
  | PptxImagePrimitiveIR
  | PptxTablePrimitiveIR
  | PptxChartPrimitiveIR

/**
 * 单页 PPTX 导出的完整中间表示。
 */
export interface PptxSlideIR {
  /** 页码索引（从 1 开始） */
  pageIndex: number
  /** 页面标题 */
  pageTitle: string
  /** 页面路由 */
  pageRoute: string
  /** 演讲者备注（已裁剪空白，无备注时为 null 或 undefined） */
  speakerNotes?: string | null
  /** 页面背景填充 */
  background?: PptxSlideBackgroundIR
  /** 按绘制顺序排列的图元列表 */
  primitives: PptxSlidePrimitiveIR[]
  /** 需要在 OOXML 阶段修补的原生线性渐变指令 */
  gradientFills: PptxGradientFillInstruction[]
  /** 需要在 OOXML 阶段修补的组封装指令 */
  groups?: import('@/core/services/pptx/writer/OoxmlGroupPatcher').PptxGroupInstruction[]
  /** 当前页面的导出诊断报告 */
  report: PptxExportReportPage
}

/**
 * 从 DOM 提取单页 PptxSlideIR 的输入参数（无需传入 PptxGenJS slide 实例）。
 */
export interface PptxSlideExtractOptions {
  /** 页面源节点 */
  pageElement: HTMLElement
  /** 页面序号，从 1 开始 */
  pageIndex: number
  /** 页面标题 */
  pageTitle: string
  /** 页面路由 */
  pageRoute: string
  /** 演讲者备注 */
  speakerNotes?: string | null
  /** 设计画布宽度，单位 px */
  pageWidthPx: number
  /** 设计画布高度，单位 px */
  pageHeightPx: number
  /** slide 宽度，单位 inch */
  slideWidthIn: number
  /** slide 高度，单位 inch */
  slideHeightIn: number
  /** PPTX 形状枚举值（不传时默认使用标准形状键名） */
  shapeTypes?: PptxShapeTypes
  /** 局部截图函数，返回 PNG data URL */
  captureElementAsPng: (element: HTMLElement) => Promise<string>
  /** 任务级资源缓存与取消上下文。 */
  resourceSession?: import('../session/PptxResourceSession').PptxResourceSession
  signal?: AbortSignal
}

/**
 * 默认的 PPTX 形状枚举名称，可在无 PptxGenJS 实例时用于 IR 提取。
 */
export const DEFAULT_PPTX_SHAPE_TYPES: PptxShapeTypes = {
  rect: 'rect',
  roundRect: 'roundRect',
  ellipse: 'ellipse',
  line: 'line',
}
