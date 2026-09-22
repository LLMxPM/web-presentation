/**
 * 文件用途：校验富文本候选只能移除既有锁定标签外壳，不能修改或新增标签属性。
 */

import {
  extractRichTextLockedStructure,
  type VisualEditRichTextLockedNode,
} from '../source/rich-text'

interface FlatLockedNode {
  signature: string
  parentIndex: number | null
}

/** 判断候选是否仅移除了锁定外壳，并保持剩余标签的原始相对结构。 */
export function isRichTextLockedStructurePruning(baselineHtml: string, candidateHtml: string): boolean {
  const baseline = extractRichTextLockedStructure(baselineHtml)
  const candidate = extractRichTextLockedStructure(candidateHtml)
  return baseline !== null
    && candidate !== null
    && canContractLockedForest(flattenLockedNodes(baseline), flattenLockedNodes(candidate))
}

/** 把锁定森林展开为带父索引的前序序列。 */
function flattenLockedNodes(
  nodes: VisualEditRichTextLockedNode[],
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

/** 候选必须是基准锁定树删除任意节点、并提升其后代得到的有序诱导子树。 */
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
