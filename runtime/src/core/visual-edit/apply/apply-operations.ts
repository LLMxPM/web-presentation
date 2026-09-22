/**
 * 文件用途：以源码 hash 和 Manifest 为基线，原子应用页面可视化编辑操作并重新分析候选 SFC。
 */

import { createHash } from 'node:crypto'
import { parse } from '@vue/compiler-sfc'

import {
  PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
  type VisualEditDiagnostic,
  type VisualEditDeleteNodeOperation,
  type VisualEditDuplicateNodeOperation,
  type VisualEditOperation,
  type VisualEditSetJsonOperation,
  type VisualEditSourceRange,
} from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'
import {
  analyzeScriptCollections,
  type ScriptCollectionDefinition,
  type ScriptCollectionItem,
} from '../source/analyze-script'
import { VisualEditApplyError } from './errors'
import {
  resolveVisualEditBinding,
  resolveVisualEditLocation,
} from './resolve-target'
import { isRichTextLockedStructurePruning } from './rich-text-style-lock'
import { buildVisualEditCanonicalDiff } from './source-diff'
import { applyTailwindTokenChanges } from './tailwind-tokens'
import { validateVisualEditOperations } from './validate-operations'
import {
  encodeVisualEditValue,
  resolveReplacementContext,
} from './value-encoding'
import { serializeVisualEditJsonValue } from '../source/json-literal'

interface SourceReplacement {
  sourceRange: VisualEditSourceRange
  content: string
  operationIndex: number
  allowEmptyRange?: boolean
  targetRange?: VisualEditSourceRange
}

type VisualEditBindingOperation = Exclude<
  VisualEditOperation,
  | VisualEditDuplicateNodeOperation
  | VisualEditDeleteNodeOperation
  | VisualEditSetJsonOperation
>

export interface ApplyVisualEditOperationsResult {
  protocolVersion: 1
  baseSourceHash: string
  nextSourceHash: string
  nextSource: string
  operationsApplied: number
  canonicalDiff: string
  diagnostics: VisualEditDiagnostic[]
}

/**
 * 重新分析规范源码并一次性构建全部替换；任何操作失败时不会产生部分候选源码。
 */
export function applyVisualEditOperations(
  canonicalSource: string,
  modulePath: string,
  sourceHash: string,
  rawOperations: unknown
): ApplyVisualEditOperationsResult {
  assertSourceHash(canonicalSource, sourceHash)
  const operations = validateVisualEditOperations(rawOperations)
  const manifest = analyzeVisualEditSfc(canonicalSource, { modulePath })
  if (
    manifest.modulePath !== modulePath ||
    manifest.sourceHash !== sourceHash
  ) {
    throw new VisualEditApplyError(
      409,
      'PAGE_VISUAL_EDIT_SOURCE_MISMATCH',
      'Manifest 与请求源码身份不一致。'
    )
  }
  assertManifestHasNoErrors(manifest.diagnostics, '规范源码无法通过 SFC 解析。')

  const valueReplacements = operations.flatMap((operation, operationIndex) =>
    operation.type === 'duplicate_node' || operation.type === 'delete_node'
      ? []
      : operation.type === 'set_json'
        ? [buildJsonReplacement(manifest, operation, operationIndex)]
        : [
            buildReplacement(
              canonicalSource,
              manifest,
              operation,
              operationIndex
            ),
          ]
  )
  const collections = analyzeCollections(canonicalSource)
  const generatedKeys = new Map<string, Set<string | number>>()
  const structuralReplacements = operations.flatMap(
    (operation, operationIndex) =>
      operation.type === 'duplicate_node' || operation.type === 'delete_node'
        ? [
            buildStructuralReplacement(
              canonicalSource,
              manifest,
              collections,
              operation,
              operationIndex,
              valueReplacements,
              generatedKeys
            ),
          ]
        : []
  )
  assertStructuralTargets(structuralReplacements)
  const replacements = [...valueReplacements, ...structuralReplacements]
  assertReplacementRanges(canonicalSource, replacements)
  const nextSource = applyReplacements(canonicalSource, replacements)
  if (nextSource === canonicalSource) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_NO_CHANGES',
      '操作没有产生任何源码变化。'
    )
  }
  const nextSourceHash = hashSource(nextSource)
  const nextManifest = analyzeVisualEditSfc(nextSource, { modulePath })
  assertManifestHasNoErrors(
    nextManifest.diagnostics,
    '改写结果无法通过 SFC 解析。'
  )

  return {
    protocolVersion: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
    baseSourceHash: sourceHash,
    nextSourceHash,
    nextSource,
    operationsApplied: operations.length,
    canonicalDiff: buildVisualEditCanonicalDiff(canonicalSource, nextSource),
    diagnostics: nextManifest.diagnostics,
  }
}

