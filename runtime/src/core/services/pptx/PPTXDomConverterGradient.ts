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
import { ShapeGeometryResolver } from './extractors/ShapeGeometryResolver'
import {
  clampColorByte,
  findClosingParenthesis,
  hexToRgbChannels,
  splitCssTopLevel,
} from './style/css-tokenizer'

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
  private readonly shapeGeometry: ShapeGeometryResolver

  constructor(private readonly layout: PPTXDomConverterLayout) {
    this.transform = new PPTXDomConverterTransform(layout)
    this.shapeGeometry = new ShapeGeometryResolver(layout)
  }

  /**
   * 将可解析的 CSS linear-gradient 导出为单个 PPT 原生渐变形状。
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
      fill: this.shapeGeometry.buildFillOptions(this.sampleLinearGradientColor(gradient.stops, 0.5)),
      line: this.shapeGeometry.buildTransparentLineOptions(),
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
   * 解析线性渐变，仅支持单个 linear-gradient。
   */
  private parseLinearGradient(value: string, element: HTMLElement): LinearGradientInfo | null {
    const normalized = String(value || '').trim()
    const match = /^linear-gradient\((.*)\)$/i.exec(normalized)
    if (!match) {
      return null
    }

    const parts = splitCssTopLevel(match[1], ',').map(part => part.trim()).filter(Boolean)
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
   * 采样渐变颜色（用于生成占位纯色）。
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
    const leftRgb = hexToRgbChannels(left.color.hex)
    const rightRgb = hexToRgbChannels(right.color.hex)
    return {
      hex: [
        clampColorByte(leftRgb.red + (rightRgb.red - leftRgb.red) * ratio),
        clampColorByte(leftRgb.green + (rightRgb.green - leftRgb.green) * ratio),
        clampColorByte(leftRgb.blue + (rightRgb.blue - leftRgb.blue) * ratio),
      ].map(channel => channel.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha: left.color.alpha + (right.color.alpha - left.color.alpha) * ratio,
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
      const closeIndex = findClosingParenthesis(value, openIndex)
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
}
