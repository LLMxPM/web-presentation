/**
 * 文件功能：管理页面可视化编辑的本地待提交操作，负责目标去重、基准恢复和批量草稿更新。
 */

import { computed, shallowRef } from 'vue'

import type {
  PageVisualEditDraftChange,
  PageVisualEditInstancePathSegment,
  PageVisualEditOperation,
  PageVisualEditSetTailwindTokensOperation,
  PageVisualEditSetValueOperation,
  PageVisualEditTailwindTokenChange,
  PageVisualEditTarget,
  PageVisualEditValue,
} from '@/types/page-visual-edit'

/**
 * 创建不触碰 Runtime 画布的可视化编辑草稿状态。
 * @returns 待提交操作及其批量写入、移除和清空能力
 */
export function usePageVisualEditDraft() {
  const operationMap = shallowRef<Map<string, PageVisualEditOperation>>(new Map())

  const pendingOperations = computed<PageVisualEditOperation[]>(() => (
    [...operationMap.value.values()].map(cloneOperation)
  ))
  const pendingCount = computed(() => operationMap.value.size)
  const hasPendingChanges = computed(() => pendingCount.value > 0)

  /**
   * 批量写入文本/参数或 Tailwind 操作；同目标后写入覆盖先写入，恢复基准值时移除目标操作。
   * @param changes 同一次 UI 交互产生的一组草稿变更
   */
  function stageChanges(changes: readonly PageVisualEditDraftChange[]): void {
    if (changes.length === 0) return

    const nextMap = new Map(operationMap.value)
    changes.forEach(change => applyDraftChange(nextMap, change))
    operationMap.value = nextMap
  }

  /**
   * 写入单个文本或组件参数值。
   * @param target 可编辑绑定目标
   * @param value 新值
   * @param baselineValue 当前 artifact 对应的规范源码值
   */
  function setValue(
    target: PageVisualEditTarget,
    value: PageVisualEditValue,
    baselineValue: PageVisualEditValue | undefined,
  ): void {
    stageChanges([{ type: 'set_value', target, value, baselineValue }])
  }

  /**
   * 按 Tailwind 冲突组增量写入 class 变更。
   * @param target 可编辑 class 绑定目标
   * @param changes 本次涉及的样式组目标值
   * @param baselineChanges 当前 artifact 对应的样式组基准值
   */
  function setTailwindTokens(
    target: PageVisualEditTarget,
    changes: readonly PageVisualEditTailwindTokenChange[],
    baselineChanges: readonly PageVisualEditTailwindTokenChange[],
  ): void {
    stageChanges([{
      type: 'set_tailwind_tokens',
      target,
      changes: changes.map(change => ({ ...change })),
      baselineChanges: baselineChanges.map(change => ({ ...change })),
    }])
  }

  /**
   * 移除指定绑定实例的待提交操作。
   * @param target 可编辑绑定目标
   * @returns 是否实际移除了操作
   */
  function removeOperation(target: PageVisualEditTarget): boolean {
    const targetKey = buildTargetKey(target)
    if (!operationMap.value.has(targetKey)) return false

    const nextMap = new Map(operationMap.value)
    nextMap.delete(targetKey)
    operationMap.value = nextMap
    return true
  }

  /** 清空全部待提交操作。 */
  function clearOperations(): void {
    if (operationMap.value.size === 0) return
    operationMap.value = new Map()
  }

  /**
   * 读取指定绑定实例当前暂存的操作。
   * @param target 可编辑绑定目标
   * @returns 操作副本；未暂存时返回 null
   */
  function getOperation(target: PageVisualEditTarget): PageVisualEditOperation | null {
    const operation = operationMap.value.get(buildTargetKey(target))
    return operation ? cloneOperation(operation) : null
  }

  return {
    pendingOperations,
    pendingCount,
    hasPendingChanges,
    stageChanges,
    setValue,
    setTailwindTokens,
    removeOperation,
    clearOperations,
    getOperation,
  }
}

/**
 * 把一个草稿变更应用到目标 Map，确保同一 nodeId、bindingId 和 instancePath 只有一条操作。
 * @param operationMap 待更新的操作 Map
 * @param change 单个草稿变更
 */
