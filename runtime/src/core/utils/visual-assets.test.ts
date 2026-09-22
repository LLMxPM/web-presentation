// @vitest-environment jsdom

/**
 * 文件用途：验证编辑器截图视觉资源就绪探针的图片、背景图、字体与单页状态等待行为。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  extractCssUrls,
  registerEditorVisualAssetProbe,
  waitForEditorVisualAssets,
} from './visual-assets'

beforeEach(() => {
  document.documentElement.innerHTML = '<head></head><body></body>'
  Object.defineProperty(Document.prototype, 'fonts', {
    value: undefined,
    configurable: true,
  })
})

afterEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
  Reflect.deleteProperty(document, 'fonts')
  Reflect.deleteProperty(document, 'getAnimations')
  Reflect.deleteProperty(Document.prototype, 'fonts')
  vi.unstubAllGlobals()
})

describe('visual asset readiness probe', () => {
  it('应解析 CSS background-image 中的 URL', () => {
    expect(extractCssUrls('url("https://assets.example/bg.png"), linear-gradient(red, blue)')).toEqual([
      'https://assets.example/bg.png',
    ])
    expect(extractCssUrls("url('./cover.png')")).toEqual(['./cover.png'])
  })

  it('应等待 img 加载后解码', async () => {
    document.body.innerHTML = '<img id="hero" src="https://assets.example/hero.png" />'
    const image = document.querySelector<HTMLImageElement>('#hero')!
    let loaded = false
    Object.defineProperty(image, 'complete', { get: () => loaded, configurable: true })
    Object.defineProperty(image, 'naturalWidth', { get: () => (loaded ? 120 : 0), configurable: true })
    Object.defineProperty(image, 'naturalHeight', { get: () => (loaded ? 80 : 0), configurable: true })
    image.decode = vi.fn().mockResolvedValue(undefined)
    window.setTimeout(() => {
      loaded = true
      image.dispatchEvent(new Event('load'))
    }, 0)

    const result = await waitForEditorVisualAssets({ timeoutMs: 1000 })

    expect(result.ok, JSON.stringify(result)).toBe(true)
    expect(result.total).toBe(1)
    expect(result.loaded).toBe(1)
    expect(image.decode).toHaveBeenCalled()
  })

  it('应等待字体 ready promise 完成', async () => {
    Object.defineProperty(Document.prototype, 'fonts', {
      value: {
        ready: new Promise(resolve => window.setTimeout(resolve, 0)),
      },
      configurable: true,
    })

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(true)
    expect(result.pending).toHaveLength(0)
  })

  it('应把未完成的 img 标记为超时 pending', async () => {
    document.body.innerHTML = '<img id="slow" src="https://assets.example/slow.png" />'
    const image = document.querySelector<HTMLImageElement>('#slow')!
    Object.defineProperty(image, 'complete', { value: false, configurable: true })
    Object.defineProperty(image, 'naturalWidth', { value: 0, configurable: true })
    Object.defineProperty(image, 'naturalHeight', { value: 0, configurable: true })

    const result = await waitForEditorVisualAssets({ timeoutMs: 20 })

    expect(result.ok).toBe(false)
    expect(result.timedOut).toBe(true)
    expect(result.pending[0]).toMatchObject({
      type: 'image',
      url: 'https://assets.example/slow.png',
    })
  })

  it('应把 img error 标记为 failed', async () => {
    document.body.innerHTML = '<img id="broken" src="https://assets.example/broken.png" />'
    const image = document.querySelector<HTMLImageElement>('#broken')!
    Object.defineProperty(image, 'complete', { value: false, configurable: true })
    Object.defineProperty(image, 'naturalWidth', { value: 0, configurable: true })
    Object.defineProperty(image, 'naturalHeight', { value: 0, configurable: true })
    window.setTimeout(() => image.dispatchEvent(new Event('error')), 0)

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(false)
    expect(result.failed[0]).toMatchObject({
      type: 'image',
      url: 'https://assets.example/broken.png',
    })
  })

  it('应等待 CSS 背景图 URL 加载完成', async () => {
    document.body.innerHTML = '<div id="card" style="background-image: url(https://assets.example/bg.png)"></div>'
    vi.stubGlobal('Image', createMockImageClass('load'))

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(true)
    expect(result.total).toBe(1)
    expect(result.loaded).toBe(1)
  })

  it('应等待 ViewPreview 状态从 loading 变为 ready', async () => {
    document.body.innerHTML = '<div id="preview" data-runtime-view-preview-state="loading"></div>'
    const preview = document.querySelector<HTMLElement>('#preview')!
    window.setTimeout(() => {
      preview.dataset.runtimeViewPreviewState = 'ready'
    }, 0)

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(true)
    expect(result.pending).toHaveLength(0)
  })

  it('应等待 Draw.io 图表状态从 loading 变为 ready', async () => {
    document.body.innerHTML = '<div id="drawio" data-runtime-drawio-state="loading"></div>'
    const drawio = document.querySelector<HTMLElement>('#drawio')!
    window.setTimeout(() => {
      drawio.dataset.runtimeDrawioState = 'ready'
    }, 0)

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(true)
    expect(result.total).toBe(1)
    expect(result.loaded).toBe(1)
  })

  it('应把未完成的 Draw.io 图表标记为超时 pending', async () => {
    document.body.innerHTML = '<div data-runtime-drawio-state="loading" data-runtime-drawio-message="渲染中"></div>'

    const result = await waitForEditorVisualAssets({ timeoutMs: 20 })

    expect(result.ok).toBe(false)
    expect(result.timedOut).toBe(true)
    expect(result.pending[0]).toMatchObject({
      type: 'drawio',
      message: '渲染中',
    })
  })

  it('应把 Draw.io 渲染错误标记为 failed', async () => {
    document.body.innerHTML = '<div data-runtime-drawio-state="error" data-runtime-drawio-message="SVG 生成失败"></div>'

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(false)
    expect(result.failed[0]).toMatchObject({
      type: 'drawio',
      message: 'SVG 生成失败',
    })
  })

  it('应等待 Mermaid 图表状态从 loading 变为 ready', async () => {
    document.body.innerHTML = '<div id="mermaid" data-runtime-mermaid-state="loading"></div>'
    const mermaid = document.querySelector<HTMLElement>('#mermaid')!
    window.setTimeout(() => {
      mermaid.dataset.runtimeMermaidState = 'ready'
    }, 0)

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(true)
    expect(result.total).toBe(1)
    expect(result.loaded).toBe(1)
  })

  it('应把未完成的 Mermaid 图表标记为超时 pending', async () => {
    document.body.innerHTML = '<div data-runtime-mermaid-state="loading" data-runtime-mermaid-message="渲染中"></div>'

    const result = await waitForEditorVisualAssets({ timeoutMs: 20 })

    expect(result.ok).toBe(false)
    expect(result.timedOut).toBe(true)
    expect(result.pending[0]).toMatchObject({
      type: 'mermaid',
      message: '渲染中',
    })
  })

  it('应把 Mermaid 渲染错误标记为 failed', async () => {
    document.body.innerHTML = '<div data-runtime-mermaid-state="error" data-runtime-mermaid-message="语法错误"></div>'

    const result = await waitForEditorVisualAssets({ timeoutMs: 100 })

    expect(result.ok).toBe(false)
    expect(result.failed[0]).toMatchObject({
      type: 'mermaid',
      message: '语法错误',
    })
  })

  it('应等待有限次动画结束后再返回', async () => {
    let finished = false
    const animation = createFakeAnimation({
      finished: new Promise(resolve => window.setTimeout(() => {
        finished = true
        resolve()
      }, 20)),
    })
    stubDocumentAnimations([animation])

    const result = await waitForEditorVisualAssets({ timeoutMs: 1000 })

    expect(finished).toBe(true)
    expect(result.ok).toBe(true)
    expect(result.timedOut).toBe(false)
  })

  it('应跳过无限循环动画不阻塞截图', async () => {
    const animation = createFakeAnimation({ iterations: Infinity })
    stubDocumentAnimations([animation])

    const result = await waitForEditorVisualAssets({ timeoutMs: 1000 })

    expect(result.ok).toBe(true)
    expect(result.waitedMs).toBeLessThan(500)
  })

  it('有限动画等待超时不应计入失败', async () => {
    const animation = createFakeAnimation({})
    stubDocumentAnimations([animation])

    const result = await waitForEditorVisualAssets({ timeoutMs: 50 })

    expect(result.ok).toBe(true)
    expect(result.timedOut).toBe(false)
    expect(result.pending).toHaveLength(0)
  })

  it('应注册全局视觉资源等待函数', () => {
    registerEditorVisualAssetProbe()

    expect(window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__).toBe(waitForEditorVisualAssets)
  })
})

/**
 * 构造可控的动画对象替身，用于模拟有限/无限次动画。
 * @param options 动画行为配置
 * @returns Animation 替身
 */
function createFakeAnimation(options: {
  playState?: AnimationPlayState
  iterations?: number
  finished?: Promise<void>
}): Animation {
  return {
    playState: options.playState ?? 'running',
    effect: {
      getTiming: () => ({ iterations: options.iterations ?? 1 }),
    },
    finished: options.finished ?? new Promise<void>(() => {}),
  } as unknown as Animation
}

/**
 * 在 jsdom 上注入 document.getAnimations 替身。
 * @param animations 返回的动画列表
 */
function stubDocumentAnimations(animations: Animation[]): void {
  Object.defineProperty(document, 'getAnimations', {
    value: () => animations,
    configurable: true,
  })
}

/**
 * 构造可控的 Image 类，用于模拟背景图加载结果。
 * @param eventName 触发的图片事件
 * @returns Image 构造函数替身
 */
function createMockImageClass(eventName: 'load' | 'error') {
  return class MockImage extends EventTarget {
    private value = ''

    get src(): string {
      return this.value
    }

    set src(nextValue: string) {
      this.value = nextValue
      window.setTimeout(() => this.dispatchEvent(new Event(eventName)), 0)
    }
  }
}
