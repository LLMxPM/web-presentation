/**
 * 文件用途：验证可视化编辑原子改写成功路径、稳定数组定位、Tailwind 保留策略与安全编码。
 */

import { createHash } from 'node:crypto'

import { describe, expect, it } from 'vitest'

import type {
  VisualEditBinding,
  VisualEditOperation,
  VisualEditSfcManifest,
  VisualEditTemplateNode,
} from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'
import { applyVisualEditOperations } from './apply-operations'

const SOURCE = `<script setup lang="ts">
const items = [
  { id: 'a', title: '标题 A', subtitle: '副标题 A', classes: 'block p-2' },
  { id: 'b', title: '标题 B', subtitle: '副标题 B', classes: 'flex p-4 item-unknown hover:bg-red-500 w-[10px]' },
]
const refItems = ref([
  { id: 'ref-a', title: 'Ref A' },
  { id: 'ref-b', title: 'Ref B' },
])
const reactiveItems = reactive([{ id: 10, title: 'Reactive A' }])
</script>
<template>
  <section>
    <h1 class="block p-4 custom-token hover:bg-blue-500 w-[123px]" title="旧属性">   旧标题 &amp; 说明   </h1>
    <article v-for="(item, index) in items" :key="item.id" :class="item.classes">
      <h2>{{ item.title }}</h2>
      <Card :title="item.subtitle" />
    </article>
    <p v-for="(refItem, index) in refItems" :key="refItem.id">{{ refItem.title }}</p>
    <span v-for="(reactiveItem, index) in reactiveItems" :key="reactiveItem.id">{{ reactiveItem.title }}</span>
  </section>
</template>`