function applyDraftChange(
  operationMap: Map<string, PageVisualEditOperation>,
  change: PageVisualEditDraftChange,
): void {
  const targetKey = buildTargetKey(change.target)

  if (change.type === 'set_value') {
    if (Object.is(change.value, change.baselineValue)) {
      operationMap.delete(targetKey)
      return
    }
    operationMap.set(targetKey, createSetValueOperation(change.target, change.value))
    return
  }

  const normalizedChanges = normalizeTailwindChanges(change.changes)
  const baselineByGroup = new Map(
    normalizeTailwindChanges(change.baselineChanges).map(item => [item.group, item.className ?? null]),
  )
  const existingOperation = operationMap.get(targetKey)
  const pendingByGroup = new Map<string, PageVisualEditTailwindTokenChange>(
    existingOperation?.type === 'set_tailwind_tokens'
      ? existingOperation.changes.map(item => [item.group, { ...item }])
      : [],
  )

  normalizedChanges.forEach((item) => {
    if ((item.className ?? null) === (baselineByGroup.get(item.group) ?? null)) {
      pendingByGroup.delete(item.group)
      return
    }
    pendingByGroup.set(item.group, item)
  })

  if (pendingByGroup.size === 0) {
    operationMap.delete(targetKey)
    return
  }
  operationMap.set(
    targetKey,
    createSetTailwindTokensOperation(change.target, [...pendingByGroup.values()]),
  )
}

/**
 * 创建值写入操作，并复制目标以隔离调用方后续修改。
 * @param target 可编辑绑定目标
 * @param value 新值
 * @returns 可提交操作
 */
function createSetValueOperation(
  target: PageVisualEditTarget,
  value: PageVisualEditValue,
): PageVisualEditSetValueOperation {
  return {
    type: 'set_value',
    ...cloneTarget(target),
    value,
  }
}

/**
 * 创建 Tailwind 写入操作，并复制冲突组变更与目标。
 * @param target 可编辑 class 绑定目标
 * @param changes 已按 group 归一化的变更
 * @returns 可提交操作
 */
function createSetTailwindTokensOperation(
  target: PageVisualEditTarget,
  changes: PageVisualEditTailwindTokenChange[],
): PageVisualEditSetTailwindTokensOperation {
  return {
    type: 'set_tailwind_tokens',
    ...cloneTarget(target),
    changes: changes.map(change => ({ ...change })),
  }
}

/**
 * 按目标的三个稳定维度生成草稿键；路径段显式区分“字段缺失”和 null。
 * @param target 可编辑绑定目标
 * @returns 可安全用于 Map 的稳定字符串
 */
function buildTargetKey(target: PageVisualEditTarget): string {
  return JSON.stringify([
    target.nodeId,
    target.bindingId,
    target.instancePath.map(segment => ({
      loopNodeId: segment.loopNodeId,
      key: Object.prototype.hasOwnProperty.call(segment, 'key')
        ? { present: true, value: segment.key }
        : { present: false },
      index: Object.prototype.hasOwnProperty.call(segment, 'index')
        ? { present: true, value: segment.index }
        : { present: false },
    })),
  ])
}

/**
 * 归一化 Tailwind 变更，裁剪字段并让同一 group 的最后一个值生效。
 * @param changes 原始样式组变更
 * @returns group 唯一且 className 显式为字符串或 null 的变更
 */
function normalizeTailwindChanges(
  changes: readonly PageVisualEditTailwindTokenChange[],
): PageVisualEditTailwindTokenChange[] {
  const changeByGroup = new Map<string, PageVisualEditTailwindTokenChange>()
  changes.forEach((change) => {
    const group = change.group.trim()
    const normalizedClassName = change.className?.trim() || null
    changeByGroup.set(group, { group, className: normalizedClassName })
  })
  return [...changeByGroup.values()]
}

/**
 * 复制操作，避免外部改写 computed 返回值时污染内部 Map。
 * @param operation 原始操作
 * @returns 独立操作副本
 */
function cloneOperation(operation: PageVisualEditOperation): PageVisualEditOperation {
  if (operation.type === 'set_value') {
    return {
      type: operation.type,
      ...cloneTarget(operation),
      value: operation.value,
    }
  }
  return {
    type: operation.type,
    ...cloneTarget(operation),
    changes: operation.changes.map(change => ({ ...change })),
  }
}

/**
 * 复制编辑目标和实例路径，保持可选 key/index 的缺省状态。
 * @param target 原始目标
 * @returns 独立目标副本
 */
function cloneTarget(target: PageVisualEditTarget): PageVisualEditTarget {
  return {
    nodeId: target.nodeId,
    bindingId: target.bindingId,
    instancePath: target.instancePath.map(cloneInstancePathSegment),
  }
}

/**
 * 复制一个循环实例路径段，并保持“key 或 index 至少存在一个”的联合类型约束。
 * @param segment 原始实例路径段
 * @returns 独立路径段副本
 */
function cloneInstancePathSegment(
  segment: PageVisualEditInstancePathSegment,
): PageVisualEditInstancePathSegment {
  if (segment.key !== undefined) {
    return {
      loopNodeId: segment.loopNodeId,
      key: segment.key,
      ...(segment.index !== undefined ? { index: segment.index } : {}),
    }
  }
  return {
    loopNodeId: segment.loopNodeId,
    index: segment.index,
  }
}