/** 根据 Manifest 去重 source 定位并构建整块 JSON 替换。 */
function buildJsonReplacement(
  manifest: ReturnType<typeof analyzeVisualEditSfc>,
  operation: VisualEditSetJsonOperation,
  operationIndex: number
): SourceReplacement {
  const source = manifest.jsonSources.find(
    (item) => item.sourceId === operation.sourceId
  )
  if (!source?.editable) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_NOT_FOUND',
      `未找到可编辑 JSON sourceId=${operation.sourceId}。`
    )
  }
  if (
    source.kind !== 'template-expression' &&
    (operation.value === null ||
      typeof operation.value !== 'object' ||
      Array.isArray(source.value) !== Array.isArray(operation.value))
  ) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_JSON_ROOT_TYPE_INVALID',
      '顶层 JSON 数据必须保持原有数组或对象根类型。'
    )
  }
  return {
    sourceRange: source.sourceRange,
    content: serializeVisualEditJsonValue(operation.value),
    operationIndex,
  }
}

/**
 * 将单个受信协议操作转换成源码替换，但不立即修改字符串。
 */
function buildReplacement(
  canonicalSource: string,
  manifest: ReturnType<typeof analyzeVisualEditSfc>,
  operation: VisualEditBindingOperation,
  operationIndex: number
): SourceReplacement {
  const target = resolveVisualEditBinding(
    manifest,
    operation.nodeId,
    operation.bindingId
  )
  const location = resolveVisualEditLocation(target, operation.instancePath)
  const currentSourceToken = canonicalSource.slice(
    location.sourceRange.start,
    location.sourceRange.end
  )

  if (operation.type === 'set_rich_text') {
    if (
      target.binding.kind !== 'rich_text' ||
      target.binding.source?.kind !== 'template-rich-text'
    ) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID',
        'set_rich_text 只能用于可编辑的模板富文本 binding。'
      )
    }
    if (!isRichTextLockedStructurePruning(currentSourceToken, operation.html)) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_RICH_TEXT_STYLE_LOCKED',
        '富文本中的锁定标签可以移除外壳，但不能新增、修改属性、重排或重新挂载剩余标签。'
      )
    }
    return {
      sourceRange: location.sourceRange,
      content: operation.html,
      operationIndex,
      allowEmptyRange: true,
    }
  }

  if (operation.type === 'set_value') {
    if (target.binding.kind === 'class') {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID',
        'class binding 只能使用 set_tailwind_tokens。'
      )
    }
    return {
      sourceRange: location.sourceRange,
      content: encodeVisualEditValue(
        target.binding,
        currentSourceToken,
        operation.value,
        location.valueType,
        resolveReplacementContext(target.binding)
      ),
      operationIndex,
    }
  }

  if (target.binding.kind !== 'class') {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID',
      'set_tailwind_tokens 只能用于 class binding。'
    )
  }
  if (typeof location.currentValue !== 'string') {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_VALUE_TYPE_MISMATCH',
      'class binding 当前值必须是字符串。'
    )
  }
  const nextClassValue = applyTailwindTokenChanges(
    location.currentValue,
    operation.changes
  )
  return {
    sourceRange: location.sourceRange,
    content: encodeVisualEditValue(
      target.binding,
      currentSourceToken,
      nextClassValue,
      'string',
      resolveReplacementContext(target.binding)
    ),
    operationIndex,
  }
}

