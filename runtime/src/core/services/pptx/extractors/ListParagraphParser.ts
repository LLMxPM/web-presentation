/**
 * 文件用途：解析 HTML 列表结构（ul、ol、li），提取原生 PPTX 段落列表（支持 bullet 符号、有序列表编号、分级缩进与列表内富文本）。
 */

import type { PptxTextRunLike } from '@/core/services/pptx/PPTXDomConverter.types'
import { PPTXDomRichTextParser, type PptxRunOptionsResolver } from '@/core/services/pptx/PPTXDomRichTextParser'

/**
 * 原生列表解析结果。
 */
export interface PptxListParseResult {
  runs: PptxTextRunLike[]
  fullText: string
  itemCount: number
}

/**
 * 列表段落解析器。
 */
export class ListParagraphParser {
  private readonly richTextParser = new PPTXDomRichTextParser()

  /**
   * 判断元素是否为独立的列表根节点（ul 或 ol，且非嵌套在父级列表内部）。
   * @param element 待检查元素
   */
  isListRootElement(element: HTMLElement): boolean {
    const tag = element.tagName.toLowerCase()
    if (tag !== 'ul' && tag !== 'ol') {
      return false
    }

    const listStyle = window.getComputedStyle(element)
    const display = (listStyle.display || '').toLowerCase()
    if (
      display.includes('flex') ||
      display.includes('grid') ||
      element.classList.contains('flex') ||
      element.classList.contains('grid')
    ) {
      return false
    }

    // 若直接祖先已经是列表项或列表，则属于嵌套列表的一部分，由顶层列表统一处理
    const parentList = element.parentElement?.closest('ul, ol')
    return !parentList
  }

  /**
   * 检查列表树是否完全由可表达为 PPTX 原生段落的元素构成。
   * 若包含表格、嵌入媒体或复杂块级布局，则返回 false，触发安全降级。
   * @param element 列表根元素
   */
  isNativeListCompatible(element: HTMLElement): boolean {
    const tag = element.tagName.toLowerCase()
    if (tag !== 'ul' && tag !== 'ol') {
      return false
    }

    const items = element.querySelectorAll('li')
    if (items.length === 0) {
      return false
    }

    for (const li of Array.from(items)) {
      if (!this.isListItemContentCompatible(li)) {
        return false
      }
    }

    return true
  }

  /**
   * 将整个列表解析为带有段落级 bullet、indentLevel 和 breakLine 的 PptxTextRunLike 列表。
   * @param rootElement 列表根元素（ul 或 ol）
   * @param resolveOptions 字符样式解析函数
   */
  parseList(
    rootElement: HTMLElement,
    resolveOptions: PptxRunOptionsResolver,
  ): PptxListParseResult | null {
    if (!this.isNativeListCompatible(rootElement)) {
      return null
    }

    const runs: PptxTextRunLike[] = []
    let fullText = ''
    let itemCount = 0

    const traverseList = (
      listEl: HTMLElement,
      depth: number,
      inheritedStart = 1,
    ) => {
      const isOrdered = listEl.tagName.toLowerCase() === 'ol'
      const startAttr = Number.parseInt(listEl.getAttribute('start') || '', 10)
      let currentNumber = Number.isFinite(startAttr) ? startAttr : inheritedStart

      const children = Array.from(listEl.children)
      for (const child of children) {
        if (!(child instanceof HTMLElement)) {
          continue
        }

        if (child.tagName.toLowerCase() === 'li') {
          itemCount += 1
          const valueAttr = Number.parseInt(child.getAttribute('value') || '', 10)
          const numberStart = Number.isFinite(valueAttr) ? valueAttr : currentNumber

          // 解析 li 的独立样式与段落设置
          const liStyle = window.getComputedStyle(child)
          const listStyleType = (liStyle.listStyleType || '').toLowerCase()
          const isNoneBullet = listStyleType === 'none'

          let bulletOption: unknown = true
          if (isNoneBullet) {
            bulletOption = false
          } else if (isOrdered) {
            bulletOption = {
              type: 'number',
              numberStart,
            }
          } else {
            bulletOption = true
          }

          // 提取该 li 内部直属富文本 runs（排除嵌套的 ul/ol，嵌套列表随后递归处理）
          const itemRuns = this.extractListItemRuns(child, resolveOptions)
          if (itemRuns.length > 0) {
            // 第一个 run 承载该段落的列表属性
            const firstRun = itemRuns[0]
            const isFirstItemOverall = runs.length === 0

            const paragraphOptions: Record<string, unknown> = {
              ...firstRun.options,
              indentLevel: depth,
              bullet: bulletOption,
            }

            // 除了整棵列表的第一个 run 外，每个列表段落首个 run 标记 breakLine: true
            if (!isFirstItemOverall) {
              paragraphOptions.breakLine = true
            }

            firstRun.options = paragraphOptions
            runs.push(...itemRuns)
            fullText += `${isFirstItemOverall ? '' : '\n'}${itemRuns.map(r => r.text).join('')}`
          }

          currentNumber = numberStart + 1

          // 检查该 li 内部是否包含嵌套的 ul 或 ol
          for (const grandChild of Array.from(child.children)) {
            if (grandChild instanceof HTMLElement && (grandChild.tagName.toLowerCase() === 'ul' || grandChild.tagName.toLowerCase() === 'ol')) {
              traverseList(grandChild, depth + 1, 1)
            }
          }
        } else if (child.tagName.toLowerCase() === 'ul' || child.tagName.toLowerCase() === 'ol') {
          traverseList(child, depth + 1, 1)
        }
      }
    }

    traverseList(rootElement, 0, 1)

    if (runs.length === 0) {
      return null
    }

    return {
      runs,
      fullText,
      itemCount,
    }
  }

