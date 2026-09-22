/**
 * 文件用途：把 Vue 模板编译器节点转换为可视化编辑语义树，并关联脚本数组成员定位信息。
 */

import type {
  VisualEditBinding,
  VisualEditBindingKind,
  VisualEditDiagnostic,
  VisualEditJsonSource,
  VisualEditLoopContext,
  VisualEditReadonlyReason,
  VisualEditTemplateNode,
} from '../protocol'
import { VISUAL_EDIT_RESERVED_ATTRIBUTES } from '../instrumentation/markers'
import type {
  ScriptCollectionDefinition,
  ScriptLiteralMember,
} from './analyze-script'
import {
  TEMPLATE_NODE_ATTRIBUTE,
  TEMPLATE_NODE_DIRECTIVE,
  TEMPLATE_NODE_ELEMENT,
  TEMPLATE_NODE_INTERPOLATION,
  TEMPLATE_NODE_TEXT,
  TEMPLATE_TAG_COMPONENT,
  type CompilerAttributeNode,
  type CompilerDirectiveNode,
  type CompilerElementNode,
  type CompilerPropNode,
  type CompilerRootNode,
  type CompilerTemplateChild,
  type CompilerTextNode,
  type CompilerInterpolationNode,
} from './compiler-node-types'
import {
  createStableId,
  isIdentifier,
  parseDirectMemberExpression,
  parseTemplateExpression,
  toSourceRange,
} from './template-expression'
import {
  normalizeRichTextFragment,
  resolveElementInnerRange,
  resolveRichTextContainerKind,
  type VisualEditRichTextContentKind,
} from './rich-text'
import { parseJsonExpressionText } from './json-literal'

interface TemplateWalkContext {
  modulePath: string
  collections: Map<string, ScriptCollectionDefinition>
  jsonSources: Map<string, VisualEditJsonSource>
  diagnostics: VisualEditDiagnostic[]
  activeLoop?: VisualEditLoopContext
  loopDepth: number
}

export interface AnalyzeTemplateOptions {
  modulePath: string
  collections: Map<string, ScriptCollectionDefinition>
  jsonSources: Map<string, VisualEditJsonSource>
  diagnostics: VisualEditDiagnostic[]
  rootNodeId: string
}

/**
 * 分析模板根节点，返回根容器直接持有的文本绑定和元素树。
 */
export function analyzeTemplate(
  templateRoot: CompilerRootNode,
  options: AnalyzeTemplateOptions
): Pick<VisualEditTemplateNode, 'bindings' | 'children'> {
  const context: TemplateWalkContext = {
    modulePath: options.modulePath,
    collections: options.collections,
    jsonSources: options.jsonSources,
    diagnostics: options.diagnostics,
    loopDepth: 0,
  }
  return {
    children: collectElementChildren(templateRoot.children, '0', context),
    bindings: collectContentBindings(
      templateRoot.children,
      options.rootNodeId,
      '0',
      context
    ),
  }
}

/**
 * 递归收集模板中的元素与组件节点，跳过注释和纯文本产生的伪容器。
 */
function collectElementChildren(
  children: CompilerTemplateChild[],
  parentPath: string,
  context: TemplateWalkContext
): VisualEditTemplateNode[] {
  const result: VisualEditTemplateNode[] = []
  children.forEach((child, childIndex) => {
    if (child.type === TEMPLATE_NODE_ELEMENT) {
      result.push(
        analyzeElementNode(
          child as CompilerElementNode,
          `${parentPath}.${childIndex}`,
          context
        )
      )
    }
  })
  return result
}

/**
 * 分析单个模板元素，并把当前 v-for 作用域传递给所有后代绑定。
 */
