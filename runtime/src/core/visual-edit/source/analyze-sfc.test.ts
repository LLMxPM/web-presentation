/**
 * 文件用途：验证页面可视化编辑 SFC 分析器的稳定定位、数组循环映射和动态表达式只读边界。
 */

import { describe, expect, it } from 'vitest'

import type { VisualEditBinding, VisualEditTemplateNode } from '../protocol'
import { analyzeVisualEditSfc } from './analyze-sfc'

describe('analyzeVisualEditSfc', () => {
  it('应把 const items 第二项映射到 v-for 文本与 class 绑定', () => {
    const source = `<script setup lang="ts">
const items = [
  { id: 'first', title: '第一项', classes: 'rounded p-4' },
  { id: 'second', title: '第二项', classes: 'rounded p-6' },
]
</script>

<template>
  <section class="grid gap-4">
    <article
      v-for="(item, index) in items"
      :key="item.id"
      :class="item.classes"
    >
      <h3>{{ item.title }}</h3>
    </article>
  </section>
</template>`

    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/Items.vue',
    })
    const repeatedNode = findNode(manifest.root, 'article')
    const titleNode = findNode(manifest.root, 'h3')
    const titleBinding = titleNode?.bindings.find(
      (binding) => binding.kind === 'text'
    )
    const classBinding = repeatedNode?.bindings.find(
      (binding) => binding.kind === 'class'
    )

    expect(manifest.diagnostics).toEqual([])
    expect(manifest.tailwindCatalog).toMatchObject({
      version: 1,
      groups: expect.arrayContaining([
        expect.objectContaining({ key: 'display' }),
        expect.objectContaining({ key: 'text-color' }),
      ]),
    })
    expect(repeatedNode?.loopContext).toMatchObject({
      sourceBinding: 'items',
      itemAlias: 'item',
      indexAlias: 'index',
      keyMember: 'id',
      editable: true,
    })
    expect(repeatedNode?.templateActions).toEqual({
      canDuplicate: false,
      canDelete: true,
    })
    expect(repeatedNode?.loopItemActions).toMatchObject({
      canDuplicate: true,
      canDelete: true,
      collectionName: 'items',
      keyMember: 'id',
      instances: [
        { index: 0, key: 'first' },
        { index: 1, key: 'second' },
      ],
    })
    expect(titleNode?.templateActions).toMatchObject({
      canDuplicate: false,
      canDelete: false,
      readonlyReason: 'STRUCTURE_LOOP_INSTANCE_REQUIRED',
    })
    expect(titleBinding).toMatchObject({
      expression: 'item.title',
      editable: true,
      source: {
        kind: 'script-array-item',
        collectionName: 'items',
        collectionKind: 'const-array',
        member: 'title',
        keyMember: 'id',
        locations: [
          { index: 0, key: 'first', value: '第一项', editable: true },
          { index: 1, key: 'second', value: '第二项', editable: true },
        ],
      },
    })
    expect(classBinding).toMatchObject({
      expression: 'item.classes',
      editable: true,
      source: {
        kind: 'script-array-item',
        locations: [
          { index: 0, key: 'first', value: 'rounded p-4' },
          { index: 1, key: 'second', value: 'rounded p-6' },
        ],
      },
    })

    const secondLocation = getScriptLocations(titleBinding)[1]
    expect(
      source.slice(
        secondLocation?.sourceRange?.start,
        secondLocation?.sourceRange?.end
      )
    ).toBe("'第二项'")

    const secondManifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/Items.vue',
    })
    expect(collectIds(secondManifest.root)).toEqual(collectIds(manifest.root))
  })

  it.each([
    ['ref', 'ref-array'],
    ['reactive', 'reactive-array'],
  ])('应支持 %s 包裹的数组字面量', (wrapper, expectedKind) => {
    const source = `<script setup lang="ts">
const items = ${wrapper}([{ id: 1, title: '标题' }])
</script>
<template><p v-for="item in items" :key="item.id">{{ item.title }}</p></template>`

    const manifest = analyzeVisualEditSfc(source, {
      modulePath: `src/views/${wrapper}.vue`,
    })
    const binding = findNode(manifest.root, 'p')?.bindings.find(
      (item) => item.kind === 'text'
    )

    expect(binding).toMatchObject({
      editable: true,
      source: {
        collectionKind: expectedKind,
        locations: [{ index: 0, key: 1, value: '标题', editable: true }],
      },
    })
  })

  it.each([
    ["const items = [{ id: 'a', title: 'A' }]", ''],
    [
      "const items = ref([{ id: 'same', title: 'A' }, { id: 'same', title: 'B' }])",
      ':key="item.id"',
    ],
    ["const items = reactive([{ id: true, title: 'A' }])", ':key="item.id"'],
    ["const items = reactive([{ id: 1.5, title: 'A' }])", ':key="item.id"'],
    ["const items = [{ id: createId(), title: 'A' }]", ':key="item.id"'],
    [
      "const items = reactive([{ id: 'a', title: 'A' }])",
      ':key="item.missing"',
    ],
    ["const items = [{ id: 'a', title: 'A' }]", ':key="index"'],
  ])(
    '不稳定 key 应让循环和成员绑定只读：%s / %s',
    (declaration, keyAttribute) => {
      const source = `<script setup lang="ts">${declaration}</script>
<template><p v-for="(item, index) in items" ${keyAttribute}>{{ item.title }}</p></template>`

      const manifest = analyzeVisualEditSfc(source, {
        modulePath: 'src/views/UnsafeKey.vue',
      })
      const node = findNode(manifest.root, 'p')
      const binding = node?.bindings.find((item) => item.kind === 'text')

      expect(node?.loopContext).toMatchObject({
        editable: false,
        readonlyReason: 'LOOP_MEMBER_UNSUPPORTED',
      })
      expect(binding).toMatchObject({
        editable: false,
        readonlyReason: 'LOOP_MEMBER_UNSUPPORTED',
      })
    }
  )

  it('应允许静态文本、class 和 props，并把 computed、map 与调用表达式标为只读', () => {
    const source = `<script setup lang="ts">
const computedItems = computed(() => [{ id: 'a', title: 'A' }])
const mappedItems = rawItems.map(item => ({ ...item }))
</script>
<template>
  <Card class="rounded p-4" title="静态标题" :count="2">静态文本</Card>
  <div v-for="item in computedItems" :key="item.id">{{ item.title }}</div>
  <div v-for="entry in mappedItems" :key="entry.id">{{ format(entry.title) }}</div>
</template>`

    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/Dynamic.vue',
    })
    const card = findNode(manifest.root, 'Card')
    const computedLoop = findNodes(manifest.root, 'div')[0]
    const mappedLoop = findNodes(manifest.root, 'div')[1]

    expect(card?.bindings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'class',
          value: 'rounded p-4',
          editable: true,
        }),
        expect.objectContaining({
          kind: 'prop',
          name: 'title',
          value: '静态标题',
          editable: true,
        }),
        expect.objectContaining({
          kind: 'prop',
          name: 'count',
          value: 2,
          editable: true,
        }),
        expect.objectContaining({
          kind: 'text',
          value: '静态文本',
          editable: true,
        }),
      ])
    )
    expect(computedLoop?.loopContext).toMatchObject({
      editable: false,
      readonlyReason: 'DYNAMIC_SCRIPT_SOURCE',
    })
    expect(
      computedLoop?.bindings.find((binding) => binding.kind === 'text')
    ).toMatchObject({
      editable: false,
      readonlyReason: 'DYNAMIC_SCRIPT_SOURCE',
    })
    expect(mappedLoop?.loopContext?.editable).toBe(false)
    expect(
      mappedLoop?.bindings.find((binding) => binding.kind === 'text')
    ).toMatchObject({
      editable: false,
      readonlyReason: 'DYNAMIC_EXPRESSION',
    })
  })

  it('静态文本范围应按 loc.source 排除缩进并完整覆盖 HTML entity', () => {
    const source = `<template><Card>   A &amp; B   </Card></template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/TextRange.vue',
    })
    const binding = findNode(manifest.root, 'Card')?.bindings.find(
      (item) => item.kind === 'text'
    )

    expect(binding?.value).toBe('A & B')
    expect(
      source.slice(binding?.sourceRange.start, binding?.sourceRange.end)
    ).toBe('A &amp; B')
  })

  it('应把文本容器内的换行与语义强调聚合为单一富文本 binding', () => {
    const source =
      '<template><p>普通 <strong>重点</strong><br><em>补充</em></p><span></span></template>'
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/RichText.vue',
    })
    const paragraph = findNode(manifest.root, 'p')
    const emptySpan = findNode(manifest.root, 'span')

    expect(paragraph?.bindings).toEqual([
      expect.objectContaining({
        kind: 'rich_text',
        value: '普通 <strong>重点</strong><br><em>补充</em>',
        editable: true,
        source: { kind: 'template-rich-text' },
      }),
    ])
    expect(paragraph?.children).toEqual([])
    expect(emptySpan?.bindings[0]).toMatchObject({
      kind: 'rich_text',
      value: '',
      editable: true,
    })
    expect(emptySpan?.bindings[0]?.sourceRange.start).toBe(
      emptySpan?.bindings[0]?.sourceRange.end
    )
  })

  it('自闭合富文本候选应保留节点与 class 绑定，且不生成富文本 binding', () => {
    const source = `<template>
  <main>
    <span class="dot" />
    <span v-for="n in 6" :key="n" class="indicator" />
    <span></span>
    <span>正文</span>
  </main>
</template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/SelfClosingRichText.vue',
    })
    const spans = findNodes(manifest.root, 'span')

    expect(manifest.diagnostics).toEqual([])
    expect(spans).toHaveLength(4)
    expect(spans[0]?.bindings).toEqual([
      expect.objectContaining({ kind: 'class', value: 'dot', editable: true }),
    ])
    expect(spans[1]?.loopContext).toMatchObject({
      itemAlias: 'n',
      editable: false,
      readonlyReason: 'LOOP_SOURCE_UNSUPPORTED',
    })
    expect(spans[1]?.bindings).toEqual([
      expect.objectContaining({
        kind: 'class',
        value: 'indicator',
        editable: true,
      }),
    ])
    expect(
      spans
        .slice(0, 2)
        .flatMap((node) => node?.bindings || [])
        .some((binding) => binding.kind === 'rich_text')
    ).toBe(false)

    const emptyBinding = spans[2]?.bindings[0]
    expect(emptyBinding).toMatchObject({
      kind: 'rich_text',
      value: '',
      editable: true,
      source: { kind: 'template-rich-text' },
    })
    expect(emptyBinding?.sourceRange.start).toBe(emptyBinding?.sourceRange.end)
    const textBinding = spans[3]?.bindings[0]
    expect(textBinding).toMatchObject({
      kind: 'rich_text',
      value: '正文',
      editable: true,
    })
    expect(
      source.slice(textBinding?.sourceRange.start, textBinding?.sourceRange.end)
    ).toBe('正文')
  })

  it('无法定位内部范围的富文本候选应降级为节点级诊断，不中断整页分析', () => {
    const source =
      '<template><section><p>第一段<p>第二段</section></template>'
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/ImpliedEndTag.vue',
    })
    const paragraphs = findNodes(manifest.root, 'p')

    expect(paragraphs.length).toBeGreaterThan(0)
    for (const paragraph of paragraphs) {
      expect(
        paragraph.bindings.some((binding) => binding.kind === 'rich_text')
      ).toBe(false)
      expect(
        paragraph.bindings.some(
          (binding) =>
            binding.source?.kind === 'template-rich-text' && binding.editable
        )
      ).toBe(false)
    }
    const degraded = manifest.diagnostics.filter(
      (diagnostic) => diagnostic.code === 'RICH_TEXT_SOURCE_RANGE_UNRESOLVED'
    )
    expect(degraded.length).toBeGreaterThan(0)
    for (const diagnostic of degraded) {
      expect(diagnostic.severity).toBe('warning')
      expect(diagnostic.sourceRange).toBeDefined()
    }
    // 首段静态文本仍以普通 text binding 保留编辑能力。
    expect(
      paragraphs[0]?.bindings.find((binding) => binding.kind === 'text')
    ).toMatchObject({ value: '第一段', editable: true })
  })

  it('动态混排应合并只读，静态 class 应随内联语义结构聚合', () => {
    const source = `<template>
      <p>你好 <strong>{{ user.name }}</strong><br>欢迎</p>
      <label>标题 <span class="text-red-500"><strong class="font-bold">重点</strong></span></label>
    </template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/RichTextReadonly.vue',
    })
    const paragraph = findNode(manifest.root, 'p')
    const label = findNode(manifest.root, 'label')

    expect(paragraph?.bindings[0]).toMatchObject({
      kind: 'rich_text',
      editable: false,
      readonlyReason: 'RICH_TEXT_DYNAMIC_CONTENT',
    })
    expect(paragraph?.children).toEqual([])
    expect(label?.bindings[0]).toMatchObject({
      kind: 'rich_text',
      editable: true,
      value:
        '标题 <span class="text-red-500"><strong class="font-bold">重点</strong></span>',
    })
    expect(label?.children).toEqual([])
  })

  it('链接、组件、动态属性与 style 应锁定标签外壳并开放全部静态文本', () => {
    const source = `<template>
      <p>开场 <a href="/docs"><strong :class="tone">链接文本</strong></a> 结尾</p>
      <label><Badge :tone="tone"><em style="color: red">组件文本</em></Badge></label>
    </template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/RichTextUnsupported.vue',
    })

    expect(findNode(manifest.root, 'p')?.bindings[0]).toMatchObject({
      kind: 'rich_text',
      editable: true,
      value:
        '开场 <a href="/docs"><strong :class="tone">链接文本</strong></a> 结尾',
      source: { kind: 'template-rich-text' },
    })
    expect(findNode(manifest.root, 'label')?.bindings[0]).toMatchObject({
      kind: 'rich_text',
      editable: true,
      value: '<Badge :tone="tone"><em style="color: red">组件文本</em></Badge>',
      source: { kind: 'template-rich-text' },
    })
    expect(findNode(manifest.root, 'p')?.children).toEqual([])
    expect(findNode(manifest.root, 'label')?.children).toEqual([])
  })

  it('style 与 Runtime 保留 marker 不应进入可编辑 prop，普通 prop 和 class 保持可编辑', () => {
    const source = `<template>
      <Card
        class="p-4"
        style="color: red"
        :style="{ opacity: 0.5 }"
        data-page-visual-node-id="forged"
        title="标题"
      />
    </template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/StyleBoundary.vue',
    })
    const bindings = findNode(manifest.root, 'Card')?.bindings || []

    expect(bindings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'class',
          name: 'class',
          editable: true,
        }),
        expect.objectContaining({
          kind: 'prop',
          name: 'title',
          editable: true,
        }),
      ])
    )
    expect(bindings.some((binding) => binding.name === 'style')).toBe(false)
    expect(
      bindings.some((binding) => binding.name === 'data-page-visual-node-id')
    ).toBe(false)
  })

  it('应把基本类型循环和组件 JSON prop 关联到去重 JSON source', () => {
    const source = `<script setup lang="ts">
const benefits = ['上下文稳定', '品牌统一']
const config = reactive({ columns: 3, flags: [true, false] })
</script>
<template>
  <div v-for="(benefit, index) in benefits" :key="index">{{ benefit }}</div>
  <Card :config="config" :inline="{ mode: 'compact', rows: [1, 2] }" />
</template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/JsonSources.vue',
    })
    const loop = findNode(manifest.root, 'div')
    const card = findNode(manifest.root, 'Card')

    expect(loop?.loopContext).toMatchObject({
      editable: false,
      readonlyReason: 'DYNAMIC_SCRIPT_SOURCE',
    })
    expect(loop?.loopItemActions).toBeUndefined()
    expect(loop?.bindings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: 'json',
          name: 'benefits',
          valueType: 'json',
          editable: true,
        }),
      ])
    )
    expect(
      card?.bindings.filter((binding) => binding.source?.kind === 'json-source')
    ).toHaveLength(2)
    expect(manifest.jsonSources.map((item) => item.name ?? item.kind)).toEqual([
      'benefits',
      'config',
      'template-expression',
    ])
    expect(
      new Set(manifest.jsonSources.map((item) => item.sourceId)).size
    ).toBe(3)
  })

  it('应为组件 prop 的内联 JSON 基本值生成独立 source', () => {
    const source = `<script setup lang="ts">
import DemoCard from './DemoCard.vue'
</script>
<template>
  <DemoCard :count="1" :enabled="true" :empty="null" />
</template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/ScalarJson.vue',
    })
    const component = findNode(manifest.root, 'DemoCard')
    const jsonBindings =
      component?.bindings.filter((binding) => binding.valueType === 'json') ??
      []

    expect(jsonBindings.map((binding) => binding.value)).toEqual([
      1,
      true,
      null,
    ])
    expect(manifest.jsonSources.map((item) => item.value)).toEqual([
      1,
      true,
      null,
    ])
    expect(
      manifest.jsonSources.every((item) => item.kind === 'template-expression')
    ).toBe(true)
  })
})

/**
 * 深度优先查找第一个指定标签节点。
 */
function findNode(
  root: VisualEditTemplateNode,
  tag: string
): VisualEditTemplateNode | undefined {
  return findNodes(root, tag)[0]
}

/**
 * 查找所有指定标签节点。
 */
function findNodes(
  root: VisualEditTemplateNode,
  tag: string
): VisualEditTemplateNode[] {
  const result: VisualEditTemplateNode[] = []
  if (root.tag === tag) {
    result.push(root)
  }
  for (const child of root.children) {
    result.push(...findNodes(child, tag))
  }
  return result
}

/**
 * 提取脚本数组绑定位置，测试调用方已先断言 source 类型。
 */
function getScriptLocations(binding?: VisualEditBinding) {
  return binding?.source?.kind === 'script-array-item'
    ? binding.source.locations
    : []
}

/**
 * 收集节点和绑定 ID，验证相同源码分析结果稳定。
 */
function collectIds(root: VisualEditTemplateNode): string[] {
  return [
    root.nodeId,
    ...root.bindings.map((binding) => binding.bindingId),
    ...root.children.flatMap(collectIds),
  ]
}
