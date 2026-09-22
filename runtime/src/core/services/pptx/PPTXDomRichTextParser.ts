/**
 * 文件用途：将安全的 HTML inline 文本子树解析为 PptxGenJS rich text runs，并统一处理跨节点空白。
 */

import type { PptxTextRunLike } from './PPTXDomConverter.types'

interface RawTextSegment {
  kind: 'text'
  text: string
  options: Record<string, unknown>
}

interface RawBreakSegment {
  kind: 'break'
}

type RawSegment = RawTextSegment | RawBreakSegment

export interface PptxDomRichTextResult {
  runs: PptxTextRunLike[]
  text: string
}

export type PptxRunOptionsResolver = (
  element: HTMLElement,
  style: CSSStyleDeclaration,
  text: string,
) => Record<string, unknown>

const SAFE_INLINE_TAGS = new Set([
  'a',
  'b',
  'code',
  'del',
  'em',
  'i',
  'small',
  's',
  'span',
  'strong',
  'sub',
  'sup',
  'u',
])

const MAX_RICH_TEXT_RUNS = 512

/**
 * 解析只包含字符级样式的 inline DOM；遇到盒模型或布局语义时返回 null，由调用方继续拆分元素。
 */
export class PPTXDomRichTextParser {
  /**
   * 将元素子树解析为 rich text runs。
   * @param element 文本框根元素
   * @param resolveOptions 字符级 PPT 样式解析器
   */
  parse(element: HTMLElement, resolveOptions: PptxRunOptionsResolver): PptxDomRichTextResult | null {
    const segments: RawSegment[] = []
    if (!this.collectSegments(element, element, segments, resolveOptions)) {
      return null
    }

    const whiteSpace = window.getComputedStyle(element).whiteSpace || 'normal'
    const runs = this.normalizeSegments(segments, whiteSpace)
    if (runs.length === 0 || runs.length > MAX_RICH_TEXT_RUNS) {
      return null
    }

    return {
      runs,
      text: runs.map(run => `${run.options?.softBreakBefore ? '\n' : ''}${run.text}`).join(''),
    }
  }

  /**
   * 递归收集文本和换行标记，并拒绝无法由 PPT run 表达的 inline 盒模型。
   */
  private collectSegments(
    root: HTMLElement,
    current: Node,
    segments: RawSegment[],
    resolveOptions: PptxRunOptionsResolver,
  ): boolean {
    for (const node of Array.from(current.childNodes)) {
      if (node instanceof Text) {
        if (!node.textContent) {
          continue
        }
        const owner = current instanceof HTMLElement ? current : root
        const style = window.getComputedStyle(owner)
        segments.push({
          kind: 'text',
          text: node.textContent,
          options: resolveOptions(owner, style, node.textContent),
        })
        continue
      }

      if (!(node instanceof HTMLElement)) {
        return false
      }
      if (node.tagName.toLowerCase() === 'br') {
        segments.push({ kind: 'break' })
        continue
      }
      if (!this.isSafeInlineElement(node)) {
        return false
      }
      if (!this.collectSegments(root, node, segments, resolveOptions)) {
        return false
      }
    }
    return true
  }

  /**
   * 判断元素是否只有字符级语义；inline-block、视觉盒和定位元素必须保留为独立对象。
   */
  private isSafeInlineElement(element: HTMLElement): boolean {
    if (!SAFE_INLINE_TAGS.has(element.tagName.toLowerCase())) {
      return false
    }

    const style = window.getComputedStyle(element)
    const display = style.display || 'inline'
    if (!['inline', 'contents'].includes(display)) {
      return false
    }
    if (['absolute', 'fixed'].includes(style.position)) {
      return false
    }
    if (style.transform && style.transform !== 'none') {
      return false
    }
    if (style.backgroundImage && style.backgroundImage !== 'none') {
      return false
    }
    if (this.hasVisibleBackground(style) || this.hasBoxSpacing(style) || this.hasVisibleBorder(style)) {
      return false
    }
    return true
  }

  /** 判断 inline 元素是否带有可见背景。 */
  private hasVisibleBackground(style: CSSStyleDeclaration): boolean {
    const color = String(style.backgroundColor || '').replace(/\s+/g, '').toLowerCase()
    return Boolean(color && !['transparent', 'rgba(0,0,0,0)', 'rgb(0,0,0,0)'].includes(color))
  }

  /** 判断 inline 元素是否依赖 padding 或 margin 形成布局。 */
  private hasBoxSpacing(style: CSSStyleDeclaration): boolean {
    return [
      style.paddingTop,
      style.paddingRight,
      style.paddingBottom,
      style.paddingLeft,
      style.marginTop,
      style.marginRight,
      style.marginBottom,
      style.marginLeft,
    ].some(value => this.parsePixel(value) !== 0)
  }

  /** 判断 inline 元素是否带有可见边框。 */
  private hasVisibleBorder(style: CSSStyleDeclaration): boolean {
    return [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth]
      .some(value => this.parsePixel(value) > 0)
  }

  /** 将 CSS 长度解析为数值，仅用于判断是否存在盒模型。 */
  private parsePixel(value: string): number {
    const parsed = Number.parseFloat(value)
    return Number.isFinite(parsed) ? parsed : 0
  }

  /**
   * 按根元素 white-space 规则规范空白，并在 run 边界之间保持连续语义。
   */
  private normalizeSegments(segments: RawSegment[], whiteSpace: string): PptxTextRunLike[] {
    const preserveSpaces = ['pre', 'pre-wrap', 'break-spaces'].includes(whiteSpace)
    const preserveBreaks = preserveSpaces || whiteSpace === 'pre-line'
    const runs: PptxTextRunLike[] = []
    let pendingSpace: Record<string, unknown> | null = null
    let pendingBreak = false
    let hasContent = false

    const appendText = (text: string, options: Record<string, unknown>) => {
      if (!text) return
      const nextOptions = pendingBreak ? { ...options, softBreakBefore: true } : options
      pendingBreak = false
      const previous = runs[runs.length - 1]
      if (previous && !nextOptions.softBreakBefore && this.sameOptions(previous.options, nextOptions)) {
        previous.text += text
      } else {
        runs.push({ text, options: nextOptions })
      }
      hasContent = true
    }

    const appendBreak = () => {
      pendingSpace = null
      if (hasContent) pendingBreak = true
    }

    segments.forEach(segment => {
      if (segment.kind === 'break') {
        appendBreak()
        return
      }

      let buffer = ''
      const flush = () => {
        appendText(buffer, segment.options)
        buffer = ''
      }
      const normalized = segment.text.replace(/\r\n?/g, '\n')
      for (const character of normalized) {
        if (character === '\n' && preserveBreaks) {
          flush()
          appendBreak()
          continue
        }
        if (!preserveSpaces && this.isCollapsibleWhitespace(character)) {
          flush()
          pendingSpace ||= segment.options
          continue
        }
        if (pendingSpace && hasContent && !pendingBreak) {
          appendText(' ', pendingSpace)
        }
        pendingSpace = null
        buffer += character
      }
      flush()
    })

    return runs
  }

  /** CSS normal 模式只折叠可折叠空白，NBSP 必须保留。 */
  private isCollapsibleWhitespace(character: string): boolean {
    return character === ' ' || character === '\t' || character === '\n' || character === '\f'
  }

  /** 比较相邻 run 的字符级选项，减少 OOXML run 数量。 */
  private sameOptions(left: Record<string, unknown> | undefined, right: Record<string, unknown>): boolean {
    return JSON.stringify(left || {}) === JSON.stringify(right)
  }
}
