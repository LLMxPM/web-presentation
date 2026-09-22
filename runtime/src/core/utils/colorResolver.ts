/**
 * 颜色解析工具
 * 支持将主题系统的颜色类转换为 CSS 变量或实际颜色值
 */

/**
 * 主题颜色映射表
 * 将 Tailwind 颜色类映射到对应的 CSS 变量
 */
const THEME_COLOR_MAP: Record<string, string> = {
  // 文本颜色
  'text-primary': '--tw-color-text-primary',
  'text-secondary': '--tw-color-text-secondary',
  'text-invert': '--tw-color-text-invert',
  
  // 背景颜色
  'bg-bg': '--tw-color-bg-default',
  'bg-bg-invert': '--tw-color-bg-invert',
  
  // 边框颜色
  'border-border': '--tw-color-border-default',
  'border-border-subtle': '--tw-color-border-subtle',
  
  // 链接颜色
  'text-link': '--tw-color-link-default',
  'text-link-hover': '--tw-color-link-hover',
  'text-link-visited': '--tw-color-link-visited',
  
  // 强调色
  'text-accent1': '--tw-color-accent1',
  'text-accent2': '--tw-color-accent2',
  'text-accent3': '--tw-color-accent3',
  'text-accent4': '--tw-color-accent4',
  'text-accent5': '--tw-color-accent5',
  'text-accent6': '--tw-color-accent6',
  
  // 简化的颜色类名（不带前缀）
  'primary': '--tw-color-text-primary',
  'secondary': '--tw-color-text-secondary',
  'invert': '--tw-color-text-invert',
  'background': '--tw-color-bg-default',
  'background-invert': '--tw-color-bg-invert',
  'bg': '--tw-color-bg-default',
  'bg-invert': '--tw-color-bg-invert',
  'border': '--tw-color-border-default',
  'border-subtle': '--tw-color-border-subtle',
  'link': '--tw-color-link-default',
  'link-hover': '--tw-color-link-hover',
  'link-visited': '--tw-color-link-visited',
  'accent1': '--tw-color-accent1',
  'accent2': '--tw-color-accent2',
  'accent3': '--tw-color-accent3',
  'accent4': '--tw-color-accent4',
  'accent5': '--tw-color-accent5',
  'accent6': '--tw-color-accent6',
}

/**
 * 颜色强度映射表
 * 用于处理带强度的颜色类（如 primary-500, accent1-300）
 */
const COLOR_INTENSITY_MAP: Record<string, number> = {
  '50': 0.9,
  '100': 0.8,
  '200': 0.65,
  '300': 0.5,
  '400': 0.3,
  '500': 1, // 默认强度
  '600': 0.85,
  '700': 0.7,
  '800': 0.55,
  '900': 0.4,
}

/**
 * 根据主题变量和色阶生成可直接用于 style 的颜色表达式。
 * 说明：
 * - 基础色直接返回 CSS 变量，避免 `rgb(from var(...))` 在 SVG 内联样式中兼容性不足
 * - 浅色阶使用 `color-mix` 与白色混合
 * - 深色阶使用 `color-mix` 与黑色混合
 * @param cssVar 主题 CSS 变量名
 * @param intensity 色阶，如 50/100/700
 * @returns 可直接用于 CSS color/fill/stroke 的颜色值
 */
function buildThemeColorValue(cssVar: string, intensity?: string): string {
  if (!intensity || COLOR_INTENSITY_MAP[intensity] === 1) {
    return `var(${cssVar})`
  }

  const intensityValue = COLOR_INTENSITY_MAP[intensity]
  if (typeof intensityValue !== 'number') {
    return `var(${cssVar})`
  }

  const intensityNumber = Number(intensity)
  if (Number.isNaN(intensityNumber)) {
    return `var(${cssVar})`
  }

  if (intensityNumber < 500) {
    const colorPercent = Math.max(0, Math.min(100, (1 - intensityValue) * 100))
    return `color-mix(in srgb, var(${cssVar}) ${colorPercent}%, white)`
  }

  const colorPercent = Math.max(0, Math.min(100, intensityValue * 100))
  return `color-mix(in srgb, var(${cssVar}) ${colorPercent}%, black)`
}

