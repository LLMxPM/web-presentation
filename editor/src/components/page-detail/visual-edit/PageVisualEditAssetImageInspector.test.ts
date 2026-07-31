/**
 * 文件功能：验证 AssetImage.v1 专用检查器的资源、替代文本、填充、位置和图片框安全写回。
 */

import { fireEvent, render, screen, within } from '@testing-library/vue'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditAssetImageInspector from './PageVisualEditAssetImageInspector.vue'
import type { PageVisualEditValue } from '@/types/page-visual-edit'

describe('PageVisualEditAssetImageInspector', () => {
  it('应使用业务控件编辑四个静态 prop，并把图片框样式限制在允许组', async () => {
    const rendered = renderAssetImageInspector({
      fields: [
        createField('name', 'hero-old'),
        createField('alt', '旧替代文本'),
        createField('fit', 'contain'),
        createField('position', 'center'),
      ],
      style: createStyle(),
    })

    expect(screen.getByRole('heading', { name: '图片内容' })).toBeInTheDocument()
    expect(screen.getByText('完整显示')).toBeInTheDocument()
    expect(screen.getByText('填满并裁切')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '选择图片资源' }))
    await fireEvent.update(screen.getByRole('textbox', { name: '替代文本' }), '新的替代文本')
    await fireEvent.update(screen.getByRole('combobox', { name: '框内填充' }), 'cover')
    await fireEvent.click(screen.getByRole('radio', { name: '右下' }))
    await fireEvent.click(screen.getByRole('button', { name: '调整图片框圆角' }))

    expect(rendered.emitted()['set-value']?.map(events => events[0])).toEqual([
      { bindingId: 'binding-name', value: 'hero-new' },
      { bindingId: 'binding-alt', value: '新的替代文本' },
      { bindingId: 'binding-fit', value: 'cover' },
      { bindingId: 'binding-position', value: 'right bottom' },
    ])
    expect(rendered.emitted()['set-tailwind']?.[0]?.[0]).toEqual({
      bindingId: 'binding-class',
      group: 'radius',
      className: 'rounded-xl',
    })

    const styleStub = screen.getByTestId('tailwind-style-stub')
    const allowedGroups = styleStub.getAttribute('data-allowed-groups')?.split(',') ?? []
    expect(allowedGroups).toEqual(expect.arrayContaining([
      'width',
      'height',
      'padding',
      'background-color',
      'border-width',
      'border-color',
      'radius',
    ]))
    expect(allowedGroups).not.toContain('object-fit')
    expect(allowedGroups).not.toContain('object-position')
    expect(styleStub).toHaveAttribute('data-common-groups', styleStub.getAttribute('data-allowed-groups'))
  })

  it('应以方向键操作九宫格，并保留未选择前的自定义位置', async () => {
    const rendered = renderAssetImageInspector({
      fields: [
        createField('name', 'hero'),
        createField('alt', '产品主图'),
        createField('fit', 'contain'),
        createField('position', '50% 40%'),
      ],
      style: null,
    })

    expect(screen.getByText('50% 40%')).toBeInTheDocument()
    expect(screen.getByText(/选择上方九宫格后才会替换此值/)).toBeInTheDocument()
    expect(screen.getByText(/没有为该图片声明静态 class/)).toBeInTheDocument()

    const centerButton = screen.getByRole('radio', { name: '居中' })
    centerButton.focus()
    await fireEvent.keyDown(centerButton, { key: 'ArrowRight' })

    expect(screen.getByRole('radio', { name: '右侧居中' })).toHaveFocus()
    expect(rendered.emitted()['set-value']?.at(-1)?.[0]).toEqual({
      bindingId: 'binding-position',
      value: 'right',
    })
  })

  it('缺失或动态 prop 应给出普通说明，且不能伪造 set-value 操作', async () => {
    const rendered = renderAssetImageInspector({
      fields: [{
        ...createField('name', undefined),
        editable: false,
        readonlyMessage: '该图片资源来自动态表达式，需要通过 AI 或高级源码调整。',
      }],
      style: null,
    })

    expect(screen.getByText(/动态表达式/)).toBeInTheDocument()
    expect(screen.getByText(/没有声明静态 alt 属性/)).toBeInTheDocument()
    expect(screen.getByText(/没有声明静态 fit 属性/)).toBeInTheDocument()
    expect(screen.getByText(/没有声明静态 position 属性/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '选择图片资源' })).toBeNull()

    const imageContent = screen.getByRole('region', { name: '图片内容' })
    await fireEvent.click(within(imageContent).getByText(/动态表达式/))
    expect(rendered.emitted()['set-value']).toBeUndefined()
  })

  it('待保存字段应支持恢复规范源码中的原值', async () => {
    const rendered = renderAssetImageInspector({
      fields: [
        {
          ...createField('name', 'hero-new'),
          baselineValue: 'hero-old',
          pending: true,
        },
        createField('alt', '产品主图'),
        createField('fit', 'contain'),
        createField('position', 'center'),
      ],
      style: null,
    })

    await fireEvent.click(screen.getByRole('button', { name: '恢复原值' }))
    expect(rendered.emitted()['set-value']?.[0]?.[0]).toEqual({
      bindingId: 'binding-name',
      value: 'hero-old',
    })
  })

  it('待保存填充方式应显示业务标签的原值与当前值', () => {
    renderAssetImageInspector({
      fields: [
        createField('name', 'hero'),
        createField('alt', '产品主图'),
        {
          ...createField('fit', 'cover'),
          baselineValue: 'contain',
          pending: true,
        },
        createField('position', 'center'),
      ],
      style: null,
    })

    expect(screen.getByText('框内填充：完整显示 → 填满并裁切')).toBeInTheDocument()
  })
})

