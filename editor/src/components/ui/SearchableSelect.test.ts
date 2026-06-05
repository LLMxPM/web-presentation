/**
 * 文件功能：验证通用下拉选择组件的搜索过滤、单选与多选输出行为。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SearchableSelect from './SearchableSelect.vue'

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('SearchableSelect', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

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

  it('向上展开时应按实际面板高度贴近触发器', async () => {
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 })
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 })
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.classList.contains('fixed')) {
        return createRect({ top: 0, left: 0, width: 320, height: 180 })
      }
      return createRect({ top: 420, left: 40, width: 320, height: 40 })
    })

    render(SearchableSelect, {
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

    const dropdown = await findDropdownElement('浅海蓝')
    await waitFor(() => {
      expect(dropdown.style.top).toBe('232px')
    })
  })
})

/**
 * 构造测试用 DOMRect，便于稳定模拟触发器与浮层尺寸。
 */
function createRect(rect: { top: number; left: number; width: number; height: number }): DOMRect {
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
    right: rect.left + rect.width,
    bottom: rect.top + rect.height,
    x: rect.left,
    y: rect.top,
    toJSON: () => ({}),
  } as DOMRect
}

/**
 * 从 Teleport 到 body 的节点中定位当前展开的下拉面板。
 */
async function findDropdownElement(optionText: string): Promise<HTMLElement> {
  await screen.findByText(optionText)
  const dropdown = Array.from(document.body.querySelectorAll('div')).find(element => (
    element.classList.contains('fixed') && element.textContent?.includes(optionText)
  ))
  expect(dropdown).toBeTruthy()
  return dropdown as HTMLElement
}