function analyzeElementNode(
  element: CompilerElementNode,
  path: string,
  parentContext: TemplateWalkContext
): VisualEditTemplateNode {
  const nodeId = createStableId(
    'node',
    parentContext.modulePath,
    path,
    element.tag
  )
  const ownLoop = analyzeLoopContext(element, nodeId, parentContext)
  const activeLoop = ownLoop || parentContext.activeLoop
  const childContext: TemplateWalkContext = {
    ...parentContext,
    activeLoop,
    loopDepth: parentContext.loopDepth + (ownLoop ? 1 : 0),
  }
  const richText = resolveRichTextContainerKind(element)
  if (richText.mode === 'unresolved') {
    parentContext.diagnostics.push(buildRichTextRangeDiagnostic(element))
  }
  const richTextResult =
    richText.mode === 'aggregate'
      ? buildRichTextBinding(element, path, nodeId, richText.contentKind)
      : null
  if (richTextResult?.diagnostic) {
    parentContext.diagnostics.push(richTextResult.diagnostic)
  }
  const richTextBinding = richTextResult?.binding ?? null
  const aggregatesChildren =
    richTextBinding !== null &&
    richText.mode === 'aggregate' &&
    (richText.contentKind === 'static' ||
      richText.contentKind === 'locked' ||
      richText.contentKind === 'dynamic')
  return {
    nodeId,
    kind: element.tagType === TEMPLATE_TAG_COMPONENT ? 'component' : 'element',
    tag: element.tag,
    sourceRange: toSourceRange(element.loc),
    loopContext: ownLoop,
    templateActions: buildTemplateActions(
      element,
      ownLoop,
      parentContext.activeLoop
    ),
    loopItemActions: buildLoopItemActions(
      activeLoop,
      parentContext.collections
    ),
    bindings: [
      ...buildLoopJsonBindings(ownLoop, nodeId, path, childContext),
      ...collectPropBindings(element, path, nodeId, childContext),
      ...(richTextBinding
        ? [richTextBinding]
        : collectContentBindings(element.children, nodeId, path, childContext)),
    ],
    children: aggregatesChildren
      ? []
      : collectElementChildren(element.children, path, childContext),
  }
}

/** 计算节点模板级能力；循环后代只能操作数据项，循环根只允许整体删除。 */
function buildTemplateActions(
  element: CompilerElementNode,
  ownLoop: VisualEditLoopContext | undefined,
  parentLoop: VisualEditLoopContext | undefined
): VisualEditTemplateNode['templateActions'] {
  if (parentLoop) {
    return {
      canDuplicate: false,
      canDelete: false,
      readonlyReason: 'STRUCTURE_LOOP_INSTANCE_REQUIRED',
    }
  }
  if (ownLoop) {
    return { canDuplicate: false, canDelete: true }
  }
  if (hasStructuralControlFlow(element)) {
    return {
      canDuplicate: false,
      canDelete: false,
      readonlyReason: 'STRUCTURE_CONTROL_FLOW_UNSUPPORTED',
    }
  }
  return { canDuplicate: true, canDelete: true }
}

/** 循环项能力只对稳定、可编辑的本地对象数组开放。 */
function buildLoopItemActions(
  loop: VisualEditLoopContext | undefined,
  collections: Map<string, ScriptCollectionDefinition>
): VisualEditTemplateNode['loopItemActions'] {
  if (!loop?.editable || !loop.sourceBinding || !loop.keyMember)
    return undefined
  const collection = collections.get(loop.sourceBinding)
  if (!collection?.editable || !collection.kind) return undefined
  const instances =
    collection?.items.flatMap((item) => {
      const key = resolveItemKey(item.members.get(loop.keyMember || ''))
      return key === undefined ? [] : [{ index: item.index, key }]
    }) ?? []
  if (instances.length === 0 || instances.length !== collection.items.length)
    return undefined
  return {
    canDuplicate: true,
    canDelete: true,
    loopNodeId: loop.loopNodeId,
    collectionName: loop.sourceBinding,
    keyMember: loop.keyMember,
    instances,
  }
}

/** 为直接引用顶层 JSON 数组的循环增加整块数据 binding。 */
function buildLoopJsonBindings(
  loop: VisualEditLoopContext | undefined,
  nodeId: string,
  path: string,
  context: TemplateWalkContext
): VisualEditBinding[] {
  if (!loop?.sourceBinding) return []
  const source = context.jsonSources.get(loop.sourceBinding)
  if (!source || !Array.isArray(source.value)) return []
  return [
    buildJsonBinding(
      source,
      nodeId,
      path,
      'json',
      loop.sourceBinding,
      loop.sourceExpression
    ),
  ]
}

/** 带条件、slot 等控制语义的节点不直接做模板结构改写。 */
function hasStructuralControlFlow(element: CompilerElementNode): boolean {
  return element.props.some(
    (prop) =>
      prop.type === TEMPLATE_NODE_DIRECTIVE &&
      ['if', 'else', 'else-if', 'slot'].includes(
        (prop as CompilerDirectiveNode).name
      )
  )
}

/** 富文本 binding 构建结果；定位失败时 binding 为 null 并附带降级诊断。 */
interface RichTextBindingResult {
  binding: VisualEditBinding | null
  diagnostic?: VisualEditDiagnostic
}