/**
 * 检查字符串是否为有效的颜色值
 * @param color 颜色字符串
 * @returns 是否为有效颜色值
 */
function isValidColor(color: string): boolean {
  // 检查十六进制颜色
  if (/^#([0-9A-F]{3}){1,2}$/i.test(color)) {
    return true
  }
  
  // 检查 RGB/RGBA
  if (/^rgba?\(/.test(color)) {
    return true
  }
  
  // 检查 HSL/HSLA
  if (/^hsla?\(/.test(color)) {
    return true
  }
  
  // 检查 CSS 变量
  if (/^var\(--/.test(color)) {
    return true
  }
  
  // 检查命名颜色
  const namedColors = [
    'transparent', 'currentColor', 'inherit', 'initial', 'unset',
    'black', 'white', 'red', 'green', 'blue', 'yellow', 'orange', 'purple', 'pink', 'gray', 'grey'
  ]
  
  return namedColors.includes(color.toLowerCase())
}

/**
 * 解析颜色类名，返回对应的 CSS 变量或颜色值
 * @param colorInput 颜色输入（可以是颜色值、颜色类名等）
 * @returns 解析后的颜色值
 */
export function resolveColor(colorInput?: string): string | undefined {
  if (!colorInput) {
    return undefined
  }

  const trimmedInput = colorInput.trim()
  if (!trimmedInput) {
    return undefined
  }
  
  // 如果已经是有效的颜色值，直接返回
  if (isValidColor(trimmedInput)) {
    return trimmedInput
  }

  // 处理带强度的颜色类（如 primary-500, accent1-300）
  const intensityMatch = trimmedInput.match(/^(.+)-(\d+)$/)
  if (intensityMatch) {
    const [, baseColor, intensity] = intensityMatch
    const cssVar = THEME_COLOR_MAP[baseColor]
    
    if (cssVar && COLOR_INTENSITY_MAP[intensity]) {
      return buildThemeColorValue(cssVar, intensity)
    }
  }
  
  // 处理基础颜色类
  const cssVar = THEME_COLOR_MAP[trimmedInput]
  if (cssVar) {
    return buildThemeColorValue(cssVar)
  }
  
  // 如果都不匹配，返回原始输入（可能是自定义 CSS 变量或其他格式）
  return trimmedInput
}

/**
 * 获取颜色的 CSS 变量名
 * @param colorClass 颜色类名
 * @returns CSS 变量名
 */
export function getColorVariable(colorClass: string): string | undefined {
  // 处理带强度的颜色类
  const intensityMatch = colorClass.match(/^(.+)-(\d+)$/)
  if (intensityMatch) {
    const [, baseColor] = intensityMatch
    return THEME_COLOR_MAP[baseColor]
  }
  
  return THEME_COLOR_MAP[colorClass]
}

/**
 * 检查是否为主题颜色类
 * @param colorInput 颜色输入
 * @returns 是否为主题颜色类
 */
export function isThemeColor(colorInput: string): boolean {
  if (!colorInput) return false
  
  // 检查带强度的颜色类
  const intensityMatch = colorInput.match(/^(.+)-(\d+)$/)
  if (intensityMatch) {
    const [, baseColor, intensity] = intensityMatch
    return THEME_COLOR_MAP[baseColor] !== undefined && COLOR_INTENSITY_MAP[intensity] !== undefined
  }
  
  // 检查基础颜色类
  return THEME_COLOR_MAP[colorInput] !== undefined
}

/**
 * 获取所有支持的主题颜色类名
 * @returns 支持的颜色类名数组
 */
export function getSupportedThemeColors(): string[] {
  const baseColors = Object.keys(THEME_COLOR_MAP)
  const intensities = Object.keys(COLOR_INTENSITY_MAP)
  
  const result: string[] = [...baseColors]
  
  // 添加带强度的颜色类
  baseColors.forEach(baseColor => {
    intensities.forEach(intensity => {
      result.push(`${baseColor}-${intensity}`)
    })
  })
  
  return result
}
