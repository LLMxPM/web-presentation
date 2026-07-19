/**
 * 文件功能：解析和序列化带锁定标签外壳的富文本，并比较锁定结构是否仅发生子树删除。
 */

import {
  createPageVisualEditRichTextElementNode,
  createPageVisualEditRichTextTextNode,
  normalizePageVisualEditRichTextInput,
  type PageVisualEditRichTextElementNode,
  type PageVisualEditRichTextNode,
} from '@/utils/page-visual-edit-rich-text-model'

interface LockedNode {
  signature: string
  children: LockedNode[]
}

interface FlatLockedNode {
  signature: string
  parentIndex: number | null
}

interface ParseContainer {
  tag: string | null
  node: PageVisualEditRichTextElementNode | null
  children: PageVisualEditRichTextNode[]
}

const VOID_TAGS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
  'param', 'source', 'track', 'wbr',
])

/** 把 Runtime 下发的规范片段解析为可递归展示的富文本树。 */
export function parsePageVisualEditRichText(html: string): PageVisualEditRichTextNode[] {
  const root: ParseContainer = { tag: null, node: null, children: [] }
  const stack: ParseContainer[] = [root]
  let offset = 0
  while (offset < html.length) {
    if (html[offset] !== '<') {
      const nextTag = html.indexOf('<', offset)
      const end = nextTag < 0 ? html.length : nextTag
      appendTextNode(currentContainer(stack).children, decodeText(html.slice(offset, end)))
      offset = end
      continue
    }
    const tagEnd = findTagEnd(html, offset)
    if (tagEnd < 0) {
      appendTextNode(currentContainer(stack).children, decodeText(html.slice(offset)))
      break
    }
    const token = html.slice(offset, tagEnd + 1)
    offset = tagEnd + 1
    if (/^<!--/.test(token) || /^<![^-]/.test(token) || /^<\?/.test(token)) continue
    const closingMatch = token.match(/^<\s*\/\s*([^\s>]+)[^>]*>$/)
    if (closingMatch) {
      closeElement(stack, closingMatch[1]!, token)
      continue
    }
    const openingMatch = token.match(/^<\s*([^\s/>]+)/)
    if (!openingMatch) {
      appendTextNode(currentContainer(stack).children, decodeText(token))
      continue
    }
    const rawTag = openingMatch[1]!
    const lowerTag = rawTag.toLowerCase()
    if (lowerTag === 'br' && isAttributeFreeTag(token, 'br')) {
      appendTextNode(currentContainer(stack).children, '\n')
      continue
    }
    const locked = !isMutableSemanticTag(token, lowerTag)
    const node = createPageVisualEditRichTextElementNode(
      rawTag,
      extractStaticClass(token),
      locked,
      locked ? token : null,
    )
    currentContainer(stack).children.push(node)
    if (!/\/\s*>$/.test(token) && !VOID_TAGS.has(lowerTag)) {
      stack.push({ tag: rawTag, node, children: node.children })
    }
  }
  while (stack.length > 1) closeElement(stack, currentContainer(stack).tag || '', '')
  return root.children.length > 0 ? root.children : [createPageVisualEditRichTextTextNode('')]
}

/** 把结构化节点序列化为协议使用的稳定 HTML。 */
export function serializePageVisualEditRichText(nodes: PageVisualEditRichTextNode[]): string {
  return nodes.map(serializeNode).join('')
}

/** 规范化 Runtime 富文本，同时原样保留锁定标签 shell。 */
export function normalizePageVisualEditRichText(html: string): string {
  return serializePageVisualEditRichText(parsePageVisualEditRichText(html))
}

/** 校验候选只能移除锁定外壳，并保持所有剩余锁定标签的原始相对结构。 */
export function isPageVisualEditRichTextLockedStructurePruning(
  baselineHtml: string,
  candidateHtml: string,
): boolean {
  return canContractLockedForest(
    flattenLockedNodes(collectLockedNodes(parsePageVisualEditRichText(baselineHtml))),
    flattenLockedNodes(collectLockedNodes(parsePageVisualEditRichText(candidateHtml))),
  )
}

/** 转义纯文本并把用户输入换行转换成 br。 */
export function escapePageVisualEditRichTextWithBreaks(value: string): string {
  return normalizePageVisualEditRichTextInput(value).split('\n').map(escapeText).join('<br>')
}

/** 查找标签结束位置，避免属性字符串中的大于号提前截断。 */
function findTagEnd(source: string, start: number): number {
  let quote: '"' | "'" | null = null
  for (let index = start + 1; index < source.length; index += 1) {
    const character = source[index]
    if (quote) {
      if (character === quote && source[index - 1] !== '\\') quote = null
    } else if (character === '"' || character === "'") {
      quote = character
    } else if (character === '>') {
      return index
    }
  }
  return -1
}

