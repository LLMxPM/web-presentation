// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */

/**
 * 文件用途：验证单页预览组件向截图探针暴露 loading、ready 与 error 状态。
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ViewPreview from './ViewPreview.vue'

const mockImportViewModule = vi.hoisted(() => vi.fn())

vi.mock('@/core/utils/config', () => ({
  DEFAULT_PAGE_CONFIG: {
    width: 1920,
    height: 1080,
    baseFontSize: '20px',
    iconDefaultStrokeWidth: 2,
  },
  appPageConfig: {
    value: {
      width: 1920,
      height: 1080,
    },
  },
}))

vi.mock('@/core/utils/view-module', () => ({
  importViewModule: mockImportViewModule,
}))

class MockResizeObserver {
  observe = vi.fn()
  disconnect = vi.fn()
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  mockImportViewModule.mockReset()
  vi.unstubAllGlobals()
})

describe('ViewPreview screenshot state marker', () => {
  it('页面模块尚未返回时应展示加载态且不误报未找到页面', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    const deferred = createDeferred<{ default: { name: string; setup: () => () => null } }>()
    mockImportViewModule.mockReturnValue(deferred.promise)

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/slow.vue' })
    app.mount(host)
    await nextTick()

    expect(host.textContent).toContain('正在加载页面预览')
    expect(host.textContent).not.toContain('未找到可预览页面')
    expect(host.querySelector<HTMLElement>('[data-runtime-view-preview-state]')?.dataset.runtimeViewPreviewState).toBe('loading')

    deferred.resolve({ default: { name: 'SlowPreviewPage', setup: () => () => null } })
    await waitForState(host, 'ready')
    app.unmount()
  })

  it('仅空路径应展示未找到可预览页面', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: '' })
    app.mount(host)

    const marker = await waitForState(host, 'empty')
    expect(marker?.dataset.runtimeViewPreviewMessage).toBe('未找到可预览页面')
    expect(host.textContent).toContain('未找到可预览页面')
    expect(mockImportViewModule).not.toHaveBeenCalled()
    app.unmount()
  })

  it('页面模块加载成功后应标记为 ready', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    mockImportViewModule.mockResolvedValue({
      default: {
        name: 'MockPreviewPage',
        setup: () => () => null,
      },
    })

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/demo.vue' })
    app.mount(host)

    const marker = await waitForState(host, 'ready')

    expect(marker?.dataset.runtimeViewPreviewState).toBe('ready')
    expect(marker?.dataset.runtimeViewPreviewMessage).toBe('')
    const previewSource = host.querySelector<HTMLElement>('.runtime-view-preview-source')
    expect(previewSource?.style.getPropertyValue('--runtime-page-typography-scale')).toBe('')
    expect(previewSource?.style.getPropertyValue('--tw-font-size-base')).toBe('var(--theme-font-size-base, 20px)')
    expect(previewSource?.style.getPropertyValue('--tw-spacing-unit')).toBe('calc(var(--tw-font-size-base) * 0.25)')
    expect(previewSource?.hasAttribute('inert')).toBe(true)
    app.unmount()
  })

  it('交互预览应移除 inert，允许可视化编辑捕获页面节点点击', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    mockImportViewModule.mockResolvedValue({
      default: {
        name: 'InteractivePreviewPage',
        setup: () => () => null,
      },
    })

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/demo.vue', inert: false })

    app.mount(host)
    await waitForState(host, 'ready')

    expect(host.querySelector('.runtime-view-preview-source')?.hasAttribute('inert')).toBe(false)
    app.unmount()
  })

  it('页面模块加载失败后应标记为 error', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    mockImportViewModule.mockRejectedValue(new Error('模块加载失败'))

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/missing.vue' })
    app.mount(host)

    const marker = await waitForState(host, 'error')

    expect(marker?.dataset.runtimeViewPreviewState).toBe('error')
    expect(marker?.dataset.runtimeViewPreviewMessage).toContain('模块加载失败')
    app.unmount()
  })

  it('默认应对预览内容启用 inert，拦截缩略图交互', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    mockImportViewModule.mockResolvedValue({
      default: {
        name: 'MockPreviewPage',
        setup: () => () => null,
      },
    })

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/demo.vue' })
    app.mount(host)

    await waitForState(host, 'ready')
    expect(host.querySelector('.runtime-view-preview-source')?.hasAttribute('inert')).toBe(true)
    app.unmount()
  })

  it('传入 inert=false 时应允许 Editor 主预览选中文字', async () => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    mockImportViewModule.mockResolvedValue({
      default: {
        name: 'MockPreviewPage',
        setup: () => () => null,
      },
    })

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(ViewPreview, { filePath: 'src/views/demo.vue', inert: false })
    app.mount(host)

    await waitForState(host, 'ready')
    expect(host.querySelector('.runtime-view-preview-source')?.hasAttribute('inert')).toBe(false)
    app.unmount()
  })
})

/** 创建可由测试控制完成时机的 Promise。 */
function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

/**
 * 等待组件状态属性变为目标值。
 * @param host 宿主节点
 * @param state 目标状态
 * @returns 状态标记元素
 */
async function waitForState(host: HTMLElement, state: string): Promise<HTMLElement | null> {
  for (let index = 0; index < 10; index += 1) {
    await Promise.resolve()
    await nextTick()
    const marker = host.querySelector<HTMLElement>('[data-runtime-view-preview-state]')
    if (marker?.dataset.runtimeViewPreviewState === state) {
      return marker
    }
  }
  return host.querySelector<HTMLElement>('[data-runtime-view-preview-state]')
}