describe('applyVisualEditOperations', () => {
  it('应原子改写静态文本/prop/class、const 第二项及 ref/reactive 成员', () => {
    const manifest = analyzeVisualEditSfc(SOURCE, {
      modulePath: 'src/views/ApplyDemo.vue',
    })
    const h1 = requireNode(manifest, 'h1')
    const article = requireNode(manifest, 'article')
    const h2 = requireNode(manifest, 'h2')
    const card = requireNode(manifest, 'Card')
    const refText = requireBinding(
      requireNode(manifest, 'p'),
      (binding) => binding.expression === 'refItem.title'
    )
    const reactiveText = requireBinding(
      requireNode(manifest, 'span'),
      (binding) => binding.expression === 'reactiveItem.title'
    )
    const operations: VisualEditOperation[] = [
      setRichText(
        h1,
        requireBinding(h1, (binding) => binding.kind === 'rich_text'),
        '<strong>新标题</strong><br>说明 &amp;'
      ),
      setValue(
        h1,
        requireBinding(h1, (binding) => binding.name === 'title'),
        '属性 "安全" <ok>'
      ),
      setTailwind(
        h1,
        requireBinding(h1, (binding) => binding.kind === 'class'),
        [
          { group: 'display', className: 'flex' },
          { group: 'padding', className: 'p-8' },
          { group: 'background-color', className: 'bg-primary' },
        ]
      ),
      setValue(
        h2,
        requireBinding(h2, (binding) => binding.expression === 'item.title'),
        "新的 B\nO'Reilly",
        {
          loopNodeId: article.nodeId,
          key: 'b',
          index: 1,
        }
      ),
      setValue(
        card,
        requireBinding(
          card,
          (binding) => binding.expression === 'item.subtitle'
        ),
        '新副标题 B',
        {
          loopNodeId: article.nodeId,
          key: 'b',
          index: 1,
        }
      ),
      setTailwind(
        article,
        requireBinding(article, (binding) => binding.kind === 'class'),
        [
          { group: 'display', className: 'grid' },
          { group: 'padding', className: 'p-10' },
        ],
        {
          loopNodeId: article.nodeId,
          key: 'b',
          index: 1,
        }
      ),
      setValue(requireNode(manifest, 'p'), refText, 'Ref B 已修改', {
        loopNodeId: requireNode(manifest, 'p').nodeId,
        key: 'ref-b',
        index: 1,
      }),
      setValue(requireNode(manifest, 'span'), reactiveText, 'Reactive 已修改', {
        loopNodeId: requireNode(manifest, 'span').nodeId,
        key: 10,
        index: 0,
      }),
    ]

    const result = applyVisualEditOperations(
      SOURCE,
      manifest.modulePath,
      manifest.sourceHash,
      operations
    )

    expect(result.operationsApplied).toBe(operations.length)
    expect(result.baseSourceHash).toBe(manifest.sourceHash)
    expect(result.nextSourceHash).toBe(hash(result.nextSource))
    expect(result.canonicalDiff).toContain('+++ proposed')
    expect(result.nextSource).toContain('<strong>新标题</strong><br>说明 &amp;')
    expect(result.nextSource).not.toContain('旧标题 &amp; 说明')
    expect(result.nextSource).toContain(
      'title="属性 &quot;安全&quot; &lt;ok&gt;"'
    )
    expect(result.nextSource).toContain("title: '新的 B\\nO\\'Reilly'")

    const nextManifest = analyzeVisualEditSfc(result.nextSource, {
      modulePath: manifest.modulePath,
    })
    const nextH1 = requireNode(nextManifest, 'h1')
    expect(
      requireBinding(nextH1, (binding) => binding.kind === 'rich_text').value
    ).toBe('<strong>新标题</strong><br>说明 &amp;')
    expect(
      requireBinding(nextH1, (binding) => binding.name === 'title').value
    ).toBe('属性 "安全" <ok>')
    expect(
      requireBinding(nextH1, (binding) => binding.kind === 'class').value
    ).toBe('flex p-8 custom-token hover:bg-blue-500 w-[123px] bg-primary')

    const nextArticle = requireNode(nextManifest, 'article')
    expect(
      scriptLocation(
        requireBinding(
          requireNode(nextManifest, 'h2'),
          (binding) => binding.expression === 'item.title'
        ),
        'b'
      ).value
    ).toBe("新的 B\nO'Reilly")
    expect(
      scriptLocation(
        requireBinding(
          requireNode(nextManifest, 'Card'),
          (binding) => binding.expression === 'item.subtitle'
        ),
        'b'
      ).value
    ).toBe('新副标题 B')
    expect(
      scriptLocation(
        requireBinding(nextArticle, (binding) => binding.kind === 'class'),
        'b'
      ).value
    ).toBe('grid p-10 item-unknown hover:bg-red-500 w-[10px]')
    expect(
      scriptLocation(
        requireBinding(
          requireNode(nextManifest, 'p'),
          (binding) => binding.expression === 'refItem.title'
        ),
        'ref-b'
      ).value
    ).toBe('Ref B 已修改')
    expect(
      scriptLocation(
        requireBinding(
          requireNode(nextManifest, 'span'),
          (binding) => binding.expression === 'reactiveItem.title'
        ),
        10
      ).value
    ).toBe('Reactive 已修改')
  })

  it('variant、任意值和未知 class 应保留，但不能作为新目录值写入', () => {
    const manifest = analyzeVisualEditSfc(SOURCE, {
      modulePath: 'src/views/ApplyDemo.vue',
    })
    const h1 = requireNode(manifest, 'h1')
    const classBinding = requireBinding(
      h1,
      (binding) => binding.kind === 'class'
    )
    const result = applyVisualEditOperations(
      SOURCE,
      manifest.modulePath,
      manifest.sourceHash,
      [setTailwind(h1, classBinding, [{ group: 'display', className: 'grid' }])]
    )

    expect(result.nextSource).toContain(
      'grid p-4 custom-token hover:bg-blue-500 w-[123px]'
    )
    for (const className of ['hover:flex', 'w-[222px]', 'not-in-catalog']) {
      expect(() =>
        applyVisualEditOperations(
          SOURCE,
          manifest.modulePath,
          manifest.sourceHash,
          [setTailwind(h1, classBinding, [{ group: 'display', className }])]
        )
      ).toThrow(/不属于组/)
    }
  })

  it('应允许从空文本容器的零长度范围插入富文本', () => {
    const source = '<template><p></p></template>'
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/EmptyRichText.vue',
    })
    const paragraph = requireNode(manifest, 'p')
    const binding = requireBinding(
      paragraph,
      (item) => item.kind === 'rich_text'
    )

    const result = applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [setRichText(paragraph, binding, '第一行<br><em>第二行</em>')]
    )

    expect(result.nextSource).toContain('<p>第一行<br><em>第二行</em></p>')
  })

  it('自闭合节点不提供富文本写入目标，伪造 set_rich_text 应被拒绝', () => {
    const source = `<template>
  <main>
    <span class="dot" />
    <span>正文</span>
  </main>
</template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/SelfClosingApply.vue',
    })
    const [selfClosing, paired] = collectNodes(manifest, 'span')

    // 自闭合节点没有任何 rich_text binding，可写目标集合中不存在它。
    expect(
      selfClosing?.bindings.some((binding) => binding.kind === 'rich_text')
    ).toBe(false)

    // 伪造 bindingId 直接指向自闭合节点时，apply 重新分析后应定位失败。
    expect(() =>
      applyVisualEditOperations(source, manifest.modulePath, manifest.sourceHash, [
        {
          type: 'set_rich_text',
          nodeId: selfClosing!.nodeId,
          bindingId: 'binding-forged-rich-text',
          instancePath: [],
          html: '注入文本',
        },
      ])
    ).toThrow(/未找到/)

    // 借用自闭合节点的 class binding 伪造富文本写入时，应被操作类型校验拒绝。
    expect(() =>
      applyVisualEditOperations(source, manifest.modulePath, manifest.sourceHash, [
        setRichText(
          selfClosing!,
          requireBinding(selfClosing!, (binding) => binding.kind === 'class'),
          '注入文本'
        ),
      ])
    ).toThrow(/只能用于可编辑的模板富文本/)

    // 同页成对容器的正常富文本替换不受降级影响，且自闭合节点源码保持原样。
    const result = applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [
        setRichText(
          paired!,
          requireBinding(paired!, (binding) => binding.kind === 'rich_text'),
          '新正文'
        ),
      ]
    )
    expect(result.nextSource).toContain('<span>新正文</span>')
    expect(result.nextSource).toContain('<span class="dot" />')
  })

  it('应复制和删除普通节点，并按稳定 key 复制、删除循环数据项', () => {
    const manifest = analyzeVisualEditSfc(SOURCE, {
      modulePath: 'src/views/StructureDemo.vue',
    })
    const h1 = requireNode(manifest, 'h1')
    const article = requireNode(manifest, 'article')
    const h2 = requireNode(manifest, 'h2')
    const title = requireBinding(
      h2,
      (binding) => binding.expression === 'item.title'
    )

    const duplicated = applyVisualEditOperations(
      SOURCE,
      manifest.modulePath,
      manifest.sourceHash,
      [
        setValue(h2, title, '复制后的标题', {
          loopNodeId: article.nodeId,
          key: 'b',
          index: 1,
        }),
        {
          type: 'duplicate_node',
          nodeId: h2.nodeId,
          instancePath: [{ loopNodeId: article.nodeId, key: 'b', index: 1 }],
        },
        { type: 'duplicate_node', nodeId: h1.nodeId, instancePath: [] },
      ]
    )
    expect(duplicated.nextSource).toContain(
      '{ id: "b-copy", title: \'复制后的标题\''
    )
    expect(duplicated.nextSource.match(/<h1/g)).toHaveLength(2)

    const duplicatedManifest = analyzeVisualEditSfc(duplicated.nextSource, {
      modulePath: manifest.modulePath,
    })
    const nextArticle = requireNode(duplicatedManifest, 'article')
    const deleted = applyVisualEditOperations(
      duplicated.nextSource,
      duplicatedManifest.modulePath,
      duplicatedManifest.sourceHash,
      [
        {
          type: 'delete_node',
          nodeId: nextArticle.nodeId,
          instancePath: [
            { loopNodeId: nextArticle.nodeId, key: 'a', index: 0 },
          ],
        },
      ]
    )
    expect(deleted.nextSource).not.toContain("id: 'a'")
    expect(deleted.nextSource).toContain('v-for=')

    const deleteLoopManifest = analyzeVisualEditSfc(deleted.nextSource, {
      modulePath: manifest.modulePath,
    })
    const loop = requireNode(deleteLoopManifest, 'article')
    const withoutLoop = applyVisualEditOperations(
      deleted.nextSource,
      deleteLoopManifest.modulePath,
      deleteLoopManifest.sourceHash,
      [{ type: 'delete_node', nodeId: loop.nodeId, instancePath: [] }]
    )
    expect(withoutLoop.nextSource).not.toContain('<article v-for=')
    expect(withoutLoop.nextSource).toContain('const items = [')
  })

  it.each([
    ['首项', 'a', ["id: 'b'", "id: 'c'"]],
    ['中间项', 'b', ["id: 'a'", "id: 'c'"]],
    ['末项', 'c', ["id: 'a'", "id: 'b'"]],
  ])('应安全删除数组%s并处理相邻逗号', (_label, key, remaining) => {
    const source = `<script setup lang="ts">
const items = [
  { id: 'a', title: 'A' },
  { id: 'b', title: 'B' },
  { id: 'c', title: 'C' },
]
</script>
<template><p v-for="item in items" :key="item.id">{{ item.title }}</p></template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/DeletePosition.vue',
    })
    const loop = requireNode(manifest, 'p')
    const result = applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [
        {
          type: 'delete_node',
          nodeId: loop.nodeId,
          instancePath: [{ loopNodeId: loop.nodeId, key }],
        },
      ]
    )

    expect(result.nextSource).not.toContain(`id: '${key}'`)
    for (const token of remaining) expect(result.nextSource).toContain(token)
    expect(
      analyzeVisualEditSfc(result.nextSource, {
        modulePath: manifest.modulePath,
      }).diagnostics
    ).toEqual([])
  })

  it('应允许删除唯一循环项，并为 ref 字符串 key 与 reactive 整数 key 生成避重副本', () => {
    const manifest = analyzeVisualEditSfc(SOURCE, {
      modulePath: 'src/views/CollectionStructure.vue',
    })
    const refLoop = requireNode(manifest, 'p')
    const reactiveLoop = requireNode(manifest, 'span')
    const first = applyVisualEditOperations(
      SOURCE,
      manifest.modulePath,
      manifest.sourceHash,
      [
        {
          type: 'duplicate_node',
          nodeId: refLoop.nodeId,
          instancePath: [{ loopNodeId: refLoop.nodeId, key: 'ref-a' }],
        },
        {
          type: 'duplicate_node',
          nodeId: reactiveLoop.nodeId,
          instancePath: [{ loopNodeId: reactiveLoop.nodeId, key: 10 }],
        },
      ]
    )
    expect(first.nextSource).toContain('"ref-a-copy"')
    expect(first.nextSource).toContain('id: 11')

    const nextManifest = analyzeVisualEditSfc(first.nextSource, {
      modulePath: manifest.modulePath,
    })
    const nextRefLoop = requireNode(nextManifest, 'p')
    const nextReactiveLoop = requireNode(nextManifest, 'span')
    const second = applyVisualEditOperations(
      first.nextSource,
      nextManifest.modulePath,
      nextManifest.sourceHash,
      [
        {
          type: 'duplicate_node',
          nodeId: nextRefLoop.nodeId,
          instancePath: [{ loopNodeId: nextRefLoop.nodeId, key: 'ref-a' }],
        },
        {
          type: 'duplicate_node',
          nodeId: nextReactiveLoop.nodeId,
          instancePath: [{ loopNodeId: nextReactiveLoop.nodeId, key: 10 }],
        },
      ]
    )
    expect(second.nextSource).toContain('"ref-a-copy-2"')
    expect(second.nextSource).toContain('id: 12')

    const singleSource = `<script setup>const items = [{ id: 'only' }]</script><template><i v-for="item in items" :key="item.id" /></template>`
    const singleManifest = analyzeVisualEditSfc(singleSource, {
      modulePath: 'src/views/DeleteOnly.vue',
    })
    const singleLoop = requireNode(singleManifest, 'i')
    const empty = applyVisualEditOperations(
      singleSource,
      singleManifest.modulePath,
      singleManifest.sourceHash,
      [
        {
          type: 'delete_node',
          nodeId: singleLoop.nodeId,
          instancePath: [{ loopNodeId: singleLoop.nodeId, key: 'only' }],
        },
      ]
    )
    expect(empty.nextSource).toContain('const items = []')
  })

  it('应按 sourceId 原子替换基本类型数组并保留 ref/reactive 外壳', () => {
    const source = `<script setup lang="ts">
const benefits = ref(['旧值', '第二项'])
</script><template><div v-for="(item, index) in benefits" :key="index">{{ item }}</div></template>`
    const manifest = analyzeVisualEditSfc(source, {
      modulePath: 'src/views/JsonApply.vue',
    })
    const jsonSource = manifest.jsonSources[0]!
    const result = applyVisualEditOperations(
      source,
      manifest.modulePath,
      manifest.sourceHash,
      [
        {
          type: 'set_json',
          sourceId: jsonSource.sourceId,
          value: ['新值', { label: '结构化' }],
        },
      ]
    )

    expect(result.nextSource).toContain('const benefits = ref([')
    expect(result.nextSource).toContain("'新值'")
    expect(result.nextSource).toContain("'label': '结构化'")
    const nextManifest = analyzeVisualEditSfc(result.nextSource, {
      modulePath: manifest.modulePath,
    })
    expect(nextManifest.jsonSources[0]?.value).toEqual([
      '新值',
      { label: '结构化' },
    ])
  })
})

