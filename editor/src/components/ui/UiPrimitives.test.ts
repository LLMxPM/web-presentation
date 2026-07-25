/** 文件功能：验证首批 UI Primitive 的状态、表单语义和交互能力。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import UiButton from './button/UiButton.vue'
import UiIconButton from './button/UiIconButton.vue'
import UiFormField from './form-field/UiFormField.vue'
import UiInput from './input/UiInput.vue'
import UiUnitInput from './input/UiUnitInput.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('UiButton', () => {
  it('加载时应禁用按钮并向辅助技术暴露忙碌状态', () => {
    render(UiButton, { props: { loading: true }, slots: { default: '保存' } })

    const button = screen.getByRole('button', { name: '保存' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('应透传调用方 class 并渲染图标插槽', () => {
    render(UiButton, {
      attrs: { class: 'custom-button' },
      slots: { icon: '<span>图标</span>', default: '提交' },
    })

    expect(screen.getByRole('button', { name: '图标提交' })).toHaveClass('custom-button')
  })

  it('应通过 API 支持占满宽度的内容对齐', () => {
    render(UiButton, {
      props: { contentAlign: 'between' },
      slots: { default: '<span>左侧</span><span>右侧</span>' },
    })

    expect(screen.getByRole('button', { name: '左侧右侧' }).firstElementChild).toHaveClass('w-full', 'justify-between')
  })
})

describe('UiIconButton', () => {
  it('必须使用 label 作为可访问名称', () => {
    render(UiIconButton, { props: { label: '关闭' }, slots: { default: '<span>×</span>' } })

    expect(screen.getByRole('button', { name: '关闭' })).toHaveAttribute('title', '关闭')
  })
})

describe('UiFormField 与 UiInput', () => {
  it('应关联标签、描述和错误信息，并回传输入值', async () => {
    const onUpdate = vi.fn()
    render(UiFormField, {
      props: { label: '名称', description: '用于展示', error: '不能为空' },
      slots: {
        default: `<input id="manual-name" aria-describedby="manual-description manual-error" aria-invalid="true" />`,
      },
    })
    expect(screen.getByText('用于展示')).toHaveAttribute('id', expect.stringContaining('-description'))
    expect(screen.getByRole('alert')).toHaveTextContent('不能为空')

    render(UiInput, { props: { modelValue: '', 'onUpdate:modelValue': onUpdate } })
    await fireEvent.update(screen.getAllByRole('textbox')[1], '新名称')
    expect(onUpdate).toHaveBeenCalledWith('新名称')
  })

  it('应支持密码显隐和多行输入', async () => {
    const onUpdate = vi.fn()
    const view = render(UiInput, {
      props: { modelValue: 'secret', type: 'password', passwordToggle: true, 'onUpdate:modelValue': onUpdate },
      attrs: { 'aria-label': '密码' },
    })
    const input = screen.getByLabelText('密码')
    expect(input).toHaveAttribute('type', 'password')
    await fireEvent.click(screen.getByRole('button', { name: '显示密码' }))
    expect(input).toHaveAttribute('type', 'text')
    view.unmount()

    render(UiInput, { props: { modelValue: '', type: 'textarea', rows: 5, 'onUpdate:modelValue': onUpdate }, attrs: { 'aria-label': '说明' } })
    const textarea = screen.getByLabelText('说明')
    expect(textarea.tagName).toBe('TEXTAREA')
    expect(textarea).toHaveAttribute('rows', '5')
    await fireEvent.update(textarea, '新的说明')
    expect(onUpdate).toHaveBeenCalledWith('新的说明')
  })

  it('填充模式应让多行输入占满可用高度并内部滚动', () => {
    render(UiInput, {
      props: { type: 'textarea', textareaMode: 'fill' },
      attrs: { 'aria-label': '正文' },
    })

    const textarea = screen.getByLabelText('正文')
    expect(textarea).toHaveClass('h-full', 'min-h-0', 'flex-1', 'overflow-y-auto', 'resize-none')
    expect(textarea.parentElement).toHaveClass('flex', 'min-h-0', 'flex-1', 'flex-col')
  })
})

describe('UiUnitInput', () => {
  it('应分离展示固定单位并维持带单位字符串契约', async () => {
    const onUpdate = vi.fn()
    render(UiUnitInput, {
      props: {
        modelValue: '20px',
        unit: 'px',
        min: 1,
        max: 200,
        integer: true,
        fallback: 20,
        'onUpdate:modelValue': onUpdate,
      },
      attrs: { 'aria-label': '基础字号' },
    })

    const input = screen.getByLabelText('基础字号')
    expect(input).toHaveValue('20')
    expect(screen.getByText('px')).toBeInTheDocument()

    await fireEvent.update(input, '28')
    expect(onUpdate).toHaveBeenLastCalledWith('28px')

    await fireEvent.update(input, '300')
    await fireEvent.blur(input)
    expect(input).toHaveValue('200')
    expect(onUpdate).toHaveBeenLastCalledWith('200px')
  })
})
