/**
 * 文件用途：收敛 Runtime Kit 组件「显式导出 DOM 契约」的属性名、取值词汇与读取逻辑，
 * 让 PPTX 导出以带版本的 data 属性识别媒体与连接线，样式类名只保留为兜底路径。
 *
 * 契约分两类，互不共用词汇：
 * - 媒体契约：data-runtime-kit-media 标记版本，data-runtime-kit-media-kind 声明类型，
 *   由 PPTXDomConverterMedia 与 PPTXDomConverterRaster 消费。
 * - 连接线契约：data-runtime-kit-connector 标记版本，由 ConnectorTightBounds 消费，
 *   只决定是否启用紧边界导出视口，不参与源类型判定。
 */

import type { PptxReportSourceType } from '@/core/types/pptx-export'

/** 当前契约版本；节点标记与该值不一致时一律视为未声明契约，回退类名兜底。 */
export const RUNTIME_KIT_EXPORT_DOM_VERSION = 'v1'

/** 媒体导出标记属性，取值只承载契约版本。 */
export const RUNTIME_KIT_MEDIA_ATTR = 'data-runtime-kit-media'

/** 媒体类型属性，取值必须来自 RUNTIME_KIT_MEDIA_KINDS 词汇表。 */
export const RUNTIME_KIT_MEDIA_KIND_ATTR = 'data-runtime-kit-media-kind'

/** 连接线导出标记属性，取值只承载契约版本。 */
export const RUNTIME_KIT_CONNECTOR_ATTR = 'data-runtime-kit-connector'

/** 连接线根节点的历史样式类名，仅在显式契约缺失时作为兜底依据。 */
export const LEGACY_CONNECTOR_CLASS = 'connector-svg'

/**
 * Runtime Kit 媒体类型词汇表。
 * 说明：只收录由 Runtime Kit viewer 组件产出的类型，取值与 PptxReportSourceType 对齐；
 * canvas 与 svg 由标签名判定，连接线走独立契约，都不进入本词汇表。
 */
export const RUNTIME_KIT_MEDIA_KINDS = [
  'mermaid',
  'drawio',
  'formula',
  'chart',
  'video',
  'image',
] as const

/** 媒体类型取值，字面量均为 PptxReportSourceType 成员，可直接作为报告源类型返回。 */
export type RuntimeKitMediaKind = (typeof RUNTIME_KIT_MEDIA_KINDS)[number]

/** 历史 viewer 根节点类名，仅在显式契约缺失或版本不识别时作为兜底依据。 */
const LEGACY_MEDIA_VIEWER_CLASSES = [
  'mermaid-viewer',
  'drawio-viewer',
  'latex-viewer',
  'echarts-viewer',
  'video-viewer',
  'image-viewer',
] as const

/** 类名兜底选择器，语义等价于历史 MEDIA_SELECTORS 常量。 */
export const LEGACY_MEDIA_VIEWER_SELECTOR = LEGACY_MEDIA_VIEWER_CLASSES
  .map(className => `.${className}`)
  .join(',')

/**
 * 类名与标签名兜底的源类型判定顺序。
 * 说明：顺序必须与引入显式契约前完全一致，类名判定与标签名判定交错排列，
 * 否则 canvas.image-viewer、svg.image-viewer 这类混合节点会被改判为 image。
 */
const LEGACY_MEDIA_SOURCE_RULES: ReadonlyArray<readonly [(element: Element) => boolean, PptxReportSourceType]> = [
  [element => element.matches('.mermaid-viewer'), 'mermaid'],
  [element => element.matches('.drawio-viewer'), 'drawio'],
  [element => element.matches('.latex-viewer'), 'formula'],
  [element => element.matches('.echarts-viewer'), 'chart'],
  [element => element.matches('.video-viewer') || isTagName(element, 'video'), 'video'],
  [element => isTagName(element, 'canvas'), 'canvas'],
  [element => isTagName(element, 'svg'), 'svg'],
  [element => element.matches('.image-viewer') || isTagName(element, 'img'), 'image'],
]

/**
 * 判断标签名是否匹配，统一小写比较。
 * @param element 候选元素
 * @param tagName 小写标签名
 */
function isTagName(element: Element, tagName: string): boolean {
  return element.tagName.toLowerCase() === tagName
}

/**
 * 判断节点是否声明了当前版本的媒体导出契约。
 * @param element 候选元素
 * @returns 标记存在且版本可识别时为 true；未知版本返回 false，交由类名兜底
 */
export function hasRuntimeKitMediaMarker(element: Element): boolean {
  return element.getAttribute(RUNTIME_KIT_MEDIA_ATTR) === RUNTIME_KIT_EXPORT_DOM_VERSION
}

