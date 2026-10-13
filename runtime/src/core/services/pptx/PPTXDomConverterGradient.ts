/**
 * 文件用途：封装 PPTX DOM 转换里的 CSS linear-gradient 解析与 PPT 原生渐变形状导出。
 */

import { getComputedStyle as getOwnerComputedStyle } from '@/core/services/pptx/dom/PPTXDomEnvironment'

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
    const style = element.ownerDocument.defaultView?.getComputedStyle(element) ?? getOwnerComputedStyle(element)
    const rawImage = this.resolveGradientImageValue(element)
    const gradient = this.parseLinearGradient(rawImage, element)
    if (!gradient) {
      return false
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    const label = this.layout.buildElementLabel(element)
    if (!box) {
      host.addSkippedItem('shape', label, '渐变形状尺寸无效', context)
      return true
    }

    const shapeGeometry = this.shapeGeometry.resolveShapeGeometry(host.options.shapeTypes, element, style, box)
    const elementOpacity = (context.inheritedOpacity ?? 1) * this.layout.parseOpacity(style.opacity)
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.shapeGeometry.applyOpacity(border.color, elementOpacity) || border.color,
    }))
    const uniformBorder = this.shapeGeometry.getUniformBorderInfo(borders)
    const lineOptions = uniformBorder
      ? this.shapeGeometry.buildLineOptions(uniformBorder)
      : this.shapeGeometry.buildTransparentLineOptions()

    const objectName = host.createGradientObjectName(element)
    host.options.slide.addShape(shapeGeometry.shape, {
      ...this.transform.applyToBox(box, context),
      fill: this.shapeGeometry.buildFillOptions(this.sampleLinearGradientColor(gradient.stops, 0.5)),
      line: lineOptions,
      ...shapeGeometry.options,
      ...host.buildPptObjectMeta(context, 'gradient', label),
      objectName,
    })
    host.options.gradientFillCollector?.({
      pageIndex: host.options.pageIndex,
      objectName,
      direction: gradient.direction,
      angle: gradient.angle,
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
    let angle: number | undefined
    let stopParts = parts
    const firstStop = this.parseLinearGradientStop(parts[0], element)
    if (!firstStop) {
      const parsedDirection = this.parseLinearGradientDirection(parts[0])
      if (!parsedDirection) {
        return null
      }
      direction = parsedDirection.direction
      angle = parsedDirection.angle
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
      angle,
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
   * 解析 linear-gradient 方向与角度。
   * 支持 to [side/corner]、deg、rad、turn 格式。
   * @param value 方向片段
   */
  private parseLinearGradientDirection(value: string): { direction: LinearGradientDirection; angle?: number } | null {
    const normalized = value.trim().toLowerCase()

    if (normalized.startsWith('to ')) {
      const target = normalized.slice(3).trim().replace(/\s+/g, ' ')
      switch (target) {
        case 'right':
          return { direction: 'right', angle: 90 }
        case 'left':
          return { direction: 'left', angle: 270 }
        case 'bottom':
          return { direction: 'bottom', angle: 180 }
        case 'top':
          return { direction: 'top', angle: 0 }
        case 'bottom right':
        case 'right bottom':
          return { direction: 'bottom', angle: 135 }
        case 'bottom left':
        case 'left bottom':
          return { direction: 'bottom', angle: 225 }
        case 'right top':
        case 'top right':
          return { direction: 'top', angle: 45 }
        case 'left top':
        case 'top left':
          return { direction: 'top', angle: 315 }
        default:
          return null
      }
    }

    let degrees: number | null = null
    if (normalized.endsWith('deg')) {
      degrees = Number.parseFloat(normalized.slice(0, -3))
    } else if (normalized.endsWith('rad')) {
      const rad = Number.parseFloat(normalized.slice(0, -3))
      if (Number.isFinite(rad)) {
        degrees = rad * (180 / Math.PI)
      }
    } else if (normalized.endsWith('turn')) {
      const turn = Number.parseFloat(normalized.slice(0, -4))
      if (Number.isFinite(turn)) {
        degrees = turn * 360
      }
    }

    if (degrees === null || !Number.isFinite(degrees)) {
      return null
    }

    const normalizedAngle = ((degrees % 360) + 360) % 360
    let direction: LinearGradientDirection = 'top'
    if (normalizedAngle >= 45 && normalizedAngle < 135) {
      direction = 'right'
    } else if (normalizedAngle >= 135 && normalizedAngle < 225) {
      direction = 'bottom'
    } else if (normalizedAngle >= 225 && normalizedAngle < 315) {
      direction = 'left'
    }

    return { direction, angle: normalizedAngle }
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

  /**
   * 提取元素的线性渐变值，优先使用计算样式，回退内联属性。
   */
  private resolveGradientImageValue(element: HTMLElement): string {
    const style = element.ownerDocument.defaultView?.getComputedStyle(element) ?? getOwnerComputedStyle(element)
    if (style.backgroundImage && style.backgroundImage !== 'none' && style.backgroundImage.includes('gradient')) {
      return style.backgroundImage
    }
    const inlineStyle = element.getAttribute('style') || ''
    const match = /(?:background-image|background):\s*([^;]*linear-gradient\([^;]+\))/i.exec(inlineStyle)
    if (match) {
      return match[1].trim()
    }
    return style.backgroundImage || ''
  }
}