/** 构造富文本范围无法定位的节点级只读降级诊断，sourceRange 指向整个元素。 */
function buildRichTextRangeDiagnostic(
  element: CompilerElementNode
): VisualEditDiagnostic {
  return {
    severity: 'warning',
    code: 'RICH_TEXT_SOURCE_RANGE_UNRESOLVED',
    message: `无法定位富文本容器 <${element.tag}> 的内部源码范围，该节点已降级为只读。`,
    sourceRange: toSourceRange(element.loc),
  }
}

/**
 * 把文本容器内部内容聚合为一个富文本 binding；复杂静态标签锁定外壳后仍可编辑文本。
 * 内部范围无法定位时不中断分析，返回降级诊断由调用方记入 Manifest diagnostics。
 */
function buildRichTextBinding(
  element: CompilerElementNode,
  path: string,
  nodeId: string,
  contentKind: VisualEditRichTextContentKind
): RichTextBindingResult {
  const sourceRange = resolveElementInnerRange(element)
  if (!sourceRange) {
    return { binding: null, diagnostic: buildRichTextRangeDiagnostic(element) }
  }
  const relativeStart = sourceRange.start - element.loc.start.offset
  const relativeEnd = sourceRange.end - element.loc.start.offset
  const rawValue = element.loc.source.slice(relativeStart, relativeEnd)
  const normalizedValue =
    contentKind === 'static' || contentKind === 'locked'
      ? normalizeRichTextFragment(rawValue)
      : null
  const editable =
    (contentKind === 'static' || contentKind === 'locked') &&
    normalizedValue !== null
  return {
    binding: {
      bindingId: createStableId('binding', nodeId, path, 'rich_text'),
      nodeId,
      kind: 'rich_text',
      valueType: 'string',
      value: normalizedValue ?? rawValue,
      sourceRange,
      editable,
      readonlyReason: editable
        ? undefined
        : contentKind === 'dynamic'
          ? 'RICH_TEXT_DYNAMIC_CONTENT'
          : 'RICH_TEXT_UNSUPPORTED_STRUCTURE',
      source: editable ? { kind: 'template-rich-text' } : undefined,
    },
  }
}

/**
 * 从 v-for 和 :key 提取单层循环语义，并判断数据源是否为受支持的静态数组。
 */
function analyzeLoopContext(
  element: CompilerElementNode,
  nodeId: string,
  context: TemplateWalkContext
): VisualEditLoopContext | undefined {
  const forDirective = element.props.find(isForDirective)
  if (!forDirective) {
    return undefined
  }
  const parsedFor = parseForDirective(forDirective)
  const keyExpression = findBoundExpression(element.props, 'key')
  const parsedKey = keyExpression
    ? parseDirectMemberExpression(keyExpression)
    : undefined
  const keyMember =
    parsedFor && parsedKey?.object === parsedFor.itemAlias
      ? parsedKey.property
      : undefined
  if (!parsedFor) {
    const fallbackItemAlias =
      forDirective.forParseResult?.value?.content.trim() || '_unsupported'
    return {
      loopNodeId: nodeId,
      sourceExpression:
        forDirective.forParseResult?.source?.content.trim() ||
        forDirective.exp?.content.trim() ||
        '(unsupported)',
      itemAlias: isIdentifier(fallbackItemAlias)
        ? fallbackItemAlias
        : '_unsupported',
      keyExpression,
      editable: false,
      readonlyReason: 'LOOP_SOURCE_UNSUPPORTED',
    }
  }
  if (context.loopDepth > 0) {
    return {
      loopNodeId: nodeId,
      ...parsedFor,
      keyExpression,
      keyMember,
      editable: false,
      readonlyReason: 'NESTED_LOOP_UNSUPPORTED',
    }
  }

  const collection = context.collections.get(parsedFor.sourceExpression)
  const readonlyReason = resolveLoopReadonlyReason(
    parsedFor.sourceExpression,
    collection,
    keyMember
  )
  return {
    loopNodeId: nodeId,
    ...parsedFor,
    sourceBinding: collection ? parsedFor.sourceExpression : undefined,
    keyExpression,
    keyMember,
    editable: !readonlyReason,
    readonlyReason,
  }
}

/**
 * 解析编译器提供的 v-for 结果；仅接受简单别名和直接变量数据源。
 */
