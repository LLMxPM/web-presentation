/**
 * 文件用途：解析 CSS 颜色（支持命名色、HEX、RGB/HSL、OKLCH/OKLab、color()、color-mix()、相对 RGB、CSS 变量与浏览器回退探测）。
 */

import { getComputedStyle as getOwnerComputedStyle, getOwnerDocument, isHTMLElement, isSVGElement } from '@/core/services/pptx/dom/PPTXDomEnvironment'

import {
  clamp01,
  clampColorByte,
  evaluateCssArithmetic,
  findClosingParenthesis,
  hexToRgbChannels,
  parseCssPercentage,
  splitCssTopLevel,
  splitCssWhitespaceTopLevel,
} from './css-tokenizer'

export interface ParsedColor {
  hex: string
  alpha: number
}

const NAMED_COLORS: Record<string, string> = {
  aqua: '00FFFF',
  black: '000000',
  blue: '0000FF',
  cyan: '00FFFF',
  fuchsia: 'FF00FF',
  gray: '808080',
  green: '008000',
  grey: '808080',
  lime: '00FF00',
  magenta: 'FF00FF',
  maroon: '800000',
  navy: '000080',
  olive: '808000',
  orange: 'FFA500',
  pink: 'FFC0CB',
  purple: '800080',
  red: 'FF0000',
  silver: 'C0C0C0',
  teal: '008080',
  white: 'FFFFFF',
  yellow: 'FFFF00',
}

/**
 * CSS 颜色解析器，将复杂 CSS 颜色值转换为 PPT 可用的六位 HEX 与 alpha。
 */
export class CssColorParser {
  /**
   * 判断是否为需要保留原始内联声明的高级 CSS 颜色函数。
   * @param value CSS 颜色值
   * @returns 是否包含高级颜色函数
   */
  isAdvancedCssColorValue(value: string): boolean {
    const normalized = value.toLowerCase()
    return normalized.includes('color-mix(') ||
      normalized.includes('rgb(from ') ||
      normalized.includes('oklch(') ||
      normalized.includes('oklab(') ||
      normalized.includes('color(')
  }

  /**
   * 解析 CSS 颜色，支持变量、命名色、HEX、RGB/HSL、OKLCH/OKLab、color-mix 与 alpha。
   * @param value CSS 颜色值
   * @param context 变量和 currentColor 的解析上下文
   * @param currentColor SVG currentColor 的显式兜底
   * @returns 解析后的 HEX 与透明度，完全透明或无效时返回 null
   */
  parseCssColor(
    value: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    const resolved = this.resolveCssColorString(value, context)
    const normalized = resolved.trim().toLowerCase()
    if (!normalized || normalized === 'transparent' || normalized === 'none') {
      return null
    }

    if (normalized === 'currentcolor') {
      if (currentColor) {
        return currentColor
      }
      const computedColor = context ? getOwnerComputedStyle(context).color : ''
      if (computedColor && computedColor.toLowerCase() !== 'currentcolor') {
        return this.parseCssColor(computedColor, context, { hex: '000000', alpha: 1 })
      }
      return { hex: '000000', alpha: 1 }
    }

    const namedColor = this.parseNamedColor(normalized)
    if (namedColor) {
      return namedColor
    }

    const hexMatch = normalized.match(/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i)
    if (hexMatch) {
      const raw = hexMatch[1]
      const expanded = raw.length === 3 || raw.length === 4
        ? raw.split('').map(item => item + item).join('')
        : raw
      const hex = expanded.slice(0, 6).toUpperCase()
      const alpha = expanded.length === 8 ? clamp01(Number.parseInt(expanded.slice(6, 8), 16) / 255) : 1
      return alpha <= 0 ? null : { hex, alpha }
    }

    const colorMixMatch = normalized.match(/^color-mix\((.*)\)$/i)
    if (colorMixMatch) {
      return this.parseColorMixColor(colorMixMatch[1], context, currentColor)
    }

    const colorFunctionMatch = normalized.match(/^color\((.*)\)$/i)
    if (colorFunctionMatch) {
      return this.parseCssColorFunction(colorFunctionMatch[1])
    }

    const oklchMatch = normalized.match(/^oklch\((.*)\)$/i)
    if (oklchMatch) {
      return this.parseOklchColor(oklchMatch[1])
    }

    const oklabMatch = normalized.match(/^oklab\((.*)\)$/i)
    if (oklabMatch) {
      return this.parseOklabColor(oklabMatch[1])
    }

    const rgbMatch = normalized.match(/^rgba?\((.*)\)$/i)
    if (rgbMatch) {
      return this.parseRgbColor(rgbMatch[1], context, currentColor)
    }

    const hslMatch = normalized.match(/^hsla?\((.*)\)$/i)
    if (hslMatch) {
      return this.parseHslColor(hslMatch[1])
    }

    const browserColor = this.normalizeCssColorWithBrowser(resolved)
    if (browserColor && browserColor.trim().toLowerCase() !== normalized) {
      return this.parseCssColor(browserColor, context, currentColor)
    }

    return null
  }

