/**
 * 文件用途：根据 nodeId、bindingId 与单层稳定循环 key，把编辑操作解析为唯一源码替换位置。
 */

import type {
  VisualEditBinding,
  VisualEditInstancePathSegment,
  VisualEditLiteralValue,
  VisualEditLoopContext,
  VisualEditSfcManifest,
  VisualEditSourceRange,
  VisualEditTemplateNode,
  VisualEditValueType,
} from '../protocol'
import { VisualEditApplyError } from './errors'

export interface ResolvedVisualEditBinding {
  node: VisualEditTemplateNode
  binding: VisualEditBinding
  activeLoop?: VisualEditLoopContext
}

export interface ResolvedVisualEditLocation {
  sourceRange: VisualEditSourceRange
  currentValue?: VisualEditLiteralValue
  valueType: VisualEditValueType
}

/**
 * 查找并校验操作声明的 node/binding 归属，同时恢复其最近单层循环上下文。
 */
export function resolveVisualEditBinding(
  manifest: VisualEditSfcManifest,
  nodeId: string,
  bindingId: string
): ResolvedVisualEditBinding {
  const resolved = findBindingInTree(manifest.root, nodeId, bindingId)
  if (!resolved) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_NOT_FOUND',
      `未找到 nodeId=${nodeId}、bindingId=${bindingId} 的绑定。`
    )
  }
  if (!resolved.binding.editable) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_READONLY',
      `binding ${bindingId} 不可编辑：${resolved.binding.readonlyReason || 'UNKNOWN'}。`
    )
  }
  return resolved
}

/**
 * 根据 binding 来源解析模板字面量或脚本数组项位置。
 */
export function resolveVisualEditLocation(
  target: ResolvedVisualEditBinding,
  instancePath: VisualEditInstancePathSegment[]
): ResolvedVisualEditLocation {
  const source = target.binding.source
  if (source?.kind === 'template-literal') {
    if (instancePath.length !== 0) {
      throw invalidInstancePath(
        '模板字面量修改作用于源码模板，不接受循环实例路径。'
      )
    }
    return {
      sourceRange: target.binding.sourceRange,
      currentValue: toLiteralValue(target.binding.value),
      valueType: target.binding.valueType,
    }
  }
  if (source?.kind === 'template-rich-text') {
    if (instancePath.length !== 0) {
      throw invalidInstancePath(
        '模板富文本修改作用于源码模板，不接受循环实例路径。'
      )
    }
    return {
      sourceRange: target.binding.sourceRange,
      currentValue: toLiteralValue(target.binding.value),
      valueType: 'string',
    }
  }
  if (source?.kind !== 'script-array-item') {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_READONLY',
      '目标没有可写源码位置。'
    )
  }
  if (instancePath.length !== 1 || !target.activeLoop) {
    throw invalidInstancePath('数组成员修改必须提供单层稳定循环实例路径。')
  }
  const segment = instancePath[0]
  if (segment.loopNodeId !== target.activeLoop.loopNodeId) {
    throw invalidInstancePath(
      'instancePath.loopNodeId 与 binding 循环上下文不一致。'
    )
  }
  if (segment.key === undefined) {
    throw invalidInstancePath(
      '数组成员修改必须提供稳定字符串或数字 key，index 只能辅助校验。'
    )
  }
  const matchingLocations = source.locations.filter(
    (location) => location.key === segment.key
  )
  if (matchingLocations.length !== 1) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_KEY_INVALID',
      `稳定 key ${String(segment.key)} 未唯一定位数组项。`
    )
  }
  const location = matchingLocations[0]
  if (segment.index !== undefined && segment.index !== location.index) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_INSTANCE_INDEX_MISMATCH',
      '辅助 index 与稳定 key 定位结果不一致。'
    )
  }
  if (!location.editable || !location.sourceRange) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_READONLY',
      '目标数组成员没有可写字面量位置。'
    )
  }
  return {
    sourceRange: location.sourceRange,
    currentValue: location.value,
    valueType: inferLiteralValueType(location.value),
  }
}

/**
 * 深度优先查找 binding，并让节点自身 v-for 覆盖父循环上下文。
 */
function findBindingInTree(
  node: VisualEditTemplateNode,
  nodeId: string,
  bindingId: string,
  parentLoop?: VisualEditLoopContext
): ResolvedVisualEditBinding | undefined {
  const activeLoop = node.loopContext || parentLoop
  if (node.nodeId === nodeId) {
    const binding = node.bindings.find(
      (candidate) => candidate.bindingId === bindingId
    )
    return binding ? { node, binding, activeLoop } : undefined
  }
  for (const child of node.children) {
    const found = findBindingInTree(child, nodeId, bindingId, activeLoop)
    if (found) {
      return found
    }
  }
  return undefined
}

/**
 * 从实际数组项值推断精确类型，避免异构数组沿用第一项类型。
 */
function inferLiteralValueType(
  value: VisualEditLiteralValue | undefined
): VisualEditValueType {
  if (value === null) {
    return 'null'
  }
  if (typeof value === 'string') {
    return 'string'
  }
  if (typeof value === 'number') {
    return 'number'
  }
  if (typeof value === 'boolean') {
    return 'boolean'
  }
  return 'unknown'
}

/** JSON binding 不进入字段级替换；这里只保留基础字面量作为当前值。 */
function toLiteralValue(
  value: VisualEditBinding['value']
): VisualEditLiteralValue | undefined {
  return value === null ||
    ['string', 'number', 'boolean'].includes(typeof value)
    ? (value as VisualEditLiteralValue)
    : undefined
}

/**
 * 创建统一实例路径错误。
 */
function invalidInstancePath(message: string): VisualEditApplyError {
  return new VisualEditApplyError(
    422,
    'PAGE_VISUAL_EDIT_INSTANCE_PATH_INVALID',
    message
  )
}
