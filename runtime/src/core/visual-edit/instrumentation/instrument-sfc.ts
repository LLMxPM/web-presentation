/**
 * 文件用途：基于 canonical Manifest 坐标向派生 Vue SFC 注入只读 DOM 选择 marker，不修改规范源码。
 */

import { parse } from '@vue/compiler-sfc'

import type {
  VisualEditLoopContext,
  VisualEditSfcManifest,
  VisualEditTemplateNode,
} from '../protocol'
import {
  TEMPLATE_NODE_DIRECTIVE,
  TEMPLATE_NODE_ELEMENT,
  type CompilerDirectiveNode,
  type CompilerElementNode,
  type CompilerPropNode,
  type CompilerRootNode,
  type CompilerTemplateChild,
} from '../source/compiler-node-types'
import {
  VISUAL_EDIT_LOOP_ATTRIBUTE,
  VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE,
  VISUAL_EDIT_LOOP_KEY_ATTRIBUTE,
  VISUAL_EDIT_NODE_ATTRIBUTE,
  VISUAL_EDIT_RESERVED_ATTRIBUTES,
} from './markers'

interface InstrumentationInsertion {
  offset: number
  content: string
}

interface InstrumentationScope {
  activeLoop?: VisualEditLoopContext
  loopBlocked: boolean
}

/**
 * 生成仅供 visual-edit artifact 使用的派生源码。Manifest 和 sourceHash 始终仍指向 canonicalSource。
 */
export function instrumentVisualEditSfc(canonicalSource: string, manifest: VisualEditSfcManifest): string {
  const parsed = parse(canonicalSource, { filename: manifest.modulePath, sourceMap: false })
  if (!parsed.descriptor.template?.ast || parsed.errors.length > 0) {
    throw new VisualEditInstrumentationError('PAGE_VISUAL_EDIT_INSTRUMENTATION_PARSE_FAILED', 'Vue SFC 无法执行可视化编辑插桩。')
  }
  const compilerElements = collectCompilerElements(
    (parsed.descriptor.template.ast as unknown as CompilerRootNode).children,
  )
  const compilerElementsByStart = new Map(
    compilerElements.map(element => [element.loc.start.offset, element]),
  )
  const insertions: InstrumentationInsertion[] = []
  for (const node of manifest.root.children) {
    collectNodeInsertions(canonicalSource, node, compilerElementsByStart, {
      activeLoop: undefined,
      loopBlocked: false,
    }, insertions)
  }
  return applyInsertions(canonicalSource, insertions)
}

/**
 * 递归匹配 Manifest 节点与编译器节点，并为 DOM 可落地标签构造 marker。
 */
function collectNodeInsertions(
  source: string,
  node: VisualEditTemplateNode,
  compilerElementsByStart: Map<number, CompilerElementNode>,
  parentScope: InstrumentationScope,
  insertions: InstrumentationInsertion[],
): void {
  const scope = resolveInstrumentationScope(node, parentScope)
  const element = compilerElementsByStart.get(node.sourceRange.start)
  if (!element || element.tag !== node.tag) {
    throw new VisualEditInstrumentationError(
      'PAGE_VISUAL_EDIT_INSTRUMENTATION_NODE_MISMATCH',
      `Manifest 节点 ${node.nodeId} 无法映射 canonical template。`,
    )
  }
  assertNoReservedAttributes(element.props, node.nodeId)
  if (node.tag !== 'template') {
    insertions.push({
      offset: findOpeningTagInsertionOffset(source, node.sourceRange.start),
      content: buildMarkerAttributes(node, scope.activeLoop),
    })
  }
  for (const child of node.children) {
    collectNodeInsertions(source, child, compilerElementsByStart, scope, insertions)
  }
}

/**
 * 节点自身循环覆盖父作用域；不稳定或嵌套循环会阻断其整棵子树的实例 marker。
 */
function resolveInstrumentationScope(
  node: VisualEditTemplateNode,
  parentScope: InstrumentationScope,
): InstrumentationScope {
  if (node.loopContext) {
    return !parentScope.loopBlocked
      && !parentScope.activeLoop
      && node.loopContext.editable
      && node.loopContext.keyMember
      ? { activeLoop: node.loopContext, loopBlocked: false }
      : { activeLoop: undefined, loopBlocked: true }
  }
  return parentScope.loopBlocked
    ? { activeLoop: undefined, loopBlocked: true }
    : parentScope
}