/** 将模板节点或循环数组项操作转换成源码替换。 */
function buildStructuralReplacement(
  source: string,
  manifest: ReturnType<typeof analyzeVisualEditSfc>,
  collections: Map<string, ScriptCollectionDefinition>,
  operation: VisualEditDuplicateNodeOperation | VisualEditDeleteNodeOperation,
  operationIndex: number,
  valueReplacements: SourceReplacement[],
  generatedKeys: Map<string, Set<string | number>>
): SourceReplacement {
  const node = findNode(manifest.root, operation.nodeId)
  if (!node) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_NOT_FOUND',
      `未找到 nodeId=${operation.nodeId}。`
    )
  }
  if (operation.instancePath.length > 0) {
    const actions = node.loopItemActions
    if (
      !actions ||
      !(operation.type === 'duplicate_node'
        ? actions.canDuplicate
        : actions.canDelete)
    ) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_TARGET_READONLY',
        '当前节点不允许循环项结构操作。'
      )
    }
    const collection = collections.get(actions.collectionName)
    const item = resolveLoopItem(
      collection,
      actions.loopNodeId,
      actions.keyMember,
      operation.instancePath
    )
    return operation.type === 'duplicate_node'
      ? buildLoopItemDuplicate(
          source,
          collection!,
          item,
          actions.keyMember,
          operationIndex,
          valueReplacements,
          generatedKeys
        )
      : buildLoopItemDelete(
          source,
          collection!,
          item,
          operationIndex,
          valueReplacements
        )
  }

  const allowed =
    operation.type === 'duplicate_node'
      ? node.templateActions.canDuplicate
      : node.templateActions.canDelete
  if (!allowed) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_READONLY',
      '当前节点不允许模板结构操作。'
    )
  }
  const conflicts = nestedReplacements(valueReplacements, node.sourceRange)
  if (operation.type === 'delete_node' && conflicts.length > 0) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT',
      '删除结构不能与其内部属性修改同时提交。'
    )
  }
  if (operation.type === 'delete_node') {
    return {
      sourceRange: node.sourceRange,
      targetRange: node.sourceRange,
      content: '',
      operationIndex,
    }
  }
  const raw = source.slice(node.sourceRange.start, node.sourceRange.end)
  const content = applyNestedReplacements(
    raw,
    node.sourceRange.start,
    conflicts
  )
  return {
    sourceRange: { start: node.sourceRange.end, end: node.sourceRange.end },
    targetRange: node.sourceRange,
    content: formatDuplicateInsertion(source, node.sourceRange, content),
    operationIndex,
    allowEmptyRange: true,
  }
}

/** 重新读取 script setup 中的本地数组范围，供结构操作定位完整对象。 */
function analyzeCollections(
  source: string
): Map<string, ScriptCollectionDefinition> {
  const parsed = parse(source, {
    filename: 'VisualEditPage.vue',
    sourceMap: false,
  })
  const script = parsed.descriptor.scriptSetup
  return script
    ? analyzeScriptCollections(
        script.content,
        script.loc.start.offset,
        script.lang || 'ts'
      )
    : new Map()
}

/** 深度优先查找 Manifest 节点。 */
function findNode(
  node: ReturnType<typeof analyzeVisualEditSfc>['root'],
  nodeId: string
): ReturnType<typeof analyzeVisualEditSfc>['root'] | undefined {
  if (node.nodeId === nodeId) return node
  for (const child of node.children) {
    const found = findNode(child, nodeId)
    if (found) return found
  }
  return undefined
}

/** 通过稳定 key 解析唯一循环数组项。 */
function resolveLoopItem(
  collection: ScriptCollectionDefinition | undefined,
  loopNodeId: string,
  keyMember: string,
  instancePath: VisualEditDuplicateNodeOperation['instancePath']
): ScriptCollectionItem {
  if (
    !collection?.editable ||
    !collection.arrayRange ||
    instancePath.length !== 1
  ) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_PATH_INVALID',
      '循环项结构操作需要可编辑本地数组和单层实例路径。'
    )
  }
  const segment = instancePath[0]
  if (segment.loopNodeId !== loopNodeId || segment.key === undefined) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_PATH_INVALID',
      '循环项结构操作必须使用匹配的稳定 key。'
    )
  }
  const matches = collection.items.filter(
    (item) => item.members.get(keyMember)?.value === segment.key
  )
  const indexed = matches.filter(
    (item) => segment.index === undefined || item.index === segment.index
  )
  if (indexed.length !== 1) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_KEY_INVALID',
      '稳定 key 未唯一定位循环数组项。'
    )
  }
  return indexed[0]
}

