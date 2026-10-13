/**
 * 文件用途：管理 PPTX 单页转换坐标系、DOM 盒模型测量（含 Range 文本节点测量），并聚合复杂 CSS 判定与排版对齐解析。
 */

import type { ParsedColor, PptxBorderSide } from '@/core/services/pptx/PPTXCssParser'
import { PPTXCssParser } from '@/core/services/pptx/PPTXCssParser'
import type {
  BorderInfo,
  ElementBox,
  ElementPadding,
  MeasuredElementBox,
  PptxPageConvertOptions,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import { ComplexCssDetector } from './layout/ComplexCssDetector'
import { JsdomFlexFallback } from './layout/JsdomFlexFallback'
import { TypographyAndAlignmentResolver } from './style/TypographyAndAlignmentResolver'
import {
  createRange,
  getComputedStyle,
  isHTMLElement,
  isSVGElement,
} from './dom/PPTXDomEnvironment'

/**
 * PPTX DOM 转换布局测量与样式坐标门面。
 */
export class PPTXDomConverterLayout {
  private options!: PptxPageConvertOptions
  private rootBox!: MeasuredElementBox
  private readonly complexCssDetector = new ComplexCssDetector()
  private readonly flexFallback = new JsdomFlexFallback()
  private readonly typography = new TypographyAndAlignmentResolver()

  constructor(private readonly cssParser: PPTXCssParser) {}

  /**
   * 初始化当前页面转换上下文。
   * @param options 页面转换选项
   */
  beginPage(options: PptxPageConvertOptions): void {
    this.options = options
  }

  /**
   * 写入当前页面根节点测量结果。
   * @param rootBox 页面根节点盒模型
   */
  setRootBox(rootBox: MeasuredElementBox): void {
    this.rootBox = rootBox
  }

  /**
   * 判断元素是否包含可见子元素。
   */
  hasVisibleChildElement(element: HTMLElement): boolean {
    return Array.from(element.children).some(child => this.isVisibleElement(child))
  }

  /**
   * 判断是否应将元素作为复杂 CSS 截图。
   */
  shouldScreenshotComplexElement(element: HTMLElement): boolean {
    const box = this.measureElementPixels(element)
    return this.complexCssDetector.shouldScreenshotComplexElement(element, box, this.rootBox)
  }

  /**
   * 判断背景图片值是否复杂。
   */
  isComplexImageValue(value: string): boolean {
    return this.complexCssDetector.isComplexImageValue(value)
  }

  /**
   * 判断 CSS 特效属性是否启用。
   */
  isEnabledCssEffect(value?: string): boolean {
    return this.complexCssDetector.isEnabledCssEffect(value)
  }

  /**
   * 判断 transform 是否超出可编辑映射范围。
   */
  isComplexTransform(value: string): boolean {
    return this.complexCssDetector.isComplexTransform(value)
  }

  /**
   * 计算元素在 slide 中的位置（单位 inch）。
   */
  getPptxBox(element: Element, allowOverflow = false): ElementBox | null {
    const rect = this.measureElementPixels(element)
    if (rect.width <= 0 || rect.height <= 0) {
      return null
    }

    const x = (rect.left - this.rootBox.left) * this.inchPerPxX()
    const y = (rect.top - this.rootBox.top) * this.inchPerPxY()
    return {
      x: this.roundInch(allowOverflow ? x : Math.max(0, x)),
      y: this.roundInch(allowOverflow ? y : Math.max(0, y)),
      w: this.roundInch(Math.max(0.01, Math.min(rect.width, this.rootBox.width) * this.inchPerPxX())),
      h: this.roundInch(Math.max(0.01, Math.min(rect.height, this.rootBox.height) * this.inchPerPxY())),
    }
  }

  /**
   * 计算直属文本节点在 slide 中的位置（单位 inch）。
   */
  getPptxTextNodeBox(textNode: Text, allowOverflow = false): ElementBox | null {
    const rect = this.measureTextNodePixels(textNode)
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return null
    }

    const x = (rect.left - this.rootBox.left) * this.inchPerPxX()
    const y = (rect.top - this.rootBox.top) * this.inchPerPxY()
    return {
      x: this.roundInch(allowOverflow ? x : Math.max(0, x)),
      y: this.roundInch(allowOverflow ? y : Math.max(0, y)),
      w: this.roundInch(Math.max(0.01, Math.min(rect.width, this.rootBox.width) * this.inchPerPxX())),
      h: this.roundInch(Math.max(0.01, Math.min(rect.height, this.rootBox.height) * this.inchPerPxY())),
    }
  }

  /**
   * 测量页面根节点。
   */
  measureRootBox(element: HTMLElement): MeasuredElementBox {
    const measured = this.measureElementPixels(element)
    return {
      left: measured.left,
      top: measured.top,
      width: measured.width || this.options.pageWidthPx,
      height: measured.height || this.options.pageHeightPx,
    }
  }

  /**
   * 测量元素像素位置和尺寸，jsdom 下回退读取 CSS 值与 Flex 估算。
   */
  measureElementPixels(element: Element): MeasuredElementBox {
    const rawBox = this.measureElementRawPixels(element)
    return this.applyFlexItemLayoutFallback(element, rawBox)
  }

  /**
   * 测量直属文本节点的像素位置和尺寸，优先使用 Range 获取真实文本包围盒。
   */
  measureTextNodePixels(textNode: Text): MeasuredElementBox | null {
    if (!this.normalizeText(textNode.textContent || '')) {
      return null
    }

    try {
      const range = createRange(textNode)
      range.selectNodeContents(textNode)

      const clientRects = typeof range.getClientRects === 'function'
        ? Array.from(range.getClientRects())
            .map(rect => this.rectToMeasuredBox(rect))
            .filter((rect): rect is MeasuredElementBox => rect.width > 0 && rect.height > 0)
        : []
      const mergedClientRect = this.mergeMeasuredBoxes(clientRects)
      if (mergedClientRect) {
        return mergedClientRect
      }

      if (typeof range.getBoundingClientRect === 'function') {
        const rect = this.rectToMeasuredBox(range.getBoundingClientRect())
        if (rect.width > 0 && rect.height > 0) {
          return rect
        }
      }
    } catch {
      return null
    }

    return null
  }

  /**
   * 读取元素原始像素位置和尺寸，不做布局推断。
   */
  measureElementRawPixels(element: Element): MeasuredElementBox {
    const rect = element.getBoundingClientRect()
    const style = getComputedStyle(element)
    const width = rect.width || this.parseCssPixel(style.width) || (isHTMLElement(element) ? element.offsetWidth : 0) || 0
    const height = rect.height || this.parseCssPixel(style.height) || (isHTMLElement(element) ? element.offsetHeight : 0) || 0
    const left = rect.left || this.parseCssPixel(style.left)
    const top = rect.top || this.parseCssPixel(style.top)

    return { left, top, width, height }
  }

  /**
   * 判断元素原始测量结果是否可见。
   */
  isRawVisibleElement(element: Element): boolean {
    const style = getComputedStyle(element)
    const box = this.measureElementRawPixels(element)
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      Number(style.opacity) !== 0 &&
      box.width > 0 &&
      box.height > 0
  }

  /**
   * 在测量环境没有执行 flex 布局时，按父级 flex 规则推断直接子项位置。
   */
  applyFlexItemLayoutFallback(element: Element, rawBox: MeasuredElementBox): MeasuredElementBox {
    return this.flexFallback.applyFlexItemLayoutFallback(this, element, rawBox)
  }

  /**
   * 读取四边边框样式。
   */
  getBorderInfos(element: HTMLElement, style: CSSStyleDeclaration): BorderInfo[] {
    const borderSides = [
      ['top', style.borderTopStyle, style.borderTopWidth, style.borderTopColor],
      ['right', style.borderRightStyle, style.borderRightWidth, style.borderRightColor],
      ['bottom', style.borderBottomStyle, style.borderBottomWidth, style.borderBottomColor],
      ['left', style.borderLeftStyle, style.borderLeftWidth, style.borderLeftColor],
    ] as const
    const borders: BorderInfo[] = []

    for (const [side, borderStyle, borderWidth, borderColor] of borderSides) {
      const resolvedBorderStyle = this.resolveBorderStyleValue(element, side, borderStyle)
      const widthPx = this.parseCssPixel(this.resolveBorderWidthValue(element, side, borderWidth))
      const color = this.parseCssColor(this.resolveBorderColorValue(element, side, borderColor), element)
      if (widthPx > 0 && color && resolvedBorderStyle !== 'none' && resolvedBorderStyle !== 'hidden') {
        borders.push({
          color,
          side,
          style: resolvedBorderStyle,
          widthPx,
          widthPt: Math.max(0.25, this.cssPxToPt(widthPx)),
          dashType: this.normalizeBorderDashType(resolvedBorderStyle),
        })
      }
    }

    return borders
  }

  resolveBackgroundColorValue(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.cssParser.resolveBackgroundColorValue(element, style)
  }

  resolveBorderColorValue(element: HTMLElement, side: PptxBorderSide, computedColor: string): string {
    return this.cssParser.resolveBorderColorValue(element, side, computedColor)
  }

  resolveBorderStyleValue(element: HTMLElement, side: PptxBorderSide, computedStyle: string): string {
    return this.cssParser.resolveBorderStyleValue(element, side, computedStyle)
  }

  resolveBorderWidthValue(element: HTMLElement, side: PptxBorderSide, computedWidth: string): string {
    return this.cssParser.resolveBorderWidthValue(element, side, computedWidth)
  }

  parseCssColor(value: string, context?: Element, currentColor?: ParsedColor | null): ParsedColor | null {
    return this.cssParser.parseCssColor(value, context, currentColor)
  }

  parseOpacity(value: string): number {
    return this.cssParser.parseOpacity(value)
  }

  normalizeBorderDashType(value: string): string {
    return this.cssParser.normalizeBorderDashType(value)
  }

  parseCssPixel(value: string): number {
    return this.cssParser.parseCssPixel(value)
  }

  measuredPxToPt(value: number): number {
    return Math.round(value * this.inchPerPxY() * 72 * 100) / 100
  }

  cssPxToPt(value: number): number {
    const pageHeight = this.options.pageHeightPx || this.rootBox.height
    return Math.round(value * (this.options.slideHeightIn / pageHeight) * 72 * 100) / 100
  }

  cssPxToMeasuredPx(value: number): number {
    const scaleX = this.options.pageWidthPx > 0 ? this.rootBox.width / this.options.pageWidthPx : 1
    const scaleY = this.options.pageHeightPx > 0 ? this.rootBox.height / this.options.pageHeightPx : 1
    const scale = Math.min(
      Number.isFinite(scaleX) && scaleX > 0 ? scaleX : 1,
      Number.isFinite(scaleY) && scaleY > 0 ? scaleY : 1,
    )
    return value * scale
  }

  alphaToTransparency(alpha: number): number {
    return Math.round((1 - Math.max(0, Math.min(1, alpha))) * 100)
  }

  measuredPxToInch(value: number): number {
    return value * Math.min(this.inchPerPxX(), this.inchPerPxY())
  }

  inchPerPxX(): number {
    return this.options.slideWidthIn / this.rootBox.width
  }

  inchPerPxY(): number {
    return this.options.slideHeightIn / this.rootBox.height
  }

  rootLeft(): number {
    return this.rootBox.left
  }

  rootTop(): number {
    return this.rootBox.top
  }

  roundInch(value: number): number {
    return Math.round(value * 10000) / 10000
  }

  normalizeText(text: string): string {
    return this.typography.normalizeText(text)
  }

  normalizeFontFace(fontFamily: string, text = ''): string {
    return this.typography.normalizeFontFace(fontFamily, text)
  }

  containsCjkText(text: string): boolean {
    return this.typography.containsCjkText(text)
  }

  isBoldFont(fontWeight: string): boolean {
    return this.typography.isBoldFont(fontWeight)
  }

  resolveTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration, context: VisitContext): string {
    return this.typography.resolveTextHorizontalAlign(element, style, context)
  }

  resolveTextShapeHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration, context: VisitContext): string {
    return this.typography.resolveTextShapeHorizontalAlign(element, style, context)
  }

  resolveTextVerticalAlign(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    context: VisitContext,
  ): string {
    return this.typography.resolveTextVerticalAlign(
      element,
      style,
      text,
      context,
      el => this.measureElementPixels(el),
      px => this.cssPxToMeasuredPx(px),
    )
  }

  resolveOwnInheritableTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.typography.resolveOwnInheritableTextHorizontalAlign(element, style)
  }

  resolveOwnTextVerticalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.typography.resolveOwnTextVerticalAlign(element, style, el => this.measureElementPixels(el))
  }

  resolveLayoutDisplay(element: HTMLElement, style: CSSStyleDeclaration): 'flex' | 'grid' | '' {
    return this.typography.resolveLayoutDisplay(element, style)
  }

  resolveFlexDirection(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.typography.resolveFlexDirection(element, style)
  }

  resolveClassJustifyContent(element: HTMLElement): string {
    return this.typography.resolveClassJustifyContent(element)
  }

  resolveClassAlignItems(element: HTMLElement): string {
    return this.typography.resolveClassAlignItems(element)
  }

  resolveElementCornerRadiusPx(element: HTMLElement, style: CSSStyleDeclaration): number {
    return this.typography.resolveElementCornerRadiusPx(element, style)
  }

  isPillLikeTextShape(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    return this.typography.isPillLikeTextShape(element, style)
  }

  shouldPreservePaddedInlineTextBox(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    return this.typography.isPillLikeTextShape(element, style)
  }

  resolveElementPaddingPixels(element: HTMLElement, style: CSSStyleDeclaration): ElementPadding {
    return this.typography.resolveElementPaddingPixels(element, style)
  }

  hasExplicitTextHorizontalAlign(element: HTMLElement): boolean {
    return this.typography.hasExplicitTextHorizontalAlign(element)
  }

  hasExplicitVerticalAlign(element: HTMLElement): boolean {
    return this.typography.hasExplicitVerticalAlign(element)
  }

  isSingleLineText(text: string): boolean {
    return this.typography.isSingleLineText(text)
  }

  /**
   * 构造元素摘要，用于报告和位置追踪。
   */
  buildElementLabel(element: Element): string {
    const tagName = element.tagName.toLowerCase()
    const id = element.id ? `#${element.id}` : ''
    const className = isHTMLElement(element) || isSVGElement(element)
      ? String(element.getAttribute('class') || '')
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 3)
        .map(item => `.${item}`)
        .join('')
      : ''
    const text = this.normalizeText(element.textContent || '').slice(0, 40)
    return `${tagName}${id}${className}${text ? ` ${text}` : ''}`.slice(0, 120)
  }

  /**
   * 判断元素是否可见且有有效尺寸。
   */
  isVisibleElement(element: Element): boolean {
    const style = getComputedStyle(element)
    const box = this.measureElementPixels(element)
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      Number(style.opacity) !== 0 &&
      box.width > 0 &&
      box.height > 0
  }

  private rectToMeasuredBox(rect: Pick<DOMRectReadOnly, 'left' | 'top' | 'width' | 'height'>): MeasuredElementBox {
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
  }

  private mergeMeasuredBoxes(boxes: MeasuredElementBox[]): MeasuredElementBox | null {
    if (boxes.length === 0) {
      return null
    }

    const left = Math.min(...boxes.map(box => box.left))
    const top = Math.min(...boxes.map(box => box.top))
    const right = Math.max(...boxes.map(box => box.left + box.width))
    const bottom = Math.max(...boxes.map(box => box.top + box.height))
    return {
      left,
      top,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top),
    }
  }
}
