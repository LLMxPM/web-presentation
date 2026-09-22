/**
 * 文件用途：封装 PPTX DOM 转换里的 CSS linear-gradient 解析与 PPT 原生渐变形状导出。
 */

import type {
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type { ParsedColor } from '@/core/services/pptx/PPTXCssParser'
import type {
  LinearGradientDirection,
  LinearGradientInfo,
  LinearGradientStop,
  PptxGradientFillInstruction,
  PptxPageConvertOptions,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXDomConverterTransform } from '@/core/services/pptx/PPTXDomConverterTransform'

export interface PptxDomGradientExportHost {
  options: PptxPageConvertOptions
  buildPptObjectMeta: (
    context: VisitContext,
    role: string,
    label: string,
    includeAltText?: boolean,
  ) => Record<string, unknown>
  addReportItem: (
    sourceType: PptxReportSourceType,
    result: PptxReportItemResult,
    editable: boolean,
    label: string,
    reason?: string,
    context?: VisitContext,
  ) => PptxExportReportItem
  addSkippedItem: (
    sourceType: PptxReportSourceType,
    label: string,
    reason: string,
    context?: VisitContext,
  ) => void
  createGradientObjectName: (element: HTMLElement) => string
}

/**
 * PPTX 渐变导出 helper。
 */
export class PPTXDomConverterGradient {
  private readonly transform: PPTXDomConverterTransform

  constructor(private readonly layout: PPTXDomConverterLayout) {
    this.transform = new PPTXDomConverterTransform(layout)
  }

  /**
   * 将可解析的 CSS linear-gradient 导出为单个 PPT 原生渐变形状。
   * @param host 导出宿主能力
   * @param element 渐变元素
   * @param context 当前组合上下文
   */
  addLinearGradientElement(host: PptxDomGradientExportHost, element: HTMLElement, context: VisitContext): boolean {
    const style = window.getComputedStyle(element)
    const gradient = this.parseLinearGradient(style.backgroundImage, element)
    if (!gradient) {
      return false
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    const label = this.layout.buildElementLabel(element)
    if (!box) {
      host.addSkippedItem('shape', label, '渐变形状尺寸无效', context)
      return true
    }

    const objectName = host.createGradientObjectName(element)
    host.options.slide.addShape(host.options.shapeTypes.rect, {
      ...this.transform.applyToBox(box, context),
      fill: this.buildFillOptions(this.sampleLinearGradientColor(gradient.stops, 0.5)),
      line: this.buildTransparentLineOptions(),
      ...host.buildPptObjectMeta(context, 'gradient', label),
      objectName,
    })
    host.options.gradientFillCollector?.({
      pageIndex: host.options.pageIndex,
      objectName,
      direction: gradient.direction,
      stops: gradient.stops,
    } satisfies PptxGradientFillInstruction)

    host.addReportItem('shape', 'editable-shape', true, label, 'linear-gradient 导出为 PPT 原生渐变形状', context)
    return true
  }

  /**
   * 构造 PPT fill 参数。
   * @param color 填充颜色
   */
  private buildFillOptions(color: ParsedColor | null): Record<string, unknown> {
    if (!color) {
      return {
        type: 'none',
        transparency: 100,
      }
    }

    return {
      type: 'solid',
      color: color.hex,
      transparency: this.layout.alphaToTransparency(color.alpha),
    }
  }

  /**
   * 构造透明线条参数。
   */
  private buildTransparentLineOptions(): Record<string, unknown> {
    return {
      color: 'FFFFFF',
      transparency: 100,
      width: 0,
    }
  }

  /**
   * 解析线性渐变，仅支持单个 linear-gradient。
   * @param value background-image 值
   * @param element CSS 变量解析上下文
   */
  private parseLinearGradient(value: string, element: HTMLElement): LinearGradientInfo | null {
    const normalized = String(value || '').trim()
    const match = /^linear-gradient\((.*)\)$/i.exec(normalized)
    if (!match) {
      return null
    }

    const parts = this.splitCssTopLevel(match[1], ',').map(part => part.trim()).filter(Boolean)
    if (parts.length < 2) {
      return null
    }

    let direction: LinearGradientDirection = 'bottom'
    let stopParts = parts
    const firstStop = this.parseLinearGradientStop(parts[0], element)
    if (!firstStop) {
      const parsedDirection = this.parseLinearGradientDirection(parts[0])
      if (!parsedDirection) {
        return null
      }
      direction = parsedDirection
      stopParts = parts.slice(1)
    }

    const stops = stopParts
      .map(part => this.parseLinearGradientStop(part, element))
      .filter((stop): stop is { color: ParsedColor; position?: number } => Boolean(stop))
    if (stops.length < 2) {
      return null
    }

    return {
      direction,
      stops: this.normalizeLinearGradientStops(stops),
    }
  }

  /**
   * 解析 linear-gradient 方向。
   * @param value 方向片段
   */
  private parseLinearGradientDirection(value: string): LinearGradientDirection | '' {
    const normalized = value.trim().toLowerCase()
    if (normalized.startsWith('to ')) {
      const direction = normalized.slice(3).trim()
      if (['right', 'left', 'bottom', 'top'].includes(direction)) {
        return direction as LinearGradientDirection
      }
      return ''
    }

    if (!normalized.endsWith('deg')) {
      return ''
    }

    const angle = ((Number.parseFloat(normalized) % 360) + 360) % 360
    if (Math.abs(angle - 90) <= 1) return 'right'
    if (Math.abs(angle - 270) <= 1) return 'left'
    if (Math.abs(angle - 180) <= 1) return 'bottom'
    if (angle <= 1 || Math.abs(angle - 360) <= 1) return 'top'
    return ''
  }

  /**
   * 解析单个 linear-gradient 颜色停靠点。
   * @param value 停靠点片段
   * @param element CSS 变量解析上下文
   */
  private parseLinearGradientStop(
    value: string,
    element: HTMLElement,
  ): { color: ParsedColor; position?: number } | null {
    const colorEnd = this.findCssColorStopEnd(value)
    if (colorEnd <= 0) {
      return null
    }

    const colorText = value.slice(0, colorEnd).trim()
    const color = colorText.toLowerCase() === 'transparent'
      ? { hex: '000000', alpha: 0 }
      : this.layout.parseCssColor(colorText, element)
    if (!color) {
      return null
    }

    const rest = value.slice(colorEnd).trim()
    const positionToken = rest.split(/\s+/).find(token => token.endsWith('%') || /^-?\d*\.?\d+$/.test(token))
    return {
      color,
      position: positionToken ? this.parseGradientPosition(positionToken) : undefined,
    }
  }

  /**
   * 查找颜色停靠点里颜色值的结束位置。
   * @param value 停靠点片段
   */
  private findCssColorStopEnd(value: string): number {
    const trimmed = value.trimStart()
    const leadingOffset = value.length - trimmed.length
    const functionMatch = /^[a-z-]+\(/i.exec(trimmed)
    if (functionMatch) {
      const openIndex = leadingOffset + functionMatch[0].length - 1
      const closeIndex = this.findClosingParenthesis(value, openIndex)
      return closeIndex >= 0 ? closeIndex + 1 : -1
    }

    const tokenMatch = /^\S+/.exec(trimmed)
    return tokenMatch ? leadingOffset + tokenMatch[0].length : -1
  }

  /**
   * 解析渐变停靠点位置。
   * @param value 百分比或 0-1 数值
   */
  private parseGradientPosition(value: string): number {
    const normalized = String(value || '').trim()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    return Math.max(0, Math.min(1, normalized.endsWith('%') || parsed > 1 ? parsed / 100 : parsed))
  }

  /**
   * 补齐渐变停靠点位置，保持位置单调。
   * @param stops 已解析停靠点
   */
  private normalizeLinearGradientStops(stops: Array<{ color: ParsedColor; position?: number }>): LinearGradientStop[] {
    const normalized = stops.map(stop => ({ ...stop }))
    if (normalized[0].position === undefined) {
      normalized[0].position = 0
    }
    const lastIndex = normalized.length - 1
    if (normalized[lastIndex].position === undefined) {
      normalized[lastIndex].position = 1
    }

    let index = 0
    while (index < normalized.length) {
      if (normalized[index].position !== undefined) {
        index += 1
        continue
      }

      const startIndex = index - 1
      let endIndex = index + 1
      while (endIndex < normalized.length && normalized[endIndex].position === undefined) {
        endIndex += 1
      }
      const start = normalized[startIndex].position ?? 0
      const end = normalized[endIndex]?.position ?? start
      const gap = endIndex - startIndex
      for (let fillIndex = index; fillIndex < endIndex; fillIndex += 1) {
        normalized[fillIndex].position = start + (end - start) * ((fillIndex - startIndex) / gap)
      }
      index = endIndex
    }

    let lastPosition = 0
    return normalized.map(stop => {
      const position = Math.max(lastPosition, Math.min(1, stop.position ?? lastPosition))
      lastPosition = position
      return {
        color: stop.color,
        position,
      }
    })
  }

  /**
   * 采样渐变颜色。
   * @param stops 渐变停靠点
   * @param position 0-1 位置
   */
  private sampleLinearGradientColor(stops: LinearGradientStop[], position: number): ParsedColor {
    const current = Math.max(0, Math.min(1, position))
    let left = stops[0]
    let right = stops[stops.length - 1]
    for (let index = 0; index < stops.length - 1; index += 1) {
      if (current >= stops[index].position && current <= stops[index + 1].position) {
        left = stops[index]
        right = stops[index + 1]
        break
      }
    }

    const span = Math.max(0.0001, right.position - left.position)
    const ratio = (current - left.position) / span
    const leftRgb = this.hexToRgb(left.color.hex)
    const rightRgb = this.hexToRgb(right.color.hex)
    return {
      hex: [
        this.interpolateColorChannel(leftRgb.red, rightRgb.red, ratio),
        this.interpolateColorChannel(leftRgb.green, rightRgb.green, ratio),
        this.interpolateColorChannel(leftRgb.blue, rightRgb.blue, ratio),
      ].map(channel => channel.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha: left.color.alpha + (right.color.alpha - left.color.alpha) * ratio,
    }
  }

  /**
   * 十六进制颜色转 RGB。
   * @param hex HEX 颜色
   */
  private hexToRgb(hex: string): { red: number; green: number; blue: number } {
    const normalized = hex.padEnd(6, '0')
    return {
      red: Number.parseInt(normalized.slice(0, 2), 16),
      green: Number.parseInt(normalized.slice(2, 4), 16),
      blue: Number.parseInt(normalized.slice(4, 6), 16),
    }
  }

  /**
   * 插值 RGB 单通道。
   * @param left 左侧颜色通道
   * @param right 右侧颜色通道
   * @param ratio 插值比例
   */
  private interpolateColorChannel(left: number, right: number, ratio: number): number {
    return Math.max(0, Math.min(255, Math.round(left + (right - left) * ratio)))
  }

  /**
   * 按顶层分隔符拆分 CSS 函数参数。
   * @param value CSS 参数
   * @param delimiter 分隔符
   */
  private splitCssTopLevel(value: string, delimiter: string): string[] {
    const parts: string[] = []
    let depth = 0
    let quote = ''
    let start = 0

    for (let index = 0; index < value.length; index += 1) {
      const char = value[index]
      if (quote) {
        if (char === quote && value[index - 1] !== '\\') {
          quote = ''
        }
        continue
      }
      if (char === '"' || char === '\'') {
        quote = char
        continue
      }
      if (char === '(') {
        depth += 1
        continue
      }
      if (char === ')') {
        depth = Math.max(0, depth - 1)
        continue
      }
      if (depth === 0 && char === delimiter) {
        parts.push(value.slice(start, index))
        start = index + 1
      }
    }

    parts.push(value.slice(start))
    return parts
  }

  /**
   * 查找闭合括号位置。
   * @param value 原始字符串
   * @param openIndex 左括号位置
   */
  private findClosingParenthesis(value: string, openIndex: number): number {
    let depth = 0
    let quote = ''
    for (let index = openIndex; index < value.length; index += 1) {
      const char = value[index]
      if (quote) {
        if (char === quote && value[index - 1] !== '\\') {
          quote = ''
        }
        continue
      }
      if (char === '"' || char === '\'') {
        quote = char
        continue
      }
      if (char === '(') {
        depth += 1
        continue
      }
      if (char === ')') {
        depth -= 1
        if (depth === 0) {
          return index
        }
      }
    }
    return -1
  }
}
