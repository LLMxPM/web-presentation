/**
 * 文件用途：解析 CSS box-shadow 属性，识别单层无 spread 外阴影，并将其换算为 PPT 原生阴影参数或标记复杂阴影降级。
 */

import type { ParsedColor } from './CssColorParser'
import type { CssColorParser } from './CssColorParser'
import {
  parseCssPixelValue,
  splitCssTopLevel,
  splitCssWhitespaceTopLevel,
} from './css-tokenizer'

export interface NativeOuterShadow {
  type: 'outer'
  color: string
  opacity: number
  blurPt: number
  offsetPt: number
  angleDegrees: number
}

export type ParsedBoxShadowResult =
  | { kind: 'none' }
  | { kind: 'native'; shadow: NativeOuterShadow }
  | { kind: 'complex'; reason: string }

/**
 * CSS 阴影解析与 PPTX 参数转换器。
 */
export class BoxShadowParser {
  /**
   * 解析 CSS box-shadow 字符串。
   * @param value box-shadow 计算样式或声明值
   * @param element 宿主 DOM 元素
   * @param colorParser 颜色解析器
   * @param pxToPt 像素转点数换算函数
   * @returns 解析结果（无阴影、原生外阴影或复杂阴影）
   */
  parse(
    value: string,
    element: HTMLElement,
    colorParser: CssColorParser,
    pxToPt: (px: number) => number,
  ): ParsedBoxShadowResult {
    const trimmed = String(value || '').trim()
    if (!trimmed || trimmed === 'none') {
      return { kind: 'none' }
    }

    // 按顶层逗号拆分阴影层级
    const layers = splitCssTopLevel(trimmed, ',').map(item => item.trim()).filter(Boolean)
    if (layers.length === 0) {
      return { kind: 'none' }
    }
    if (layers.length > 1) {
      return { kind: 'complex', reason: '多层 box-shadow 无法用单一 PPT 形状阴影原生表达' }
    }

    const singleLayer = layers[0]
    const tokens = splitCssWhitespaceTopLevel(singleLayer)
    if (tokens.length === 0) {
      return { kind: 'none' }
    }

    let isInset = false
    const lengthTokens: string[] = []
    const colorTokens: string[] = []

    for (const token of tokens) {
      const lower = token.toLowerCase()
      if (lower === 'inset') {
        isInset = true
        continue
      }
      if (this.isLengthToken(token)) {
        lengthTokens.push(token)
      } else {
        colorTokens.push(token)
      }
    }

    if (isInset) {
      return { kind: 'complex', reason: '内阴影 (inset) 超出 PPT 原生外阴影支持范围' }
    }

    if (lengthTokens.length < 2) {
      return { kind: 'none' }
    }

    const offsetX = parseCssPixelValue(lengthTokens[0])
    const offsetY = parseCssPixelValue(lengthTokens[1])
    const blurRadius = lengthTokens.length >= 3 ? parseCssPixelValue(lengthTokens[2]) : 0
    const spreadRadius = lengthTokens.length >= 4 ? parseCssPixelValue(lengthTokens[3]) : 0

    if (Math.abs(spreadRadius) > 0.01) {
      return { kind: 'complex', reason: '带扩展半径 (spread-radius) 的阴影超出 PPT 原生外阴影支持范围' }
    }

    const colorString = colorTokens.join(' ').trim()
    let parsedColor: ParsedColor | null = null
    if (colorString) {
      parsedColor = colorParser.parseCssColor(colorString, element)
    } else {
      // 默认使用当前文本色
      const computedColor = element.ownerDocument.defaultView?.getComputedStyle(element).color || 'rgba(0,0,0,0.5)'
      parsedColor = colorParser.parseCssColor(computedColor, element)
    }

    const hex = parsedColor?.hex || '000000'
    const opacity = typeof parsedColor?.alpha === 'number' ? parsedColor.alpha : 1
    const distancePx = Math.hypot(offsetX, offsetY)
    const offsetPt = pxToPt(distancePx)
    const blurPt = pxToPt(blurRadius)

    // PPT 角度体系：0 度为正右方 (+X)，90 度为正下方 (+Y)，180 度为正左方 (-X)，270 度为正上方 (-Y)
    let angleDegrees = 0
    if (distancePx > 0.0001) {
      const rawAngle = Math.atan2(offsetY, offsetX) * (180 / Math.PI)
      angleDegrees = Math.round(((rawAngle % 360) + 360) % 360)
    }

    return {
      kind: 'native',
      shadow: {
        type: 'outer',
        color: hex,
        opacity,
        blurPt: Math.round(blurPt * 100) / 100,
        offsetPt: Math.round(offsetPt * 100) / 100,
        angleDegrees,
      },
    }
  }

  /**
   * 判断一个 CSS token 是否是长度值（以 px/pt/em/rem 等结尾或为纯数字 0）。
   */
  private isLengthToken(token: string): boolean {
    const trimmed = token.trim()
    if (trimmed === '0') {
      return true
    }
    return /^[-+]?[0-9]*\.?[0-9]+(px|pt|em|rem|vw|vh|cm|mm|in|pc|%)?$/i.test(trimmed)
  }
}
