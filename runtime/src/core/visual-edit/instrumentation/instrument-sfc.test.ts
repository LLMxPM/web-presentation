/**
 * 文件用途：验证可视化编辑派生源码插桩不污染 canonical 坐标，并覆盖循环 marker 与保留属性冲突边界。
 */

import { createHash } from 'node:crypto'

import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

import type { VisualEditTemplateNode } from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'
import { instrumentVisualEditSfc, VisualEditInstrumentationError } from './instrument-sfc'
import {
  VISUAL_EDIT_LOOP_ATTRIBUTE,
  VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE,
  VISUAL_EDIT_LOOP_KEY_ATTRIBUTE,
  VISUAL_EDIT_NODE_ATTRIBUTE,
} from './markers'

describe('instrumentVisualEditSfc', () => {
  it('应为字符串/整数 key 的单层循环及后代注入实例 marker，且 canonical hash/range 保持不变', () => {
    const source = `<script setup lang="ts">
const stringItems = [{ id: 'alpha', title: '字符串项' }]
const numberItems = [{ id: 7, title: '数字项' }]
</script>
<template>
  <section>
    <article v-for="(item, index) in stringItems" :key="item.id">
      <h3>{{ item.title }}</h3>
    </article>
    <p v-for="entry in numberItems" :key="entry.id">{{ entry.title }}</p>
    <Card />
  </section>
</template>`
    const manifest = analyzeVisualEditSfc(source, { modulePath: 'src/views/Instrumented.vue' })
    const article = findNode(manifest.root, 'article')
    const heading = findNode(manifest.root, 'h3')
    const paragraph = findNode(manifest.root, 'p')
    const card = findNode(manifest.root, 'Card')
    const instrumentedSource = instrumentVisualEditSfc(source, manifest)

    expect(manifest.sourceHash).toBe(hashSource(source))
    expect(instrumentedSource).not.toBe(source)
    expect(openingTag(instrumentedSource, 'article')).toContain(`${VISUAL_EDIT_NODE_ATTRIBUTE}="${article?.nodeId}"`)
    expect(openingTag(instrumentedSource, 'article')).toContain(`${VISUAL_EDIT_LOOP_ATTRIBUTE}="${article?.nodeId}"`)
    expect(openingTag(instrumentedSource, 'article')).toContain(
      `:${VISUAL_EDIT_LOOP_KEY_ATTRIBUTE}="JSON.stringify(item.id)"`,
    )
    expect(openingTag(instrumentedSource, 'article')).toContain(`:${VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE}="index"`)
    expect(openingTag(instrumentedSource, 'h3')).toContain(`${VISUAL_EDIT_NODE_ATTRIBUTE}="${heading?.nodeId}"`)
    expect(openingTag(instrumentedSource, 'h3')).toContain(`${VISUAL_EDIT_LOOP_ATTRIBUTE}="${article?.nodeId}"`)
    expect(openingTag(instrumentedSource, 'p')).toContain(`${VISUAL_EDIT_NODE_ATTRIBUTE}="${paragraph?.nodeId}"`)
    expect(openingTag(instrumentedSource, 'p')).toContain(
      `:${VISUAL_EDIT_LOOP_KEY_ATTRIBUTE}="JSON.stringify(entry.id)"`,
    )
    expect(openingTag(instrumentedSource, 'Card')).toContain(`${VISUAL_EDIT_NODE_ATTRIBUTE}="${card?.nodeId}"`)

    for (const node of flattenNodes(manifest.root)) {
      expect(source.slice(node.sourceRange.start, node.sourceRange.end)).toBeTruthy()
      for (const binding of node.bindings) {
        expect(source.slice(binding.sourceRange.start, binding.sourceRange.end)).toBeTruthy()
      }
    }
    expect(parse(instrumentedSource, { filename: manifest.modulePath }).errors).toEqual([])
  })

  it('不稳定循环与嵌套循环应仅保留 node marker，不注入实例 marker', () => {
    const source = `<script setup lang="ts">
const groups = [{ id: 'group', items: [{ id: 'item', title: '标题' }] }]
const unstable = [{ title: '无 key' }]
</script>
<template>
  <main>
    <article v-for="group in groups" :key="group.id">
      <span v-for="item in group.items" :key="item.id"><b>{{ item.title }}</b></span>
    </article>
    <p v-for="entry in unstable">{{ entry.title }}</p>
  </main>
</template>`
    const manifest = analyzeVisualEditSfc(source, { modulePath: 'src/views/UnsafeLoops.vue' })
    const instrumentedSource = instrumentVisualEditSfc(source, manifest)
    const articleTag = openingTag(instrumentedSource, 'article')
    const nestedTag = openingTag(instrumentedSource, 'span')
    const nestedChildTag = openingTag(instrumentedSource, 'b')
    const unstableTag = openingTag(instrumentedSource, 'p')

    expect(articleTag).toContain(VISUAL_EDIT_LOOP_ATTRIBUTE)
    for (const tag of [nestedTag, nestedChildTag, unstableTag]) {
      expect(tag).toContain(VISUAL_EDIT_NODE_ATTRIBUTE)
      expect(tag).not.toContain(VISUAL_EDIT_LOOP_ATTRIBUTE)
      expect(tag).not.toContain(VISUAL_EDIT_LOOP_KEY_ATTRIBUTE)
    }
  })

  it.each([
    `<template><div ${VISUAL_EDIT_NODE_ATTRIBUTE}="forged">内容</div></template>`,
    `<template><div :${VISUAL_EDIT_LOOP_KEY_ATTRIBUTE}="'forged'">内容</div></template>`,
    '<template><div v-bind="attrs">内容</div></template>',
    '<template><div :[dynamicName]="value">内容</div></template>',
  ])('canonical 源码可能覆盖保留 marker 时应 fail closed', (source) => {
    const manifest = analyzeVisualEditSfc(source, { modulePath: 'src/views/Collision.vue' })

    expect(() => instrumentVisualEditSfc(source, manifest)).toThrowError(VisualEditInstrumentationError)
    expect(() => instrumentVisualEditSfc(source, manifest)).toThrowError(/保留属性/)
  })
})

/**
 * 取得指定标签的第一个 opening tag。
 */
function openingTag(source: string, tag: string): string {
  const match = source.match(new RegExp(`<${tag}\\b[^>]*>`))
  if (!match) {
    throw new Error(`未找到 ${tag} opening tag。`)
  }
  return match[0]
}

/**
 * 深度优先查找指定标签节点。
 */
function findNode(root: VisualEditTemplateNode, tag: string): VisualEditTemplateNode | undefined {
  return flattenNodes(root).find(node => node.tag === tag)
}

/**
 * 展开 Manifest 节点树。
 */
function flattenNodes(root: VisualEditTemplateNode): VisualEditTemplateNode[] {
  return [root, ...root.children.flatMap(flattenNodes)]
}

/**
 * 按协议计算 UTF-8 canonical source hash。
 */
function hashSource(source: string): string {
  return createHash('sha256').update(source).digest('hex')
}