  /**
   * 解析 CSS color() 函数，当前支持 srgb/display-p3 等标准 RGB 色彩空间的通道近似。
   * @param content 函数括号内内容
   * @returns 解析后的颜色
   */
  parseCssColorFunction(content: string): ParsedColor | null {
    const slashParts = splitCssTopLevel(content.trim(), '/')
    const channelTokens = splitCssWhitespaceTopLevel(slashParts[0] || '')
    const colorSpace = channelTokens.shift()?.toLowerCase()
    if (!colorSpace || !['srgb', 'display-p3', 'a98-rgb', 'prophoto-rgb', 'rec2020'].includes(colorSpace)) {
      return null
    }
    if (channelTokens.length < 3) {
      return null
    }

    const alpha = this.parseAlphaChannel(slashParts[1])
    if (alpha <= 0) {
      return null
    }

    return {
      hex: channelTokens.slice(0, 3)
        .map(channel => clampColorByte(this.parseUnitInterval(channel) * 255).toString(16).padStart(2, '0'))
        .join('')
        .toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析元素 opacity。
   * @param value CSS opacity 字符串
   * @returns 0-1 透明度
   */
  parseOpacity(value: string): number {
    const normalized = String(value || '').trim()
    if (!normalized) {
      return 1
    }
    if (normalized.endsWith('%')) {
      return parseCssPercentage(normalized)
    }
    return clamp01(Number.parseFloat(normalized))
  }

  /**
   * 替换颜色中的 CSS 变量，支持 var(--x, fallback)。
   * @param value 原始 CSS 颜色字符串
   * @param context 变量查找上下文
   * @returns 替换后的颜色文本
   */
  private resolveCssColorString(value: string, context?: Element): string {
    let resolved = String(value || '').trim()
    for (let index = 0; index < 8 && resolved.includes('var('); index += 1) {
      const start = resolved.indexOf('var(')
      const end = findClosingParenthesis(resolved, start + 3)
      if (start < 0 || end < 0) {
        break
      }

      const content = resolved.slice(start + 4, end)
      const [rawName, fallback] = splitCssTopLevel(content, ',')
      const variableName = rawName.trim()
      const variableValue = variableName.startsWith('--')
        ? this.resolveCssVariable(variableName, context)
        : ''
      const replacement = variableValue || fallback?.trim() || ''
      resolved = `${resolved.slice(0, start)}${replacement}${resolved.slice(end + 1)}`.trim()
    }

    return resolved
  }

  /**
   * 沿元素祖先和根节点查找 CSS 自定义属性。
   * @param variableName CSS 变量名
   * @param context 起始元素
   * @returns 变量值字符串
   */
  private resolveCssVariable(variableName: string, context?: Element): string {
    const document = getOwnerDocument(context)
    const candidates: Element[] = []
    let current: Element | null = context || null
    while (current) {
      candidates.push(current)
      current = current.parentElement
    }
    if (document.documentElement) {
      candidates.push(document.documentElement)
    }
    if (document.body) {
      candidates.push(document.body)
    }

    for (const candidate of candidates) {
      const inlineValue = isHTMLElement(candidate) || isSVGElement(candidate)
        ? candidate.style.getPropertyValue(variableName).trim()
        : ''
      const computedValue = getOwnerComputedStyle(candidate).getPropertyValue(variableName).trim()
      if (inlineValue) {
        return inlineValue
      }
      if (computedValue) {
        return computedValue
      }
    }

    return ''
  }

  /**
   * 解析 RGB/RGBA 颜色函数。
   */
  private parseRgbColor(
    content: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    if (content.trim().toLowerCase().startsWith('from ')) {
      return this.parseRelativeRgbColor(content, context, currentColor)
    }

    const slashParts = splitCssTopLevel(content.trim(), '/')
    const channelPart = slashParts[0] || ''
    let alphaPart = slashParts[1]?.trim()
    let channels = splitCssTopLevel(channelPart, ',').map(item => item.trim()).filter(Boolean)
    if (channels.length === 1) {
      channels = channelPart.trim().split(/\s+/).filter(Boolean)
    }
    if (!alphaPart && channels.length >= 4) {
      alphaPart = channels[3]
      channels = channels.slice(0, 3)
    }
    if (channels.length < 3) {
      return null
    }

    const red = this.parseRgbChannel(channels[0])
    const green = this.parseRgbChannel(channels[1])
    const blue = this.parseRgbChannel(channels[2])
    const alpha = this.parseAlphaChannel(alphaPart)
    return alpha <= 0
      ? null
      : { hex: [red, green, blue].map(item => item.toString(16).padStart(2, '0')).join('').toUpperCase(), alpha }
  }

  /**
   * 解析 CSS color-mix，当前按 srgb 通道混合。
   */
  private parseColorMixColor(
    content: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    const parts = splitCssTopLevel(content, ',').map(item => item.trim()).filter(Boolean)
    if (parts.length < 3 || !parts[0].toLowerCase().startsWith('in ')) {
      return null
    }

    const first = this.parseColorMixStop(parts[1], context, currentColor)
    const second = this.parseColorMixStop(parts[2], context, currentColor)
    if (!first.color || !second.color) {
      return null
    }

    const firstWeight = first.weight ?? (second.weight === undefined ? 0.5 : 1 - second.weight)
    const secondWeight = second.weight ?? (1 - firstWeight)
    const totalWeight = firstWeight + secondWeight
    if (totalWeight <= 0) {
      return null
    }

    const ratio = firstWeight / totalWeight
    const firstRgb = hexToRgbChannels(first.color.hex)
    const secondRgb = hexToRgbChannels(second.color.hex)
    const alpha = first.color.alpha * ratio + second.color.alpha * (1 - ratio)
    if (alpha <= 0) {
      return null
    }

    return {
      hex: [
        clampColorByte(firstRgb.red * ratio + secondRgb.red * (1 - ratio)),
        clampColorByte(firstRgb.green * ratio + secondRgb.green * (1 - ratio)),
        clampColorByte(firstRgb.blue * ratio + secondRgb.blue * (1 - ratio)),
      ].map(item => item.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析 color-mix 单个颜色停靠点。
   */
  private parseColorMixStop(
    value: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): { color: ParsedColor | null; weight?: number } {
    const tokens = splitCssWhitespaceTopLevel(value)
    const lastToken = tokens[tokens.length - 1]
    const hasWeight = Boolean(lastToken?.endsWith('%'))
    const colorText = hasWeight ? tokens.slice(0, -1).join(' ') : value.trim()
    const color = colorText.toLowerCase() === 'transparent'
      ? { hex: '000000', alpha: 0 }
      : this.parseCssColor(colorText, context, currentColor)

    return {
      color,
      weight: hasWeight ? parseCssPercentage(lastToken) : undefined,
    }
  }

  /**
   * 解析 CSS 相对 RGB 颜色：rgb(from <color> r g b / alpha)。
   */
  private parseRelativeRgbColor(
    content: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    const rest = content.trim().slice(5).trim()
    const sourceEnd = this.findRelativeColorSourceEnd(rest)
    if (sourceEnd <= 0) {
      return null
    }

    const sourceColor = this.parseCssColor(rest.slice(0, sourceEnd).trim(), context, currentColor)
    if (!sourceColor) {
      return null
    }

    const sourceRgb = hexToRgbChannels(sourceColor.hex)
    const channelContent = rest.slice(sourceEnd).trim()
    const slashParts = splitCssTopLevel(channelContent, '/')
    const channels = splitCssWhitespaceTopLevel(slashParts[0] || '')
    if (channels.length < 3) {
      return null
    }

    const alpha = this.parseAlphaChannel(slashParts[1]) * sourceColor.alpha
    if (alpha <= 0) {
      return null
    }

    return {
      hex: [
        this.evaluateRelativeRgbChannel(channels[0], sourceRgb),
        this.evaluateRelativeRgbChannel(channels[1], sourceRgb),
        this.evaluateRelativeRgbChannel(channels[2], sourceRgb),
      ].map(channel => channel.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析 RGB 单个通道，支持百分比。
   */
  private parseRgbChannel(value: string): number {
    const normalized = String(value || '').trim()
    if (normalized.endsWith('%')) {
      return clampColorByte(parseCssPercentage(normalized) * 255)
    }
    return clampColorByte(Number.parseFloat(normalized))
  }

  /**
   * 查找相对颜色语法中的源颜色结束位置。
   */
  private findRelativeColorSourceEnd(value: string): number {
    const trimmed = value.trimStart()
    const leadingOffset = value.length - trimmed.length
    const functionMatch = trimmed.match(/^[a-z-]+\(/i)
    if (functionMatch) {
      const openIndex = leadingOffset + functionMatch[0].length - 1
      const closeIndex = findClosingParenthesis(value, openIndex)
      return closeIndex >= 0 ? closeIndex + 1 : -1
    }

    const tokenMatch = trimmed.match(/^\S+/)
    return tokenMatch ? leadingOffset + tokenMatch[0].length : -1
  }

  /**
   * 计算相对 RGB 通道。
   */
  private evaluateRelativeRgbChannel(
    expression: string,
    sourceRgb: { red: number; green: number; blue: number },
  ): number {
    const normalized = String(expression || '').trim().toLowerCase()
    if (normalized === 'r') return sourceRgb.red
    if (normalized === 'g') return sourceRgb.green
    if (normalized === 'b') return sourceRgb.blue
    if (normalized.endsWith('%')) {
      return this.parseRgbChannel(normalized)
    }
    if (!normalized.startsWith('calc(')) {
      return clampColorByte(Number.parseFloat(normalized))
    }

    const expressionBody = normalized.slice(5, -1)
      .replace(/\br\b/g, String(sourceRgb.red))
      .replace(/\bg\b/g, String(sourceRgb.green))
      .replace(/\bb\b/g, String(sourceRgb.blue))
    return clampColorByte(evaluateCssArithmetic(expressionBody))
  }

  /**
   * 解析 HSL/HSLA 颜色函数。
   */
  private parseHslColor(content: string): ParsedColor | null {
    const slashParts = splitCssTopLevel(content.trim(), '/')
    const channelPart = slashParts[0] || ''
    let alphaPart = slashParts[1]?.trim()
    let channels = splitCssTopLevel(channelPart, ',').map(item => item.trim()).filter(Boolean)
    if (channels.length === 1) {
      channels = channelPart.trim().split(/\s+/).filter(Boolean)
    }
    if (!alphaPart && channels.length >= 4) {
      alphaPart = channels[3]
      channels = channels.slice(0, 3)
    }
    if (channels.length < 3) {
      return null
    }

    const hue = this.normalizeHue(channels[0])
    const saturation = parseCssPercentage(channels[1])
    const lightness = parseCssPercentage(channels[2])
    const alpha = this.parseAlphaChannel(alphaPart)
    if (alpha <= 0) {
      return null
    }

    const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
    const hueSegment = hue / 60
    const second = chroma * (1 - Math.abs((hueSegment % 2) - 1))
    const match = lightness - chroma / 2
    const [redBase, greenBase, blueBase] = hueSegment < 1
      ? [chroma, second, 0]
      : hueSegment < 2
        ? [second, chroma, 0]
        : hueSegment < 3
          ? [0, chroma, second]
          : hueSegment < 4
            ? [0, second, chroma]
            : hueSegment < 5
              ? [second, 0, chroma]
              : [chroma, 0, second]

    const red = clampColorByte((redBase + match) * 255)
    const green = clampColorByte((greenBase + match) * 255)
    const blue = clampColorByte((blueBase + match) * 255)
    return { hex: [red, green, blue].map(item => item.toString(16).padStart(2, '0')).join('').toUpperCase(), alpha }
  }

  /**
   * 解析 OKLCH 颜色并转换到 sRGB。
   */
  private parseOklchColor(content: string): ParsedColor | null {
    const slashParts = splitCssTopLevel(content.trim(), '/')
    const channels = splitCssWhitespaceTopLevel(slashParts[0] || '')
    if (channels.length < 3) {
      return null
    }

    const lightness = this.parseOklabLightness(channels[0])
    const chroma = Number.parseFloat(channels[1])
    const hue = this.normalizeHue(channels[2])
    const alpha = this.parseAlphaChannel(slashParts[1])
    if (!Number.isFinite(chroma) || alpha <= 0) {
      return null
    }

    const hueRadians = hue * Math.PI / 180
    return this.oklabToSrgbColor(
      lightness,
      chroma * Math.cos(hueRadians),
      chroma * Math.sin(hueRadians),
      alpha,
    )
  }

  /**
   * 解析 OKLab 颜色并转换到 sRGB。
   */
  private parseOklabColor(content: string): ParsedColor | null {
    const slashParts = splitCssTopLevel(content.trim(), '/')
    const channels = splitCssWhitespaceTopLevel(slashParts[0] || '')
    if (channels.length < 3) {
      return null
    }

    const lightness = this.parseOklabLightness(channels[0])
    const a = this.parseOklabAxis(channels[1])
    const b = this.parseOklabAxis(channels[2])
    const alpha = this.parseAlphaChannel(slashParts[1])
    return alpha <= 0 ? null : this.oklabToSrgbColor(lightness, a, b, alpha)
  }

  /**
   * OKLab 转 sRGB HEX。
   */
  private oklabToSrgbColor(lightness: number, a: number, b: number, alpha: number): ParsedColor {
    const lPrime = lightness + 0.3963377774 * a + 0.2158037573 * b
    const mPrime = lightness - 0.1055613458 * a - 0.0638541728 * b
    const sPrime = lightness - 0.0894841775 * a - 1.291485548 * b
    const l = lPrime ** 3
    const m = mPrime ** 3
    const s = sPrime ** 3

    return {
      hex: [
        this.linearSrgbToByte(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        this.linearSrgbToByte(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        this.linearSrgbToByte(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
      ].map(channel => channel.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析 OKLab 亮度。
   */
  private parseOklabLightness(value: string): number {
    const normalized = String(value || '').trim()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    return clamp01(normalized.endsWith('%') || parsed > 1 ? parsed / 100 : parsed)
  }

  /**
   * 解析 OKLab a/b 轴。
   */
  private parseOklabAxis(value: string): number {
    const normalized = String(value || '').trim()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    return normalized.endsWith('%') ? parsed / 100 : parsed
  }

  /**
   * 线性 sRGB 通道转 0-255。
   */
  private linearSrgbToByte(value: number): number {
    const clamped = Math.max(0, Math.min(1, value))
    const encoded = clamped <= 0.0031308
      ? 12.92 * clamped
      : 1.055 * (clamped ** (1 / 2.4)) - 0.055
    return clampColorByte(encoded * 255)
  }

  /**
   * 解析透明度通道。
   */
  private parseAlphaChannel(value?: string): number {
    const normalized = String(value || '').trim()
    if (!normalized) {
      return 1
    }
    if (normalized.endsWith('%')) {
      return parseCssPercentage(normalized)
    }
    return clamp01(Number.parseFloat(normalized))
  }

  /**
   * 解析 color() 中 0-1 或百分比通道。
   */
  private parseUnitInterval(value: string): number {
    const normalized = String(value || '').trim().toLowerCase()
    if (!normalized || normalized === 'none') {
      return 0
    }
    if (normalized.endsWith('%')) {
      return parseCssPercentage(normalized)
    }
    return clamp01(Number.parseFloat(normalized))
  }

  /**
   * 解析并归一化 hue 角度。
   */
  private normalizeHue(value: string): number {
    const normalized = String(value || '').trim().toLowerCase()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    const degrees = normalized.endsWith('turn')
      ? parsed * 360
      : normalized.endsWith('grad')
        ? parsed * 0.9
        : normalized.endsWith('rad')
          ? parsed * 180 / Math.PI
          : parsed
    return ((degrees % 360) + 360) % 360
  }

  /**
   * 解析 CSS 命名色。
   */
  private parseNamedColor(value: string): ParsedColor | null {
    const hex = NAMED_COLORS[value.toLowerCase()]
    return hex ? { hex, alpha: 1 } : null
  }

  /**
   * 尝试让浏览器把复杂 CSS 颜色归一成 computed color。
   */
  private normalizeCssColorWithBrowser(value: string): string {
    if (!document.body) {
      return ''
    }

    const probe = document.createElement('span')
    probe.style.color = value
    if (!probe.style.color) {
      return ''
    }

    probe.style.position = 'absolute'
    probe.style.visibility = 'hidden'
    document.body.appendChild(probe)
    const color = getOwnerComputedStyle(probe).color
    probe.remove()
    return color || ''
  }
}
