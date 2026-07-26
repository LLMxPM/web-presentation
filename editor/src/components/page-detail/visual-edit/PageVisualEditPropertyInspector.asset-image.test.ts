/**
 * 文件功能：验证属性面板精确路由到 AssetImage.v1 专用检查器，并保持既有操作协议与安全边界。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditPropertyInspector from './PageVisualEditPropertyInspector.vue'
import type {
  PageVisualEditComponentSchema,
  PageVisualEditNode,
} from '@/types/page-visual-edit'

describe('PageVisualEditPropertyInspector AssetImage 路由', () => {
  it('Runtime Kit AssetImage.v1 应使用专用检查器并沿用 set-value/set-tailwind payload', async () => {
    const rendered = renderInspector({
      node: createAssetImageNode(),
      componentSchemas: {
        LocalAssetImage: createAssetImageSchema(),
      },
    })

    expect(screen.getByRole('heading', { name: '图片：产品主图' })).toBeInTheDocument()
    expect(screen.getByTestId('asset-image-inspector')).toHaveAttribute('data-workspace-id', '7')
    const sourceTag = screen.getByText('LocalAssetImage')
    expect(sourceTag.closest('details')).not.toHaveAttribute('open')

    await fireEvent.click(screen.getByRole('button', { name: '替换图片' }))
    await fireEvent.click(screen.getByRole('button', { name: '修改填充' }))
    await fireEvent.click(screen.getByRole('button', { name: '修改图片框圆角' }))
    await fireEvent.click(screen.getByRole('button', { name: '尝试写入图片 object-fit' }))

    expect(rendered.emitted()['set-value']?.map(events => events[0])).toEqual([
      {
        target: { nodeId: 'node-image', bindingId: 'binding-name', instancePath: [] },
        value: 'hero-new',
        baselineValue: 'hero-old',
      },
      {
        target: { nodeId: 'node-image', bindingId: 'binding-fit', instancePath: [] },
        value: 'cover',
        baselineValue: 'contain',
      },
    ])
    expect(rendered.emitted()['set-tailwind']).toEqual([[
      {
        target: { nodeId: 'node-image', bindingId: 'binding-class', instancePath: [] },
        changes: [{ group: 'radius', className: 'rounded-xl' }],
        baselineChanges: [{ group: 'radius', className: 'rounded-lg' }],
      },
    ]])
  })

  it.each([
    { source: 'workspace_component' as const, componentCode: 'AssetImage', versionNo: 1 },
    { source: 'runtime_kit' as const, componentCode: 'AssetImage', versionNo: 2 },
    { source: 'runtime_kit' as const, componentCode: 'AssetVideo', versionNo: 1 },
  ])('非精确 schema 不得启用专用检查器：$source/$componentCode/v$versionNo', (identity) => {
    renderInspector({
      node: createAssetImageNode(),
      componentSchemas: {
        LocalAssetImage: {
          ...createAssetImageSchema(),
          source: identity.source,
          component_code: identity.componentCode,
          version_no: identity.versionNo,
        },
      },
    })

    expect(screen.queryByTestId('asset-image-inspector')).toBeNull()
    expect(screen.getByRole('heading', { name: `组件：${identity.componentCode}` })).toBeInTheDocument()
  })

  it('原生 img 应只显示迁移提示，不暴露通用图片内容或样式控件', () => {
    const node = createAssetImageNode()
    node.kind = 'element'
    node.tag = 'img'

    renderInspector({ node, componentSchemas: {} })

    expect(screen.getByText(/原生图片不提供低代码内容编辑/)).toBeInTheDocument()
    expect(screen.getByText(/AssetImage\.v1/)).toBeInTheDocument()
    expect(screen.queryByTestId('asset-image-inspector')).toBeNull()
    expect(screen.queryByRole('tab', { name: '样式' })).toBeNull()
  })

  it('动态图片 prop 即使收到子组件事件也不能生成写回操作', async () => {
    const node = createAssetImageNode()
    const nameBinding = node.bindings.find(binding => binding.binding_id === 'binding-name')!
    nameBinding.editable = false
    nameBinding.value_type = 'unknown'
    nameBinding.value = undefined
    nameBinding.expression = 'item.imageName'
    nameBinding.readonly_reason = 'DYNAMIC_EXPRESSION'

    const rendered = renderInspector({
      node,
      componentSchemas: { LocalAssetImage: createAssetImageSchema() },
    })
    await fireEvent.click(screen.getByRole('button', { name: '替换图片' }))

    expect(rendered.emitted()['set-value']).toBeUndefined()
  })

  it('可定位脚本数组仍属于动态图片 prop，专用检查器不得生成实例写回', async () => {
    const node = createAssetImageNode()
    const nameBinding = node.bindings.find(binding => binding.binding_id === 'binding-name')!
    nameBinding.expression = 'item.imageName'
    nameBinding.source = {
      kind: 'script-array-item',
      collection_name: 'items',
      collection_kind: 'const-array',
      item_alias: 'item',
      member: 'imageName',
      key_member: 'id',
      locations: [{
        index: 0,
        key: 'hero',
        value: 'hero-old',
        source_range: { start: 2, end: 8 },
        editable: true,
      }],
    }

    const rendered = render(PageVisualEditPropertyInspector, {
      props: {
        node,
        selectedBindingId: 'binding-name',
        selectedInstancePath: [{ loopNodeId: 'node-loop', key: 'hero', index: 0 }],
        loopNodeId: 'node-loop',
        catalog: { version: 1, groups: [] },
        componentSchemas: { LocalAssetImage: createAssetImageSchema() },
        jsonSources: [],
        pendingOperations: [],
        workspaceId: 7,
      },
      global: {
        stubs: {
          PageVisualEditAssetImageInspector: defineComponent({
            emits: ['set-value'],
            template: '<button type="button" aria-label="尝试修改动态图片" @click="$emit(\'set-value\', { bindingId: \'binding-name\', value: \'hero-new\' })" />',
          }),
        },
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: '尝试修改动态图片' }))
    expect(rendered.emitted()['set-value']).toBeUndefined()
  })
})

/** 渲染属性面板，并用主动发事件的专用检查器 stub 验证父层安全收窄。 */
function renderInspector(options: {
  node: PageVisualEditNode
  componentSchemas: Record<string, PageVisualEditComponentSchema>
}) {
  return render(PageVisualEditPropertyInspector, {
    props: {
      node: options.node,
      selectedBindingId: 'binding-name',
      selectedInstancePath: [],
      loopNodeId: '',
      catalog: {
        version: 1,
        groups: [{
          key: 'radius',
          label: '圆角',
          options: [
            { class_name: 'rounded-lg', label: '大圆角' },
            { class_name: 'rounded-xl', label: '超大圆角' },
          ],
        }],
      },
      componentSchemas: options.componentSchemas,
      jsonSources: [],
      pendingOperations: [],
      workspaceId: 7,
    },
    global: {
      stubs: {
        PageVisualEditAssetImageInspector: defineComponent({
          props: ['workspaceId', 'fields', 'style'],
          emits: ['select', 'set-value', 'set-tailwind'],
          template: `
            <div data-testid="asset-image-inspector" :data-workspace-id="workspaceId">
              <button type="button" aria-label="替换图片" @click="$emit('set-value', { bindingId: 'binding-name', value: 'hero-new' })" />
              <button type="button" aria-label="修改填充" @click="$emit('set-value', { bindingId: 'binding-fit', value: 'cover' })" />
              <button type="button" aria-label="修改图片框圆角" @click="$emit('set-tailwind', { bindingId: 'binding-class', group: 'radius', className: 'rounded-xl' })" />
              <button type="button" aria-label="尝试写入图片 object-fit" @click="$emit('set-tailwind', { bindingId: 'binding-class', group: 'object-fit', className: 'object-cover' })" />
            </div>
          `,
        }),
        UiSelect: defineComponent({
          props: ['modelValue', 'options'],
          template: '<select><option v-for="option in options" :key="String(option.value)">{{ option.label }}</option></select>',
        }),
      },
    },
  })
}

