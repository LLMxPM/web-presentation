/**
 * 文件用途：收敛 PPTX DOM 转换器在多个 helper 间共享的类型与常量定义。
 */

export interface PptxTextRunLike {
  text: string
  options?: Record<string, unknown>
}

export type PptxTextContentLike = string | PptxTextRunLike[]

export type PptxSlideLike = {
  addText: (text: PptxTextContentLike, options?: Record<string, unknown>) => unknown
  addShape: (shapeType: string, options?: Record<string, unknown>) => unknown
  addImage: (options: Record<string, unknown>) => unknown
  addTable: (rows: PptxTableRowLike[], options?: Record<string, unknown>) => unknown
  background?: unknown
}

export interface PptxShapeTypes {
  rect: string
  roundRect: string
  ellipse: string
  line: string
}

export interface PptxPageConvertOptions {
  /** PPTX slide 对象 */
  slide: PptxSlideLike
  /** 页面源节点 */
  pageElement: HTMLElement
  /** 页面序号，从 1 开始 */
  pageIndex: number
  /** 页面标题 */
  pageTitle: string
  /** 页面路由 */
  pageRoute: string
  /** 演讲者备注，由投影器统一写入 slide */
  speakerNotes?: string | null
  /** 设计画布宽度，单位 px */
  pageWidthPx: number
  /** 设计画布高度，单位 px */
  pageHeightPx: number
  /** slide 宽度，单位 inch */
  slideWidthIn: number
  /** slide 高度，单位 inch */
  slideHeightIn: number
  /** PPTX 形状枚举值 */
  shapeTypes: PptxShapeTypes
  /** 局部截图函数，返回 PNG data URL */
  captureElementAsPng: (element: HTMLElement) => Promise<string>
  /** 收集需要写入 PPTX XML 的原生渐变填充指令 */
  gradientFillCollector?: (instruction: PptxGradientFillInstruction) => void
}

export interface ElementBox {
  x: number
  y: number
  w: number
  h: number
}

export interface MeasuredElementBox {
  left: number
  top: number
  width: number
  height: number
}

export interface BorderInfo {
  color: import('@/core/services/pptx/PPTXCssParser').ParsedColor
  side: import('@/core/services/pptx/PPTXCssParser').PptxBorderSide
  style: string
  widthPx: number
  widthPt: number
  dashType: string
}

export interface ElementPadding {
  top: number
  right: number
  bottom: number
  left: number
}

export interface ImageSizingOptions {
  type: 'contain' | 'cover'
  w: number
  h: number
}

export interface PptxTableCellLike {
  text?: PptxTextContentLike
  options?: Record<string, unknown>
}

export type PptxTableRowLike = PptxTableCellLike[]

export type LinearGradientDirection = 'right' | 'left' | 'bottom' | 'top'

export interface LinearGradientStop {
  color: import('@/core/services/pptx/PPTXCssParser').ParsedColor
  position: number
}

export interface LinearGradientInfo {
  direction: LinearGradientDirection
  /** 精确角度值（单位：度，0-360），存在时优先于枚举 direction 计算 OOXML 渐变角度 */
  angle?: number
  stops: LinearGradientStop[]
}

export interface PptxGradientFillInstruction extends LinearGradientInfo {
  /** 目标页码，从 1 开始，对应 ppt/slides/slideN.xml */
  pageIndex: number
  /** PPT 形状对象名，用于写文件前定位 XML 节点 */
  objectName: string
}

export interface VisitContext {
  groupId?: string
  parentGroupId?: string
  groupDepth: number
  groupLabel?: string
  inheritedTextAlign?: string
  inheritedVerticalAlign?: string
  /** 祖先累计不透明度 (0.0 - 1.0)，子元素计算有效透明度时需乘以该值 */
  inheritedOpacity?: number
  /** 从外到内排列的纯 2D 旋转与等比缩放步骤，导出对象时按相反顺序应用。 */
  rotationSteps?: PptxRotationStep[]
}

/**
 * 描述一个可映射到 PPT 原生 rotate 与尺寸缩放的 CSS 2D 刚性与等比变换。
 */
export interface PptxRotationStep {
  angle: number
  /** 等比缩放比例，默认为 1 */
  scale?: number
  originX: number
  originY: number
  translateX: number
  translateY: number
}

export const INLINE_TEXT_TAGS = new Set([
  'a',
  'b',
  'code',
  'em',
  'i',
  'small',
  'span',
  'strong',
  'sub',
  'sup',
  'u',
])
