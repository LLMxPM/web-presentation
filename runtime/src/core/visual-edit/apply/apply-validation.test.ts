/**
 * 文件用途：验证可视化编辑改写器拒绝伪造目录、错误定位、重复/重叠目标、类型绕过和非原子批次。
 */

import { describe, expect, it } from 'vitest'

import type { VisualEditBinding, VisualEditOperation, VisualEditTemplateNode } from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'
import { applyVisualEditOperations } from './apply-operations'

const SOURCE = `<script setup lang="ts">
const items = [
  { id: 'a', title: 'A', classes: 'block p-4 custom' },
  { id: 'b', title: 'B', classes: 'flex p-6 custom' },
]
</script>
<template>
  <main>
    <h1 class="block p-4 custom" title="旧值" :count="2">旧标题</h1>
    <article v-for="(item, index) in items" :key="item.id" :class="item.classes">
      <h2>{{ item.title }}</h2>
      <Card :title="item.title" />
    </article>
  </main>
</template>`

describe('applyVisualEditOperations validation', () => {
  it('set_value 不得修改 class，set_tailwind_tokens 不得修改非 class', () => {
    const fixture = buildFixture()
    expectApplyError([
      setValue(fixture.h1, fixture.staticClass, 'grid'),
    ], 'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID')
    expectApplyError([{
      type: 'set_tailwind_tokens',
      nodeId: fixture.h1.nodeId,
      bindingId: fixture.staticTitle.bindingId,
      instancePath: [],
      changes: [{ group: 'display', className: 'grid' }],
    }], 'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID')
  })

  it('应拒绝伪造 group、跨组 class、variant 和任意值', () => {
    const fixture = buildFixture()
    for (const changes of [
      [{ group: 'forged-group', className: 'grid' }],
      [{ group: 'display', className: 'p-4' }],
      [{ group: 'display', className: 'hover:grid' }],
      [{ group: 'width', className: 'w-[120px]' }],
    ]) {
      expect(() => apply([{
        type: 'set_tailwind_tokens',
        nodeId: fixture.h1.nodeId,
        bindingId: fixture.staticClass.bindingId,
        instancePath: [],
        changes,
      }])).toThrow()
    }
  })

  it('应拒绝错误 node、binding、key、index 和仅 index 数组定位', () => {
    const fixture = buildFixture()
    const base = setValue(fixture.h2, fixture.itemTitle, '新值', {
      loopNodeId: fixture.article.nodeId,
      key: 'b',
      index: 1,
    })
    expectApplyError([{ ...base, nodeId: 'node_forged' }], 'PAGE_VISUAL_EDIT_TARGET_NOT_FOUND')
    expectApplyError([{ ...base, bindingId: 'binding_forged' }], 'PAGE_VISUAL_EDIT_TARGET_NOT_FOUND')
    expectApplyError([{ ...base, instancePath: [{ loopNodeId: fixture.article.nodeId, key: 'missing', index: 1 }] }],
      'PAGE_VISUAL_EDIT_INSTANCE_KEY_INVALID')
    expectApplyError([{ ...base, instancePath: [{ loopNodeId: fixture.article.nodeId, key: 'b', index: 0 }] }],
      'PAGE_VISUAL_EDIT_INSTANCE_INDEX_MISMATCH')
    expectApplyError([{ ...base, instancePath: [{ loopNodeId: fixture.article.nodeId, index: 1 }] }],
      'PAGE_VISUAL_EDIT_INSTANCE_PATH_INVALID')
  })

  it('应拒绝同目标重复操作和不同 binding 指向同一源码范围', () => {
    const fixture = buildFixture()
    const operation = setValue(fixture.h2, fixture.itemTitle, '第一次', {
      loopNodeId: fixture.article.nodeId,
      key: 'b',
      index: 1,
    })
    expectApplyError([operation, { ...operation, value: '第二次' }], 'PAGE_VISUAL_EDIT_TARGET_DUPLICATED')

    const card = requireNode(fixture.manifest.root, 'Card')
    const cardTitle = requireBinding(card, binding => binding.expression === 'item.title')
    expectApplyError([
      operation,
      setValue(card, cardTitle, '另一处', {
        loopNodeId: fixture.article.nodeId,
        key: 'b',
        index: 1,
      }),
    ], 'PAGE_VISUAL_EDIT_REPLACEMENT_OVERLAP')
  })

  it('应严格校验 value 类型、基线 hash 与 no-op', () => {
    const fixture = buildFixture()
    const countBinding = requireBinding(fixture.h1, binding => binding.name === 'count')
    expectApplyError([setValue(fixture.h1, countBinding, '不是数字')], 'PAGE_VISUAL_EDIT_VALUE_TYPE_MISMATCH')
    expect(() => apply([setValue(fixture.h1, fixture.staticTitle, '新值')], '0'.repeat(64)))
      .toThrow(/sourceHash/)
    expectApplyError([{
      type: 'set_tailwind_tokens',
      nodeId: fixture.h1.nodeId,
      bindingId: fixture.staticClass.bindingId,
      instancePath: [],
      changes: [{ group: 'display', className: 'block' }],
    }], 'PAGE_VISUAL_EDIT_NO_CHANGES')
  })

  it('富文本应拒绝新增静态 class、非规范标签、危险属性、Vue 插值和错误 binding 类型', () => {
    const fixture = buildFixture()
    const richBinding = requireBinding(fixture.h1, binding => binding.kind === 'rich_text')
    expect(() => apply([{
      type: 'set_rich_text',
      nodeId: fixture.h1.nodeId,
      bindingId: richBinding.bindingId,
      instancePath: [],
      html: '<strong>重点</strong><br><em>补充</em>',
    }])).not.toThrow()
    for (const html of [
      '<span class="text-red-500">重点</span>',
      '<b>粗体</b>',
      '<strong style="color:red">重点</strong>',
      '<strong :class="tone">重点</strong>',
      '<script>bad()</script>',
      '{{ user.name }}',
      'x'.repeat(20_001),
    ]) {
      expect(() => apply([{
        type: 'set_rich_text',
        nodeId: fixture.h1.nodeId,
        bindingId: richBinding.bindingId,
        instancePath: [],
        html,
      }])).toThrow()
    }
    expectApplyError([{
      type: 'set_rich_text',
      nodeId: fixture.h1.nodeId,
      bindingId: fixture.staticTitle.bindingId,
      instancePath: [],
      html: '<strong>重点</strong>',
    }], 'PAGE_VISUAL_EDIT_OPERATION_TYPE_INVALID')
  })

  it('富文本锁定骨架应允许移除外壳并提升后代，同时拒绝修改、重排和错误重挂', () => {
    const source = '<template><p>开场<span class="tone"><strong class="weight">重点</strong>补充</span><em class="ending">结尾</em></p></template>'
    const manifest = analyzeVisualEditSfc(source, { modulePath: 'src/views/LockedRichText.vue' })
    const paragraph = requireNode(manifest.root, 'p')
    const binding = requireBinding(paragraph, item => item.kind === 'rich_text')
    const applyRichText = (html: string) => applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [{
        type: 'set_rich_text',
        nodeId: paragraph.nodeId,
        bindingId: binding.bindingId,
        instancePath: [],
        html,
      }],
    )

    expect(() => applyRichText(
      '新开场<span class="tone"><strong class="weight"><em>新重点</em></strong><br>补充</span><em class="ending">新结尾</em>',
    )).not.toThrow()
    expect(applyRichText('开场<em class="ending">结尾</em>').nextSource)
      .not.toContain('class="tone"')
    expect(applyRichText('仅保留普通文本').nextSource).not.toContain('class=')
    expect(() => applyRichText(
      '<strong class="weight">重点</strong><em class="ending">结尾</em>',
    )).not.toThrow()

    for (const html of [
      '<span class="changed"><strong class="weight">重点</strong></span><em class="ending">结尾</em>',
      '<span class="tone"><strong class="new">重点</strong></span><em class="ending">结尾</em>',
      '<em class="ending">结尾</em><span class="tone"><strong class="weight">重点</strong></span>',
      '<strong class="weight"><span class="tone">重点</span></strong><em class="ending">结尾</em>',
    ]) {
      try {
        applyRichText(html)
        throw new Error('期望锁定样式校验失败，但实际成功。')
      } catch (error) {
        expect(error).toMatchObject({ code: 'PAGE_VISUAL_EDIT_RICH_TEXT_STYLE_LOCKED' })
      }
    }
  })

  it('复杂标签应允许编辑全部静态文本，并锁定链接、组件参数、动态属性与内联样式', () => {
    const source = '<template><p>普通<a href="/docs" :class="tone">链接<Badge :level="level">组件文本</Badge></a><em style="color:red">强调</em></p></template>'
    const manifest = analyzeVisualEditSfc(source, { modulePath: 'src/views/ComplexRichText.vue' })
    const paragraph = requireNode(manifest.root, 'p')
    const binding = requireBinding(paragraph, item => item.kind === 'rich_text')
    const applyRichText = (html: string) => applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [{
        type: 'set_rich_text',
        nodeId: paragraph.nodeId,
        bindingId: binding.bindingId,
        instancePath: [],
        html,
      }],
    )

    expect(binding).toMatchObject({ editable: true, source: { kind: 'template-rich-text' } })
    expect(applyRichText(
      '新普通<a href="/docs" :class="tone"><strong>新链接</strong><Badge :level="level">新组件文本</Badge></a><em style="color:red">新强调</em>',
    ).nextSource).toContain('新组件文本')
    expect(() => applyRichText(
      '普通链接<Badge :level="level">组件文本</Badge><em style="color:red">强调</em>',
    )).not.toThrow()

    for (const html of [
      '普通<a href="/changed" :class="tone">链接<Badge :level="level">组件文本</Badge></a><em style="color:red">强调</em>',
      '普通<a href="/docs" :class="other">链接<Badge :level="level">组件文本</Badge></a><em style="color:red">强调</em>',
      '普通<a href="/docs" :class="tone">链接<Badge :level="changed">组件文本</Badge></a><em style="color:red">强调</em>',
      '普通<a href="/docs" :class="tone">链接<Badge :level="level">组件文本</Badge></a><em style="color:blue">强调</em>',
    ]) {
      try {
        applyRichText(html)
        throw new Error('期望复杂标签外壳校验失败，但实际成功。')
      } catch (error) {
        expect(error).toMatchObject({ code: 'PAGE_VISUAL_EDIT_RICH_TEXT_STYLE_LOCKED' })
      }
    }
  })

  it('批次任一操作失败时不得返回部分候选源码', () => {
    const fixture = buildFixture()
    const canonicalBefore = SOURCE
    const operations: VisualEditOperation[] = [
      setValue(fixture.h1, fixture.staticTitle, '本可成功的新值'),
      setValue(fixture.h2, fixture.itemTitle, '失败值', {
        loopNodeId: fixture.article.nodeId,
        key: 'missing',
        index: 1,
      }),
    ]

    expect(() => apply(operations)).toThrow()
    expect(SOURCE).toBe(canonicalBefore)
    expect(SOURCE).not.toContain('本可成功的新值')
  })

  it('结构操作应拒绝循环模板复制、伪造实例、重复数据项和源码范围冲突', () => {
    const fixture = buildFixture()
    expectApplyError([
      { type: 'duplicate_node', nodeId: fixture.article.nodeId, instancePath: [] },
    ], 'PAGE_VISUAL_EDIT_TARGET_READONLY')
    expectApplyError([{
      type: 'duplicate_node',
      nodeId: fixture.h2.nodeId,
      instancePath: [{ loopNodeId: fixture.article.nodeId, key: 'missing' }],
    }], 'PAGE_VISUAL_EDIT_INSTANCE_KEY_INVALID')
    expectApplyError([
      { type: 'duplicate_node', nodeId: fixture.article.nodeId, instancePath: [{ loopNodeId: fixture.article.nodeId, key: 'a' }] },
      { type: 'delete_node', nodeId: fixture.h2.nodeId, instancePath: [{ loopNodeId: fixture.article.nodeId, key: 'a' }] },
    ], 'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT')
    expectApplyError([
      setValue(fixture.h1, fixture.staticTitle, '冲突修改'),
      { type: 'delete_node', nodeId: fixture.h1.nodeId, instancePath: [] },
    ], 'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT')

    const nestedSource = '<template><main><section><span>内容</span></section></main></template>'
    const nestedManifest = analyzeVisualEditSfc(nestedSource, { modulePath: 'src/views/NestedStructure.vue' })
    const section = requireNode(nestedManifest.root, 'section')
    const span = requireNode(nestedManifest.root, 'span')
    expect(() => applyVisualEditOperations(nestedSource, nestedManifest.modulePath, nestedManifest.sourceHash, [
      { type: 'duplicate_node', nodeId: section.nodeId, instancePath: [] },
      { type: 'delete_node', nodeId: span.nodeId, instancePath: [] },
    ])).toThrow(expect.objectContaining({ code: 'PAGE_VISUAL_EDIT_STRUCTURE_CONFLICT' }))
  })
})

