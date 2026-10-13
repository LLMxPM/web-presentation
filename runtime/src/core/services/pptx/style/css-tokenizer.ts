/**
 * 文件用途：提供 CSS 表达式顶层分词、括号匹配、四则运算与基础数值归一化工具函数。
 */

/**
 * 拆分 CSS 顶层分隔符，忽略括号和引号内字符。
 * @param value CSS 片段
 * @param delimiter 单字符分隔符
 * @returns 顶层切分后的字符串数组
 */
export function splitCssTopLevel(value: string, delimiter: string): string[] {
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
 * @returns 顶层空白切分后的 token 列表
 */
export function splitCssWhitespaceTopLevel(value: string): string[] {
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
 * 查找给定左括号的匹配右括号索引。
 * @param value CSS 字符串
 * @param openIndex 左括号索引
 * @returns 右括号索引，未找到时返回 -1
 */
export function findClosingParenthesis(value: string, openIndex: number): number {
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
 * 计算受限 CSS calc 表达式，仅允许数字、括号和四则运算。
 * @param value 算术表达式
 * @returns 计算结果
 */
export function evaluateCssArithmetic(value: string): number {
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
 * 将数值限制在 [0, 1] 区间。
 * @param value 原始数值
 * @returns 归一化后的 0-1 数值
 */
export function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 1
  }
  return Math.max(0, Math.min(1, value))
}

/**
 * 将颜色通道限制在 [0, 255] 整数。
 * @param value 原始通道值
 * @returns 0-255 整数
 */
export function clampColorByte(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.min(255, Math.round(value)))
}

/**
 * 六位 HEX 转 RGB 通道对象。
 * @param hex 六位 HEX 字符串
 * @returns RGB 通道值
 */
export function hexToRgbChannels(hex: string): { red: number; green: number; blue: number } {
  const normalized = hex.replace(/^#/, '').padEnd(6, '0')
  return {
    red: Number.parseInt(normalized.slice(0, 2), 16) || 0,
    green: Number.parseInt(normalized.slice(2, 4), 16) || 0,
    blue: Number.parseInt(normalized.slice(4, 6), 16) || 0,
  }
}

/**
 * 解析百分比或 0-1 数值并归一化到 [0, 1]。
 * @param value 百分比或数值字符串
 * @returns 0-1 数值
 */
export function parseCssPercentage(value: string): number {
  const normalized = String(value || '').trim()
  const parsed = Number.parseFloat(normalized)
  if (!Number.isFinite(parsed)) {
    return 0
  }
  return clamp01(normalized.endsWith('%') || parsed > 1 ? parsed / 100 : parsed)
}

/**
 * 解析 CSS px 数值。
 * @param value CSS 长度字符串
 * @returns 浮点像素值，无效时返回 0
 */
export function parseCssPixelValue(value: string): number {
  const parsed = Number.parseFloat(String(value || ''))
  return Number.isFinite(parsed) ? parsed : 0
}