/** 构造循环项复制插入，并为副本生成唯一 key。 */
function buildLoopItemDuplicate(
  source: string,
  collection: ScriptCollectionDefinition,
  item: ScriptCollectionItem,
  keyMemberName: string,
  operationIndex: number,
  valueReplacements: SourceReplacement[],
  generatedKeys: Map<string, Set<string | number>>
): SourceReplacement {
  const keyMember = item.members.get(keyMemberName)
  if (!keyMember?.sourceRange || keyMember.value === undefined) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_KEY_INVALID',
      '循环项缺少可重写的稳定 key。'
    )
  }
  const conflicts = nestedReplacements(valueReplacements, item.sourceRange)
  const used =
    generatedKeys.get(collection.name) ||
    collectCollectionKeys(collection, keyMemberName)
  generatedKeys.set(collection.name, used)
  const nextKey = generateDuplicateKey(keyMember.value as string | number, used)
  used.add(nextKey)
  const clone = applyNestedReplacements(
    source.slice(item.sourceRange.start, item.sourceRange.end),
    item.sourceRange.start,
    [
      ...conflicts,
      {
        sourceRange: keyMember.sourceRange,
        content: JSON.stringify(nextKey),
        operationIndex,
      },
    ]
  )
  return {
    sourceRange: { start: item.sourceRange.end, end: item.sourceRange.end },
    targetRange: item.sourceRange,
    content: formatDuplicateInsertion(source, item.sourceRange, clone, true),
    operationIndex,
    allowEmptyRange: true,
  }
}

/** 构造循环项删除范围并正确吞掉一个相邻逗号。 */
function buildLoopItemDelete(
  source: string,
  collection: ScriptCollectionDefinition,
  item: ScriptCollectionItem,
  operationIndex: number,
  valueReplacements: SourceReplacement[]
): SourceReplacement {
  if (nestedReplacements(valueReplacements, item.sourceRange).length > 0) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT',
      '删除循环项不能与该项内部属性修改同时提交。'
    )
  }
  const position = collection.items.findIndex(
    (candidate) => candidate.index === item.index
  )
  const next = collection.items[position + 1]
  const previous = collection.items[position - 1]
  let range: VisualEditSourceRange
  if (next)
    range = { start: item.sourceRange.start, end: next.sourceRange.start }
  else if (previous)
    range = { start: previous.sourceRange.end, end: item.sourceRange.end }
  else {
    let end = item.sourceRange.end
    while (end < source.length && /\s/.test(source[end] || '')) end += 1
    if (source[end] === ',') end += 1
    range = { start: item.sourceRange.start, end }
  }
  return {
    sourceRange: range,
    targetRange: item.sourceRange,
    content: '',
    operationIndex,
  }
}

/** 收集数组中稳定 key 成员值，生成副本 key 时用于避重。 */
function collectCollectionKeys(
  collection: ScriptCollectionDefinition,
  keyMember: string
): Set<string | number> {
  return new Set(
    collection.items.flatMap((item) => {
      const value = item.members.get(keyMember)?.value
      return typeof value === 'string' ||
        (typeof value === 'number' && Number.isSafeInteger(value))
        ? [value]
        : []
    })
  )
}

/** 根据原 key 类型生成确定且唯一的新 key。 */
function generateDuplicateKey(
  original: string | number,
  used: Set<string | number>
): string | number {
  if (typeof original === 'string') {
    let candidate = `${original}-copy`
    let suffix = 2
    while (used.has(candidate)) candidate = `${original}-copy-${suffix++}`
    return candidate
  }
  const numeric = [...used].filter(
    (value): value is number => typeof value === 'number'
  )
  let candidate = numeric.length ? Math.max(...numeric) + 1 : original + 1
  if (!Number.isSafeInteger(candidate)) candidate = 0
  while (used.has(candidate)) candidate += 1
  return candidate
}

/** 读取完整落在目标范围内的属性替换。 */
function nestedReplacements(
  replacements: SourceReplacement[],
  range: VisualEditSourceRange
): SourceReplacement[] {
  return replacements.filter(
    (item) =>
      item.sourceRange.start >= range.start && item.sourceRange.end <= range.end
  )
}

/** 把基线坐标的内部属性修改应用到待复制源码片段。 */
function applyNestedReplacements(
  raw: string,
  offset: number,
  replacements: SourceReplacement[]
): string {
  return [...replacements]
    .sort((a, b) => b.sourceRange.start - a.sourceRange.start)
    .reduce(
      (result, item) =>
        result.slice(0, item.sourceRange.start - offset) +
        item.content +
        result.slice(item.sourceRange.end - offset),
      raw
    )
}

