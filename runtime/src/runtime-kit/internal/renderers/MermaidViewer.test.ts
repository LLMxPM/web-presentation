/**
 * 文件用途：验证 Mermaid 渲染器不会用内部默认高度覆盖外部 Tailwind class。
 *
 * @vitest-environment jsdom
 */

import { createApp, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import MermaidViewer from './MermaidViewer.vue'

vi.mock('mermaid', () => ({
  default: {
    initialize: () => undefined,
    render: async () => ({
      svg: '<svg viewBox="0 0 200 100"><g><text>Demo</text></g></svg>',
    }),
  },
}))

/**
 * 等待 Mermaid 异步导入、SVG 插入和绘制帧确认完成。
 */
async function waitForMermaidRender(): Promise<void> {
  for (let index = 0; index < 6; index += 1) {
    await new Promise(resolve => window.setTimeout(resolve, 20))
    await nextTick()
  }
}

describe('MermaidViewer', () => {
  it('应允许外部 class 控制容器高度和最小高度', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(MermaidViewer, {
      class: 'w-full h-96 min-h-56 rounded-lg',
    })
    app.mount(host)
    await nextTick()

    const viewer = host.querySelector<HTMLElement>('.mermaid-viewer')
    expect(viewer).toBeTruthy()
    expect(viewer?.classList.contains('h-96')).toBe(true)
    expect(viewer?.classList.contains('min-h-56')).toBe(true)
    expect(viewer?.style.height).toBe('')
    expect(window.getComputedStyle(viewer!).minHeight).not.toBe('200px')

    app.unmount()
    host.remove()
  })

  it('默认应开启放大预览，且尺寸与 DrawioViewer 保持一致', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(MermaidViewer)
    app.mount(host)
    await nextTick()

    host.querySelector<HTMLElement>('.mermaid-viewer')?.click()
    await nextTick()
    await nextTick()

    const previewPanel = document.body.querySelector<HTMLElement>('.cursor-zoom-out')
    expect(previewPanel?.style.width).toBe('calc(100vw - 24px)')
    expect(previewPanel?.style.height).toBe('calc(100vh - 24px)')

    app.unmount()
    host.remove()
    document.body.querySelector('.fixed.inset-0')?.remove()
  })

  it('有 Mermaid 来源时初始状态应为 loading', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(MermaidViewer, {
      content: 'flowchart TD\n  A --> B',
    })
    app.mount(host)
    await nextTick()

    expect(host.querySelector<HTMLElement>('.mermaid-viewer')?.dataset.runtimeMermaidState).toBe('loading')

    app.unmount()
    host.remove()
  })

  it('渲染完成后应将 Mermaid 状态标记为 ready', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(MermaidViewer, {
      content: 'flowchart TD\n  A --> B',
      height: 240,
    })
    app.mount(host)

    await waitForMermaidRender()

    expect(host.querySelector<SVGSVGElement>('.mermaid-viewer svg')).not.toBeNull()
    expect(host.querySelector<HTMLElement>('.mermaid-viewer')?.dataset.runtimeMermaidState).toBe('ready')

    app.unmount()
    host.remove()
  })
})