  /**
   * 检查单个 li 的内容是否与原生富文本段落兼容（允许纯文本、inline 标签、嵌套列表）。
   */
  private isListItemContentCompatible(li: HTMLElement): boolean {
    const liStyle = window.getComputedStyle(li)
    const display = (liStyle.display || '').toLowerCase()
    if (
      display.includes('flex') ||
      display.includes('grid') ||
      li.classList.contains('flex') ||
      li.classList.contains('grid')
    ) {
      return false
    }

    for (const child of Array.from(li.childNodes)) {
      if (child instanceof Text) {
        continue
      }
      if (child instanceof HTMLElement) {
        const tag = child.tagName.toLowerCase()
        if (tag === 'ul' || tag === 'ol') {
          continue
        }
        // 允许常见的段落/行内容器如 p 或 span，但若包含 table、canvas、svg 或媒体，则不兼容
        if (tag === 'table' || tag === 'canvas' || tag === 'svg' || tag === 'video' || tag === 'iframe') {
          return false
        }
        // 若子元素具有 inline-block/block 盒模型或显式宽高，说明是自定义 marker，触发降级展开
        const childStyle = window.getComputedStyle(child)
        const childDisplay = (childStyle.display || '').toLowerCase()
        if (
          ['inline-block', 'block', 'flex', 'grid'].includes(childDisplay) ||
          child.classList.contains('inline-block') ||
          child.classList.contains('block') ||
          child.classList.contains('flex') ||
          child.classList.contains('grid')
        ) {
          return false
        }
      }
    }
    return true
  }

  /**
   * 提取 li 节点内的文本 runs，跳过子级嵌套的 ul 和 ol（避免重复提取）。
   */
  private extractListItemRuns(
    li: HTMLElement,
    resolveOptions: PptxRunOptionsResolver,
  ): PptxTextRunLike[] {
    // 构造临时克隆节点，移除嵌套列表后再提取 rich text
    const clone = li.cloneNode(true) as HTMLElement
    for (const nestedList of Array.from(clone.querySelectorAll('ul, ol'))) {
      nestedList.remove()
    }

    const richResult = this.richTextParser.parse(clone, resolveOptions)
    if (richResult && richResult.runs.length > 0) {
      return richResult.runs
    }

    const rawText = (clone.textContent || '').trim()
    if (!rawText) {
      return []
    }

    const style = window.getComputedStyle(li)
    return [
      {
        text: rawText,
        options: resolveOptions(li, style, rawText),
      },
    ]
  }
}