/**
 * 判断取值是否属于媒体类型词汇表。
 * @param value data-runtime-kit-media-kind 原始取值
 */
export function isRuntimeKitMediaKind(value: string | null): value is RuntimeKitMediaKind {
  return value !== null && (RUNTIME_KIT_MEDIA_KINDS as readonly string[]).includes(value)
}

/**
 * 解析节点声明的媒体类型。
 * @param element 候选元素
 * @returns 媒体类型；标记缺失、版本不识别或类型不在词汇表内时返回 null
 */
export function resolveRuntimeKitMediaKind(element: Element): RuntimeKitMediaKind | null {
  if (!hasRuntimeKitMediaMarker(element)) {
    return null
  }
  const kind = element.getAttribute(RUNTIME_KIT_MEDIA_KIND_ATTR)
  return isRuntimeKitMediaKind(kind) ? kind : null
}

/**
 * 判断节点是否为历史 viewer 类名兜底可识别的媒体根节点。
 * @param element 候选元素
 */
export function isLegacyMediaViewerElement(element: Element): boolean {
  return element.matches(LEGACY_MEDIA_VIEWER_SELECTOR)
}

/**
 * 判断节点是否属于媒体 viewer 根节点，显式契约优先、类名兜底。
 * @param element 候选元素
 */
export function isMediaViewerElement(element: Element): boolean {
  return hasRuntimeKitMediaMarker(element) || isLegacyMediaViewerElement(element)
}

/**
 * 按「显式契约优先、类名与标签名兜底」解析媒体源类型。
 * @param element 候选元素
 * @returns 报告源类型；节点不属于任何媒体形态时返回 null，由调用方决定兜底值
 */
export function resolveRuntimeKitMediaSourceType(element: Element): PptxReportSourceType | null {
  const kind = resolveRuntimeKitMediaKind(element)
  if (kind) {
    return kind
  }

  for (const [matches, sourceType] of LEGACY_MEDIA_SOURCE_RULES) {
    if (matches(element)) {
      return sourceType
    }
  }

  return null
}

/**
 * 判断节点是否声明了当前版本的连接线导出契约。
 * @param element 候选元素
 * @returns 标记存在且版本可识别时为 true；未知版本返回 false，交由类名兜底
 */
export function isRuntimeKitConnectorSvg(element: Element): boolean {
  return element.getAttribute(RUNTIME_KIT_CONNECTOR_ATTR) === RUNTIME_KIT_EXPORT_DOM_VERSION
}

/**
 * 判断节点是否为连接线根 SVG，显式契约优先、类名兜底。
 * @param element 候选元素
 */
export function isConnectorSvg(element: Element): boolean {
  return isRuntimeKitConnectorSvg(element) || element.classList.contains(LEGACY_CONNECTOR_CLASS)
}

/** 图表数据导出契约标记属性，取值只承载契约版本（v1）。 */
export const RUNTIME_KIT_CHART_ATTR = 'data-runtime-kit-chart'

/** 图表归一化数据属性名，承载 JSON 序列化的图表数据。 */
export const RUNTIME_KIT_CHART_DATA_ATTR = 'data-runtime-kit-chart-data'

export type PptxChartType = 'bar' | 'line' | 'pie' | 'doughnut'

/**
 * 原生图表导出数据载荷结构。
 */
export interface PptxChartDataPayload {
  version: 'v1'
  chartType: PptxChartType
  title?: string
  categories: string[]
  series: Array<{
    name: string
    values: number[]
    color?: string
  }>
  options?: {
    showLegend?: boolean
    showTitle?: boolean
    showValue?: boolean
    holeSize?: number
  }
}

/**
 * 从元素中解析图表导出数据载荷；若未声明契约或解析失败返回 null。
 * @param element 待检查元素
 */
export function parseRuntimeKitChartPayload(element: Element): PptxChartDataPayload | null {
  if (element.getAttribute(RUNTIME_KIT_CHART_ATTR) !== RUNTIME_KIT_EXPORT_DOM_VERSION) {
    return null
  }
  const rawData = element.getAttribute(RUNTIME_KIT_CHART_DATA_ATTR)
  if (!rawData) {
    return null
  }
  try {
    const parsed = JSON.parse(rawData) as PptxChartDataPayload
    if (
      parsed &&
      parsed.version === 'v1' &&
      Array.isArray(parsed.categories) &&
      Array.isArray(parsed.series) &&
      parsed.series.length > 0
    ) {
      return parsed
    }
  } catch {
    return null
  }
  return null
}