/**
 * 汇总测试常用节点与 binding。
 */
function buildFixture() {
  const manifest = analyzeVisualEditSfc(SOURCE, { modulePath: 'src/views/Validation.vue' })
  const h1 = requireNode(manifest.root, 'h1')
  const article = requireNode(manifest.root, 'article')
  const h2 = requireNode(manifest.root, 'h2')
  return {
    manifest,
    h1,
    article,
    h2,
    staticClass: requireBinding(h1, binding => binding.kind === 'class'),
    staticTitle: requireBinding(h1, binding => binding.name === 'title'),
    itemTitle: requireBinding(h2, binding => binding.expression === 'item.title'),
  }
}

/**
 * 使用当前 fixture 基线执行改写。
 */
function apply(operations: unknown, sourceHash?: string) {
  const manifest = analyzeVisualEditSfc(SOURCE, { modulePath: 'src/views/Validation.vue' })
  return applyVisualEditOperations(SOURCE, manifest.modulePath, sourceHash || manifest.sourceHash, operations)
}

/**
 * 断言稳定业务错误码。
 */
function expectApplyError(operations: unknown, code: string): void {
  try {
    apply(operations)
    throw new Error('期望 apply 失败，但实际成功。')
  } catch (error) {
    expect(error).toMatchObject({ code })
  }
}

/**
 * 构造 set_value 操作。
 */
function setValue(
  node: VisualEditTemplateNode,
  binding: VisualEditBinding,
  value: string,
  segment?: { loopNodeId: string; key?: string | number; index?: number },
): VisualEditOperation {
  return {
    type: 'set_value',
    nodeId: node.nodeId,
    bindingId: binding.bindingId,
    instancePath: segment ? [segment as { loopNodeId: string; key: string | number; index?: number }] : [],
    value,
  }
}

/**
 * 深度优先查找测试节点。
 */
function requireNode(root: VisualEditTemplateNode, tag: string): VisualEditTemplateNode {
  if (root.tag === tag) {
    return root
  }
  for (const child of root.children) {
    try {
      return requireNode(child, tag)
    } catch {
      // 继续查找同级节点。
    }
  }
  throw new Error(`测试节点不存在：${tag}`)
}

/**
 * 查找测试 binding。
 */
function requireBinding(
  node: VisualEditTemplateNode,
  predicate: (binding: VisualEditBinding) => boolean,
): VisualEditBinding {
  const binding = node.bindings.find(predicate)
  if (!binding) {
    throw new Error(`测试 binding 不存在：${node.tag}`)
  }
  return binding
}