/**
 * 构造 set_value 操作。
 */
function setValue(
  node: VisualEditTemplateNode,
  binding: VisualEditBinding,
  value: string,
  segment?: { loopNodeId: string; key: string | number; index?: number }
): VisualEditOperation {
  return {
    type: 'set_value',
    nodeId: node.nodeId,
    bindingId: binding.bindingId,
    instancePath: segment ? [segment] : [],
    value,
  }
}

/** 构造 set_rich_text 操作。 */
function setRichText(
  node: VisualEditTemplateNode,
  binding: VisualEditBinding,
  html: string
): VisualEditOperation {
  return {
    type: 'set_rich_text',
    nodeId: node.nodeId,
    bindingId: binding.bindingId,
    instancePath: [],
    html,
  }
}

/**
 * 构造 set_tailwind_tokens 操作。
 */
function setTailwind(
  node: VisualEditTemplateNode,
  binding: VisualEditBinding,
  changes: Array<{ group: string; className: string | null }>,
  segment?: { loopNodeId: string; key: string | number; index?: number }
): VisualEditOperation {
  return {
    type: 'set_tailwind_tokens',
    nodeId: node.nodeId,
    bindingId: binding.bindingId,
    instancePath: segment ? [segment] : [],
    changes,
  }
}

/**
 * 收集指定标签的全部节点（按遍历顺序）。
 */
