/**
 * 文件功能：验证 UiSelect 将标签关联和 ARIA 属性透传到实际可交互的选择触发器，并保障长文本单行截断。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it } from 'vitest'

import UiSelect from './UiSelect.vue'

describe('UiSelect', () => {
  beforeEach(() => {
    // jsdom 未实现 Pointer Capture API，reka-ui 触发器打开下拉时依赖这些方法。
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', { configurable: true, value: () => false })
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', { configurable: true, value: () => undefined })
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', { configurable: true, value: () => undefined })
    Element.prototype.scrollIntoView = () => {}
  })

  it('应把 id 与可访问属性绑定到 combobox 触发器', () => {
    render(UiSelect, {
      props: {
        modelValue: '',
        options: [{ label: '常规', value: 'normal' }],
        id: 'font-weight-control',
        'aria-label': '字重',
        'aria-describedby': 'font-weight-help',
      },
      global: { stubs: { teleport: true } },
    })

    const trigger = screen.getByRole('combobox', { name: '字重' })
    expect(trigger).toHaveAttribute('id', 'font-weight-control')
    expect(trigger).toHaveAttribute('aria-describedby', 'font-weight-help')
  })

  it('长文本应在触发器与下拉选项中单行截断并提供 title 提示', async () => {
    const longLabel = `key: ${'一个非常长的循环实例标签'.repeat(8)}（第 1 项）`
    render(UiSelect, {
      props: {
        modelValue: 'long',
        options: [{ label: longLabel, value: 'long' }],
        'aria-label': '当前实例',
      },
    })

    const trigger = screen.getByRole('combobox', { name: '当前实例' })
    const valueWrapper = trigger.querySelector('span.truncate')
    expect(valueWrapper).not.toBeNull()
    expect(valueWrapper).toHaveClass('min-w-0', 'flex-1')

    await fireEvent.pointerDown(trigger, { button: 0, pointerType: 'mouse' })
    const option = await screen.findByRole('option', { name: longLabel })
    const optionLabel = option.querySelector('span.truncate')
    expect(optionLabel).not.toBeNull()
    expect(optionLabel).toHaveClass('min-w-0')
    expect(optionLabel).toHaveAttribute('title', longLabel)
  })
})
