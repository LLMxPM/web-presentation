/**
 * 文件用途：按版本化 Tailwind 互斥组更新 class 字符串，同时保留未知、variant 与任意值 token。
 */

import type { VisualEditTailwindTokenChange } from '../protocol'
import { findVisualTailwindGroup } from '../tailwind/catalog'
import { VisualEditApplyError } from './errors'

/**
 * 应用受控 Tailwind 组变更。只移除目录中属于目标组的精确 class，不解释未知复杂 token。
 */
export function applyTailwindTokenChanges(
  currentClassValue: string,
  changes: VisualEditTailwindTokenChange[],
): string {
  let tokens = splitClassTokens(currentClassValue)
  for (const change of changes) {
    const group = findVisualTailwindGroup(change.group)
    if (!group) {
      throw new VisualEditApplyError(422, 'PAGE_VISUAL_EDIT_TAILWIND_GROUP_INVALID', `未知 Tailwind 组：${change.group}。`)
    }
    const groupClasses = new Set(group.options.map(option => option.className))
    if (change.className !== null && !groupClasses.has(change.className)) {
      throw new VisualEditApplyError(
        422,
        'PAGE_VISUAL_EDIT_TAILWIND_CLASS_INVALID',
        `Tailwind class ${change.className} 不属于组 ${change.group}。`,
      )
    }

    const firstGroupIndex = tokens.findIndex(token => groupClasses.has(token))
    tokens = tokens.filter(token => !groupClasses.has(token))
    if (change.className !== null) {
      const insertionIndex = firstGroupIndex >= 0 ? Math.min(firstGroupIndex, tokens.length) : tokens.length
      tokens.splice(insertionIndex, 0, change.className)
    }
  }
  return tokens.join(' ')
}

/**
 * 只按空白切分 class；目录外 token 不做语义解析并按原顺序保留。
 */
function splitClassTokens(value: string): string[] {
  return value.trim() ? value.trim().split(/\s+/) : []
}
