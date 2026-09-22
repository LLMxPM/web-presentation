/**
 * 文件用途：严格校验页面可视化编辑操作结构，避免额外字段、重复目标和宽松 JSON 类型进入改写器。
 */

import type {
  VisualEditInstancePathSegment,
  VisualEditOperation,
  VisualEditTailwindTokenChange,
} from '../protocol'
import { VisualEditApplyError } from './errors'
import { normalizeRichTextFragment } from '../source/rich-text'
import { validateVisualEditJsonValue } from '../source/json-literal'

const MAX_OPERATIONS = 100
const MAX_TAILWIND_CHANGES = 50
const IDENTIFIER_PATTERN = /^[A-Za-z0-9_.:-]{1,128}$/
const GROUP_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/

/**
 * 校验未知操作数组并返回协议类型；同一实例 binding 不允许重复写入。
 */
export function validateVisualEditOperations(
  input: unknown
): VisualEditOperation[] {
  if (
    !Array.isArray(input) ||
    input.length === 0 ||
    input.length > MAX_OPERATIONS
  ) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_OPERATIONS_INVALID',
      'operations 数量必须在 1 到 100 之间。'
    )
  }
  const operations = input.map(validateOperation)
  const targetKeys = operations.map(buildOperationTargetKey)
  if (new Set(targetKeys).size !== targetKeys.length) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_TARGET_DUPLICATED',
      '同一批次不能重复修改同一个实例绑定。'
    )
  }
  return operations
}

/**
 * 校验单个 discriminated operation。
 */
function validateOperation(input: unknown): VisualEditOperation {
  if (!isRecord(input)) {
    throw invalidOperation('每个 operation 必须是 JSON 对象。')
  }
  if (input.type === 'set_value') {
    assertExactFields(input, [
      'type',
      'nodeId',
      'bindingId',
      'instancePath',
      'value',
    ])
    const instancePath = validateCommonFields(input)
    if (!hasOwn(input, 'value') || !isLiteralValue(input.value)) {
      throw invalidOperation('set_value.value 必须是 JSON 基本值。')
    }
    return { ...input, instancePath } as unknown as VisualEditOperation
  }
  if (input.type === 'set_json') {
    assertExactFields(input, ['type', 'sourceId', 'value'])
    if (
      typeof input.sourceId !== 'string' ||
      !IDENTIFIER_PATTERN.test(input.sourceId)
    ) {
      throw invalidOperation('set_json.sourceId 格式不合法。')
    }
    try {
      validateVisualEditJsonValue(input.value)
    } catch (error) {
      throw invalidOperation(
        error instanceof Error
          ? error.message
          : 'set_json.value 不是合法 JSON。'
      )
    }
    return input as unknown as VisualEditOperation
  }
  if (input.type === 'set_tailwind_tokens') {
    assertExactFields(input, [
      'type',
      'nodeId',
      'bindingId',
      'instancePath',
      'changes',
    ])
    const instancePath = validateCommonFields(input)
    const changes = validateTailwindChanges(input.changes)
    return { ...input, instancePath, changes } as unknown as VisualEditOperation
  }
  if (input.type === 'set_rich_text') {
    assertExactFields(input, [
      'type',
      'nodeId',
      'bindingId',
      'instancePath',
      'html',
    ])
    const instancePath = validateCommonFields(input)
    if (typeof input.html !== 'string') {
      throw invalidOperation('set_rich_text.html 必须是字符串。')
    }
    const normalized = normalizeRichTextFragment(input.html)
    if (normalized === null || normalized !== input.html) {
      throw invalidOperation('set_rich_text.html 必须是规范化的受限富文本。')
    }
    return { ...input, instancePath } as unknown as VisualEditOperation
  }
  if (input.type === 'duplicate_node' || input.type === 'delete_node') {
    assertExactFields(input, ['type', 'nodeId', 'instancePath'])
    if (
      typeof input.nodeId !== 'string' ||
      !IDENTIFIER_PATTERN.test(input.nodeId)
    ) {
      throw invalidOperation('nodeId 格式不合法。')
    }
    return {
      type: input.type,
      nodeId: input.nodeId,
      instancePath: normalizeInstancePath(input.instancePath),
    }
  }
  throw invalidOperation('operation.type 不受支持。')
}

/**
 * 校验 node、binding 与实例路径公共字段。
 */
function validateCommonFields(
  input: Record<string, unknown>
): VisualEditInstancePathSegment[] {
  if (
    typeof input.nodeId !== 'string' ||
    !IDENTIFIER_PATTERN.test(input.nodeId)
  ) {
    throw invalidOperation('nodeId 格式不合法。')
  }
  if (
    typeof input.bindingId !== 'string' ||
    !IDENTIFIER_PATTERN.test(input.bindingId)
  ) {
    throw invalidOperation('bindingId 格式不合法。')
  }
  return normalizeInstancePath(input.instancePath)
}