function parseForDirective(directive: CompilerDirectiveNode): {
  sourceExpression: string
  itemAlias: string
  indexAlias?: string
} | null {
  const result = directive.forParseResult
  const sourceExpression = result?.source?.content.trim() || ''
  const itemAlias = result?.value?.content.trim() || ''
  const indexAlias = result?.key?.content.trim() || undefined
  if (
    !isIdentifier(sourceExpression) ||
    !isIdentifier(itemAlias) ||
    (indexAlias && !isIdentifier(indexAlias))
  ) {
    return null
  }
  return { sourceExpression, itemAlias, indexAlias }
}

/**
 * 根据脚本数据源状态给循环生成稳定只读原因。
 */
function resolveLoopReadonlyReason(
  sourceExpression: string,
  collection?: ScriptCollectionDefinition,
  keyMember?: string
): VisualEditReadonlyReason | undefined {
  if (!isIdentifier(sourceExpression)) {
    return 'LOOP_SOURCE_UNSUPPORTED'
  }
  if (!collection) {
    return 'SCRIPT_SOURCE_NOT_FOUND'
  }
  if (!collection.editable || !collection.kind) {
    return 'DYNAMIC_SCRIPT_SOURCE'
  }
  if (!keyMember || !hasStableUniqueKeys(collection, keyMember)) {
    return 'LOOP_MEMBER_UNSUPPORTED'
  }
  return undefined
}

/**
 * 要求每个静态数组项都提供唯一字符串或数字 key，禁止以 index 隐式维持可编辑状态。
 */
function hasStableUniqueKeys(
  collection: ScriptCollectionDefinition,
  keyMember: string
): boolean {
  const keys = new Set<string | number>()
  for (const item of collection.items) {
    const member = item.members.get(keyMember)
    const key = resolveItemKey(member)
    if (key === undefined || !member?.editable || keys.has(key)) {
      return false
    }
    keys.add(key)
  }
  return true
}

/**
 * 分析元素属性：静态属性可写，动态绑定仅允许字面量或当前循环的 item.member。
 */
function collectPropBindings(
  element: CompilerElementNode,
  path: string,
  nodeId: string,
  context: TemplateWalkContext
): VisualEditBinding[] {
  const bindings: VisualEditBinding[] = []
  element.props.forEach((prop, propIndex) => {
    if (prop.type === TEMPLATE_NODE_ATTRIBUTE) {
      if (!shouldSkipTemplateAttribute(prop.name)) {
        bindings.push(
          buildStaticAttributeBinding(prop, nodeId, path, propIndex)
        )
      }
      return
    }
    if (
      prop.type !== TEMPLATE_NODE_DIRECTIVE ||
      prop.name !== 'bind' ||
      !prop.arg?.isStatic
    ) {
      return
    }
    const name = prop.arg.content
    if (shouldSkipTemplateAttribute(name)) {
      return
    }
    const expression = prop.exp?.content || ''
    const jsonBinding =
      element.tagType === TEMPLATE_TAG_COMPONENT
        ? buildComponentJsonBinding(
            expression,
            prop.exp ? toSourceRange(prop.exp.loc) : toSourceRange(prop.loc),
            nodeId,
            path,
            name,
            context
          )
        : null
    bindings.push(
      jsonBinding ||
        buildExpressionBinding({
          nodeId,
          path,
          ordinal: `prop.${propIndex}`,
          kind: name === 'class' ? 'class' : 'prop',
          name,
          expression,
          sourceRange: toSourceRange(prop.exp?.loc || prop.loc),
          context,
          missingValue: !prop.exp,
        })
    )
  })
  return bindings
}

/** 识别组件 prop 的顶层 JSON 引用或内联标准 JSON 值。 */
function buildComponentJsonBinding(
  expression: string,
  sourceRange: VisualEditBinding['sourceRange'],
  nodeId: string,
  path: string,
  name: string,
  context: TemplateWalkContext
): VisualEditBinding | null {
  const referenced = isIdentifier(expression)
    ? context.jsonSources.get(expression)
    : undefined
  if (referenced)
    return buildJsonBinding(referenced, nodeId, path, 'prop', name, expression)
  const value = parseJsonExpressionText(expression)
  if (value === undefined) return null
  const sourceId = createStableId(
    'source',
    context.modulePath,
    'template',
    nodeId,
    name
  )
  const source: VisualEditJsonSource = {
    sourceId,
    kind: 'template-expression',
    value,
    sourceRange,
    editable: true,
  }
  context.jsonSources.set(`#${sourceId}`, source)
  return buildJsonBinding(source, nodeId, path, 'prop', name, expression)
}

