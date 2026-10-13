/**
 * 文件用途：提供 PPTX 导出所需的 CSS 颜色、边框简写和基础样式数值解析聚合门面。
 */

import { BoxShadowParser, type ParsedBoxShadowResult } from './style/BoxShadowParser'
import { CssBoxStyleParser, type PptxBorderSide } from './style/CssBoxStyleParser'
import { CssColorParser, type ParsedColor } from './style/CssColorParser'
import { parseCssPixelValue } from './style/css-tokenizer'

export type { ParsedBoxShadowResult, ParsedColor, PptxBorderSide }

/**
 * CSS 颜色与边框解析器，委托给独立的 CssColorParser 与 CssBoxStyleParser。
 */
export class PPTXCssParser {
  private readonly colorParser = new CssColorParser()
  private readonly boxStyleParser = new CssBoxStyleParser(this.colorParser)
  private readonly boxShadowParser = new BoxShadowParser()

  /**
   * 解析 CSS box-shadow 属性为 PPT 原生外阴影或复杂阴影标记。
   */
  parseBoxShadow(value: string, element: HTMLElement, pxToPt: (px: number) => number): ParsedBoxShadowResult {
    return this.boxShadowParser.parse(value, element, this.colorParser, pxToPt)
  }

  /**
   * 读取背景色，优先保留声明中的高级颜色函数。
   */
  resolveBackgroundColorValue(element: HTMLElement, style: CSSStyleDeclaration): string {
    return this.boxStyleParser.resolveBackgroundColorValue(element, style)
  }

  /**
   * 读取边框颜色，优先保留声明中的高级颜色函数。
   */
  resolveBorderColorValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedColor: string,
  ): string {
    return this.boxStyleParser.resolveBorderColorValue(element, side, computedColor)
  }

  /**
   * 读取边框样式，computed 无效时回退解析 border 简写。
   */
  resolveBorderStyleValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedStyle: string,
  ): string {
    return this.boxStyleParser.resolveBorderStyleValue(element, side, computedStyle)
  }

  /**
   * 读取边框宽度，computed 无效时回退解析 border 简写。
   */
  resolveBorderWidthValue(
    element: HTMLElement,
    side: PptxBorderSide,
    computedWidth: string,
  ): string {
    return this.boxStyleParser.resolveBorderWidthValue(element, side, computedWidth)
  }

  /**
   * 解析 CSS 颜色，支持变量、命名色、HEX、RGB/HSL、OKLCH/OKLab 与 alpha。
   */
  parseCssColor(
    value: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    return this.colorParser.parseCssColor(value, context, currentColor)
  }

  /**
   * 解析 CSS color() 函数。
   */
  parseCssColorFunction(content: string): ParsedColor | null {
    return this.colorParser.parseCssColorFunction(content)
  }

  /**
   * 解析元素 opacity。
   */
  parseOpacity(value: string): number {
    return this.colorParser.parseOpacity(value)
  }

  /**
   * 将 CSS border-style 映射到 PPTX 虚线类型。
   */
  normalizeBorderDashType(value: string): string {
    return this.boxStyleParser.normalizeBorderDashType(value)
  }

  /**
   * 解析 CSS px 值。
   */
  parseCssPixel(value: string): number {
    return parseCssPixelValue(value)
  }
}