/** 保留同行或多行布局，把副本插入目标之后。 */
function formatDuplicateInsertion(
  source: string,
  range: VisualEditSourceRange,
  content: string,
  comma = false
): string {
  const lineStart = source.lastIndexOf('\n', range.start - 1) + 1
  const indent = source.slice(lineStart, range.start).match(/^\s*/)?.[0] || ''
  const lineEnd = source.indexOf('\n', range.end)
  const trailing = source.slice(
    range.end,
    lineEnd < 0 ? source.length : lineEnd
  )
  const separator = trailing.includes(',') || comma ? ',' : ''
  const lineOriented =
    source.slice(lineStart, range.start).trim() === '' &&
    trailing.replace(',', '').trim() === ''
  return lineOriented
    ? `${separator}\n${indent}${content}`
    : `${separator}${content}`
}

/** 禁止同批结构目标相同或互为祖先/后代。 */
function assertStructuralTargets(replacements: SourceReplacement[]): void {
  for (let index = 0; index < replacements.length; index += 1) {
    const current = replacements[index].targetRange!
    for (const previousReplacement of replacements.slice(0, index)) {
      const previous = previousReplacement.targetRange!
      if (current.start < previous.end && previous.start < current.end) {
        throw new VisualEditApplyError(
          422,
          'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT',
          '同批结构目标不能相同或互为祖先/后代。'
        )
      }
    }
  }
}

/**
 * 校验所有替换范围属于基线源码且互不重叠。
 */
function assertReplacementRanges(
  source: string,
  replacements: SourceReplacement[]
): void {
  const sorted = [...replacements].sort(
    (left, right) => left.sourceRange.start - right.sourceRange.start
  )
  for (let index = 0; index < sorted.length; index += 1) {
    const replacement = sorted[index]
    if (
      replacement.sourceRange.start < 0 ||
      replacement.sourceRange.end < replacement.sourceRange.start ||
      (!replacement.allowEmptyRange &&
        replacement.sourceRange.end === replacement.sourceRange.start) ||
      replacement.sourceRange.end > source.length
    ) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_SOURCE_RANGE_INVALID',
        '操作源码范围超出基线。'
      )
    }
    const previous = sorted[index - 1]
    if (previous && replacement.sourceRange.start < previous.sourceRange.end) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_REPLACEMENT_OVERLAP',
        `操作 ${previous.operationIndex} 与 ${replacement.operationIndex} 的源码范围重叠。`
      )
    }
  }
}

/**
 * 按偏移降序应用替换，保证每个范围仍以原始 canonicalSource 为坐标系。
 */
function applyReplacements(
  source: string,
  replacements: SourceReplacement[]
): string {
  return [...replacements]
    .sort(
      (left, right) =>
        right.sourceRange.start - left.sourceRange.start ||
        right.sourceRange.end -
          right.sourceRange.start -
          (left.sourceRange.end - left.sourceRange.start)
    )
    .reduce(
      (result, replacement) =>
        result.slice(0, replacement.sourceRange.start) +
        replacement.content +
        result.slice(replacement.sourceRange.end),
      source
    )
}

/**
 * 保存前后均拒绝 SFC 解析错误；warning 会进入响应 diagnostics。
 */
function assertManifestHasNoErrors(
  diagnostics: VisualEditDiagnostic[],
  message: string
): void {
  if (diagnostics.some((diagnostic) => diagnostic.severity === 'error')) {
    throw new VisualEditApplyError(422, 'PAGE_VISUAL_EDIT_SFC_INVALID', message)
  }
}

/**
 * 验证调用方声明的基线 hash，避免使用旧 Manifest 定位新源码。
 */
function assertSourceHash(source: string, expectedHash: string): void {
  if (hashSource(source) !== expectedHash) {
    throw new VisualEditApplyError(
      409,
      'PAGE_VISUAL_EDIT_SOURCE_HASH_MISMATCH',
      'sourceHash 与规范源码不一致。'
    )
  }
}

/**
 * 按 UTF-8 计算跨 Backend/Runtime 一致的 SHA-256。
 */
function hashSource(source: string): string {
  return createHash('sha256').update(source).digest('hex')
}
