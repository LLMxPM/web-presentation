/**
 * 文件功能：验证页面可视化编辑草稿的目标去重、基准恢复、实例隔离和批量操作行为。
 */

import { describe, expect, it } from 'vitest'

import { usePageVisualEditDraft } from '@/composables/usePageVisualEditDraft'
import type { PageVisualEditTarget } from '@/types/page-visual-edit'

describe('usePageVisualEditDraft', () => {
  it('同一 nodeId、bindingId 和 instancePath 应只保留最后一次值操作', () => {
    const draft = usePageVisualEditDraft()
    const target = createTarget('b', 1)

    draft.setValue(target, '第一次', '原标题')
    draft.setValue({ ...target, instancePath: target.instancePath.map(item => ({ ...item })) }, '第二次', '原标题')

    expect(draft.pendingCount.value).toBe(1)
    expect(draft.pendingOperations.value).toEqual([{
      type: 'set_value',
      ...target,
      value: '第二次',
    }])
  })

  it('同一绑定的不同循环实例应分别保留操作', () => {
    const draft = usePageVisualEditDraft()

    draft.setValue(createTarget('a', 0), '标题 A+', '标题 A')
    draft.setValue(createTarget('b', 1), '标题 B+', '标题 B')

    expect(draft.pendingCount.value).toBe(2)
    expect(draft.pendingOperations.value.map(operation => operation.instancePath[0]?.key)).toEqual(['a', 'b'])
  })

  it('值恢复为 artifact 基准值时应移除已有操作', () => {
    const draft = usePageVisualEditDraft()
    const target = createTarget('b', 1)

    draft.setValue(target, '新标题', '原标题')
    draft.setValue(target, '原标题', '原标题')

    expect(draft.hasPendingChanges.value).toBe(false)
    expect(draft.getOperation(target)).toBeNull()
  })

  it('富文本应按目标去重，并在恢复规范化基准时移除操作', () => {
    const draft = usePageVisualEditDraft()
    const target = { nodeId: 'node-paragraph', bindingId: 'binding-rich', instancePath: [] }

    draft.setRichText(target, '<strong>新内容</strong>', '原标题')
    draft.setRichText(target, '<em>最终内容</em>', '原标题')
    expect(draft.pendingOperations.value).toEqual([{
      type: 'set_rich_text',
      ...target,
      html: '<em>最终内容</em>',
    }])

    draft.setRichText(target, '原标题', '原标题')
    expect(draft.pendingOperations.value).toEqual([])
  })

  it('Tailwind changes 应按 group 去重合并，并在各组恢复基准后移除操作', () => {
    const draft = usePageVisualEditDraft()
    const target = createTarget('b', 1, 'binding-class')
    const baselineChanges = [
      { group: 'padding', className: 'p-6' },
      { group: 'background', className: 'bg-white' },
    ]

    draft.setTailwindTokens(target, [
      { group: ' padding ', className: 'p-7' },
      { group: 'padding', className: ' p-8 ' },
    ], baselineChanges)
    draft.setTailwindTokens(target, [
      { group: 'background', className: 'bg-slate-50' },
    ], baselineChanges)
    expect(draft.getOperation(target)).toMatchObject({
      type: 'set_tailwind_tokens',
      changes: [
        { group: 'padding', className: 'p-8' },
        { group: 'background', className: 'bg-slate-50' },
      ],
    })

    draft.setTailwindTokens(target, [
      { group: 'padding', className: 'p-6' },
    ], baselineChanges)
    expect(draft.getOperation(target)).toMatchObject({
      changes: [{ group: 'background', className: 'bg-slate-50' }],
    })

    draft.setTailwindTokens(target, [
      { group: 'background', className: 'bg-white' },
    ], baselineChanges)

    expect(draft.pendingCount.value).toBe(0)
  })

  it('应在一次批量更新中同时处理 set_value 和 set_tailwind_tokens', () => {
    const draft = usePageVisualEditDraft()
    const titleTarget = createTarget('b', 1)
    const classTarget = createTarget('b', 1, 'binding-class')

    draft.stageChanges([
      {
        type: 'set_value',
        target: titleTarget,
        value: '新标题',
        baselineValue: '原标题',
      },
      {
        type: 'set_tailwind_tokens',
        target: classTarget,
        changes: [
          { group: 'padding', className: 'p-7' },
          { group: 'padding', className: ' p-8 ' },
          { group: 'background' },
        ],
        baselineChanges: [
          { group: 'padding', className: 'p-6' },
          { group: 'background', className: null },
        ],
      },
    ])

    expect(draft.pendingOperations.value).toEqual([
      {
        type: 'set_value',
        ...titleTarget,
        value: '新标题',
      },
      {
        type: 'set_tailwind_tokens',
        ...classTarget,
        changes: [{ group: 'padding', className: 'p-8' }],
      },
    ])
  })

  it('同一目标在批处理中恢复基准值时应删除批处理中较早的修改', () => {
    const draft = usePageVisualEditDraft()
    const target = createTarget('b', 1)

    draft.stageChanges([
      { type: 'set_value', target, value: '临时标题', baselineValue: '原标题' },
      { type: 'set_value', target, value: '原标题', baselineValue: '原标题' },
    ])

    expect(draft.pendingOperations.value).toEqual([])
  })

  it('应支持按目标移除操作并清空草稿', () => {
    const draft = usePageVisualEditDraft()
    const firstTarget = createTarget('a', 0)
    const secondTarget = createTarget('b', 1)
    draft.setValue(firstTarget, '标题 A+', '标题 A')
    draft.setValue(secondTarget, '标题 B+', '标题 B')

    expect(draft.removeOperation(firstTarget)).toBe(true)
    expect(draft.removeOperation(firstTarget)).toBe(false)
    expect(draft.pendingCount.value).toBe(1)

    draft.clearOperations()

    expect(draft.pendingCount.value).toBe(0)
    expect(draft.hasPendingChanges.value).toBe(false)
  })

  it('同一节点实例的复制和删除应互相覆盖并支持撤销', () => {
    const draft = usePageVisualEditDraft()
    const target = {
      nodeId: 'node-card',
      instancePath: [{ loopNodeId: 'loop-items', key: 'b', index: 1 }],
    }

    draft.setStructuralOperation('duplicate_node', target)
    draft.setStructuralOperation('delete_node', target)

    expect(draft.pendingOperations.value).toEqual([{ type: 'delete_node', ...target }])
    expect(draft.removeStructuralOperation(target)).toBe(true)
    expect(draft.pendingOperations.value).toEqual([])
  })

  it('整块 JSON 应按 sourceId 去重、深拷贝并在恢复基准时移除', () => {
    const draft = usePageVisualEditDraft()
    const baseline = ['第一项', { label: '第二项' }]
    const next = ['新值', { label: '第二项' }]

    draft.setJson('source_benefits', next, baseline)
    ;(next[1] as { label: string }).label = '外部改写'
    expect(draft.pendingOperations.value).toEqual([{
      type: 'set_json',
      sourceId: 'source_benefits',
      value: ['新值', { label: '第二项' }],
    }])

    draft.setJson('source_benefits', baseline, baseline)
    expect(draft.pendingOperations.value).toEqual([])
  })
})

/**
 * 创建测试用循环实例目标。
 * @param key items 中的稳定 key
 * @param index 当前运行时索引
 * @param bindingId 绑定标识
 * @returns 可用于草稿去重的目标
 */
function createTarget(
  key: string,
  index: number,
  bindingId = 'binding-title',
): PageVisualEditTarget {
  return {
    nodeId: 'node-card',
    bindingId,
    instancePath: [{ loopNodeId: 'loop-items', key, index }],
  }
}