/**
 * 首版仅接受单层循环实例；每段必须至少包含稳定 key 或 index。
 */
function normalizeInstancePath(
  input: unknown
): VisualEditInstancePathSegment[] {
  if (!Array.isArray(input) || input.length > 1) {
    throw invalidOperation('instancePath 首版仅支持零层或单层循环。')
  }
  return input.map((segment) => {
    if (!isRecord(segment)) {
      throw invalidOperation('instancePath 段必须是 JSON 对象。')
    }
    assertExactFields(segment, ['loopNodeId', 'key', 'index'], true)
    if (
      typeof segment.loopNodeId !== 'string' ||
      !IDENTIFIER_PATTERN.test(segment.loopNodeId)
    ) {
      throw invalidOperation('instancePath.loopNodeId 格式不合法。')
    }
    const keyValid =
      typeof segment.key === 'string' ||
      (typeof segment.key === 'number' && Number.isSafeInteger(segment.key))
    const indexValid =
      typeof segment.index === 'number' &&
      Number.isInteger(segment.index) &&
      segment.index >= 0
    if (!keyValid && !indexValid) {
      throw invalidOperation(
        'instancePath 每段至少需要字符串/整数 key 或非负 index。'
      )
    }
    if (keyValid) {
      return {
        loopNodeId: segment.loopNodeId as string,
        key: segment.key as string | number,
        ...(indexValid ? { index: segment.index as number } : {}),
      }
    }
    return {
      loopNodeId: segment.loopNodeId as string,
      index: segment.index as number,
    }
  })
}

/**
 * 校验 Tailwind 组变更，并拒绝一个操作内重复组。
 */
function validateTailwindChanges(
  input: unknown
): VisualEditTailwindTokenChange[] {
  if (
    !Array.isArray(input) ||
    input.length === 0 ||
    input.length > MAX_TAILWIND_CHANGES
  ) {
    throw invalidOperation('changes 数量必须在 1 到 50 之间。')
  }
  const changes = input.map((change) => {
    if (!isRecord(change)) {
      throw invalidOperation('Tailwind change 必须是 JSON 对象。')
    }
    assertExactFields(change, ['group', 'className'])
    if (typeof change.group !== 'string' || !GROUP_PATTERN.test(change.group)) {
      throw invalidOperation('Tailwind group 格式不合法。')
    }
    if (
      change.className !== null &&
      (typeof change.className !== 'string' ||
        change.className.length === 0 ||
        change.className.length > 128 ||
        /\s/.test(change.className))
    ) {
      throw invalidOperation('className 必须是单个 class 或 null。')
    }
    return change as unknown as VisualEditTailwindTokenChange
  })
  const groups = changes.map((change) => change.group)
  if (new Set(groups).size !== groups.length) {
    throw invalidOperation('同一个 Tailwind 操作中 group 不能重复。')
  }
  return changes
}

/**
 * 构造忽略辅助 index 的目标键；稳定 key 相同即视为同一数组实例。
 */
function buildOperationTargetKey(operation: VisualEditOperation): string {
  if (operation.type === 'set_json')
    return JSON.stringify(['json', operation.sourceId])
  const instancePath = operation.instancePath.map((segment) => ({
    loopNodeId: segment.loopNodeId,
    key: segment.key,
    index: segment.key === undefined ? segment.index : undefined,
  }))
  return 'bindingId' in operation
    ? JSON.stringify([operation.nodeId, operation.bindingId, instancePath])
    : JSON.stringify([operation.type, operation.nodeId, instancePath])
}

/**
 * 拒绝未声明字段，optional=true 时允许白名单字段缺失。
 */
function assertExactFields(
  input: Record<string, unknown>,
  fields: string[],
  optional = false
): void {
  const allowed = new Set(fields)
  const unexpected = Object.keys(input).filter((key) => !allowed.has(key))
  const missing = optional ? [] : fields.filter((key) => !hasOwn(input, key))
  if (unexpected.length > 0 || missing.length > 0) {
    throw invalidOperation('operation 包含额外字段或缺少必需字段。')
  }
}

/**
 * 兼容当前 ES target 的自有字段检查。
 */
function hasOwn(input: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(input, key)
}

/**
 * 判断值是否为线协议允许的 JSON 基本值。
 */
function isLiteralValue(value: unknown): boolean {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value))
  )
}

/**
 * 判断未知值是否为对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

/**
 * 创建统一操作结构错误。
 */
function invalidOperation(message: string): VisualEditApplyError {
  return new VisualEditApplyError(
    422,
    'PAGE_VISUAL_EDIT_OPERATION_INVALID',
    message
  )
}
