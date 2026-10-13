/**
 * 文件用途：负责 PPTX 形状几何类型判定（正圆/椭圆、圆角正方形、胶囊、圆角矩形、单边线）与填充/线条样式构造。
 */

import type { ParsedColor } from '@/core/services/pptx/PPTXCssParser'
import type { BorderInfo, ElementBox, PptxShapeTypes } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'

export type TextShapeGeometryKind =
  | 'circle'
  | 'rounded-square'
  | 'horizontal-capsule'
  | 'vertical-capsule'
  | 'rounded-rect'
  | 'rect'

export interface ResolvedTextShapeGeometry {
  shape: string
  options: Record<string, unknown>
  kind: TextShapeGeometryKind
}

export interface ResolvedTextShapeVisual {
  options: Record<string, unknown>
  geometry: ResolvedTextShapeGeometry
}

/**
 * 形状几何判定与视觉参数构造器。
 */
export class ShapeGeometryResolver {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /**
   * 构造文本形状的外观参数。
   */
  buildTextShapeVisualOptions(
    shapeTypes: PptxShapeTypes,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): ResolvedTextShapeVisual | null {
    const isHorizontalLine = box.h <= 0.04 && box.w > box.h
    const isVerticalLine = box.w <= 0.04 && box.h > box.w
    if (isHorizontalLine || isVerticalLine) {
      return null
    }

    const elementOpacity = this.layout.parseOpacity(style.opacity)
    const fillColor = this.applyOpacity(
      this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element),
      elementOpacity,
    )
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.applyOpacity(border.color, elementOpacity) || border.color,
    }))
    const uniformBorder = this.getUniformBorderInfo(borders)
    if (borders.length > 0 && !uniformBorder) {
      return null
    }

    const shapeGeometry = this.resolveShapeGeometry(shapeTypes, element, style, box)
    return {
      options: {
        shape: shapeGeometry.shape,
        fill: this.buildFillOptions(fillColor),
        line: uniformBorder ? this.buildLineOptions(uniformBorder) : this.buildTransparentLineOptions(),
        ...shapeGeometry.options,
      },
      geometry: shapeGeometry,
    }
  }

  /**
   * 解析 PPT 形状类型和圆角参数，正圆优先使用原生 ellipse。
   */
  resolveShapeGeometry(
    shapeTypes: PptxShapeTypes,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): ResolvedTextShapeGeometry {
    if (this.shouldUseEllipseShape(element, style, box)) {
      return {
        shape: shapeTypes.ellipse,
        options: {},
        kind: 'circle',
      }
    }

    const radiusIn = this.resolveShapeCornerRadiusIn(element, style, box)
    const isFullRadius = radiusIn > 0 && this.isFullRadiusShape(element, radiusIn, box)
    const kind: TextShapeGeometryKind = radiusIn <= 0
      ? 'rect'
      : (this.isExplicitFixedSquareShape(element, box)
          ? 'rounded-square'
          : isFullRadius
            ? (box.w > box.h ? 'horizontal-capsule' : 'vertical-capsule')
            : 'rounded-rect')
    return {
      shape: radiusIn > 0 ? shapeTypes.roundRect : shapeTypes.rect,
      options: radiusIn > 0 ? { rectRadius: radiusIn } : {},
      kind,
    }
  }

  /**
   * 将近似正圆的 PPT 外接框收敛为保持中心不变的正方形。
   */
  normalizeCircleBox(box: ElementBox): ElementBox {
    const side = Math.min(box.w, box.h)
    return {
      x: this.layout.roundInch(box.x + (box.w - side) / 2),
      y: this.layout.roundInch(box.y + (box.h - side) / 2),
      w: this.layout.roundInch(side),
      h: this.layout.roundInch(side),
    }
  }

  /**
   * 构造 PPT fill 参数。
   */
  buildFillOptions(color: ParsedColor | null): Record<string, unknown> {
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
   * 构造 PPT line 参数。
   */
  buildLineOptions(
    border?: BorderInfo | null,
    fallbackColor?: ParsedColor | null,
    fallbackWidthPt = 1,
  ): Record<string, unknown> {
    const color = border?.color || fallbackColor || { hex: '000000', alpha: 1 }
    return {
      color: color.hex,
      transparency: this.layout.alphaToTransparency(color.alpha),
      width: border?.widthPt || fallbackWidthPt,
      dashType: border?.dashType || 'solid',
    }
  }

  /**
   * 构造透明线条参数。
   */
  buildTransparentLineOptions(): Record<string, unknown> {
    return {
      color: 'FFFFFF',
      transparency: 100,
      width: 0,
    }
  }

  /**
   * 判断边框是否四边一致，可直接用 rect line 表示。
   */
  getUniformBorderInfo(borders: BorderInfo[]): BorderInfo | null {
    if (borders.length !== 4) {
      return null
    }

    const [first] = borders
    const isUniform = borders.every(border => {
      return border.color.hex === first.color.hex &&
        Math.abs(border.color.alpha - first.color.alpha) < 0.001 &&
        Math.abs(border.widthPx - first.widthPx) < 0.001 &&
        border.dashType === first.dashType
    })

    return isUniform ? first : null
  }

  /**
   * 将元素 opacity 叠加到颜色透明度。
   */
  applyOpacity(color: ParsedColor | null, opacity: number): ParsedColor | null {
    if (!color) {
      return null
    }

    return {
      hex: color.hex,
      alpha: Math.max(0, Math.min(1, color.alpha * opacity)),
    }
  }

  /**
   * 判断圆角是否表达了 full-radius 形状。
   */
  private isFullRadiusShape(element: HTMLElement, radiusIn: number, box: ElementBox): boolean {
    return element.classList.contains('rounded-full') ||
      radiusIn >= (Math.min(box.w, box.h) / 2) - 0.0001
  }

  /**
   * 判断 full-radius 的近似正方形是否应导出为 PPT 原生椭圆。
   */
  private shouldUseEllipseShape(element: HTMLElement, style: CSSStyleDeclaration, box: ElementBox): boolean {
    if (!this.isNearSquareBox(box)) {
      return false
    }

    const minSide = Math.min(box.w, box.h)
    const radiusIn = this.resolveShapeCornerRadiusIn(element, style, box)
    if (radiusIn <= 0) {
      return false
    }

    return element.classList.contains('rounded-full') || radiusIn >= (minSide / 2) - 0.0001
  }

  /**
   * 判断 PPT 外接框是否可视为近似正方形。
   */
  private isNearSquareBox(box: ElementBox): boolean {
    const minSide = Math.min(box.w, box.h)
    const maxSide = Math.max(box.w, box.h)
    return minSide > 0 && Math.abs(maxSide - minSide) <= Math.max(0.01, minSide * 0.04)
  }

  /**
   * 判断作者是否通过 width/height、尺寸类或 aspect-square 明确声明了固定正方形。
   */
  private isExplicitFixedSquareShape(element: HTMLElement, box: ElementBox): boolean {
    if (!this.isNearSquareBox(box)) {
      return false
    }

    const utilities = Array.from(element.classList).map(className => className.split(':').pop() || className)
    const hasSizeUtility = utilities.some(className => /^size-/.test(className))
    const hasWidthUtility = utilities.some(className => /^w-/.test(className))
    const hasHeightUtility = utilities.some(className => /^h-/.test(className))
    const hasAspectSquare = utilities.includes('aspect-square')
    const hasInlineWidth = Boolean(element.style.getPropertyValue('width'))
    const hasInlineHeight = Boolean(element.style.getPropertyValue('height'))
    const hasExplicitWidth = hasInlineWidth || hasWidthUtility
    const hasExplicitHeight = hasInlineHeight || hasHeightUtility
    return hasSizeUtility ||
      (hasExplicitWidth && hasExplicitHeight) ||
      (hasAspectSquare && (hasExplicitWidth || hasExplicitHeight))
  }

  /**
   * 将元素圆角从 CSS px 换算为 PPTX roundRect 需要的 inch 半径。
   */
  private resolveShapeCornerRadiusIn(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): number {
    const radiusPx = this.layout.resolveElementCornerRadiusPx(element, style)
    if (radiusPx <= 0) {
      return 0
    }

    const measuredRadiusPx = this.layout.cssPxToMeasuredPx(radiusPx)
    const radiusIn = this.layout.measuredPxToInch(measuredRadiusPx)
    const maxRadiusIn = Math.max(0, Math.min(box.w, box.h) / 2)
    return this.layout.roundInch(Math.min(maxRadiusIn, Math.max(0, radiusIn)))
  }
}