/** 生成指向去重 JSON source 的节点 binding。 */
function buildJsonBinding(
  source: VisualEditJsonSource,
  nodeId: string,
  path: string,
  kind: 'json' | 'prop',
  name: string,
  expression: string
): VisualEditBinding {
  return {
    bindingId: createStableId('binding', nodeId, path, 'json', name),
    nodeId,
    kind,
    name,
    valueType: 'json',
    value: source.value,
    expression,
    sourceRange: source.sourceRange,
    editable: true,
    source: { kind: 'json-source', sourceId: source.sourceId },
  }
}

/**
 * 排除 Vue 身份字段、复杂内联 CSS 与 Runtime 保留 marker；样式首版只经受控 Tailwind class 操作编辑。
 */
function shouldSkipTemplateAttribute(name: string): boolean {
  return (
    name === 'key' ||
    name === 'style' ||
    VISUAL_EDIT_RESERVED_ATTRIBUTES.has(name)
  )
}

/**
 * 把静态 HTML/Vue 属性转换成模板字面量绑定。
 */
function buildStaticAttributeBinding(
  attribute: CompilerAttributeNode,
  nodeId: string,
  path: string,
  ordinal: number
): VisualEditBinding {
  const kind: VisualEditBindingKind =
    attribute.name === 'class' ? 'class' : 'prop'
  return {
    bindingId: createStableId(
      'binding',
      nodeId,
      path,
      kind,
      attribute.name,
      ordinal
    ),
    nodeId,
    kind,
    name: attribute.name,
    valueType: attribute.value ? 'string' : 'unknown',
    value: attribute.value?.content,
    sourceRange: toSourceRange(attribute.value?.loc || attribute.loc),
    editable: Boolean(attribute.value),
    readonlyReason: attribute.value ? undefined : 'ATTRIBUTE_VALUE_MISSING',
    source: attribute.value ? { kind: 'template-literal' } : undefined,
  }
}

/**
 * 收集元素直接文本子节点；子元素的文本由其自身负责，避免绑定重复。
 */
function collectContentBindings(
  children: CompilerTemplateChild[],
  nodeId: string,
  path: string,
  context: TemplateWalkContext
): VisualEditBinding[] {
  const bindings: VisualEditBinding[] = []
  children.forEach((child, childIndex) => {
    if (child.type === TEMPLATE_NODE_TEXT) {
      const binding = buildStaticTextBinding(
        child as CompilerTextNode,
        nodeId,
        path,
        childIndex
      )
      if (binding) {
        bindings.push(binding)
      }
    } else if (child.type === TEMPLATE_NODE_INTERPOLATION) {
      const interpolation = child as CompilerInterpolationNode
      bindings.push(
        buildExpressionBinding({
          nodeId,
          path,
          ordinal: `text.${childIndex}`,
          kind: 'text',
          expression: interpolation.content.content,
          sourceRange: toSourceRange(interpolation.content.loc),
          context,
        })
      )
    }
  })
  return bindings
}

/**
 * 忽略格式化产生的纯空白文本，并让替换范围只覆盖用户可见内容。
 */
function buildStaticTextBinding(
  text: CompilerTextNode,
  nodeId: string,
  path: string,
  ordinal: number
): VisualEditBinding | null {
  const value = text.content.trim()
  if (!value) {
    return null
  }
  const rawSource = text.loc.source
  const leadingLength = rawSource.length - rawSource.trimStart().length
  const trailingLength = rawSource.length - rawSource.trimEnd().length
  return {
    bindingId: createStableId('binding', nodeId, path, 'text', ordinal),
    nodeId,
    kind: 'text',
    valueType: 'string',
    value,
    sourceRange: {
      start: text.loc.start.offset + leadingLength,
      end: text.loc.end.offset - trailingLength,
    },
    editable: true,
    source: { kind: 'template-literal' },
  }
}

interface ExpressionBindingOptions {
  nodeId: string
  path: string
  ordinal: string
  kind: VisualEditBindingKind
  name?: string
  expression: string
  sourceRange: VisualEditBinding['sourceRange']
  context: TemplateWalkContext
  missingValue?: boolean
}

/**
 * 把模板表达式归类为字面量、循环数组成员或动态只读表达式。
 */