/**
 * 构造静态 node marker 及可选的单层循环动态 key/index marker。
 */
function buildMarkerAttributes(node: VisualEditTemplateNode, activeLoop?: VisualEditLoopContext): string {
  const attributes = [`${VISUAL_EDIT_NODE_ATTRIBUTE}="${node.nodeId}"`]
  if (activeLoop?.keyMember) {
    attributes.push(`${VISUAL_EDIT_LOOP_ATTRIBUTE}="${activeLoop.loopNodeId}"`)
    attributes.push(
      `:${VISUAL_EDIT_LOOP_KEY_ATTRIBUTE}="JSON.stringify(${activeLoop.itemAlias}.${activeLoop.keyMember})"`,
    )
    if (activeLoop.indexAlias) {
      attributes.push(`:${VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE}="${activeLoop.indexAlias}"`)
    }
  }
  return ` ${attributes.join(' ')}`
}

/**
 * 拒绝 canonical 页面声明保留属性或无参数 v-bind，防止页面自带值冒充 Runtime marker。
 */
function assertNoReservedAttributes(props: CompilerPropNode[], nodeId: string): void {
  for (const prop of props) {
    if (prop.type !== TEMPLATE_NODE_DIRECTIVE) {
      if (VISUAL_EDIT_RESERVED_ATTRIBUTES.has(prop.name)) {
        throw reservedAttributeError(nodeId)
      }
      continue
    }
    const directive = prop as CompilerDirectiveNode
    if (directive.name === 'bind' && (
      !directive.arg
      || !directive.arg.isStatic
      || VISUAL_EDIT_RESERVED_ATTRIBUTES.has(directive.arg.content)
    )) {
      throw reservedAttributeError(nodeId)
    }
  }
}

/**
 * 扫描 opening tag，并找到不在引号中的 `>` 或 `/>` 前插入点。
 */
function findOpeningTagInsertionOffset(source: string, startOffset: number): number {
  let quote: '"' | "'" | null = null
  for (let offset = startOffset; offset < source.length; offset += 1) {
    const character = source[offset]
    if (quote) {
      if (character === quote && source[offset - 1] !== '\\') {
        quote = null
      }
      continue
    }
    if (character === '"' || character === "'") {
      quote = character
      continue
    }
    if (character === '>') {
      let insertionOffset = offset
      while (insertionOffset > startOffset && /\s/.test(source[insertionOffset - 1])) {
        insertionOffset -= 1
      }
      if (source[insertionOffset - 1] === '/') {
        insertionOffset -= 1
      }
      return insertionOffset
    }
  }
  throw new VisualEditInstrumentationError('PAGE_VISUAL_EDIT_INSTRUMENTATION_TAG_INVALID', '模板 opening tag 未闭合。')
}

/**
 * 收集原始模板中的全部 element/component 节点。
 */
function collectCompilerElements(children: CompilerTemplateChild[]): CompilerElementNode[] {
  const result: CompilerElementNode[] = []
  for (const child of children) {
    if (child.type !== TEMPLATE_NODE_ELEMENT) {
      continue
    }
    const element = child as CompilerElementNode
    result.push(element, ...collectCompilerElements(element.children))
  }
  return result
}

/**
 * 按偏移倒序应用插入，保持所有 canonical range 坐标有效。
 */
function applyInsertions(source: string, insertions: InstrumentationInsertion[]): string {
  return [...insertions]
    .sort((left, right) => right.offset - left.offset)
    .reduce((result, insertion) => (
      result.slice(0, insertion.offset) + insertion.content + result.slice(insertion.offset)
    ), source)
}

/**
 * 创建保留属性冲突错误。
 */
function reservedAttributeError(nodeId: string): VisualEditInstrumentationError {
  return new VisualEditInstrumentationError(
    'PAGE_VISUAL_EDIT_RESERVED_ATTRIBUTE_COLLISION',
    `节点 ${nodeId} 使用了 Runtime 可视化编辑保留属性。`,
  )
}

export class VisualEditInstrumentationError extends Error {
  statusCode = 422
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'VisualEditInstrumentationError'
    this.code = code
  }
}