function collectNodes(
  manifest: VisualEditSfcManifest,
  tag: string
): VisualEditTemplateNode[] {
  const result: VisualEditTemplateNode[] = []
  const pending = [manifest.root]
  while (pending.length > 0) {
    const node = pending.shift()
    if (node?.tag === tag) result.push(node)
    pending.push(...(node?.children || []))
  }
  return result
}

/**
 * 查找指定标签的第一个节点。
 */
function requireNode(
  manifest: VisualEditSfcManifest,
  tag: string
): VisualEditTemplateNode {
  const pending = [manifest.root]
  while (pending.length > 0) {
    const node = pending.shift()
    if (node?.tag === tag) {
      return node
    }
    pending.push(...(node?.children || []))
  }
  throw new Error(`测试节点不存在：${tag}`)
}

/**
 * 查找节点内指定 binding。
 */
function requireBinding(
  node: VisualEditTemplateNode,
  predicate: (binding: VisualEditBinding) => boolean
): VisualEditBinding {
  const binding = node.bindings.find(predicate)
  if (!binding) {
    throw new Error(`测试 binding 不存在：${node.tag}`)
  }
  return binding
}

/**
 * 按稳定 key 读取脚本数组定位元数据。
 */
function scriptLocation(binding: VisualEditBinding, key: string | number) {
  if (binding.source?.kind !== 'script-array-item') {
    throw new Error('测试 binding 不是脚本数组来源。')
  }
  const location = binding.source.locations.find(
    (candidate) => candidate.key === key
  )
  if (!location) {
    throw new Error(`测试 location 不存在：${String(key)}`)
  }
  return location
}

/**
 * 计算 UTF-8 SHA-256。
 */
function hash(source: string): string {
  return createHash('sha256').update(source).digest('hex')
}
