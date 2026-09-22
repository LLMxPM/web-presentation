/**
 * 文件用途：从 SVG 字符串中提取近似宽高比例，供资源渲染提示测量复用。
 */

export interface SvgMeasureBox {
  width: number
  height: number
}

const SVG_TAG_RE = /<svg\b([^>]*)>/gi
const ATTRIBUTE_RE = /([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/g
const NUMBER_RE = /[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?/gi
// LatexViewer 使用 0.65em 作为多段公式间距；在默认 MathJax SVG ex 单位下约等于 1.75ex。
const MATHJAX_STACK_GAP_EX = 1.75

/**
 * 从 SVG 文本中提取所有可用尺寸盒。
 * @param source SVG 或包含 SVG 的 HTML 字符串
 * @returns 可用于计算比例的尺寸盒列表
 */
export function extractSvgMeasureBoxes(source: string): SvgMeasureBox[] {
  const boxes: SvgMeasureBox[] = []
  SVG_TAG_RE.lastIndex = 0
  for (const match of source.matchAll(SVG_TAG_RE)) {
    const attrs = parseAttributes(match[1] || '')
    const viewBox = parseViewBox(attrs.viewBox || attrs.viewbox)
    if (viewBox) {
      boxes.push(viewBox)
      continue
    }
    const width = parseLength(attrs.width)
    const height = parseLength(attrs.height)
    if (isPositiveFinite(width) && isPositiveFinite(height)) {
      boxes.push({ width, height })
    }
  }
  return boxes
}

/**
 * 按单个 SVG 语义计算比例。
 * @param source SVG 或包含 SVG 的 HTML 字符串
 * @returns 宽高比；无法解析时返回 null
 */
export function resolveSingleSvgAspectRatio(source: string): number | null {
  const box = extractSvgMeasureBoxes(source)[0]
  return box ? box.width / box.height : resolveSvgBBoxAspectRatio(source)
}

/**
 * 按垂直堆叠公式组语义计算比例。
 * @param source 包含一个或多个 SVG 的 HTML 字符串
 * @returns 宽高比；无法解析时返回 null
 */
export function resolveStackedSvgAspectRatio(source: string): number | null {
  const boxes = extractSvgMeasureBoxes(source)
  if (boxes.length === 0) return resolveSvgBBoxAspectRatio(source)
  const width = Math.max(...boxes.map(item => item.width))
  const height = boxes.reduce((total, item) => total + item.height, 0)
  return isPositiveFinite(width) && isPositiveFinite(height) ? width / height : null
}

/**
 * 按 Runtime LatexViewer 的多段公式排版计算整体比例。
 * @param source MathJax 输出的 HTML 字符串
 * @returns 宽高比；无法解析时返回 null
 */
export function resolveMathJaxStackedSvgAspectRatio(source: string): number | null {
  const boxes = extractMathJaxRenderedBoxes(source)
  if (boxes.length === 0) return resolveStackedSvgAspectRatio(source)
  const width = Math.max(...boxes.map(item => item.width))
  const rawHeight = boxes.reduce((total, item) => total + item.height, 0)
  const gapHeight = Math.max(0, boxes.length - 1) * MATHJAX_STACK_GAP_EX
  const height = rawHeight + gapHeight
  return isPositiveFinite(width) && isPositiveFinite(height) ? width / height : null
}

/**
 * 在浏览器测量上下文中通过 getBBox 读取首个 SVG 的比例。
 * @param source SVG 或包含 SVG 的 HTML 字符串
 * @returns 宽高比；当前环境无法测量时返回 null
 */
export function resolveSvgBBoxAspectRatio(source: string): number | null {
  if (typeof document === 'undefined') return null
  const container = document.createElement('div')
  container.innerHTML = source
  const svg = container.querySelector('svg') as (SVGElement & {
    getBBox?: () => { width: number; height: number }
  }) | null
  if (!svg || typeof svg.getBBox !== 'function') return null
  try {
    const box = svg.getBBox()
    return isPositiveFinite(box.width) && isPositiveFinite(box.height) ? box.width / box.height : null
  } catch {
    return null
  }
}

/**
 * 把数值比例格式化为后端渲染提示字段。
 * @param ratio 数值宽高比
 * @returns 稳定比例字符串和值
 */
export function formatAspectRatio(ratio: number): { aspectRatio: string; aspectRatioValue: number } | null {
  if (!isPositiveFinite(ratio)) return null
  const fraction = approximateFraction(ratio, 100)
  return {
    aspectRatio: `${fraction.numerator}:${fraction.denominator}`,
    aspectRatioValue: Math.round(ratio * 10000) / 10000,
  }
}

function parseAttributes(source: string): Record<string, string> {
  const attrs: Record<string, string> = {}
  ATTRIBUTE_RE.lastIndex = 0
  for (const match of source.matchAll(ATTRIBUTE_RE)) {
    attrs[match[1]] = match[2] ?? match[3] ?? match[4] ?? ''
  }
  return attrs
}

function extractMathJaxRenderedBoxes(source: string): SvgMeasureBox[] {
  const boxes: SvgMeasureBox[] = []
  SVG_TAG_RE.lastIndex = 0
  for (const match of source.matchAll(SVG_TAG_RE)) {
    const attrs = parseAttributes(match[1] || '')
    const width = parseLength(attrs.width)
    const height = parseLength(attrs.height)
    if (isPositiveFinite(width) && isPositiveFinite(height)) {
      boxes.push({ width, height })
      continue
    }
    const viewBox = parseViewBox(attrs.viewBox || attrs.viewbox)
    if (viewBox) {
      boxes.push(viewBox)
    }
  }
  return boxes
}

function parseViewBox(value?: string): SvgMeasureBox | null {
  const numbers = Array.from(String(value || '').matchAll(NUMBER_RE)).map(item => Number(item[0]))
  if (numbers.length < 4) return null
  const width = numbers[2]
  const height = numbers[3]
  return isPositiveFinite(width) && isPositiveFinite(height) ? { width, height } : null
}

function parseLength(value?: string): number | null {
  const normalized = String(value || '').trim()
  if (!normalized || normalized.includes('%')) return null
  const match = normalized.match(NUMBER_RE)
  if (!match) return null
  const parsed = Number(match[0])
  return isPositiveFinite(parsed) ? parsed : null
}

function isPositiveFinite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

function approximateFraction(value: number, maxDenominator: number): { numerator: number; denominator: number } {
  let bestNumerator = 1
  let bestDenominator = 1
  let bestError = Math.abs(value - 1)
  for (let denominator = 1; denominator <= maxDenominator; denominator += 1) {
    const numerator = Math.max(1, Math.round(value * denominator))
    const error = Math.abs(value - numerator / denominator)
    if (error < bestError) {
      bestNumerator = numerator
      bestDenominator = denominator
      bestError = error
    }
  }
  return { numerator: bestNumerator, denominator: bestDenominator }
}