/** 创建包含所有专用字段和图片框 class 的最小组件节点。 */
function createAssetImageNode(): PageVisualEditNode {
  return {
    node_id: 'node-image',
    kind: 'component',
    tag: 'LocalAssetImage',
    source_range: { start: 10, end: 180 },
    template_actions: { can_duplicate: true, can_delete: true },
    bindings: [
      createPropBinding('name', 'hero-old'),
      createPropBinding('alt', '产品主图'),
      createPropBinding('fit', 'contain'),
      createPropBinding('position', 'center'),
      {
        binding_id: 'binding-class',
        node_id: 'node-image',
        kind: 'class',
        name: 'class',
        value_type: 'string',
        value: 'w-full rounded-lg object-cover',
        source_range: { start: 100, end: 140 },
        editable: true,
        source: { kind: 'template-literal' },
      },
    ],
    children: [],
  }
}

/** 创建一个已有静态字符串 prop binding。 */
function createPropBinding(name: string, value: string): PageVisualEditNode['bindings'][number] {
  return {
    binding_id: `binding-${name}`,
    node_id: 'node-image',
    kind: 'prop',
    name,
    value_type: 'string',
    value,
    source_range: { start: 20, end: 40 },
    editable: true,
    source: { kind: 'template-literal' },
  }
}

/** 创建 Backend 实际下发的 Runtime Kit AssetImage.v1 schema 身份。 */
function createAssetImageSchema(): PageVisualEditComponentSchema {
  return {
    source: 'runtime_kit',
    import_path: '@runtime-kit/public/components/assets/AssetImage.v1.vue',
    component_code: 'AssetImage',
    version_no: 1,
    props: {
      name: { type: 'string', label: '资源名', required: true },
      alt: { type: 'string', label: '替代文本' },
      fit: {
        type: 'select',
        label: '框内填充方式',
        options: [
          { label: 'contain', value: 'contain' },
          { label: 'cover', value: 'cover' },
        ],
      },
      position: { type: 'string', label: '框内图片位置' },
      class: { type: 'string', label: 'Tailwind 类' },
    },
  }
}
