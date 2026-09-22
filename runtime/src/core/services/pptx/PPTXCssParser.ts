/**
 * 文件用途：解析 PPTX 导出所需的 CSS 颜色、边框简写和基础样式数值。
 */

export interface ParsedColor {
  hex: string
  alpha: number
}

export type PptxBorderSide = 'top' | 'right' | 'bottom' | 'left'

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
 * CSS 颜色与边框解析器，负责把浏览器样式值转换成 PPT 可用的 HEX/alpha/线型数据。
 */
export class PPTXCssParser {
  /**
   * 读取背景色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param style 计算样式
   */
  resolveBackgroundColorValue(element: HTMLElement, style: CSSStyleDeclaration): string {
    const declaredBackgroundColor = element.style.getPropertyValue('background-color').trim()
    if (this.isAdvancedCssColorValue(declaredBackgroundColor)) {
      return declaredBackgroundColor
    }

    const declaredBackground = element.style.getPropertyValue('background').trim()
    const backgroundColor = this.extractColorFromCssShorthand(declaredBackground, element)
    if (backgroundColor && this.isAdvancedCssColorValue(backgroundColor)) {
      return backgroundColor
    }

    return style.backgroundColor || declaredBackgroundColor || backgroundColor || ''
  }

  /**
   * 读取边框颜色，优先保留声明中的高级颜色函数。
   * @param element 元素
   * @param side 边框方向
   * @param computedColor 计算样式颜色
   */
  resolveBorderColorValue(
    element: HTMLElement,
    side: 'top' | 'right' | 'bottom' | 'left',
    computedColor: string,
  ): string {
    const inlineStyle = element.style
    const declaredValues = [
      inlineStyle.getPropertyValue(`border-${side}-color`).trim(),
      inlineStyle.getPropertyValue('border-color').trim(),
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue(`border-${side}`).trim(), element).color || '',
      this.extractBorderShorthandParts(inlineStyle.getPropertyValue('border').trim(), element).color || '',
    ].filter(Boolean)
    const advancedColor = declaredValues.find(value => this.isAdvancedCssColorValue(value))
    return advancedColor || computedColor || declaredValues[0] || ''
  }

  /**
   * 读取边框样式，computed 无效时回退解析 border 简写。
   * @param element 元素
   * @param side 边框方向
   * @param computedStyle 计算样式
   */
  resolveBorderStyleValue(
    element: HTMLElement,
    side: 'top' | 'right' | 'bottom' | 'left',
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
   */
  resolveBorderWidthValue(
    element: HTMLElement,
    side: 'top' | 'right' | 'bottom' | 'left',
    computedWidth: string,
  ): string {
    if (this.parseCssPixel(computedWidth) > 0) {
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
   * 从 background/border 简写中提取可解析颜色。
   * @param value CSS 简写值
   * @param context CSS 变量解析上下文
   */
  private extractColorFromCssShorthand(value: string, context: Element): string {
    const tokens = this.splitCssWhitespaceTopLevel(value)
    return tokens.find(token => Boolean(this.parseCssColor(token, context))) || ''
  }

  /**
   * 解析 border 简写中的宽度、样式和颜色。
   * @param value border 简写
   * @param context CSS 变量解析上下文
   */
  private extractBorderShorthandParts(
    value: string,
    context: Element,
  ): { width?: string; style?: string; color?: string } {
    const tokens = this.splitCssWhitespaceTopLevel(value)
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
      if (!result.color && this.parseCssColor(token, context)) {
        result.color = token
      }
    })

    return result
  }

  /**
   * 判断是否为 CSS border-width 值。
   * @param value CSS 宽度
   */
  private isCssBorderWidthValue(value: string): boolean {
    return /^(?:\d*\.?\d+)(?:px|pt|rem|em)?$/.test(value) ||
      value === 'thin' ||
      value === 'medium' ||
      value === 'thick'
  }

  /**
   * 将命名 border-width 归一到 px。
   * @param value CSS 宽度
   */
  private normalizeCssBorderWidth(value: string): string {
    if (value === 'thin') return '1px'
    if (value === 'medium') return '3px'
    if (value === 'thick') return '5px'
    return value
  }

  /**
   * 判断是否为需要保留原始声明的高级 CSS 颜色。
   * @param value CSS 颜色值
   */
  private isAdvancedCssColorValue(value: string): boolean {
    const normalized = value.toLowerCase()
    return normalized.includes('color-mix(') ||
      normalized.includes('rgb(from ') ||
      normalized.includes('oklch(') ||
      normalized.includes('oklab(') ||
      normalized.includes('color(')
  }

  /**
   * 解析 CSS 颜色，支持变量、命名色、HEX、RGB/HSL 与 alpha。
   * @param value CSS 颜色值
   * @param context 变量和 currentColor 的解析上下文
   * @param currentColor SVG currentColor 的显式兜底
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
      const computedColor = context ? window.getComputedStyle(context).color : ''
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
      const alpha = expanded.length === 8 ? this.clamp01(Number.parseInt(expanded.slice(6, 8), 16) / 255) : 1
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
   * 替换颜色中的 CSS 变量，支持 var(--x, fallback)。
   * @param value 原始 CSS 颜色字符串
   * @param context 变量查找上下文
   */
  private resolveCssColorString(value: string, context?: Element): string {
    let resolved = String(value || '').trim()
    for (let index = 0; index < 8 && resolved.includes('var('); index += 1) {
      const start = resolved.indexOf('var(')
      const end = this.findClosingParenthesis(resolved, start + 3)
      if (start < 0 || end < 0) {
        break
      }

      const content = resolved.slice(start + 4, end)
      const [rawName, fallback] = this.splitCssTopLevel(content, ',')
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
   */
  private resolveCssVariable(variableName: string, context?: Element): string {
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
      const inlineValue = candidate instanceof HTMLElement || candidate instanceof SVGElement
        ? candidate.style.getPropertyValue(variableName).trim()
        : ''
      const computedValue = window.getComputedStyle(candidate).getPropertyValue(variableName).trim()
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
   * @param content 函数括号内内容
   */
  private parseRgbColor(
    content: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    if (content.trim().toLowerCase().startsWith('from ')) {
      return this.parseRelativeRgbColor(content, context, currentColor)
    }

    const slashParts = this.splitCssTopLevel(content.trim(), '/')
    const channelPart = slashParts[0] || ''
    let alphaPart = slashParts[1]?.trim()
    let channels = this.splitCssTopLevel(channelPart, ',').map(item => item.trim()).filter(Boolean)
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
   * @param content 函数括号内内容
   * @param context CSS 变量解析上下文
   * @param currentColor currentColor 兜底
   */
  private parseColorMixColor(
    content: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): ParsedColor | null {
    const parts = this.splitCssTopLevel(content, ',').map(item => item.trim()).filter(Boolean)
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
    const firstRgb = this.hexToRgb(first.color.hex)
    const secondRgb = this.hexToRgb(second.color.hex)
    const alpha = first.color.alpha * ratio + second.color.alpha * (1 - ratio)
    if (alpha <= 0) {
      return null
    }

    return {
      hex: [
        this.clampColor(firstRgb.red * ratio + secondRgb.red * (1 - ratio)),
        this.clampColor(firstRgb.green * ratio + secondRgb.green * (1 - ratio)),
        this.clampColor(firstRgb.blue * ratio + secondRgb.blue * (1 - ratio)),
      ].map(item => item.toString(16).padStart(2, '0')).join('').toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析 color-mix 单个颜色停靠点。
   * @param value 停靠点字符串
   * @param context CSS 变量解析上下文
   * @param currentColor currentColor 兜底
   */
  private parseColorMixStop(
    value: string,
    context?: Element,
    currentColor?: ParsedColor | null,
  ): { color: ParsedColor | null; weight?: number } {
    const tokens = this.splitCssWhitespaceTopLevel(value)
    const lastToken = tokens[tokens.length - 1]
    const hasWeight = Boolean(lastToken?.endsWith('%'))
    const colorText = hasWeight ? tokens.slice(0, -1).join(' ') : value.trim()
    const color = colorText.toLowerCase() === 'transparent'
      ? { hex: '000000', alpha: 0 }
      : this.parseCssColor(colorText, context, currentColor)

    return {
      color,
      weight: hasWeight ? this.parsePercentage(lastToken) : undefined,
    }
  }

  /**
   * 解析 CSS color() 函数，当前支持 srgb/display-p3 的通道近似。
   * @param content 函数括号内内容
   */
  parseCssColorFunction(content: string): ParsedColor | null {
    const slashParts = this.splitCssTopLevel(content.trim(), '/')
    const channelTokens = this.splitCssWhitespaceTopLevel(slashParts[0] || '')
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
        .map(channel => this.clampColor(this.parseUnitInterval(channel) * 255).toString(16).padStart(2, '0'))
        .join('')
        .toUpperCase(),
      alpha,
    }
  }

  /**
   * 解析 CSS 相对 RGB 颜色：rgb(from <color> r g b / alpha)。
   * @param content rgb 函数括号内内容
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

    const sourceRgb = this.hexToRgb(sourceColor.hex)
    const channelContent = rest.slice(sourceEnd).trim()
    const slashParts = this.splitCssTopLevel(channelContent, '/')
    const channels = this.splitCssWhitespaceTopLevel(slashParts[0] || '')
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
   * @param value 通道字符串
   */
  private parseRgbChannel(value: string): number {
    const normalized = String(value || '').trim()
    if (normalized.endsWith('%')) {
      return this.clampColor(this.parsePercentage(normalized) * 255)
    }
    return this.clampColor(Number.parseFloat(normalized))
  }

  /**
   * 查找相对颜色语法中的源颜色结束位置。
   * @param value from 后面的内容
   */
  private findRelativeColorSourceEnd(value: string): number {
    const trimmed = value.trimStart()
    const leadingOffset = value.length - trimmed.length
    const functionMatch = trimmed.match(/^[a-z-]+\(/i)
    if (functionMatch) {
      const openIndex = leadingOffset + functionMatch[0].length - 1
      const closeIndex = this.findClosingParenthesis(value, openIndex)
      return closeIndex >= 0 ? closeIndex + 1 : -1
    }

    const tokenMatch = trimmed.match(/^\S+/)
    return tokenMatch ? leadingOffset + tokenMatch[0].length : -1
  }

  /**
   * 计算相对 RGB 通道。
   * @param expression 通道表达式
   * @param sourceRgb 源颜色 RGB
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
      return this.clampColor(Number.parseFloat(normalized))
    }

    const expressionBody = normalized.slice(5, -1)
      .replace(/\br\b/g, String(sourceRgb.red))
      .replace(/\bg\b/g, String(sourceRgb.green))
      .replace(/\bb\b/g, String(sourceRgb.blue))
    return this.clampColor(this.evaluateCssArithmetic(expressionBody))
  }

  /**
   * 计算受限 CSS calc 表达式，仅允许数字、括号和四则运算。
   * @param value 算术表达式
   */
  private evaluateCssArithmetic(value: string): number {
    const tokens = value.match(/\d*\.\d+|\d+|[()+\-*/]/g) || []
    let index = 0

    const parseFactor = (): number => {
      const token = tokens[index]
      if (token === '(') {
        index += 1
        const nested = parseExpression()
        if (tokens[index] === ')') {
          index += 1
        }
        return nested
      }
      if (token === '-') {
        index += 1
        return -parseFactor()
      }
      index += 1
      const parsed = Number.parseFloat(token || '0')
      return Number.isFinite(parsed) ? parsed : 0
    }

    const parseTerm = (): number => {
      let result = parseFactor()
      while (tokens[index] === '*' || tokens[index] === '/') {
        const operator = tokens[index]
        index += 1
        const next = parseFactor()
        result = operator === '*' ? result * next : result / next
      }
      return result
    }

    const parseExpression = (): number => {
      let result = parseTerm()
      while (tokens[index] === '+' || tokens[index] === '-') {
        const operator = tokens[index]
        index += 1
        const next = parseTerm()
        result = operator === '+' ? result + next : result - next
      }
      return result
    }

    return parseExpression()
  }

  /**
   * 解析 HSL/HSLA 颜色函数。
   * @param content 函数括号内内容
   */
  private parseHslColor(content: string): ParsedColor | null {
    const slashParts = this.splitCssTopLevel(content.trim(), '/')
    const channelPart = slashParts[0] || ''
    let alphaPart = slashParts[1]?.trim()
    let channels = this.splitCssTopLevel(channelPart, ',').map(item => item.trim()).filter(Boolean)
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
    const saturation = this.parsePercentage(channels[1])
    const lightness = this.parsePercentage(channels[2])
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

    const red = this.clampColor((redBase + match) * 255)
    const green = this.clampColor((greenBase + match) * 255)
    const blue = this.clampColor((blueBase + match) * 255)
    return { hex: [red, green, blue].map(item => item.toString(16).padStart(2, '0')).join('').toUpperCase(), alpha }
  }

  /**
   * 解析 OKLCH 颜色并转换到 sRGB。
   * @param content 函数括号内内容
   */
  private parseOklchColor(content: string): ParsedColor | null {
    const slashParts = this.splitCssTopLevel(content.trim(), '/')
    const channels = this.splitCssWhitespaceTopLevel(slashParts[0] || '')
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
   * @param content 函数括号内内容
   */
  private parseOklabColor(content: string): ParsedColor | null {
    const slashParts = this.splitCssTopLevel(content.trim(), '/')
    const channels = this.splitCssWhitespaceTopLevel(slashParts[0] || '')
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
   * @param lightness OKLab L
   * @param a OKLab a
   * @param b OKLab b
   * @param alpha alpha
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
   * @param value L 通道
   */
  private parseOklabLightness(value: string): number {
    const normalized = String(value || '').trim()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    return this.clamp01(normalized.endsWith('%') || parsed > 1 ? parsed / 100 : parsed)
  }

  /**
   * 解析 OKLab a/b 轴。
   * @param value 轴通道
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
   * @param value 线性通道值
   */
  private linearSrgbToByte(value: number): number {
    const clamped = Math.max(0, Math.min(1, value))
    const encoded = clamped <= 0.0031308
      ? 12.92 * clamped
      : 1.055 * (clamped ** (1 / 2.4)) - 0.055
    return this.clampColor(encoded * 255)
  }

  /**
   * 解析透明度通道。
   * @param value alpha 字符串
   */
  private parseAlphaChannel(value?: string): number {
    const normalized = String(value || '').trim()
    if (!normalized) {
      return 1
    }
    if (normalized.endsWith('%')) {
      return this.parsePercentage(normalized)
    }
    return this.clamp01(Number.parseFloat(normalized))
  }

  /**
   * 解析百分比或 0-1 数值。
   * @param value 百分比字符串
   */
  private parsePercentage(value: string): number {
    const normalized = String(value || '').trim()
    const parsed = Number.parseFloat(normalized)
    if (!Number.isFinite(parsed)) {
      return 0
    }
    return this.clamp01(normalized.endsWith('%') || parsed > 1 ? parsed / 100 : parsed)
  }

  /**
   * 解析 color() 中 0-1 或百分比通道。
   * @param value 通道值
   */
  private parseUnitInterval(value: string): number {
    const normalized = String(value || '').trim().toLowerCase()
    if (!normalized || normalized === 'none') {
      return 0
    }
    if (normalized.endsWith('%')) {
      return this.parsePercentage(normalized)
    }
    return this.clamp01(Number.parseFloat(normalized))
  }

  /**
   * HEX 转 RGB 通道。
   * @param hex 六位 HEX
   */
  private hexToRgb(hex: string): { red: number; green: number; blue: number } {
    const normalized = hex.replace(/^#/, '').padEnd(6, '0')
    return {
      red: Number.parseInt(normalized.slice(0, 2), 16) || 0,
      green: Number.parseInt(normalized.slice(2, 4), 16) || 0,
      blue: Number.parseInt(normalized.slice(4, 6), 16) || 0,
    }
  }

  /**
   * 解析并归一化 hue 角度。
   * @param value hue 字符串
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
   * @param value 命名色
   */
  private parseNamedColor(value: string): ParsedColor | null {
    const hex = NAMED_COLORS[value.toLowerCase()]
    return hex ? { hex, alpha: 1 } : null
  }

  /**
   * 解析元素 opacity。
   * @param value CSS opacity
   */
  parseOpacity(value: string): number {
    const normalized = String(value || '').trim()
    if (!normalized) {
      return 1
    }
    if (normalized.endsWith('%')) {
      return this.parsePercentage(normalized)
    }
    return this.clamp01(Number.parseFloat(normalized))
  }

  /**
   * 将 CSS border-style 映射到 PPTX 虚线类型。
   * @param value CSS border-style
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
   * 拆分 CSS 顶层分隔符，忽略括号和引号内字符。
   * @param value CSS 片段
   * @param delimiter 单字符分隔符
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
      if (char === '"' || char === "'") {
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
   * 按顶层空白拆分 CSS 片段，保留函数参数整体。
   * @param value CSS 片段
   */
  private splitCssWhitespaceTopLevel(value: string): string[] {
    const parts: string[] = []
    let depth = 0
    let quote = ''
    let start = -1

    for (let index = 0; index < value.length; index += 1) {
      const char = value[index]
      if (quote) {
        if (char === quote && value[index - 1] !== '\\') {
          quote = ''
        }
        continue
      }
      if (char === '"' || char === "'") {
        quote = char
        if (start < 0) {
          start = index
        }
        continue
      }
      if (char === '(') {
        depth += 1
        if (start < 0) {
          start = index
        }
        continue
      }
      if (char === ')') {
        depth = Math.max(0, depth - 1)
        continue
      }
      if (/\s/.test(char) && depth === 0) {
        if (start >= 0) {
          parts.push(value.slice(start, index))
          start = -1
        }
        continue
      }
      if (start < 0) {
        start = index
      }
    }

    if (start >= 0) {
      parts.push(value.slice(start))
    }
    return parts
  }

  /**
   * 尝试让浏览器把复杂 CSS 颜色归一成 computed color。
   * @param value CSS 颜色值
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
    const color = window.getComputedStyle(probe).color
    probe.remove()
    return color || ''
  }

  /**
   * 查找给定左括号的匹配右括号。
   * @param value CSS 字符串
   * @param openIndex 左括号索引
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
      if (char === '"' || char === "'") {
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

  /**
   * 将数值限制在 0-1。
   * @param value 原始数值
   */
  private clamp01(value: number): number {
    if (!Number.isFinite(value)) {
      return 1
    }
    return Math.max(0, Math.min(1, value))
  }

  /**
   * 将颜色通道限制在 0-255。
   * @param value 原始通道值
   */
  private clampColor(value: number): number {
    if (!Number.isFinite(value)) {
      return 0
    }
    return Math.max(0, Math.min(255, Math.round(value)))
  }

  /**
   * 解析 CSS px 值。
   * @param value CSS 长度
   */
  parseCssPixel(value: string): number {
    const parsed = Number.parseFloat(String(value || ''))
    return Number.isFinite(parsed) ? parsed : 0
  }
}
