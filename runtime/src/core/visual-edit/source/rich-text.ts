/**
 * 文件用途：识别、规范化并定位可编辑文本与锁定标签外壳共存的段落富文本。
 */

import { parse } from '@vue/compiler-sfc'

import type { VisualEditSourceRange } from '../protocol'
import {
  TEMPLATE_NODE_ELEMENT,
  TEMPLATE_NODE_DIRECTIVE,
  TEMPLATE_NODE_INTERPOLATION,
  TEMPLATE_NODE_TEXT,
  type CompilerElementNode,
  type CompilerTemplateChild,
} from './compiler-node-types'

export const VISUAL_EDIT_RICH_TEXT_MAX_LENGTH = 20_000
export const VISUAL_EDIT_RICH_TEXT_CONTAINER_TAGS = new Set([
  'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'label',
])

/** HTML void 标签天然没有 closing tag，不能据此判定 shell 解析失败。 */
const HTML_VOID_TAGS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'param', 'source', 'track', 'wbr',
])

export type VisualEditRichTextContentKind = 'static' | 'locked' | 'dynamic' | 'unsupported'

/** 富文本容器判定结果：不聚合、聚合为单 binding，或 shell 无法解析需降级。 */
export type VisualEditRichTextContainerResolution =
  | { mode: 'none' }
  | { mode: 'unresolved' }
  | { mode: 'aggregate'; contentKind: VisualEditRichTextContentKind }

export interface VisualEditRichTextLockedNode {
  signature: string
  children: VisualEditRichTextLockedNode[]
}

/** 可判别外壳类型：成对标签才有可编辑内部范围，自闭合元素没有内部内容。 */
type VisualEditElementShell =
  | { kind: 'paired'; openingTag: string; closingTag: string }
  | { kind: 'self-closing'; openingTag: string }

/** 判断标签是否属于富文本容器候选集合，不考虑外壳与内容形态。 */
export function isRichTextContainerTag(element: CompilerElementNode): boolean {
  return element.tagType === 0 && VISUAL_EDIT_RICH_TEXT_CONTAINER_TAGS.has(element.tag.toLowerCase())
}

/**
 * 结合标签、外壳与子节点判定元素是否进入富文本聚合：
 * 自闭合装饰节点按普通元素分析，shell 无法解析时降级并由调用方输出诊断。
 */
export function resolveRichTextContainerKind(
  element: CompilerElementNode
): VisualEditRichTextContainerResolution {
  if (!isRichTextContainerTag(element)) return { mode: 'none' }
  const shell = resolveElementShell(element)
  if (!shell) return { mode: 'unresolved' }
  if (shell.kind === 'self-closing') return { mode: 'none' }
  const contentKind = classifyRichTextContent(element.children)
  return contentKind ? { mode: 'aggregate', contentKind } : { mode: 'none' }
}

/**
 * 判断容器内容是否能聚合；动态文本仍只读，其他静态复杂标签转为锁定外壳。
 */
export function classifyRichTextContent(children: CompilerTemplateChild[]): VisualEditRichTextContentKind | null {
  const meaningful = children.filter(child => child.type !== TEMPLATE_NODE_TEXT
    || Boolean((child as { content?: string }).content?.trim()))
  if (meaningful.length === 1 && meaningful[0]?.type === TEMPLATE_NODE_INTERPOLATION) return null

  let hasDynamic = false
  let hasLockedStructure = false
  const visit = (child: CompilerTemplateChild): boolean => {
    if (child.type === TEMPLATE_NODE_TEXT) return true
    if (child.type === TEMPLATE_NODE_INTERPOLATION) {
      hasDynamic = true
      return true
    }
    if (child.type !== TEMPLATE_NODE_ELEMENT) return false
    const element = child as CompilerElementNode
    if (hasStructuralDirective(element)) return false
    if (!resolveElementShell(element)) return false
    if (isLockedRichTextElement(element)) hasLockedStructure = true
    return element.children.every(visit)
  }
  if (!children.every(visit)) return 'unsupported'
  if (hasDynamic) return hasLockedStructure ? 'unsupported' : 'dynamic'
  return hasLockedStructure ? 'locked' : 'static'
}

/** v-if/v-for 等控制流节点必须保留独立 Manifest 节点和画布 marker。 */
function hasStructuralDirective(element: CompilerElementNode): boolean {
  return element.props.some(prop => prop.type === TEMPLATE_NODE_DIRECTIVE
    && ['if', 'else', 'else-if', 'for'].includes(prop.name))
}

/** 计算元素 opening/closing tag 之间的源码范围；仅成对外壳返回范围，否则返回 null 由分析层降级。 */
export function resolveElementInnerRange(
  element: CompilerElementNode
): VisualEditSourceRange | null {
  const shell = resolveElementShell(element)
  if (shell?.kind !== 'paired') return null
  const start = element.loc.start.offset + shell.openingTag.length
  const end = element.loc.end.offset - shell.closingTag.length
  if (start > end || start < element.loc.start.offset || end > element.loc.end.offset) {
    return null
  }
  return { start, end }
}

/** 校验并规范化富文本；复杂标签外壳与属性保持原样。 */
export function normalizeRichTextFragment(fragment: string): string | null {
  const container = parseRichTextContainer(fragment)
  return container ? serializeRichTextChildren(container.children) : null
}

