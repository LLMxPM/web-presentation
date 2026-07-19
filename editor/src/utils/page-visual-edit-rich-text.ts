/**
 * 文件功能：提供结构化富文本的文本修改、节点删除、标签取消和选区包装操作。
 */

import {
  createPageVisualEditRichTextElementNode,
  createPageVisualEditRichTextTextNode,
  normalizePageVisualEditRichTextInput,
  type PageVisualEditRichTextNode,
  type PageVisualEditRichTextSemanticTag,
} from '@/utils/page-visual-edit-rich-text-model'
import { escapePageVisualEditRichTextWithBreaks } from '@/utils/page-visual-edit-rich-text-parser'

export type {
  PageVisualEditRichTextElementNode,
  PageVisualEditRichTextNode,
  PageVisualEditRichTextSemanticTag,
  PageVisualEditRichTextTextNode,
} from '@/utils/page-visual-edit-rich-text-model'
export {
  isPageVisualEditRichTextLockedStructurePruning,
  normalizePageVisualEditRichText,
  parsePageVisualEditRichText,
  serializePageVisualEditRichText,
} from '@/utils/page-visual-edit-rich-text-parser'

/** 把纯文本转换为安全 HTML，并将换行映射为 br。 */
export function plainTextToPageVisualEditRichText(text: string): string {
  return escapePageVisualEditRichTextWithBreaks(text)
}

/** 修改指定文本节点；节点不存在时返回 false。 */
export function updatePageVisualEditRichText(
  nodes: PageVisualEditRichTextNode[],
  nodeId: string,
  text: string,
): boolean {
  const node = findRichTextNode(nodes, nodeId)
  if (!node || node.kind !== 'text') return false
  node.text = normalizePageVisualEditRichTextInput(text)
  return true
}

/** 移除锁定标签外壳，保留内部内容并合并相邻文本。 */
export function removePageVisualEditRichTextLock(
  nodes: PageVisualEditRichTextNode[],
  nodeId: string,
): boolean {
  const changed = replaceRichTextNode(nodes, nodeId, (node) => {
    if (node.kind !== 'element' || !node.locked) return null
    return node.children
  })
  if (changed) normalizeEditableNodes(nodes)
  return changed
}

/** 取消未锁定的 strong/em 标签，保留内容并合并前后相邻文本。 */
export function unwrapPageVisualEditRichTextNode(
  nodes: PageVisualEditRichTextNode[],
  nodeId: string,
): boolean {
  const changed = replaceRichTextNode(nodes, nodeId, (node) => {
    if (node.kind !== 'element' || node.locked || !isSemanticTag(node.tag)) return null
    return node.children.length > 0 ? node.children : [createPageVisualEditRichTextTextNode('')]
  })
  if (changed) normalizeEditableNodes(nodes)
  return changed
}

/** 把单个文本节点内的非空选区包装成 classless strong/em。 */
export function wrapPageVisualEditRichTextSelection(
  nodes: PageVisualEditRichTextNode[],
  nodeId: string,
  start: number,
  end: number,
  tag: PageVisualEditRichTextSemanticTag,
): boolean {
  return replaceRichTextNode(nodes, nodeId, (node) => {
    if (node.kind !== 'text') return null
    const safeStart = Math.max(0, Math.min(start, node.text.length))
    const safeEnd = Math.max(safeStart, Math.min(end, node.text.length))
    if (safeStart === safeEnd) return null
    const replacements: PageVisualEditRichTextNode[] = []
    if (safeStart > 0) replacements.push(createPageVisualEditRichTextTextNode(node.text.slice(0, safeStart)))
    replacements.push(createPageVisualEditRichTextElementNode(tag, null, false, null, [
      createPageVisualEditRichTextTextNode(node.text.slice(safeStart, safeEnd)),
    ]))
    if (safeEnd < node.text.length) replacements.push(createPageVisualEditRichTextTextNode(node.text.slice(safeEnd)))
    return replacements
  })
}

/** 判断标签是否为本期开放的语义标签。 */
function isSemanticTag(tag: string): tag is PageVisualEditRichTextSemanticTag {
  const lowerTag = tag.toLowerCase()
  return lowerTag === 'strong' || lowerTag === 'em'
}

/** 递归查找节点。 */
function findRichTextNode(nodes: PageVisualEditRichTextNode[], nodeId: string): PageVisualEditRichTextNode | null {
  for (const node of nodes) {
    if (node.id === nodeId) return node
    if (node.kind === 'element') {
      const child = findRichTextNode(node.children, nodeId)
      if (child) return child
    }
  }
  return null
}

/** 递归替换节点；回调返回 null 表示不允许当前操作。 */
function replaceRichTextNode(
  nodes: PageVisualEditRichTextNode[],
  nodeId: string,
  replacement: (node: PageVisualEditRichTextNode) => PageVisualEditRichTextNode[] | null,
): boolean {
  const index = nodes.findIndex(node => node.id === nodeId)
  if (index >= 0) {
    const nextNodes = replacement(nodes[index]!)
    if (!nextNodes) return false
    nodes.splice(index, 1, ...nextNodes)
    return true
  }
  return nodes.some(node => node.kind === 'element'
    && replaceRichTextNode(node.children, nodeId, replacement))
}

/** 递归补充空文本入口，并把取消标签或删除后相邻的文本节点合并。 */
function normalizeEditableNodes(nodes: PageVisualEditRichTextNode[]): void {
  for (const node of nodes) {
    if (node.kind === 'element') normalizeEditableNodes(node.children)
  }
  for (let index = nodes.length - 1; index > 0; index -= 1) {
    const current = nodes[index]
    const previous = nodes[index - 1]
    if (current?.kind === 'text' && previous?.kind === 'text') {
      previous.text += current.text
      nodes.splice(index, 1)
    }
  }
  if (nodes.length === 0) nodes.push(createPageVisualEditRichTextTextNode(''))
}