type AssetImageFieldName = 'name' | 'alt' | 'fit' | 'position'

interface AssetImageFieldView {
  name: AssetImageFieldName
  bindingId: string | null
  value: PageVisualEditValue | undefined
  baselineValue: PageVisualEditValue | undefined
  editable: boolean
  pending: boolean
  readonlyMessage: string
  selected: boolean
  templateLiteralWarning: boolean
}

interface AssetImageStyleView {
  bindingId: string
  editable: boolean
  groups: Array<{
    key: string
    label: string
    selectedClass: string
    baselineClass: string
    options: Array<{ class_name: string; label: string }>
  }>
  pending: boolean
  readonlyMessage: string
  templateLiteralWarning: boolean
  unknownTokens: string[]
}

/** 渲染专用检查器，并用可观察 stub 隔离资源请求与 Tailwind 具体 UI。 */
function renderAssetImageInspector(options: {
  fields: AssetImageFieldView[]
  style: AssetImageStyleView | null
}) {
  return render(PageVisualEditAssetImageInspector, {
    props: {
      workspaceId: 7,
      fields: options.fields,
      style: options.style,
    },
    global: {
      stubs: {
        AssetPicker: defineComponent({
          props: {
            modelValue: { type: [String, Number], default: null },
            workspaceId: { type: Number, default: null },
            assetType: { type: String, required: true },
            valueMode: { type: String, required: true },
          },
          emits: ['update:modelValue'],
          template: `
            <button
              type="button"
              aria-label="选择图片资源"
              :data-workspace-id="workspaceId"
              :data-asset-type="assetType"
              :data-value-mode="valueMode"
              @click="$emit('update:modelValue', 'hero-new')"
            >{{ modelValue }}</button>
          `,
        }),
        UiSelect: defineComponent({
          inheritAttrs: false,
          props: ['modelValue', 'options'],
          emits: ['update:modelValue'],
          template: `
            <select
              v-bind="$attrs"
              :value="modelValue"
              @change="$emit('update:modelValue', $event.target.value)"
            >
              <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          `,
        }),
        PageVisualEditTailwindStyleEditor: defineComponent({
          props: [
            'bindingId',
            'allowedGroupKeys',
            'commonGroupKeys',
          ],
          emits: ['change', 'select'],
          template: `
            <button
              type="button"
              aria-label="调整图片框圆角"
              data-testid="tailwind-style-stub"
              :data-allowed-groups="allowedGroupKeys.join(',')"
              :data-common-groups="commonGroupKeys.join(',')"
              @click="$emit('change', { group: 'radius', className: 'rounded-xl' })"
            />
          `,
        }),
      },
    },
  })
}

/** 创建一个已有静态 prop 的字段视图。 */
function createField(name: AssetImageFieldName, value: PageVisualEditValue | undefined): AssetImageFieldView {
  return {
    name,
    bindingId: `binding-${name}`,
    value,
    baselineValue: value,
    editable: true,
    pending: false,
    readonlyMessage: '此项当前只读。',
    selected: false,
    templateLiteralWarning: false,
  }
}

/** 创建最小图片框样式视图。 */
function createStyle(): AssetImageStyleView {
  return {
    bindingId: 'binding-class',
    editable: true,
    groups: [{
      key: 'radius',
      label: '圆角',
      selectedClass: 'rounded-lg',
      baselineClass: 'rounded-lg',
      options: [{ class_name: 'rounded-xl', label: '大圆角' }],
    }],
    pending: false,
    readonlyMessage: '此项当前只读。',
    templateLiteralWarning: false,
    unknownTokens: ['object-cover'],
  }
}
