/**
 * 文件用途：负责 PPTX 导出中的字体族映射、字重判定、文本对齐（含 Flex/Grid/Tailwind class 回退）与内边距/圆角解析。
 */

import type { ElementPadding, MeasuredElementBox, VisitContext } from '@/core/services/pptx/PPTXDomConverter.types'
import { INLINE_TEXT_TAGS } from '@/core/services/pptx/PPTXDomConverter.types'
import { parseCssPixelValue } from './css-tokenizer'

const PPTX_PLATFORM_FONT_FACE_MAP: Record<string, string> = {
  'web presentation sans': 'Microsoft YaHei',
  'web presentation mono': 'Consolas',
}

/**
 * 字体映射、排版对齐与 Tailwind 工具类解析器。
 */
export class TypographyAndAlignmentResolver {
  /**
   * 规范化文本内容，合并多余空白。
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
   */
  containsCjkText(text: string): boolean {
    return /[\u3400-\u9fff\uf900-\ufaff]/.test(text)
  }

  /**
   * 判断字体是否加粗。
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
   */
  resolveTextVerticalAlign(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    context: VisitContext,
    measureElementPixels: (el: Element) => MeasuredElementBox,
    cssPxToMeasuredPx: (px: number) => number,
  ): string {
    if (this.isSingleLineText(text) && this.isLineHeightCentered(element, style, measureElementPixels, cssPxToMeasuredPx)) {
      return 'middle'
    }

    const ownAlign = this.resolveOwnTextVerticalAlign(element, style, measureElementPixels)
    if (ownAlign !== 'top' || this.hasExplicitVerticalAlign(element)) {
      return ownAlign
    }

    return context.inheritedVerticalAlign || ownAlign
  }

  /**
   * 解析元素自身声明或布局提供的水平对齐。
   */
  resolveOwnTextHorizontalAlign(element: HTMLElement, style: CSSStyleDeclaration): string {
    const textAlign = this.resolveOwnInheritableTextHorizontalAlign(element, style)
    return this.resolveLayoutHorizontalAlign(element, style) || textAlign
  }

  /**
   * 解析真正会按 HTML 规则向后代继承的文本水平对齐。
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
   */
  resolveOwnTextVerticalAlign(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    measureElementPixels: (el: Element) => MeasuredElementBox,
  ): string {
    return this.resolveCssVerticalAlign(element, style, measureElementPixels) ||
      this.resolveClassVerticalAlign(element) ||
      this.resolveLayoutVerticalAlign(element, style) ||
      'top'
  }

  /**
   * 从 flex/grid 布局中推断水平对齐。
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
   */
  resolveClassJustifyItems(element: HTMLElement): string {
    if (element.classList.contains('justify-items-center')) return 'center'
    if (element.classList.contains('justify-items-end')) return 'end'
    if (element.classList.contains('justify-items-start')) return 'start'
    return ''
  }

  /**
   * 从 Tailwind place-items-* 类名中解析网格双轴对齐。
   */
  resolveClassPlaceAlignment(element: HTMLElement, axis: 'horizontal' | 'vertical'): string {
    void axis
    if (element.classList.contains('place-items-center') || element.classList.contains('place-content-center')) {
      return 'center'
    }
    if (element.classList.contains('place-items-end') || element.classList.contains('place-content-end')) {
      return 'end'
    }
    if (element.classList.contains('place-items-start') || element.classList.contains('place-content-start')) {
      return 'start'
    }
    return ''
  }

  /**
   * 从 Tailwind vertical-align 类名中解析垂直对齐。
   */
  resolveClassVerticalAlign(element: HTMLElement): string {
    if (element.classList.contains('align-middle')) return 'middle'
    if (element.classList.contains('align-bottom') || element.classList.contains('align-text-bottom')) return 'bottom'
    if (element.classList.contains('align-top') || element.classList.contains('align-text-top')) return 'top'
    return ''
  }

