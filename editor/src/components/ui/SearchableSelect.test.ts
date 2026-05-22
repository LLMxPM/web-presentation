/**
 * 文件功能：验证通用下拉选择组件的搜索过滤、单选与多选输出行为。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import SearchableSelect from './SearchableSelect.vue'

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('SearchableSelect', () => {
  it('应支持搜索过滤并输出单选结果', async () => {
    const view = render(SearchableSelect, {
      props: {
        modelValue: null,
        options: [
          { label: '浅海蓝', value: 'lightblue', description: 'lightblue' },
          { label: '深海蓝', value: 'deepblue', description: 'deepblue' },
        ],
        placeholder: '请选择主题',
      },
    })

    await fireEvent.click(screen.getByText('请选择主题'))
    await fireEvent.update(screen.getByPlaceholderText('搜索选项'), '浅海')

    expect(screen.getByText('浅海蓝')).toBeInTheDocument()
    expect(screen.queryByText('深海蓝')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByText('浅海蓝'))

    expect(getEmittedEvents(view)['update:modelValue']?.[0]?.[0]).toBe('lightblue')
  })

  it('应支持多选并按点击顺序返回值数组', async () => {
    const view = render(SearchableSelect, {
      props: {
        modelValue: [],
        multiple: true,
        options: [
          { label: 'Logo', value: 'logo' },
          { label: '反色 Logo', value: 'invert-logo' },
          { label: '标题字体', value: 'heading-font' },
        ],
        placeholder: '请选择资源',
      },
    })

    await fireEvent.click(screen.getByText('请选择资源'))
    await fireEvent.click(screen.getByText('Logo'))

    expect(getEmittedEvents(view)['update:modelValue']?.[0]?.[0]).toEqual(['logo'])

    await view.rerender({
      modelValue: ['logo'],
      multiple: true,
      options: [
        { label: 'Logo', value: 'logo' },
        { label: '反色 Logo', value: 'invert-logo' },
        { label: '标题字体', value: 'heading-font' },
      ],
      placeholder: '请选择资源',
    })

    await fireEvent.click(screen.getByText('反色 Logo'))

    const events = getEmittedEvents(view)['update:modelValue'] ?? []
    expect(events[events.length - 1]?.[0]).toEqual(['logo', 'invert-logo'])
  })
})