function buildExpressionBinding(
  options: ExpressionBindingOptions
): VisualEditBinding {
  const bindingId = createStableId(
    'binding',
    options.nodeId,
    options.path,
    options.kind,
    options.name || '',
    options.ordinal
  )
  if (options.missingValue) {
    return buildReadonlyBinding(options, bindingId, 'ATTRIBUTE_VALUE_MISSING')
  }
  const parsedExpression = parseTemplateExpression(options.expression)
  if (
    parsedExpression.literal !== undefined ||
    parsedExpression.valueType === 'null'
  ) {
    return {
      bindingId,
      nodeId: options.nodeId,
      kind: options.kind,
      name: options.name,
      valueType: parsedExpression.valueType,
      value: parsedExpression.literal,
      expression: options.expression,
      sourceRange: options.sourceRange,
      editable: true,
      source: { kind: 'template-literal' },
    }
  }

  const loop = options.context.activeLoop
  if (
    parsedExpression.member &&
    loop &&
    parsedExpression.member.object === loop.itemAlias
  ) {
    return buildLoopMemberBinding(
      options,
      bindingId,
      parsedExpression.member.property,
      loop
    )
  }
  return buildReadonlyBinding(options, bindingId, 'DYNAMIC_EXPRESSION')
}

/**
 * 构建 item.member 到脚本数组各项字面量的定位列表。
 */
function buildLoopMemberBinding(
  options: ExpressionBindingOptions,
  bindingId: string,
  memberName: string,
  loop: VisualEditLoopContext
): VisualEditBinding {
  if (!loop.editable || !loop.sourceBinding) {
    return buildReadonlyBinding(
      options,
      bindingId,
      loop.readonlyReason || 'LOOP_SOURCE_UNSUPPORTED'
    )
  }
  const collection = options.context.collections.get(loop.sourceBinding)
  if (!collection?.kind) {
    return buildReadonlyBinding(options, bindingId, 'SCRIPT_SOURCE_NOT_FOUND')
  }
  const locations = collection.items.map((item) => {
    const member = item.members.get(memberName)
    return {
      index: item.index,
      key: resolveItemKey(item.members.get(loop.keyMember || '')),
      value: member?.value,
      sourceRange: member?.sourceRange,
      editable: Boolean(member?.editable),
      readonlyReason: member
        ? member.readonlyReason
        : ('MEMBER_NOT_FOUND' as const),
    }
  })
  const firstMember = collection.items
    .map((item) => item.members.get(memberName))
    .find((member): member is ScriptLiteralMember => Boolean(member))
  const editable = locations.some((location) => location.editable)
  return {
    bindingId,
    nodeId: options.nodeId,
    kind: options.kind,
    name: options.name,
    valueType: firstMember?.valueType || 'unknown',
    expression: options.expression,
    sourceRange: options.sourceRange,
    editable,
    readonlyReason: editable
      ? undefined
      : firstMember?.readonlyReason || 'MEMBER_NOT_FOUND',
    source: {
      kind: 'script-array-item',
      collectionName: collection.name,
      collectionKind: collection.kind,
      itemAlias: loop.itemAlias,
      member: memberName,
      keyMember: loop.keyMember,
      locations,
    },
  }
}

/**
 * 构建结构一致的只读绑定，供 Editor 解释不支持原因。
 */
function buildReadonlyBinding(
  options: ExpressionBindingOptions,
  bindingId: string,
  readonlyReason: VisualEditReadonlyReason
): VisualEditBinding {
  return {
    bindingId,
    nodeId: options.nodeId,
    kind: options.kind,
    name: options.name,
    valueType: 'unknown',
    expression: options.expression,
    sourceRange: options.sourceRange,
    editable: false,
    readonlyReason,
  }
}

/**
 * 读取 :key 或其它静态参数绑定的表达式。
 */
function findBoundExpression(
  props: CompilerPropNode[],
  name: string
): string | undefined {
  const directive = props.find(
    (prop): prop is CompilerDirectiveNode =>
      prop.type === TEMPLATE_NODE_DIRECTIVE &&
      prop.name === 'bind' &&
      prop.arg?.isStatic === true &&
      prop.arg.content === name
  )
  return directive?.exp?.content.trim() || undefined
}

/**
 * 仅允许字符串和数字作为稳定循环 key；其它值回退到 index 定位。
 */
export function resolveItemKey(
  member?: ScriptLiteralMember
): string | number | undefined {
  if (typeof member?.value === 'string') {
    return member.value
  }
  return typeof member?.value === 'number' && Number.isSafeInteger(member.value)
    ? member.value
    : undefined
}

/**
 * 判断节点是否为 v-for 指令。
 */
function isForDirective(prop: CompilerPropNode): prop is CompilerDirectiveNode {
  return prop.type === TEMPLATE_NODE_DIRECTIVE && prop.name === 'for'
}
