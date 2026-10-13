/**
 * 文件用途：解析 CSS 背景色与边框（border / border-* 简写与单边属性），并映射 PPTX 边框线型。
 */

import type { CssColorParser } from './CssColorParser'
import { parseCssPixelValue, splitCssWhitespaceTopLevel } from './css-tokenizer'

export type PptxBorderSide = 'top' | 'right' | 'bottom' | 'left'

/**
 * CSS 盒样式与边框解析器。
 */
export class CssBoxStyleParser {
  constructor(private readonly colorParser: CssColorParser) {}

  /**
   * 读取背景色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param style 计算样式
   * @returns CSS 背景色文本
   */
  resolveBackgroundColorValue(element: HTMLElement, style: CSSStyleDeclaration): string {
    const declaredBackgroundColor = element.style.getPropertyValue('background-color').trim()
    if (this.colorParser.isAdvancedCssColorValue(declaredBackgroundColor)) {
      return declaredBackgroundColor
    }

    const declaredBackground = element.style.getPropertyValue('background').trim()
    const backgroundColor = this.extractColorFromCssShorthand(declaredBackground, element)
    if (backgroundColor && this.colorParser.isAdvancedCssColorValue(backgroundColor)) {
      return backgroundColor
    }

    return style.backgroundColor || declaredBackgroundColor || backgroundColor || ''
  }

  /**
   * 读取边框颜色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param side 边框方向
   * @param computedColor 计算样式颜色
   * @returns CSS 边框颜色文本
   */
  resolveBorderColorValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedColor: string,
  ): string {
    const inlineStyle = element.style
    const declaredValues = [
      inlineStyle.getPropertyValue(`border-${side}-color`).trim(),
      inlineStyle.getPropertyValue('border-color').trim(),
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue(`border-${side}`).trim(), element).color || '',
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue('border').trim(), element).color || '',
    ].filter(Boolean)
    const advancedColor = declaredValues.find(value => this.colorParser.isAdvancedCssColorValue(value))
    return advancedColor || computedColor || declaredValues[0] || ''
  }

  /**
   * 读取边框样式，computed 无效时回退解析 border 简写。
   * @param element 元素
   * @param side 边框方向
   * @param computedStyle 计算样式
   * @returns CSS 边框样式文本
   */
  resolveBorderStyleValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedStyle: string,
  ): string {
    if (computedStyle && computedStyle !== 'none') {
      return computedStyle
    }

    const inlineStyle = element.style
    return inlineStyle.getPropertyValue(`border-${side}-style`).trim() ||
      inlineStyle.getPropertyValue('border-style').trim() ||
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue(`border-${side}`).trim(), element).style ||
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue('border').trim(), element).style ||
      computedStyle
  }

  /**
   * 读取边框宽度，computed 无效时回退解析 border 简写。
   * @param element 元素
   * @param side 边框方向
   * @param computedWidth 计算宽度
   * @returns CSS 边框宽度文本
   */
  resolveBorderWidthValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedWidth: string,
  ): string {
    if (parseCssPixelValue(computedWidth) > 0) {
      return computedWidth
    }

    const inlineStyle = element.style
    return inlineStyle.getPropertyValue(`border-${side}-width`).trim() ||
      inlineStyle.getPropertyValue('border-width').trim() ||
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue(`border-${side}`).trim(), element).width ||
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue('border').trim(), element).width ||
      computedWidth
  }

  /**
   * 将 CSS border-style 映射到 PPTX 虚线类型。
   * @param value CSS border-style
   * @returns PPTX 线型标识
   */
  normalizeBorderDashType(value: string): string {
    if (value === 'dashed') {
      return 'dash'
    }
    if (value === 'dotted') {
      return 'sysDot'
    }
    return 'solid'
  }

  /**
   * 从 background/border 简写中提取可解析颜色。
   */
  private extractColorFromCssShorthand(value: string, context: Element): string {
    const tokens = splitCssWhitespaceTopLevel(value)
    return tokens.find(token => Boolean(this.colorParser.parseCssColor(token, context))) || ''
  }

  /**
   * 解析 border 简写中的宽度、样式和颜色。
   */
  private extractBorderShorthandParts(
    value: string,
    context: Element,
  ): { width?: string; style?: string; color?: string } {
    const tokens = splitCssWhitespaceTopLevel(value)
    const borderStyles = new Set(['solid', 'dashed', 'dotted', 'double', 'groove', 'ridge', 'inset', 'outset', 'none', 'hidden'])
    const result: { width?: string; style?: string; color?: string } = {}

    tokens.forEach(token => {
      const normalized = token.toLowerCase()
      if (!result.style && borderStyles.has(normalized)) {
        result.style = normalized
        return
      }
      if (!result.width && this.isCssBorderWidthValue(normalized)) {
        result.width = this.normalizeCssBorderWidth(normalized)
        return
      }
      if (!result.color && this.colorParser.parseCssColor(token, context)) {
        result.color = token
      }
    })

    return result
  }

  /**
   * 判断是否为 CSS border-width 值。
   */
  private isCssBorderWidthValue(value: string): boolean {
    return /^(?:\d*\.?\d+)(?:px|pt|rem|em)?$/.test(value) ||
      value === 'thin' ||
      value === 'medium' ||
      value === 'thick'
  }

  /**
   * 将命名 border-width 归一到 px。
   */
  private normalizeCssBorderWidth(value: string): string {
    if (value === 'thin') return '1px'
    if (value === 'medium') return '3px'
    if (value === 'thick') return '5px'
    return value
  }
}
