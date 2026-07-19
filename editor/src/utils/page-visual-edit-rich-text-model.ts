/**
 * 文件功能：定义结构化富文本节点，并提供仅供编辑器内部使用的节点工厂。
 */

export type PageVisualEditRichTextSemanticTag = 'strong' | 'em'

export interface PageVisualEditRichTextTextNode {
  id: string
  kind: 'text'
  text: string
}

export interface PageVisualEditRichTextElementNode {
  id: string
  kind: 'element'
  tag: string
  className: string | null
  locked: boolean
  openingTag: string | null
  closingTag: string | null
  children: PageVisualEditRichTextNode[]
}

export type PageVisualEditRichTextNode =
  | PageVisualEditRichTextTextNode
  | PageVisualEditRichTextElementNode

let nextNodeId = 0

/** 创建带本地稳定 ID 的文本节点。 */
export function createPageVisualEditRichTextTextNode(text: string): PageVisualEditRichTextTextNode {
  return { id: `rich-text-${++nextNodeId}`, kind: 'text', text: normalizePageVisualEditRichTextInput(text) }
}

/** 创建带本地稳定 ID 的行内元素节点。 */
export function createPageVisualEditRichTextElementNode(
  tag: string,
  className: string | null,
  locked: boolean,
  openingTag: string | null,
  children: PageVisualEditRichTextNode[] = [],
): PageVisualEditRichTextElementNode {
  return {
    id: `rich-text-${++nextNodeId}`,
    kind: 'element',
    tag,
    className,
    locked,
    openingTag,
    closingTag: null,
    children,
  }
}

/** 统一文本框换行格式。 */
export function normalizePageVisualEditRichTextInput(value: string): string {
  return value.replace(/\r\n?|\n/g, '\n')
}
