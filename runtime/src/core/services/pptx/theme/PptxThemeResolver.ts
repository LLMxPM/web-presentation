/**
 * 文件用途：解析 Runtime 页面主题变量（标题字体、正文字体与强调色），映射到 PPTX 演示文稿主题槽位。
 */

import { CssColorParser } from '@/core/services/pptx/style/CssColorParser'

/**
 * 演示文稿主题配置。
 */
export interface PptxPresentationTheme {
  /** 标题主要字体 */
  headFontFace: string
  /** 正文主要字体 */
  bodyFontFace: string
  /** 演示文稿主题调色板（HEX 格式，不含 # 号） */
  colors: {
    accent1?: string
    accent2?: string
    accent3?: string
    accent4?: string
    accent5?: string
    accent6?: string
    primary?: string
    secondary?: string
    background?: string
  }
}

const DEFAULT_FONT_FACE = 'Microsoft YaHei'

/**
 * PPTX 主题解析器。
 */
export class PptxThemeResolver {
  private readonly colorParser = new CssColorParser()

  /**
   * 从 DOM 上下文中提取主题字体与色彩槽位。
   * @param rootElement 页面根元素或目标文档根节点（若不传则取 document.documentElement）
   */
  resolveTheme(rootElement?: HTMLElement | null): PptxPresentationTheme {
    const target = rootElement ?? (typeof document !== 'undefined' ? document.documentElement : null)
    if (!target) {
      return {
        headFontFace: DEFAULT_FONT_FACE,
        bodyFontFace: DEFAULT_FONT_FACE,
        colors: {},
      }
    }

    const style = window.getComputedStyle(target)

    const rawHeadingFont = style.getPropertyValue('--tw-font-heading').trim()
    const rawBodyFont = style.getPropertyValue('--tw-font-body').trim()

    const headFontFace = this.cleanFontFace(rawHeadingFont) || DEFAULT_FONT_FACE
    const bodyFontFace = this.cleanFontFace(rawBodyFont) || DEFAULT_FONT_FACE

    const colors: PptxPresentationTheme['colors'] = {}

    const resolveHex = (varName: string) => {
      const val = style.getPropertyValue(varName).trim()
      if (!val) return undefined
      const parsed = this.colorParser.parseCssColor(val)
      return parsed ? parsed.hex : undefined
    }

    colors.accent1 = resolveHex('--tw-color-accent1')
    colors.accent2 = resolveHex('--tw-color-accent2')
    colors.accent3 = resolveHex('--tw-color-accent3')
    colors.accent4 = resolveHex('--tw-color-accent4')
    colors.accent5 = resolveHex('--tw-color-accent5')
    colors.accent6 = resolveHex('--tw-color-accent6')
    colors.primary = resolveHex('--tw-color-text-primary')
    colors.secondary = resolveHex('--tw-color-text-secondary')
    colors.background = resolveHex('--tw-color-bg-default')

    return {
      headFontFace,
      bodyFontFace,
      colors,
    }
  }

  /**
   * 规范化 CSS 字体串（如 `"PingFang SC", sans-serif` -> `PingFang SC`）。
   */
  private cleanFontFace(fontFamily: string): string {
    if (!fontFamily) {
      return ''
    }
    const firstFont = fontFamily.split(',')[0].trim()
    return firstFont.replace(/^['"]|['"]$/g, '').trim()
  }
}