/** 提取锁定标签的有序骨架，忽略可自由变化的 classless strong/em 与 br。 */
export function extractRichTextLockedStructure(fragment: string): VisualEditRichTextLockedNode[] | null {
  const container = parseRichTextContainer(fragment)
  if (!container || serializeRichTextChildren(container.children) === null) return null
  return collectRichTextLockedNodes(container.children)
}

/** 在 Vue 编译器边界解析富文本容器。 */
function parseRichTextContainer(fragment: string): CompilerElementNode | null {
  if (fragment.length > VISUAL_EDIT_RICH_TEXT_MAX_LENGTH || fragment.includes('\0') || /{{|}}/.test(fragment)) {
    return null
  }
  const wrapped = `<template><p>${fragment}</p></template>`
  const parsed = parse(wrapped, { filename: 'visual-edit-rich-text.vue', sourceMap: false })
  const root = parsed.descriptor.template?.ast
  if (!root || parsed.errors.length > 0) return null
  const container = root.children[0] as unknown as CompilerElementNode | undefined
  return container?.type === TEMPLATE_NODE_ELEMENT && container.tag === 'p' ? container : null
}

/** 递归收集锁定节点；classless strong/em 只提升其锁定后代。 */
function collectRichTextLockedNodes(children: CompilerTemplateChild[]): VisualEditRichTextLockedNode[] {
  const result: VisualEditRichTextLockedNode[] = []
  for (const child of children) {
    if (child.type !== TEMPLATE_NODE_ELEMENT) continue
    const element = child as CompilerElementNode
    const descendants = collectRichTextLockedNodes(element.children)
    if (isLockedRichTextElement(element)) {
      const shell = resolveElementShell(element)
      if (shell) {
        result.push({
          signature: `${shell.openingTag}\u0000${shell.kind === 'paired' ? shell.closingTag : ''}`,
          children: descendants,
        })
      }
    } else {
      result.push(...descendants)
    }
  }
  return result
}

/** 把编译器解码后的节点序列化，锁定标签直接复用其原始 shell。 */
function serializeRichTextChildren(children: CompilerTemplateChild[]): string | null {
  let result = ''
  for (const child of children) {
    if (child.type === TEMPLATE_NODE_TEXT) {
      result += escapeRichText((child as { content: string }).content)
      continue
    }
    if (child.type !== TEMPLATE_NODE_ELEMENT) return null
    const element = child as CompilerElementNode
    const content = serializeRichTextChildren(element.children)
    const shell = resolveElementShell(element)
    if (content === null || !shell) return null
    const tag = element.tag.toLowerCase()
    if (tag === 'br' && element.props.length === 0) {
      if (element.children.length > 0) return null
      result += '<br>'
    } else if (isMutableSemanticElement(element)) {
      result += `<${tag}>${content}</${tag}>`
    } else if (shell.kind === 'paired') {
      result += `${shell.openingTag}${content}${shell.closingTag}`
    } else {
      // 自闭合锁定元素没有子节点，直接保留原始 opening tag。
      result += shell.openingTag
    }
  }
  return result
}

/** classless strong/em 可由用户添加或取消，其他标签与任意属性均锁定。 */
function isLockedRichTextElement(element: CompilerElementNode): boolean {
  const tag = element.tag.toLowerCase()
  return !(isMutableSemanticElement(element) || (tag === 'br' && element.props.length === 0))
}

/** 判断元素是否为无属性 strong/em。 */
function isMutableSemanticElement(element: CompilerElementNode): boolean {
  const tag = element.tag.toLowerCase()
  return (tag === 'strong' || tag === 'em') && element.props.length === 0
}

/**
 * 从元素源码中切分 opening/closing tag；自闭合与 void 标签归为 self-closing，
 * 无 closing tag 且非自闭合形态（如隐式闭合）视为解析失败返回 null。
 */
function resolveElementShell(element: CompilerElementNode): VisualEditElementShell | null {
  const source = element.loc.source
  const openingEnd = findOpeningTagEnd(source)
  if (openingEnd < 0) return null
  const openingTag = source.slice(0, openingEnd)
  const closingStart = source.toLowerCase().lastIndexOf(`</${element.tag.toLowerCase()}`)
  if (closingStart >= openingEnd) {
    return { kind: 'paired', openingTag, closingTag: source.slice(closingStart) }
  }
  if (element.children.length > 0) return null
  const selfClosing = /\/\s*>$/.test(openingTag) || HTML_VOID_TAGS.has(element.tag.toLowerCase())
  return selfClosing ? { kind: 'self-closing', openingTag } : null
}

/** 查找 opening tag 结束位置，并忽略属性字符串内的大于号。 */
function findOpeningTagEnd(source: string): number {
  let quote: '"' | "'" | null = null
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index]
    if (quote) {
      if (character === quote && source[index - 1] !== '\\') quote = null
    } else if (character === '"' || character === "'") {
      quote = character
    } else if (character === '>') {
      return index + 1
    }
  }
  return -1
}

/** 转义文本节点，避免生成新标签或 Vue 插值。 */
function escapeRichText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/{/g, '&#123;')
    .replace(/}/g, '&#125;')
}