  /**
   * 从 vertical-align/table-cell 中推断文本垂直对齐。
   */
  resolveCssVerticalAlign(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    measureElementPixels: (el: Element) => MeasuredElementBox,
  ): string {
    const normalized = this.normalizeCssVerticalAlign(style.verticalAlign)
    if (!normalized) {
      return ''
    }

    const tagName = element.tagName.toLowerCase()
    if (style.display.includes('table-cell') || ['td', 'th'].includes(tagName)) {
      return normalized
    }

    const box = measureElementPixels(element)
    if (box.height > 0 && this.isTextOnlyLayoutElement(element)) {
      return normalized
    }

    return ''
  }

  /**
   * 读取元素圆角半径，优先使用已解析的左上角或统一 border-radius。
   */
  resolveElementCornerRadiusPx(_element: HTMLElement, style: CSSStyleDeclaration): number {
    const topLeftRadius = parseCssPixelValue(style.borderTopLeftRadius)
    if (topLeftRadius > 0) {
      return topLeftRadius
    }

    const borderRadius = parseCssPixelValue(style.borderRadius)
    if (borderRadius > 0) {
      return borderRadius
    }

    return 0
  }

  /**
   * 判断文本形状是否属于 pill/badge 一类的胶囊文本盒。
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
   * 解析元素四边 padding，computed 缺失时回退常见 Tailwind spacing 类。
   */
  resolveElementPaddingPixels(element: HTMLElement, style: CSSStyleDeclaration): ElementPadding {
    const classPadding = this.resolveTailwindPaddingPixels(element)
    return {
      top: parseCssPixelValue(style.paddingTop) || classPadding.top,
      right: parseCssPixelValue(style.paddingRight) || classPadding.right,
      bottom: parseCssPixelValue(style.paddingBottom) || classPadding.bottom,
      left: parseCssPixelValue(style.paddingLeft) || classPadding.left,
    }
  }

  /**
   * 从 Tailwind padding 类中解析 px 值，覆盖测试环境没有 CSS 的场景。
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
   */
  applyPaddingUtility(padding: ElementPadding, utility: string, value: number): void {
    if (utility === 'p' || utility === 'py' || utility === 'pt') padding.top = value
    if (utility === 'p' || utility === 'px' || utility === 'pr') padding.right = value
    if (utility === 'p' || utility === 'py' || utility === 'pb') padding.bottom = value
    if (utility === 'p' || utility === 'px' || utility === 'pl') padding.left = value
  }

  /**
   * 判断元素是否有圆角类名。
   */
  hasRoundedClass(element: HTMLElement): boolean {
    return Array.from(element.classList).some(className => {
      return className.startsWith('rounded') && className !== 'rounded-none'
    })
  }

  /**
   * 判断元素是否显式声明了可继承的文本水平对齐。
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
   */
  hasAnyClass(element: HTMLElement, classNames: string[]): boolean {
    return classNames.some(className => element.classList.contains(className))
  }

  /**
   * 规范化 CSS 水平对齐。
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
   */
  isTextOnlyLayoutElement(element: HTMLElement): boolean {
    return element.children.length === 0 ||
      Array.from(element.children).every(child => INLINE_TEXT_TAGS.has(child.tagName.toLowerCase()))
  }

  /**
   * 判断是否为单行文本。
   */
  isSingleLineText(text: string): boolean {
    return !/[\r\n]/.test(text)
  }

  /**
   * 判断 line-height 是否表达了垂直居中。
   */
  isLineHeightCentered(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    measureElementPixels: (el: Element) => MeasuredElementBox,
    cssPxToMeasuredPx: (px: number) => number,
  ): boolean {
    const lineHeight = parseCssPixelValue(style.lineHeight)
    if (lineHeight <= 0) {
      return false
    }

    const cssHeight = parseCssPixelValue(style.height)
    const measuredHeight = measureElementPixels(element).height
    const measuredCssScale = cssPxToMeasuredPx(1)
    const measuredCssHeight = measuredCssScale > 0 ? measuredHeight / measuredCssScale : 0
    const targetHeight = cssHeight || measuredCssHeight
    return targetHeight > 0 && Math.abs(lineHeight - targetHeight) <= 1
  }
}
