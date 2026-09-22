/**
 * 文件用途：验证 LaTeX 渲染组件的默认布局行为，避免公式预览偏离原有居中策略。
 *
 * @vitest-environment jsdom
 */

import { createApp, nextTick, type ComponentPublicInstance } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@runtime-kit/internal/renderers/latex', () => ({
  renderLatexToString: vi.fn(),
}))

import { renderLatexToString } from '@runtime-kit/internal/renderers/latex'
import LatexViewer from './LatexViewer.vue'

const mockedRenderLatexToString = vi.mocked(renderLatexToString)

interface LatexViewerExpose extends ComponentPublicInstance {
  updateFit: () => void
}

/**
 * 等待组件内的异步 MathJax 渲染与 Vue DOM 更新完成。
 */
async function flushRender(): Promise<void> {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

/**
 * 在 jsdom 中补齐布局尺寸，便于测试缩放计算。
 *
 * @param element 目标元素
 * @param metrics 需要覆盖的尺寸
 */
function setElementMetrics(
  element: HTMLElement,
  metrics: Partial<Record<'clientWidth' | 'clientHeight' | 'scrollWidth' | 'scrollHeight' | 'offsetWidth' | 'offsetHeight', number>>,
): void {
  Object.entries(metrics).forEach(([key, value]) => {
    Object.defineProperty(element, key, {
      configurable: true,
      value,
    })
  })
}

/**
 * 在 jsdom 中补齐 getBoundingClientRect 返回值。
 *
 * @param element 目标元素
 * @param rect 需要覆盖的矩形尺寸
 */
function setBoundingRect(element: HTMLElement, rect: Partial<DOMRect>): void {
  const fullRect = {
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: rect.width || 0,
    bottom: rect.height || 0,
    width: rect.width || 0,
    height: rect.height || 0,
    toJSON: () => ({}),
    ...rect,
  }
  Object.defineProperty(element, 'getBoundingClientRect', {
    configurable: true,
    value: () => fullRect,
  })
}

/**
 * 挂载 LatexViewer 并返回常用测试句柄。
 *
 * @param props 组件 props
 */
function mountLatexViewer(props: Record<string, unknown>) {
  const host = document.createElement('div')
  document.body.appendChild(host)

  const app = createApp(LatexViewer, props)
  const vm = app.mount(host) as LatexViewerExpose

  return {
    app,
    host,
    vm,
  }
}

describe('LatexViewer', () => {
  beforeEach(() => {
    mockedRenderLatexToString.mockResolvedValue('<mjx-container><svg /></mjx-container>')
  })

  it('默认应启用整体 contain 适配，且不写入内联表面样式', async () => {
    const { app, host } = mountLatexViewer({ content: '' })
    await nextTick()

    const viewer = host.querySelector<HTMLElement>('.latex-viewer')
    expect(viewer?.style.width).toBe('')
    expect(viewer?.style.cssText).not.toContain('border')
    expect(viewer?.classList.contains('latex-viewer--fit-contain')).toBe(true)

    app.unmount()
    host.remove()
  })

  it('默认 contain 模式下，长公式应通过字号缩小到固定容器内', async () => {
    const { app, host, vm } = mountLatexViewer({
      content: String.raw`\frac{a}{b}`,
      width: '200px',
      height: '100px',
      padding: 0,
    })
    await flushRender()

    const viewer = host.querySelector<HTMLElement>('.latex-viewer')
    const content = host.querySelector<HTMLElement>('.latex-viewer__content')
    expect(viewer).toBeTruthy()
    expect(content).toBeTruthy()

    setElementMetrics(viewer!, { clientWidth: 200, clientHeight: 100 })
    setElementMetrics(content!, {
      scrollWidth: 400,
      scrollHeight: 50,
      offsetWidth: 400,
      offsetHeight: 50,
    })

    vm.updateFit()
    await nextTick()

    expect(content?.style.fontSize).toBe('')
    expect(content?.style.transform).toBe('scale(0.5)')

    app.unmount()
    host.remove()
  })

  it('默认 contain 模式下，短公式应通过字号放大并保持等比', async () => {
    const { app, host, vm } = mountLatexViewer({
      content: 'x^2',
      width: '300px',
      height: '120px',
      padding: 0,
    })
    await flushRender()

    const viewer = host.querySelector<HTMLElement>('.latex-viewer')
    const content = host.querySelector<HTMLElement>('.latex-viewer__content')
    expect(viewer).toBeTruthy()
    expect(content).toBeTruthy()

    setElementMetrics(viewer!, { clientWidth: 300, clientHeight: 120 })
    setElementMetrics(content!, {
      scrollWidth: 100,
      scrollHeight: 40,
      offsetWidth: 100,
      offsetHeight: 40,
    })

    vm.updateFit()
    await nextTick()

    expect(content?.style.fontSize).toBe('')
    expect(content?.style.transform).toBe('scale(3)')

    app.unmount()
    host.remove()
  })

  it('重复刷新 contain 适配时不应叠加上一次缩放结果', async () => {
    const { app, host, vm } = mountLatexViewer({
      content: String.raw`\sum_{i=1}^{n} i`,
      width: '200px',
      height: '100px',
      padding: 0,
    })
    await flushRender()

    const viewer = host.querySelector<HTMLElement>('.latex-viewer')
    const content = host.querySelector<HTMLElement>('.latex-viewer__content')
    const container = host.querySelector<HTMLElement>('mjx-container')
    expect(viewer).toBeTruthy()
    expect(content).toBeTruthy()
    expect(container).toBeTruthy()

    setElementMetrics(viewer!, { clientWidth: 200, clientHeight: 100 })
    setElementMetrics(content!, {
      scrollWidth: 400,
      scrollHeight: 50,
      offsetWidth: 400,
      offsetHeight: 50,
    })
    setElementMetrics(container!, {
      scrollWidth: 400,
      scrollHeight: 50,
      offsetWidth: 400,
      offsetHeight: 50,
    })

    vm.updateFit()
    await nextTick()
    expect(content?.style.transform).toBe('scale(0.5)')

    setBoundingRect(content!, { width: 200, height: 25 })
    setBoundingRect(container!, { width: 200, height: 25 })
    vm.updateFit()
    await nextTick()

    expect(content?.style.transform).toBe('scale(0.5)')

    app.unmount()
    host.remove()
  })

  it('应通过 textColor 控制 MathJax 公式颜色', async () => {
    const { app, host } = mountLatexViewer({
      content: 'x^2',
      textColor: 'var(--formula-color)',
    })
    await flushRender()

    const content = host.querySelector<HTMLElement>('.latex-viewer__content')
    expect(content?.style.color).toBe('var(--formula-color)')

    app.unmount()
    host.remove()
  })

  it('fit=none 时应保留旧的自然尺寸与非缩放布局', async () => {
    const { app, host, vm } = mountLatexViewer({
      content: 'x^2',
      fit: 'none',
      width: 'fit-content',
    })
    await flushRender()

    const viewer = host.querySelector<HTMLElement>('.latex-viewer')
    const content = host.querySelector<HTMLElement>('.latex-viewer__content')
    expect(viewer?.style.width).toBe('fit-content')
    expect(viewer?.classList.contains('latex-viewer--fit-none')).toBe(true)

    vm.updateFit()
    await nextTick()

    expect(content?.style.fontSize).toBe('')
    expect(content?.style.transform).toBe('')

    app.unmount()
    host.remove()
  })
})
