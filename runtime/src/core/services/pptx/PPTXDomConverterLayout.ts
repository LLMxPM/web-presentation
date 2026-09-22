/**
 * 文件用途：封装 PPTX DOM 转换里的布局测量、样式解析、字体映射与文本对齐推断。
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
import { INLINE_TEXT_TAGS } from '@/core/services/pptx/PPTXDomConverter.types'

const PPTX_PLATFORM_FONT_FACE_MAP: Record<string, string> = {
  'web presentation sans': 'Microsoft YaHei',
  'web presentation mono': 'Consolas',
}

/**
 * PPTX DOM 转换布局 helper。
 */
export class PPTXDomConverterLayout {
  private options!: PptxPageConvertOptions
  private rootBox!: MeasuredElementBox

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
   * @param element 当前元素
   */
  hasVisibleChildElement(element: HTMLElement): boolean {
    return Array.from(element.children).some(child => this.isVisibleElement(child))
  }

  /**
   * 判断是否应将元素作为复杂 CSS 截图。
   * @param element 候选元素
   */
  shouldScreenshotComplexElement(element: HTMLElement): boolean {
    const style = window.getComputedStyle(element)
    const box = this.measureElementPixels(element)
    const pageArea = this.rootBox.width * this.rootBox.height
    const elementArea = box.width * box.height
    if (pageArea > 0 && elementArea / pageArea > 0.82) {
      return false
    }

    return this.isComplexImageValue(style.backgroundImage) ||
      this.isEnabledCssEffect(style.filter) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { backdropFilter?: string }).backdropFilter) ||
      this.isEnabledCssEffect(style.clipPath) ||
      this.isEnabledCssEffect(style.maskImage) ||
      this.isEnabledCssEffect((style as CSSStyleDeclaration & { webkitMaskImage?: string }).webkitMaskImage) ||
      this.isComplexTransform(style.transform) ||
      (style.mixBlendMode && style.mixBlendMode !== 'normal')
  }

  /**
   * 判断背景图片值是否复杂。
   * @param value CSS background-image
   */
  isComplexImageValue(value: string): boolean {
    if (!value || value === 'none') {
      return false
    }
    return value.includes('gradient(') || value.includes('url(') || value.includes(',')
  }

  /**
   * 判断 CSS 特效属性是否启用。
   * @param value CSS 属性值
   */
  isEnabledCssEffect(value?: string): boolean {
    return Boolean(value && value !== 'none' && value !== 'normal')
  }

  /**
   * 判断 transform 是否超出 v1 可编辑映射范围。
   * @param value transform 值
   */
  isComplexTransform(value: string): boolean {
    const normalizedValue = String(value || '').trim()
    if (!normalizedValue || normalizedValue === 'none') {
      return false
    }

    if (this.isPureTranslateMatrix(normalizedValue) || this.isPureTranslateFunctionList(normalizedValue)) {
      return false
    }

    return true
  }

  /**
   * 判断 CSS matrix/matrix3d 是否只包含位移，纯位移已经体现在浏览器测量坐标里。
   * @param value transform 计算值
   */
  private isPureTranslateMatrix(value: string): boolean {
    const matrix = /^matrix\(([^)]+)\)$/.exec(value)
    if (matrix) {
      const values = this.parseTransformNumberList(matrix[1])
      return values.length === 6 &&
        this.isNearlyEqual(values[0], 1) &&
        this.isNearlyEqual(values[1], 0) &&
        this.isNearlyEqual(values[2], 0) &&
        this.isNearlyEqual(values[3], 1)
    }

    const matrix3d = /^matrix3d\(([^)]+)\)$/.exec(value)
    if (!matrix3d) {
      return false
    }

    const values = this.parseTransformNumberList(matrix3d[1])
    if (values.length !== 16) {
      return false
    }

    return values.every((item, index) => {
      if ([12, 13, 14].includes(index)) {
        return true
      }
      return this.isNearlyEqual(item, [0, 5, 10, 15].includes(index) ? 1 : 0)
    })
  }

  /**
   * 判断原始 transform 函数列表是否只由 translate 系列组成。
   * @param value transform 声明值
   */
  private isPureTranslateFunctionList(value: string): boolean {
    const functions = Array.from(value.matchAll(/([a-zA-Z0-9-]+)\(([^)]*)\)/g))
    if (functions.length === 0) {
      return false
    }

    return functions.every(match => {
      const name = match[1].toLowerCase()
      return ['translate', 'translate3d', 'translatex', 'translatey', 'translatez'].includes(name)
    })
  }

  /**
   * 解析 transform 矩阵数字列表。
   * @param value 逗号或空格分隔的矩阵参数
   */
  private parseTransformNumberList(value: string): number[] {
    return value
      .split(/[,\s]+/)
      .map(item => Number.parseFloat(item))
      .filter(item => Number.isFinite(item))
  }

  /**
   * 浮点近似比较，避免浏览器矩阵小数误差导致误判。
   * @param actual 实际值
   * @param expected 期望值
   */
  private isNearlyEqual(actual: number, expected: number): boolean {
    return Math.abs(actual - expected) <= 0.0001
  }

  /**
   * 计算元素在 slide 中的位置。
   * @param element 源元素
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
   * 计算直属文本节点在 slide 中的位置。
   * @param textNode 源文本节点
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
   * @param element 页面根元素
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
   * 测量元素像素位置和尺寸，jsdom 下回退读取 CSS 值。
   * @param element 源元素
   */
  measureElementPixels(element: Element): MeasuredElementBox {
    const rawBox = this.measureElementRawPixels(element)
    return this.applyFlexItemLayoutFallback(element, rawBox)
  }

  /**
   * 测量直属文本节点的像素位置和尺寸，优先使用 Range 获取真实文本包围盒。
   * @param textNode 源文本节点
   */
  measureTextNodePixels(textNode: Text): MeasuredElementBox | null {
    if (!this.normalizeText(textNode.textContent || '') || typeof document.createRange !== 'function') {
      return null
    }

    try {
      const range = document.createRange()
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
   * @param element 源元素
   */
  measureElementRawPixels(element: Element): MeasuredElementBox {
    const rect = element.getBoundingClientRect()
    const style = window.getComputedStyle(element)
    const width = rect.width || this.parseCssPixel(style.width) || (element as HTMLElement).offsetWidth || 0
    const height = rect.height || this.parseCssPixel(style.height) || (element as HTMLElement).offsetHeight || 0
    const left = rect.left || this.parseCssPixel(style.left)
    const top = rect.top || this.parseCssPixel(style.top)

    return { left, top, width, height }
  }

  /**
   * 将 DOMRect/ClientRect 转为内部测量盒模型。
   * @param rect 浏览器矩形
   */
  private rectToMeasuredBox(rect: Pick<DOMRectReadOnly, 'left' | 'top' | 'width' | 'height'>): MeasuredElementBox {
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
  }

  /**
   * 合并多个文本片段矩形为单个包围盒。
   * @param boxes 文本片段矩形集合
   */
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

  /**
   * 判断元素原始测量结果是否可见，避免 flex 兜底内部递归触发自身。
   * @param element 候选元素
   */
  isRawVisibleElement(element: Element): boolean {
    const style = window.getComputedStyle(element)
    const box = this.measureElementRawPixels(element)
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      Number(style.opacity) !== 0 &&
      box.width > 0 &&
      box.height > 0
  }

  /**
   * 在测量环境没有执行 flex 布局时，按父级 flex 规则推断直接子项位置。
   * @param element 源元素
   * @param rawBox 原始测量盒
   */
  applyFlexItemLayoutFallback(element: Element, rawBox: MeasuredElementBox): MeasuredElementBox {
    if (!(element instanceof HTMLElement) || !element.parentElement) {
      return rawBox
    }
    if (this.isOutOfFlowPositionedElement(element)) {
      return rawBox
    }

    const parent = element.parentElement
    const parentStyle = window.getComputedStyle(parent)
    if (this.resolveLayoutDisplay(parent, parentStyle) !== 'flex') {
      return rawBox
    }

    const items = Array.from(parent.children).filter((child): child is HTMLElement => {
      return child instanceof HTMLElement &&
        !this.isOutOfFlowPositionedElement(child) &&
        this.isRawVisibleElement(child)
    })
    const itemIndex = items.indexOf(element)
    if (itemIndex < 0) {
      return rawBox
    }

    const parentRawBox = this.measureElementRawPixels(parent)
    const parentBox = this.measureElementPixels(parent)
    const padding = this.resolveElementPaddingPixels(parent, parentStyle)
    const paddingLeft = this.cssPxToMeasuredPx(padding.left)
    const paddingRight = this.cssPxToMeasuredPx(padding.right)
    const paddingTop = this.cssPxToMeasuredPx(padding.top)
    const paddingBottom = this.cssPxToMeasuredPx(padding.bottom)
    const contentLeft = parentBox.left + paddingLeft
    const contentTop = parentBox.top + paddingTop
    const contentWidth = Math.max(0, parentBox.width - paddingLeft - paddingRight)
    const contentHeight = Math.max(0, parentBox.height - paddingTop - paddingBottom)
    const isColumn = this.resolveFlexDirection(parent, parentStyle).startsWith('column')
    const itemBoxes = items.map(item => this.measureElementRawPixels(item))
    const nextBox = { ...rawBox }

    if (isColumn) {
      const expectedTop = this.resolveFlexMainCoordinate(
        contentTop,
        contentHeight,
        itemBoxes.map(box => box.height),
        itemIndex,
        this.resolveClassJustifyContent(parent) || parentStyle.justifyContent,
      )
      const expectedLeft = this.resolveFlexCrossCoordinate(
        contentLeft,
        contentWidth,
        rawBox.width,
        this.resolveClassAlignItems(parent) || parentStyle.alignItems,
      )
      if (this.shouldUseFlexCoordinateFallback(rawBox.top, parentRawBox.top, expectedTop, parentBox.top)) {
        nextBox.top = expectedTop
      }
      if (this.shouldUseFlexCoordinateFallback(rawBox.left, parentRawBox.left, expectedLeft, parentBox.left)) {
        nextBox.left = expectedLeft
      }
      return nextBox
    }

    const expectedLeft = this.resolveFlexMainCoordinate(
      contentLeft,
      contentWidth,
      itemBoxes.map(box => box.width),
      itemIndex,
      this.resolveClassJustifyContent(parent) || parentStyle.justifyContent,
    )
    const expectedTop = this.resolveFlexCrossCoordinate(
      contentTop,
      contentHeight,
      rawBox.height,
      this.resolveClassAlignItems(parent) || parentStyle.alignItems,
    )
    if (this.shouldUseFlexCoordinateFallback(rawBox.left, parentRawBox.left, expectedLeft, parentBox.left)) {
      nextBox.left = expectedLeft
    }
    if (this.shouldUseFlexCoordinateFallback(rawBox.top, parentRawBox.top, expectedTop, parentBox.top)) {
      nextBox.top = expectedTop
    }
    return nextBox
  }

  /**
   * 判断元素是否脱离普通文档流，避免 flex 兜底错误重算绝对定位坐标。
   * @param element 候选元素
   */
  private isOutOfFlowPositionedElement(element: HTMLElement): boolean {
    const position = window.getComputedStyle(element).position
    return position === 'absolute' || position === 'fixed'
  }

  /**
   * 按 flex 主轴分布计算子项坐标。
   * @param contentStart 内容区起点
   * @param contentSize 内容区尺寸
   * @param itemSizes 子项主轴尺寸
   * @param itemIndex 当前子项序号
   * @param justifyContent 主轴分布方式
   */
  resolveFlexMainCoordinate(
    contentStart: number,
    contentSize: number,
    itemSizes: number[],
    itemIndex: number,
    justifyContent: string,
  ): number {
    const normalizedJustify = String(justifyContent || '').trim()
    const totalItemSize = itemSizes.reduce((total, size) => total + size, 0)
    const previousSize = itemSizes.slice(0, itemIndex).reduce((total, size) => total + size, 0)
    const freeSize = Math.max(0, contentSize - totalItemSize)
    const itemCount = itemSizes.length

    if (normalizedJustify === 'center') {
      return contentStart + freeSize / 2 + previousSize
    }
    if (normalizedJustify === 'flex-end' || normalizedJustify === 'end') {
      return contentStart + freeSize + previousSize
    }
    if (normalizedJustify === 'space-between' && itemCount > 1) {
      return contentStart + previousSize + (freeSize / (itemCount - 1)) * itemIndex
    }
    if (normalizedJustify === 'space-around' && itemCount > 0) {
      const distributedSize = freeSize / itemCount
      return contentStart + distributedSize / 2 + previousSize + distributedSize * itemIndex
    }
    if (normalizedJustify === 'space-evenly' && itemCount > 0) {
      const distributedSize = freeSize / (itemCount + 1)
      return contentStart + distributedSize + previousSize + distributedSize * itemIndex
    }
    return contentStart + previousSize
  }

  /**
   * 按 flex 交叉轴对齐计算子项坐标。
   * @param contentStart 内容区起点
   * @param contentSize 内容区尺寸
   * @param itemSize 当前子项交叉轴尺寸
   * @param alignItems 交叉轴对齐方式
   */
  resolveFlexCrossCoordinate(
    contentStart: number,
    contentSize: number,
    itemSize: number,
    alignItems: string,
  ): number {
    const normalizedAlign = String(alignItems || '').trim()
    const freeSize = Math.max(0, contentSize - itemSize)
    if (normalizedAlign === 'center') {
      return contentStart + freeSize / 2
    }
    if (normalizedAlign === 'flex-end' || normalizedAlign === 'end') {
      return contentStart + freeSize
    }
    return contentStart
  }

  /**
   * 判断是否应使用 flex 推断坐标，避免覆盖真实浏览器布局。
   * @param rawCoordinate 子项原始坐标
   * @param rawParentCoordinate 父级原始坐标
   * @param expectedCoordinate 推断坐标
   * @param parentCoordinate 父级最终坐标
   */
  shouldUseFlexCoordinateFallback(
    rawCoordinate: number,
    rawParentCoordinate: number,
    expectedCoordinate: number,
    parentCoordinate: number,
  ): boolean {
    if (Math.abs(rawCoordinate - expectedCoordinate) <= 1) {
      return false
    }

    const rawRelativeCoordinate = rawCoordinate - rawParentCoordinate
    const expectedRelativeCoordinate = expectedCoordinate - parentCoordinate
    return expectedRelativeCoordinate > 1 && Math.abs(rawRelativeCoordinate) <= 1
  }

  /**
   * 读取四边边框样式。
   * @param element 源元素
   * @param style 计算样式
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

  /**
   * 读取背景色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param style 计算样式
   */
  resolveBackgroundColorValue(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.cssParser.resolveBackgroundColorValue(element, style)
  }

  /**
   * 读取边框颜色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param side 边框方向
   * @param computedColor 计算样式颜色
   */
  resolveBorderColorValue(element: HTMLElement, side: PptxBorderSide, computedColor: string): string {
    return this.cssParser.resolveBorderColorValue(element, side, computedColor)
  }

  /**
   * 读取边框样式，computed 无效时回退解析 border 简写。
   * @param element 元素
   * @param side 边框方向
   * @param computedStyle 计算样式
   */
  resolveBorderStyleValue(element: HTMLElement, side: PptxBorderSide, computedStyle: string): string {
    return this.cssParser.resolveBorderStyleValue(element, side, computedStyle)
  }

  /**
   * 读取边框宽度，computed 无效时回退解析 border 简写。
   * @param element 元素
   * @param side 边框方向
   * @param computedWidth 计算宽度
   */
  resolveBorderWidthValue(element: HTMLElement, side: PptxBorderSide, computedWidth: string): string {
    return this.cssParser.resolveBorderWidthValue(element, side, computedWidth)
  }

  /**
   * 解析 CSS 颜色。
   * @param value CSS 颜色值
   * @param context 变量和 currentColor 的解析上下文
   * @param currentColor SVG currentColor 的显式兜底
   */
  parseCssColor(value: string, context?: Element, currentColor?: ParsedColor | null): ParsedColor | null {
    return this.cssParser.parseCssColor(value, context, currentColor)
  }

  /**
   * 解析元素 opacity。
   * @param value CSS opacity
   */
  parseOpacity(value: string): number {
    return this.cssParser.parseOpacity(value)
  }

  /**
   * 将 CSS border-style 映射到 PPTX 虚线类型。
   * @param value CSS border-style
   */
  normalizeBorderDashType(value: string): string {
    return this.cssParser.normalizeBorderDashType(value)
  }

  /**
   * 解析 CSS px 值。
   * @param value CSS 长度
   */
  parseCssPixel(value: string): number {
    return this.cssParser.parseCssPixel(value)
  }

  /**
   * 测量 px 按当前页面实际尺寸转 PPT pt。
   * @param value 测量 px 值
   */
  measuredPxToPt(value: number): number {
    return Math.round(value * this.inchPerPxY() * 72 * 100) / 100
  }

  /**
   * CSS px 按设计画布尺寸转 PPT pt，避免 transform 缩放导致字号放大。
   * @param value CSS px 值
   */
  cssPxToPt(value: number): number {
    const pageHeight = this.options.pageHeightPx || this.rootBox.height
    return Math.round(value * (this.options.slideHeightIn / pageHeight) * 72 * 100) / 100
  }

  /**
   * CSS px 转当前测量坐标系 px，用于圆角比例等需要和 rect 对齐的场景。
   * @param value CSS px 值
   */
  cssPxToMeasuredPx(value: number): number {
    const scaleX = this.options.pageWidthPx > 0 ? this.rootBox.width / this.options.pageWidthPx : 1
    const scaleY = this.options.pageHeightPx > 0 ? this.rootBox.height / this.options.pageHeightPx : 1
    const scale = Math.min(
      Number.isFinite(scaleX) && scaleX > 0 ? scaleX : 1,
      Number.isFinite(scaleY) && scaleY > 0 ? scaleY : 1,
    )
    return value * scale
  }

  /**
   * alpha 转 PPT 透明度。
   * @param alpha CSS alpha
   */
  alphaToTransparency(alpha: number): number {
    return Math.round((1 - Math.max(0, Math.min(1, alpha))) * 100)
  }

  /**
   * 测量坐标系 px 转 slide inch，适用于圆角等绝对长度。
   * @param value 测量 px 值
   */
  measuredPxToInch(value: number): number {
    return value * Math.min(this.inchPerPxX(), this.inchPerPxY())
  }

  /**
   * 横向每 px 对应 inch。
   */
  inchPerPxX(): number {
    return this.options.slideWidthIn / this.rootBox.width
  }

  /**
   * 纵向每 px 对应 inch。
   */
  inchPerPxY(): number {
    return this.options.slideHeightIn / this.rootBox.height
  }

  /** 返回页面根节点在视口测量坐标中的 left。 */
  rootLeft(): number {
    return this.rootBox.left
  }

  /** 返回页面根节点在视口测量坐标中的 top。 */
  rootTop(): number {
    return this.rootBox.top
  }

  /**
   * 统一控制 inch 精度，避免 PPTX XML 浮点过长。
   * @param value inch 值
   */
  roundInch(value: number): number {
    return Math.round(value * 10000) / 10000
  }

  /**
   * 规范化文本内容。
   * @param text 原始文本
   */
  normalizeText(text: string): string {
    return text.replace(/\s+/g, ' ').trim()
  }

  /**
   * 规范化 PPT 可识别字体名，跳过 CSS 系统字体别名。
   * @param fontFamily CSS font-family
   * @param text 文本内容，用于判断中文兜底字体
   */
  normalizeFontFace(fontFamily: string, text = ''): string {
    const candidates = String(fontFamily || '')
      .split(',')
      .map(item => item.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean)
    const concreteFont = candidates.find(font => !this.isCssSystemFontAlias(font))
    const platformFont = concreteFont
      ? PPTX_PLATFORM_FONT_FACE_MAP[concreteFont.toLowerCase()]
      : undefined
    if (platformFont) {
      return platformFont
    }
    if (concreteFont && !(this.containsCjkText(text) && this.isLatinSystemUiFont(concreteFont))) {
      return concreteFont
    }

    if (this.containsCjkText(text)) {
      return 'Microsoft YaHei'
    }

    return this.resolveSystemFontFallback(candidates) || 'Arial'
  }

  /**
   * 判断字体名是否为 CSS 系统或通用字体别名。
   * @param fontName 字体名
   */
  isCssSystemFontAlias(fontName: string): boolean {
    return [
      '-apple-system',
      'blinkmacsystemfont',
      'system-ui',
      'ui-sans-serif',
      'ui-serif',
      'ui-monospace',
      'ui-rounded',
      'sans-serif',
      'serif',
      'monospace',
      'cursive',
      'fantasy',
      'emoji',
      'math',
      'fangsong',
      'inherit',
      'initial',
      'unset',
      'revert',
    ].includes(fontName.trim().toLowerCase())
  }

  /**
   * 判断字体是否为常见拉丁系统 UI 字体。
   * @param fontName 字体名
   */
  isLatinSystemUiFont(fontName: string): boolean {
    return [
      'segoe ui',
      'roboto',
      'oxygen',
      'ubuntu',
      'cantarell',
      'fira sans',
      'droid sans',
      'helvetica neue',
      'arial',
    ].includes(fontName.trim().toLowerCase())
  }

  /**
   * 根据 CSS 通用字体类别选择 PPT 兜底字体。
   * @param candidates font-family 候选列表
   */
  resolveSystemFontFallback(candidates: string[]): string {
    const normalized = candidates.map(font => font.trim().toLowerCase())
    if (normalized.some(font => font === 'monospace' || font === 'ui-monospace')) {
      return 'Consolas'
    }
    if (normalized.some(font => font === 'serif' || font === 'ui-serif')) {
      return 'Times New Roman'
    }
    if (normalized.some(font => font === 'fangsong')) {
      return 'FangSong'
    }
    if (normalized.some(font => font === 'sans-serif' || font === 'system-ui' || font === 'ui-sans-serif')) {
      return 'Segoe UI'
    }
    return ''
  }

  /**
   * 判断文本是否包含中日韩字符。
   * @param text 文本内容
   */
  containsCjkText(text: string): boolean {
    return /[\u3400-\u9fff\uf900-\ufaff]/.test(text)
  }

  /**
   * 判断字体是否加粗。
   * @param fontWeight CSS font-weight
   */
  isBoldFont(fontWeight: string): boolean {
    if (fontWeight === 'bold' || fontWeight === 'bolder') {
      return true
    }
    const numericWeight = Number.parseInt(fontWeight, 10)
    return Number.isFinite(numericWeight) && numericWeight >= 600
  }

  /**
   * 解析文本水平对齐，兼容 text-align 与 flex/grid 居中布局。
   * @param element 文本元素
   * @param style 计算样式
   * @param context 当前继承上下文
   */
  resolveTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration, context: VisitContext): string {
    const ownAlign = this.resolveOwnTextHorizontalAlign(element, style)
    if (ownAlign !== 'left' || this.hasExplicitTextHorizontalAlign(element)) {
      return ownAlign
    }

    return context.inheritedTextAlign || ownAlign
  }

  /**
   * 解析文本形状水平对齐，pill/badge 默认使用居中以贴近 HTML 视觉盒。
   * @param element 文本元素
   * @param style 计算样式
   * @param context 当前继承上下文
   */
  resolveTextShapeHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration, context: VisitContext): string {
    const align = this.resolveTextHorizontalAlign(element, style, context)
    if (align !== 'left' || this.hasExplicitTextHorizontalAlign(element)) {
      return align
    }

    return this.isPillLikeTextShape(element, style) ? 'center' : align
  }

  /**
   * 解析文本垂直对齐，兼容 flex/grid 与 line-height 居中。
   * @param element 文本元素
   * @param style 计算样式
   * @param text 文本内容
   * @param context 当前继承上下文
   */
  resolveTextVerticalAlign(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    context: VisitContext,
  ): string {
    if (this.isSingleLineText(text) && this.isLineHeightCentered(element, style)) {
      return 'middle'
    }

    const ownAlign = this.resolveOwnTextVerticalAlign(element, style)
    if (ownAlign !== 'top' || this.hasExplicitVerticalAlign(element)) {
      return ownAlign
    }

    return context.inheritedVerticalAlign || ownAlign
  }

  /**
   * 解析元素自身声明或布局提供的水平对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveOwnTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const textAlign = this.resolveOwnInheritableTextHorizontalAlign(element, style)
    return this.resolveLayoutHorizontalAlign(element, style) || textAlign
  }

  /**
   * 解析真正会按 HTML 规则向后代继承的文本水平对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveOwnInheritableTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const textAlign = this.normalizeCssHorizontalAlign(style.textAlign, style.direction)
    if (textAlign !== 'left') {
      return textAlign
    }

    return this.resolveClassTextAlign(element, style.direction) || textAlign
  }

  /**
   * 解析元素自身声明或布局提供的垂直对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveOwnTextVerticalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.resolveCssVerticalAlign(element, style) ||
      this.resolveClassVerticalAlign(element) ||
      this.resolveLayoutVerticalAlign(element, style) ||
      'top'
  }

  /**
   * 从 flex/grid 布局中推断水平对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveLayoutHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const display = this.resolveLayoutDisplay(element, style)
    if (display === 'flex') {
      const isColumn = this.resolveFlexDirection(element, style).startsWith('column')
      const value = isColumn
        ? this.resolveClassAlignItems(element) || style.alignItems
        : this.resolveClassJustifyContent(element) || style.justifyContent
      return this.normalizeCssHorizontalAlign(value, style.direction, true)
    }
    if (display === 'grid') {
      const gridStyle = style as CSSStyleDeclaration & {
        justifyItems?: string
        placeContent?: string
        placeItems?: string
      }
      return this.normalizeCssHorizontalAlign(
        gridStyle.justifyItems ||
          this.resolveClassJustifyItems(element) ||
          this.extractPlaceAlignment(gridStyle.placeItems || style.getPropertyValue('place-items'), 'horizontal') ||
          this.resolveClassPlaceAlignment(element, 'horizontal') ||
          style.justifyContent ||
          this.resolveClassJustifyContent(element) ||
          this.extractPlaceAlignment(gridStyle.placeContent || style.getPropertyValue('place-content'), 'horizontal'),
        style.direction,
        true,
      )
    }

    return ''
  }

  /**
   * 从 flex/grid 布局中推断垂直对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveLayoutVerticalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const display = this.resolveLayoutDisplay(element, style)
    if (display === 'flex') {
      const isColumn = this.resolveFlexDirection(element, style).startsWith('column')
      const value = isColumn
        ? this.resolveClassJustifyContent(element) || style.justifyContent
        : this.resolveClassAlignItems(element) || style.alignItems
      return this.normalizeCssVerticalAlign(value)
    }
    if (display === 'grid') {
      const gridStyle = style as CSSStyleDeclaration & {
        placeContent?: string
        placeItems?: string
      }
      return this.normalizeCssVerticalAlign(
        style.alignItems ||
          this.resolveClassAlignItems(element) ||
          this.extractPlaceAlignment(gridStyle.placeItems || style.getPropertyValue('place-items'), 'vertical') ||
          this.resolveClassPlaceAlignment(element, 'vertical') ||
          style.alignContent ||
          this.extractPlaceAlignment(gridStyle.placeContent || style.getPropertyValue('place-content'), 'vertical'),
      )
    }

    return ''
  }

  /**
   * 解析布局 display，computed 缺失时回退 Tailwind class。
   * @param element 当前元素
   * @param style 计算样式
   */
  resolveLayoutDisplay(element: HTMLElement, style: CSSStyleDeclaration): 'flex' | 'grid' | '' {
    if (style.display.includes('flex') || this.hasAnyClass(element, ['flex', 'inline-flex'])) {
      return 'flex'
    }
    if (style.display.includes('grid') || this.hasAnyClass(element, ['grid', 'inline-grid'])) {
      return 'grid'
    }
    return ''
  }

  /**
   * 解析 flex-direction，computed 缺失时回退 Tailwind class。
   * @param element 当前元素
   * @param style 计算样式
   */
  resolveFlexDirection(element: HTMLElement, style: CSSStyleDeclaration): string {
    if (this.hasAnyClass(element, ['flex-col', 'flex-col-reverse'])) {
      return 'column'
    }
    if (this.hasAnyClass(element, ['flex-row', 'flex-row-reverse'])) {
      return 'row'
    }
    return style.flexDirection || 'row'
  }

  /**
   * 从 place-items/place-content 里取水平或垂直对齐。
   * @param value CSS place-* 值
   * @param axis 目标轴
   */
  extractPlaceAlignment(value: string | undefined, axis: 'horizontal' | 'vertical'): string {
    const parts = String(value || '').trim().split(/\s+/).filter(Boolean)
    if (parts.length === 0) {
      return ''
    }
    if (parts.length === 1) {
      return parts[0]
    }
    return axis === 'vertical' ? parts[0] : parts[1]
  }

  /**
   * 从 Tailwind 文本对齐类名中解析水平对齐。
   * @param element 当前元素
   * @param direction 文本方向
   */
  resolveClassTextAlign(element: HTMLElement, direction = 'ltr'): string {
    if (element.classList.contains('text-center')) return 'center'
    if (element.classList.contains('text-right')) return 'right'
    if (element.classList.contains('text-left')) return 'left'
    if (element.classList.contains('text-justify')) return 'justify'
    if (element.classList.contains('text-start')) return direction === 'rtl' ? 'right' : 'left'
    if (element.classList.contains('text-end')) return direction === 'rtl' ? 'left' : 'right'
    return ''
  }

  /**
   * 从 Tailwind justify-* 类名中解析主轴对齐。
   * @param element 当前元素
   */
  resolveClassJustifyContent(element: HTMLElement): string {
    if (element.classList.contains('justify-center')) return 'center'
    if (element.classList.contains('justify-end')) return 'flex-end'
    if (element.classList.contains('justify-start')) return 'flex-start'
    if (element.classList.contains('justify-between')) return 'space-between'
    if (element.classList.contains('justify-around')) return 'space-around'
    if (element.classList.contains('justify-evenly')) return 'space-evenly'
    return ''
  }

  /**
   * 从 Tailwind items-* 类名中解析交叉轴对齐。
   * @param element 当前元素
   */
  resolveClassAlignItems(element: HTMLElement): string {
    if (element.classList.contains('items-center')) return 'center'
    if (element.classList.contains('items-end')) return 'flex-end'
    if (element.classList.contains('items-start')) return 'flex-start'
    if (element.classList.contains('items-baseline')) return 'baseline'
    if (element.classList.contains('items-stretch')) return 'stretch'
    return ''
  }

  /**
   * 从 Tailwind justify-items-* 类名中解析网格水平对齐。
   * @param element 当前元素
   */
  resolveClassJustifyItems(element: HTMLElement): string {
    if (element.classList.contains('justify-items-center')) return 'center'
    if (element.classList.contains('justify-items-end')) return 'end'
    if (element.classList.contains('justify-items-start')) return 'start'
    return ''
  }

  /**
   * 从 Tailwind place-items-* 类名中解析网格双轴对齐。
   * @param element 当前元素
   * @param axis 目标轴
   */
  resolveClassPlaceAlignment(element: HTMLElement, axis: 'horizontal' | 'vertical'): string {
    if (element.classList.contains('place-items-center') || element.classList.contains('place-content-center')) {
      return 'center'
    }
    if (element.classList.contains('place-items-end') || element.classList.contains('place-content-end')) {
      return axis === 'vertical' ? 'end' : 'end'
    }
    if (element.classList.contains('place-items-start') || element.classList.contains('place-content-start')) {
      return axis === 'vertical' ? 'start' : 'start'
    }
    return ''
  }

  /**
   * 从 Tailwind vertical-align 类名中解析垂直对齐。
   * @param element 当前元素
   */
  resolveClassVerticalAlign(element: HTMLElement): string {
    if (element.classList.contains('align-middle')) return 'middle'
    if (element.classList.contains('align-bottom') || element.classList.contains('align-text-bottom')) return 'bottom'
    if (element.classList.contains('align-top') || element.classList.contains('align-text-top')) return 'top'
    return ''
  }

  /**
   * 从 vertical-align/table-cell 中推断文本垂直对齐。
   * @param element 文本元素
   * @param style 计算样式
   */
  resolveCssVerticalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const normalized = this.normalizeCssVerticalAlign(style.verticalAlign)
    if (!normalized) {
      return ''
    }

    const tagName = element.tagName.toLowerCase()
    if (style.display.includes('table-cell') || ['td', 'th'].includes(tagName)) {
      return normalized
    }

    const box = this.measureElementPixels(element)
    if (box.height > 0 && this.isTextOnlyLayoutElement(element)) {
      return normalized
    }

    return ''
  }

  /**
   * 读取元素圆角半径，优先使用已解析的左上角或统一 border-radius。
   * @param element 源元素
   * @param style 计算样式
   */
  resolveElementCornerRadiusPx(element: HTMLElement, style: CSSStyleDeclaration): number {
    const topLeftRadius = this.parseCssPixel(style.borderTopLeftRadius)
    if (topLeftRadius > 0) {
      return topLeftRadius
    }

    const borderRadius = this.parseCssPixel(style.borderRadius)
    if (borderRadius > 0) {
      return borderRadius
    }

    return 0
  }

  /**
   * 判断文本形状是否属于 pill/badge 一类的胶囊文本盒。
   * @param element 文本形状元素
   * @param style 计算样式
   */
  isPillLikeTextShape(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const tagName = element.tagName.toLowerCase()
    const padding = this.resolveElementPaddingPixels(element, style)
    const hasHorizontalPadding = padding.left > 0 || padding.right > 0
    const radiusPx = this.resolveElementCornerRadiusPx(element, style)
    const isInlineLike = style.display.includes('inline') || INLINE_TEXT_TAGS.has(tagName) || tagName === 'button'
    return hasHorizontalPadding &&
      isInlineLike &&
      (radiusPx > 0 || this.hasRoundedClass(element)) &&
      this.isSingleLineText(this.normalizeText(element.textContent || ''))
  }

  /**
   * 判断普通文本是否也需要保留 inline padding 盒子。
   * @param element 文本元素
   * @param style 计算样式
   */
  shouldPreservePaddedInlineTextBox(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    return this.isPillLikeTextShape(element, style)
  }

  /**
   * 解析元素四边 padding，computed 缺失时回退常见 Tailwind spacing 类。
   * @param element 源元素
   * @param style 计算样式
   */
  resolveElementPaddingPixels(element: HTMLElement, style: CSSStyleDeclaration): ElementPadding {
    const classPadding = this.resolveTailwindPaddingPixels(element)
    return {
      top: this.parseCssPixel(style.paddingTop) || classPadding.top,
      right: this.parseCssPixel(style.paddingRight) || classPadding.right,
      bottom: this.parseCssPixel(style.paddingBottom) || classPadding.bottom,
      left: this.parseCssPixel(style.paddingLeft) || classPadding.left,
    }
  }

  /**
   * 从 Tailwind padding 类中解析 px 值，覆盖测试环境没有 CSS 的场景。
   * @param element 源元素
   */
  resolveTailwindPaddingPixels(element: HTMLElement): ElementPadding {
    const padding: ElementPadding = { top: 0, right: 0, bottom: 0, left: 0 }
    Array.from(element.classList).forEach(className => {
      if (className.includes(':')) {
        return
      }
      const match = /^(p|px|py|pt|pr|pb|pl)-(.+)$/.exec(className)
      if (!match) {
        return
      }

      const value = this.resolveTailwindSpacingPixels(match[2])
      if (value <= 0) {
        return
      }
      this.applyPaddingUtility(padding, match[1], value)
    })
    return padding
  }

  /**
   * 将 Tailwind spacing token 转为 CSS px。
   * @param token spacing token
   */
  resolveTailwindSpacingPixels(token: string): number {
    if (token === 'px') {
      return 1
    }

    const arbitraryPx = /^\[(\d+(?:\.\d+)?)px\]$/.exec(token)
    if (arbitraryPx) {
      return Number.parseFloat(arbitraryPx[1])
    }

    const numeric = Number.parseFloat(token)
    return Number.isFinite(numeric) ? numeric * 4 : 0
  }

  /**
   * 应用 Tailwind padding utility 到四边 padding。
   * @param padding 当前 padding
   * @param utility utility 前缀
   * @param value px 值
   */
  applyPaddingUtility(padding: ElementPadding, utility: string, value: number): void {
    if (utility === 'p' || utility === 'py' || utility === 'pt') padding.top = value
    if (utility === 'p' || utility === 'px' || utility === 'pr') padding.right = value
    if (utility === 'p' || utility === 'py' || utility === 'pb') padding.bottom = value
    if (utility === 'p' || utility === 'px' || utility === 'pl') padding.left = value
  }

  /**
   * 判断元素是否有圆角类名。
   * @param element 源元素
   */
  hasRoundedClass(element: HTMLElement): boolean {
    return Array.from(element.classList).some(className => {
      return className.startsWith('rounded') && className !== 'rounded-none'
    })
  }

  /**
   * 判断元素是否显式声明了可继承的文本水平对齐。
   * @param element 文本元素
   */
  hasExplicitTextHorizontalAlign(element: HTMLElement): boolean {
    const inlineStyle = element.style
    return Boolean(
      inlineStyle.getPropertyValue('text-align') ||
      element.getAttribute('align') ||
      this.hasAnyClass(element, [
        'text-left',
        'text-center',
        'text-right',
        'text-justify',
        'text-start',
        'text-end',
      ]),
    )
  }

  /**
   * 判断元素是否显式声明了垂直对齐。
   * @param element 文本元素
   */
  hasExplicitVerticalAlign(element: HTMLElement): boolean {
    const inlineStyle = element.style
    return Boolean(
      inlineStyle.getPropertyValue('vertical-align') ||
      inlineStyle.getPropertyValue('align-items') ||
      inlineStyle.getPropertyValue('align-content') ||
      inlineStyle.getPropertyValue('justify-content') ||
      inlineStyle.getPropertyValue('place-content') ||
      inlineStyle.getPropertyValue('place-items') ||
      element.getAttribute('valign') ||
      this.hasAnyClass(element, [
        'items-start',
        'items-center',
        'items-end',
        'justify-start',
        'justify-center',
        'justify-end',
        'justify-between',
        'justify-around',
        'justify-evenly',
        'place-items-start',
        'place-items-center',
        'place-items-end',
        'place-content-start',
        'place-content-center',
        'place-content-end',
        'align-top',
        'align-middle',
        'align-bottom',
        'align-text-top',
        'align-text-bottom',
      ]),
    )
  }

  /**
   * 判断元素是否包含任一 class。
   * @param element 当前元素
   * @param classNames class 名称集合
   */
  hasAnyClass(element: HTMLElement, classNames: string[]): boolean {
    return classNames.some(className => element.classList.contains(className))
  }

  /**
   * 规范化 CSS 水平对齐。
   * @param value CSS 对齐值
   * @param direction 文本方向
   * @param fromLayout 是否来自布局属性
   */
  normalizeCssHorizontalAlign(value: string, direction = 'ltr', fromLayout = false): string {
    const normalized = String(value || '').trim()
    if (normalized === 'center') {
      return 'center'
    }
    if (normalized === 'right' || normalized === 'end' || normalized === 'flex-end') {
      return direction === 'rtl' && normalized === 'end' ? 'left' : 'right'
    }
    if (normalized === 'justify') {
      return 'justify'
    }
    if (normalized === 'left' || normalized === 'start' || normalized === 'flex-start') {
      return direction === 'rtl' && normalized === 'start' ? 'right' : 'left'
    }
    return fromLayout ? '' : 'left'
  }

  /**
   * 规范化 CSS 垂直对齐。
   * @param value CSS 对齐值
   */
  normalizeCssVerticalAlign(value: string): string {
    const normalized = String(value || '').trim()
    if (normalized === 'center' || normalized === 'middle') {
      return 'middle'
    }
    if (normalized === 'end' || normalized === 'flex-end' || normalized === 'bottom' || normalized === 'text-bottom') {
      return 'bottom'
    }
    if (normalized === 'start' || normalized === 'flex-start' || normalized === 'top' || normalized === 'text-top') {
      return 'top'
    }
    return ''
  }

  /**
   * 判断当前元素是否可把布局对齐直接映射到文本框。
   * @param element 文本元素
   */
  isTextOnlyLayoutElement(element: HTMLElement): boolean {
    return element.children.length === 0 ||
      Array.from(element.children).every(child => INLINE_TEXT_TAGS.has(child.tagName.toLowerCase()))
  }

  /**
   * 判断是否为单行文本。
   * @param text 文本内容
   */
  isSingleLineText(text: string): boolean {
    return !/[\r\n]/.test(text)
  }

  /**
   * 判断 line-height 是否表达了垂直居中。
   * @param element 文本元素
   * @param style 计算样式
   */
  isLineHeightCentered(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const lineHeight = this.parseCssPixel(style.lineHeight)
    if (lineHeight <= 0) {
      return false
    }

    const cssHeight = this.parseCssPixel(style.height)
    const measuredHeight = this.measureElementPixels(element).height
    const measuredCssScale = this.cssPxToMeasuredPx(1)
    const measuredCssHeight = measuredCssScale > 0 ? measuredHeight / measuredCssScale : 0
    const targetHeight = cssHeight || measuredCssHeight
    return targetHeight > 0 && Math.abs(lineHeight - targetHeight) <= 1
  }

  /**
   * 构造元素摘要，用于报告和位置追踪。
   * @param element 源元素
   */
  buildElementLabel(element: Element): string {
    const tagName = element.tagName.toLowerCase()
    const id = element.id ? `#${element.id}` : ''
    const className = element instanceof HTMLElement || element instanceof SVGElement
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
   * @param element 候选元素
   */
  isVisibleElement(element: Element): boolean {
    const style = window.getComputedStyle(element)
    const box = this.measureElementPixels(element)
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      Number(style.opacity) !== 0 &&
      box.width > 0 &&
      box.height > 0
  }
}
