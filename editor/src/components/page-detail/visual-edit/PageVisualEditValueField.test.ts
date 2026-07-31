/**
 * 文件功能：验证普通可视化字段的语义化变更摘要、技术详情与单字段恢复能力。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditValueField from './PageVisualEditValueField.vue'

/** 渲染一个可编辑字符串字段。 */
function renderValueField(extraProps: Record<string, unknown> = {}) {
  return render(PageVisualEditValueField, {
    props: {
      controlId: 'asset-alt',
      controlType: 'string',
      baselineValue: '原始说明',
      baselineRichText: null,
      editable: true,
      effectiveValue: '新的说明',
      kind: 'prop',
      label: '替代文本',
      optionIndex: -1,
      options: [],
      pending: true,
      propName: 'alt',
      readonlyMessage: '',
      required: false,
      selected: false,
      templateLiteralWarning: false,
      ...extraProps,
    },
    global: {
      stubs: {
        UiInput: {
          props: ['modelValue', 'inputId'],
          template: '<input :id="inputId" :value="modelValue" />',
        },
        PageVisualEditRichTextEditor: {
          props: ['modelValue'],
          template: '<div>{{ modelValue }}</div>',
        },
      },
    },
  })
}

describe('PageVisualEditValueField', () => {
  it('应显示原值到当前值的摘要，并可恢复单个字段', async () => {
    const rendered = renderValueField()

    expect(screen.getByText(/替代文本：原始说明/)).toHaveTextContent('→ 新的说明')
    await fireEvent.click(screen.getByRole('button', { name: '恢复替代文本原值' }))

    expect(rendered.emitted()['set-value']?.[0]).toEqual(['原始说明'])
  })

  it('源码属性名应只出现在技术详情中', () => {
    const { container } = renderValueField()

    expect(screen.getByText('技术详情')).toBeInTheDocument()
    expect(container.querySelector('details')).toHaveTextContent('源码属性：alt')
  })

  it('富文本恢复应使用原始 HTML', async () => {
    const rendered = renderValueField({
      kind: 'rich_text',
      controlType: 'textarea',
      baselineValue: undefined,
      baselineRichText: '<strong>原文</strong>',
      effectiveValue: '<strong>新文</strong>',
      label: '段落内容',
      propName: null,
    })

    await fireEvent.click(screen.getByRole('button', { name: '恢复段落内容原值' }))

    expect(rendered.emitted()['set-rich-text']?.[0]).toEqual(['<strong>原文</strong>'])
  })
})