/** 关闭最近的同名节点，并保存其原始 closing tag。 */
function closeElement(stack: ParseContainer[], tag: string, closingTag: string): void {
  if (stack.length <= 1) return
  const top = currentContainer(stack)
  if (top.tag?.toLowerCase() !== tag.toLowerCase()) return
  if (top.node?.locked) top.node.closingTag = closingTag
  stack.pop()
}

/** 获取当前解析容器。 */
function currentContainer(stack: ParseContainer[]): ParseContainer {
  return stack[stack.length - 1]!
}

/** 判断标签是否为允许用户添加或取消的无属性 strong/em。 */
function isMutableSemanticTag(token: string, lowerTag: string): boolean {
  return (lowerTag === 'strong' || lowerTag === 'em') && isAttributeFreeTag(token, lowerTag)
}

/** 判断 opening tag 是否不含任何属性。 */
function isAttributeFreeTag(token: string, tag: string): boolean {
  return new RegExp(`^<\\s*${tag}\\s*\\/?\\s*>$`, 'i').test(token)
}

/** 从 opening tag 中提取仅用于兼容展示的静态 class。 */
function extractStaticClass(openingTag: string): string | null {
  const match = openingTag.match(/\sclass\s*=\s*(["'])(.*?)\1/i)
  return match?.[2]?.trim().split(/\s+/).filter(Boolean).join(' ') || null
}

/** 解码静态文本实体，并把源码格式化换行折叠为空格。 */
function decodeText(value: string): string {
  if (!value) return ''
  const textarea = document.createElement('textarea')
  textarea.innerHTML = value
  return textarea.value.replace(/\r\n?|\n/g, ' ')
}

/** 合并解析阶段相邻文本节点。 */
function appendTextNode(nodes: PageVisualEditRichTextNode[], text: string): void {
  if (!text) return
  const previous = nodes.at(-1)
  if (previous?.kind === 'text') previous.text += text
  else nodes.push(createPageVisualEditRichTextTextNode(text))
}

/** 序列化文本、可变语义标签或锁定标签外壳。 */
function serializeNode(node: PageVisualEditRichTextNode): string {
  if (node.kind === 'text') return escapePageVisualEditRichTextWithBreaks(node.text)
  const content = node.children.map(serializeNode).join('')
  if (node.locked) return `${node.openingTag || ''}${content}${node.closingTag || ''}`
  const tag = node.tag.toLowerCase()
  return `<${tag}>${content}</${tag}>`
}

/** 提取锁定节点，忽略其间可自由变化的 classless strong/em。 */
function collectLockedNodes(nodes: PageVisualEditRichTextNode[]): LockedNode[] {
  const result: LockedNode[] = []
  for (const node of nodes) {
    if (node.kind !== 'element') continue
    const children = collectLockedNodes(node.children)
    if (node.locked) {
      result.push({ signature: `${node.openingTag || ''}\u0000${node.closingTag || ''}`, children })
    } else {
      result.push(...children)
    }
  }
  return result
}

/** 把锁定森林展开为带父索引的前序序列。 */
function flattenLockedNodes(
  nodes: LockedNode[],
  parentIndex: number | null = null,
  result: FlatLockedNode[] = [],
): FlatLockedNode[] {
  for (const node of nodes) {
    const nodeIndex = result.length
    result.push({ signature: node.signature, parentIndex })
    flattenLockedNodes(node.children, nodeIndex, result)
  }
  return result
}

/** 判断候选是否为基准锁定树移除任意外壳后的有序诱导子树。 */
function canContractLockedForest(
  baseline: FlatLockedNode[],
  candidate: FlatLockedNode[],
  baselineIndex = 0,
  candidateIndex = 0,
  mapping: number[] = [],
): boolean {
  if (candidateIndex >= candidate.length) return true
  const expected = candidate[candidateIndex]!
  for (let index = baselineIndex; index < baseline.length; index += 1) {
    const current = baseline[index]!
    if (current.signature !== expected.signature) continue
    const expectedParent = expected.parentIndex === null ? null : mapping[expected.parentIndex]
    if (nearestMappedAncestor(baseline, index, mapping) !== expectedParent) continue
    mapping[candidateIndex] = index
    if (canContractLockedForest(baseline, candidate, index + 1, candidateIndex + 1, mapping)) return true
    mapping.length = candidateIndex
  }
  return false
}

/** 查找某个基准节点最近的、已被候选保留的祖先。 */
function nearestMappedAncestor(
  baseline: FlatLockedNode[],
  nodeIndex: number,
  mapping: number[],
): number | null {
  let ancestorIndex = baseline[nodeIndex]?.parentIndex ?? null
  while (ancestorIndex !== null) {
    if (mapping.includes(ancestorIndex)) return ancestorIndex
    ancestorIndex = baseline[ancestorIndex]?.parentIndex ?? null
  }
  return null
}

/** 转义文本节点，防止内容被解释为 HTML 或 Vue 插值。 */
function escapeText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/{/g, '&#123;')
    .replace(/}/g, '&#125;')
}
