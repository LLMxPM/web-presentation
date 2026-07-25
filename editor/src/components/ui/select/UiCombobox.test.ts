/**
 * 文件功能：验证 UiCombobox 的清空、禁用态和显示逻辑。
 * Reka UI 在 JSDOM 中的 portal 渲染不完整，交互测试由业务组件 stub 测试覆盖。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeAll, describe, expect, it } from 'vitest'

import UiCombobox from './UiCombobox.vue'
import type { SelectOption } from '../select'

const contentStubs = {
  ComboboxPortal: { template: '<div><slot /></div>' },
  ComboboxContent: { template: '<div><slot /></div>' },
  ComboboxViewport: { template: '<div><slot /></div>' },
  ComboboxEmpty: { template: '<div><slot /></div>' },
  ComboboxItem: {
    props: ['value', 'disabled'],
    template: '<div role="option"><slot /></div>',
  },
}

const baseOptions: SelectOption[] = [
  { label: '苹果', value: 'apple', description: '红色水果', keywords: ['fruit'] },
  { label: '香蕉', value: 'banana', description: '黄色水果' },
  { label: '西瓜', value: 'watermelon' },
]

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {}
})

function renderCombobox(
  props: Record<string, unknown> = {},
  stubs: Record<string, unknown> = {},
) {
  return render(UiCombobox, {
    props: {
      modelValue: null,
      options: baseOptions,
      ...props,
    },
    global: { stubs: { teleport: true, ...stubs } },
  })
}

describe('UiCombobox', () => {
  it('单选 clearable 点击清空应 emit null', async () => {
    const { emitted } = renderCombobox({ modelValue: 'apple', clearable: true })

    const clearButton = screen.getByTitle('清空选择')
    await fireEvent.pointerDown(clearButton)

    expect(emitted()['update:modelValue']?.[0]).toEqual([null])
  })

  it('多选 clearable 点击清空应 emit 空数组', async () => {
    const { emitted } = renderCombobox({ multiple: true, modelValue: ['apple', 'banana'], clearable: true })

    const clearButton = screen.getByTitle('清空选择')
    await fireEvent.pointerDown(clearButton)

    expect(emitted()['update:modelValue']?.[0]).toEqual([[]])
  })

  it('禁用态不应展示清空按钮', () => {
    renderCombobox({ modelValue: 'apple', clearable: true, disabled: true })

    expect(screen.queryByTitle('清空选择')).not.toBeInTheDocument()
  })

  it('单选已选中时应展示当前选项 label 为 placeholder', () => {
    renderCombobox({ modelValue: 'banana' })

    const input = screen.getByRole('combobox')
    expect(input.getAttribute('placeholder')).toBe('香蕉')
  })

  it('未选中时应展示 placeholder', () => {
    renderCombobox({ placeholder: '请选择水果' })

    const input = screen.getByRole('combobox')
    expect(input.getAttribute('placeholder')).toBe('请选择水果')
  })

  it('多选已选中时应展示标签', () => {
    renderCombobox({ multiple: true, modelValue: ['apple', 'banana'] })

    expect(screen.getByText('苹果')).toBeInTheDocument()
    expect(screen.getByText('香蕉')).toBeInTheDocument()
  })

  it('多选超出 maxVisibleTags 应展示 +N 折叠', () => {
    renderCombobox({
      multiple: true,
      modelValue: ['apple', 'banana', 'watermelon'],
      maxVisibleTags: 2,
    })

    expect(screen.getByText('苹果')).toBeInTheDocument()
    expect(screen.getByText('香蕉')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('点击单选输入区域应展开全部选项且不使用已选文本过滤', async () => {
    renderCombobox({ modelValue: 'banana' }, contentStubs)

    await fireEvent.click(screen.getByRole('combobox'))

    expect(screen.getByText('苹果')).toBeInTheDocument()
    expect(screen.getByText('香蕉')).toBeInTheDocument()
    expect(screen.getByText('西瓜')).toBeInTheDocument()
  })

  it('单选使用普通对勾而不是复选框外观', async () => {
    renderCombobox({ modelValue: 'banana' }, contentStubs)

    await fireEvent.click(screen.getByRole('combobox'))

    const selectedOption = screen.getByRole('option', { name: /香蕉/ })
    expect(selectedOption.querySelector('.border')).toBeNull()
    expect(selectedOption.querySelector('.visible')).not.toBeNull()
  })

  it('多选保留复选框外观', async () => {
    renderCombobox({ multiple: true, modelValue: ['banana'] }, contentStubs)

    await fireEvent.click(screen.getByRole('combobox'))

    const selectedOption = screen.getByRole('option', { name: /香蕉/ })
    expect(selectedOption.querySelector('.border')).not.toBeNull()
  })

  it('compact 尺寸应应用对应样式类', () => {
    const { container } = renderCombobox({ size: 'compact' })

    const anchor = container.querySelector('.h-9')
    expect(anchor).toBeTruthy()
  })
})
