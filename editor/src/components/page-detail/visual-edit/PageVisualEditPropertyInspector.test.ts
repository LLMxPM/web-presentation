/**
 * 文件功能：验证可视化属性面板的稳定数组实例、按实际值类型控件和受限 Tailwind 交互边界。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditPropertyInspector from '@/components/page-detail/visual-edit/PageVisualEditPropertyInspector.vue'
import type { PageVisualEditNode } from '@/types/page-visual-edit'

describe('PageVisualEditPropertyInspector', () => {
  it('富文本 binding 应传递基准结构并发出规范化 set-rich-text 草稿', async () => {
    const node = createNode([{
      binding_id: 'binding-rich',
      node_id: 'node-value',
      kind: 'rich_text',
      value_type: 'string',
      value: '普通 <strong>重点</strong>',
      source_range: { start: 20, end: 40 },
      editable: true,
      source: { kind: 'template-rich-text' },
    }])
    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-rich',
        selectedInstancePath: [],
        loopNodeId: '',
        catalog: { version: 1, groups: [] },
        componentSchemas: {},
        pendingOperations: [],
      },
    })
    const editor = screen.getAllByRole('textbox')[0]!
    await fireEvent.update(editor, '新内容\n补充')

    expect(rendered.emitted()['set-rich-text']?.[0]?.[0]).toEqual({
      target: { nodeId: 'node-value', bindingId: 'binding-rich', instancePath: [] },
      html: '新内容<br>补充<strong>重点</strong>',
      baselineHtml: '普通 <strong>重点</strong>',
    })
  })

  it('script-array 应以稳定 key 定位，并按所选 location 实际值使用数字控件', async () => {
    const node = createNode([{
      binding_id: 'binding-value',
      node_id: 'node-value',
      kind: 'prop',
      name: 'value',
      value_type: 'string',
      expression: 'item.value',
      source_range: { start: 20, end: 30 },
      editable: true,
      source: {
        kind: 'script-array-item',
        collection_name: 'items',
        collection_kind: 'const-array',
        item_alias: 'item',
        member: 'value',
        key_member: 'id',
        locations: [
          { index: 0, key: 'first', value: '标题', source_range: { start: 2, end: 6 }, editable: true },
          { index: 1, key: 2, value: 12, source_range: { start: 8, end: 10 }, editable: true },
        ],
      },
    }])
    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-value',
        selectedInstancePath: [{ loopNodeId: 'node-loop', key: 2, index: 1 }],
        loopNodeId: 'node-loop',
        catalog: { version: 1, groups: [] },
        componentSchemas: {},
        pendingOperations: [],
      },
    })

    const numberInput = screen.getByRole('spinbutton')
    expect(numberInput).toHaveValue(12)
    await fireEvent.update(numberInput, '42')

    expect(rendered.emitted()['set-value']?.[0]?.[0]).toEqual({
      target: {
        nodeId: 'node-value',
        bindingId: 'binding-value',
        instancePath: [{ loopNodeId: 'node-loop', key: 2, index: 1 }],
      },
      value: 42,
      baselineValue: 12,
    })
  })

  it('缺少稳定 key 的数组 location 必须只读，不能回退到 index-only 操作', () => {
    const node = createNode([{
      binding_id: 'binding-title',
      node_id: 'node-value',
      kind: 'text',
      value_type: 'string',
      expression: 'item.title',
      source_range: { start: 20, end: 30 },
      editable: true,
      source: {
        kind: 'script-array-item',
        collection_name: 'items',
        collection_kind: 'const-array',
        item_alias: 'item',
        member: 'title',
        locations: [{ index: 0, value: '标题', source_range: { start: 2, end: 6 }, editable: true }],
      },
    }])

    render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-title',
        selectedInstancePath: [{ loopNodeId: 'node-loop', index: 0 }],
        loopNodeId: 'node-loop',
        catalog: { version: 1, groups: [] },
        componentSchemas: {},
        pendingOperations: [],
      },
    })

    expect(screen.getByText(/缺少稳定的字符串或整数 key/)).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('Tailwind 仅显示友好选项，复杂类保留为只读 badge', async () => {
    const node = createNode([{
      binding_id: 'binding-class',
      node_id: 'node-value',
      kind: 'class',
      name: 'class',
      value_type: 'string',
      value: 'p-4 hover:bg-slate-100 w-[37px]',
      source_range: { start: 20, end: 50 },
      editable: true,
      source: { kind: 'template-literal' },
    }])
    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-class',
        selectedInstancePath: [],
        loopNodeId: 'node-loop',
        catalog: {
          version: 1,
          groups: [{
            key: 'padding',
            label: '内边距',
            options: [
              { class_name: 'p-4', label: '标准' },
              { class_name: 'p-8', label: '宽松' },
            ],
          }],
        },
        componentSchemas: {},
        pendingOperations: [],
      },
    })

    expect(screen.getByText(/修改所有循环实例/)).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '宽松 · p-8' })).toHaveAttribute('title', 'p-8')
    expect(screen.getByRole('option', { name: '不设置' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByText('hover:bg-slate-100')).toBeInTheDocument()
    expect(screen.getByText('w-[37px]')).toBeInTheDocument()

    await fireEvent.update(screen.getByLabelText('内边距'), 'p-8')
    expect(rendered.emitted()['set-tailwind']?.[0]?.[0]).toEqual({
      target: { nodeId: 'node-value', bindingId: 'binding-class', instancePath: [] },
      changes: [{ group: 'padding', className: 'p-8' }],
      baselineChanges: [{ group: 'padding', className: 'p-4' }],
    })
  })

  it('段落结构应通过内容和样式 tab 编辑，并回显 Tailwind 类名', async () => {
    const node: PageVisualEditNode = {
      node_id: 'node-paragraph',
      kind: 'element',
      tag: 'p',
      source_range: { start: 10, end: 90 },
      bindings: [{
        binding_id: 'binding-rich',
        node_id: 'node-paragraph',
        kind: 'rich_text',
        value_type: 'string',
        value: '段落内容',
        source_range: { start: 20, end: 40 },
        editable: true,
        source: { kind: 'template-rich-text' },
      }, {
        binding_id: 'binding-class',
        node_id: 'node-paragraph',
        kind: 'class',
        name: 'class',
        value_type: 'string',
        value: 'text-left',
        source_range: { start: 41, end: 60 },
        editable: true,
        source: { kind: 'template-literal' },
      }],
      children: [],
    }
    render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-rich',
        selectedInstancePath: [],
        loopNodeId: '',
        catalog: {
          version: 1,
          groups: [{
            key: 'text-align',
            label: '文本对齐',
            options: [
              { class_name: 'text-left', label: '左对齐' },
              { class_name: 'text-center', label: '居中' },
            ],
          }],
        },
        componentSchemas: {},
        pendingOperations: [],
      },
    })

    expect(screen.getByRole('heading', { name: '段落编辑' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '内容' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('textbox')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('tab', { name: '样式' }))
    expect(screen.getByRole('button', { name: /字体/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('option', { name: '居中 · text-center' })).toHaveAttribute('title', 'text-center')
    expect(screen.getByRole('option', { name: '不设置' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /清除该组/ })).toBeNull()
  })

  it('kebab-case 组件应消费 PascalCase schema，并保持 select 原始值且让 json 只读', async () => {
    const node = createNode([{
      binding_id: 'binding-mode',
      node_id: 'node-value',
      kind: 'prop',
      name: 'show-fallback',
      value_type: 'boolean',
      value: false,
      source_range: { start: 20, end: 30 },
      editable: true,
      source: { kind: 'template-literal' },
    }, {
      binding_id: 'binding-config',
      node_id: 'node-value',
      kind: 'prop',
      name: 'config',
      value_type: 'unknown',
      value: null,
      source_range: { start: 31, end: 40 },
      editable: true,
      source: { kind: 'template-literal' },
    }])
    node.tag = 'local-card'
    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-mode',
        selectedInstancePath: [],
        loopNodeId: '',
        catalog: { version: 1, groups: [] },
        componentSchemas: {
          LocalCard: {
            source: 'workspace_component',
            import_path: '@workspace-components/local-card/v/1',
            component_code: 'local-card',
            version_no: 1,
            props: {
              showFallback: {
                type: 'select',
                label: '模式',
                description: '请选择有限模式。',
                options: [{ label: '开启', value: true }, { label: '关闭', value: false }],
              },
              config: { type: 'json', label: '高级配置' },
            },
          },
        },
        pendingOperations: [],
      },
    })

    expect(screen.getByText('请选择有限模式。')).toBeInTheDocument()
    expect(screen.getByText('高级配置')).toBeInTheDocument()
    await fireEvent.update(screen.getByRole('combobox'), '0')
    expect(rendered.emitted()['set-value']?.[0]?.[0]).toMatchObject({ value: true, baselineValue: false })
    expect(screen.getByText(/JSON 参数首版仅展示/)).toBeInTheDocument()
  })

  it('组件 schema 控件与源码字面量类型不一致时必须只读', async () => {
    const node = createNode([{
      binding_id: 'binding-count',
      node_id: 'node-value',
      kind: 'prop',
      name: 'count',
      value_type: 'string',
      value: '2',
      source_range: { start: 20, end: 30 },
      editable: true,
      source: { kind: 'template-literal' },
    }, {
      binding_id: 'binding-mode',
      node_id: 'node-value',
      kind: 'prop',
      name: 'mode',
      value_type: 'string',
      value: 'compact',
      source_range: { start: 31, end: 40 },
      editable: true,
      source: { kind: 'template-literal' },
    }])
    const componentSchemas = {
      Card: {
        source: 'workspace_component' as const,
        import_path: '@workspace-components/card/v/1',
        component_code: 'card',
        version_no: 1,
        props: {
          count: { type: 'number' as const },
          mode: {
            type: 'select' as const,
            options: [{ label: '数字模式', value: 1 }],
          },
        },
      },
    }
    render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-count',
        selectedInstancePath: [],
        loopNodeId: '',
        catalog: { version: 1, groups: [] },
        componentSchemas,
        pendingOperations: [],
      },
    })

    expect(screen.getAllByText(/源码字面量类型与组件 schema 不一致/)).toHaveLength(2)
    expect(screen.queryByRole('spinbutton')).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('组件 JSON prop 应只在 schema 声明 json 时显示整块编辑器', () => {
    const node = createNode([{
      binding_id: 'binding-config-json',
      node_id: 'node-value',
      kind: 'prop',
      name: 'config',
      value_type: 'json',
      value: { columns: 3 },
      source_range: { start: 20, end: 34 },
      editable: true,
      source: { kind: 'json-source', source_id: 'source-config' },
    }])
    node.tag = 'local-card'
    render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-config-json',
        selectedInstancePath: [],
        loopNodeId: '',
        catalog: { version: 1, groups: [] },
        componentSchemas: {
          LocalCard: {
            source: 'workspace_component',
            import_path: '@workspace-components/local-card/v/1',
            component_code: 'local-card',
            version_no: 1,
            props: { config: { type: 'json', label: '高级配置' } },
          },
        },
        jsonSources: [{
          source_id: 'source-config',
          kind: 'const',
          name: 'config',
          value: { columns: 3 },
          source_range: { start: 20, end: 34 },
          editable: true,
        }],
        pendingOperations: [],
      },
      global: {
        stubs: { MonacoCodeEditor: { template: '<textarea aria-label="JSON 编辑器" />' } },
      },
    })

    expect(screen.getByText('高级配置')).toBeInTheDocument()
    expect(screen.getByText(/仅校验 JSON 格式/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'JSON 编辑器' })).toBeInTheDocument()
  })

  it('循环节点应提供数据项复制删除和整体删除，但不提供整体复制', async () => {
    const node = createNode([])
    node.loop_context = {
      loop_node_id: 'node-value',
      source_expression: 'items',
      source_binding: 'items',
      item_alias: 'item',
      key_member: 'id',
      editable: true,
    }
    node.template_actions = { can_duplicate: false, can_delete: true }
    node.loop_item_actions = {
      can_duplicate: true,
      can_delete: true,
      loop_node_id: 'node-value',
      collection_name: 'items',
      key_member: 'id',
      instances: [{ index: 0, key: 'a' }, { index: 1, key: 'b' }],
    }
    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: '',
        selectedInstancePath: [{ loopNodeId: 'node-value', key: 'b', index: 1 }],
        loopNodeId: 'node-value',
        catalog: { version: 1, groups: [] },
        componentSchemas: {},
        pendingOperations: [],
      },
    })

    expect(screen.queryByLabelText('复制组件')).toBeNull()
    expect(screen.getByLabelText('删除整个循环结构')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '复制此项' }))
    expect(rendered.emitted()['set-structure']?.[0]?.[0]).toEqual({
      type: 'duplicate_node',
      target: {
        nodeId: 'node-value',
        instancePath: [{ loopNodeId: 'node-value', key: 'b', index: 1 }],
      },
      label: '复制此项',
    })
    await fireEvent.click(screen.getByRole('button', { name: '删除此项' }))
    await fireEvent.click(screen.getByLabelText('删除整个循环结构'))
    expect(rendered.emitted()['set-structure']?.map(events => events[0].label)).toEqual([
      '复制此项',
      '删除此项',
      '删除整个循环结构',
    ])
  })
})

/** 创建属性面板测试节点；loop 位于祖先，因此当前节点自身不含 loop_context。 */
function createNode(bindings: PageVisualEditNode['bindings']): PageVisualEditNode {
  return {
    node_id: 'node-value',
    kind: 'component',
    tag: 'Card',
    source_range: { start: 10, end: 80 },
    template_actions: { can_duplicate: true, can_delete: true },
    bindings,
    children: [],
  }
}
