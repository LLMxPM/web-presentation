/**
 * 文件功能：验证样式编辑器的渐进分层、业务文案、字段恢复和允许分组边界。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditTailwindStyleEditor from './PageVisualEditTailwindStyleEditor.vue'

const groups = [
  {
    key: 'font-weight',
    label: '字重',
    selectedClass: 'font-bold',
    baselineClass: 'font-normal',
    options: [
      { class_name: 'font-normal', label: '常规字重' },
      { class_name: 'font-bold', label: '粗体' },
    ],
  },
  {
    key: 'position',
    label: '定位方式',
    selectedClass: 'relative',
    baselineClass: 'relative',
    options: [{ class_name: 'relative', label: '相对定位' }],
  },
  {
    key: 'radius',
    label: '圆角',
    selectedClass: 'rounded-lg',
    baselineClass: 'rounded-lg',
    options: [{ class_name: 'rounded-lg', label: '大圆角' }],
  },
]

const globalStubs = {
  UiTabs: {
    props: ['modelValue', 'items'],
    template: '<div><slot name="common" /><slot name="more" /></div>',
  },
  UiSelect: {
    props: ['modelValue', 'options'],
    inheritAttrs: false,
    template: `
      <select v-bind="$attrs" :value="modelValue">
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    `,
  },
}

/** 使用稳定基础属性渲染样式编辑器。 */
function renderEditor(extraProps: Record<string, unknown> = {}) {
  return render(PageVisualEditTailwindStyleEditor, {
    props: {
      bindingId: 'node:class',
      editable: true,
      groups,
      pending: true,
      readonlyMessage: '',
      templateLiteralWarning: false,
      unknownTokens: ['prose-custom'],
      commonGroupKeys: ['font-weight'],
      ...extraProps,
    },
    global: { stubs: globalStubs },
  })
}

describe('PageVisualEditTailwindStyleEditor', () => {
  it('主流程只展示业务文案，并把类名收进技术详情', () => {
    const { container } = renderEditor()

    expect(screen.getByRole('combobox', { name: '字重' })).toHaveTextContent('粗体')
    expect(screen.queryByText('粗体 · font-bold')).not.toBeInTheDocument()
    expect(screen.getByText('技术详情')).toBeInTheDocument()
    expect(container.querySelector('details')).toHaveTextContent('font-bold')
    expect(container.querySelector('details')).toHaveTextContent('prose-custom')
  })

  it('恢复单个字段时应发出原始 class 值', async () => {
    const rendered = renderEditor()

    await fireEvent.click(screen.getByRole('button', { name: '恢复字重原值' }))

    expect(rendered.emitted().change?.[0]).toEqual([
      { group: 'font-weight', className: 'font-normal' },
    ])
  })

  it('allowedGroupKeys 应限制图片框可编辑组，但保留技术类名', () => {
    const { container } = renderEditor({
      commonGroupKeys: ['radius'],
      allowedGroupKeys: ['radius'],
    })

    expect(screen.getByRole('combobox', { name: '圆角' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '字重' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '定位方式' })).not.toBeInTheDocument()
    expect(container.querySelector('details')).toHaveTextContent('font-bold')
  })
})
