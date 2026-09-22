// @vitest-environment jsdom

/**
 * 文件用途：验证页面截图服务在运行时布局中只捕获真实页面节点，避免截入底栏缩略图和布局容器。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PageCaptureService } from './PageCaptureService'

const mockSnapdom = vi.hoisted(() => vi.fn())

vi.mock('@zumer/snapdom', () => ({
  snapdom: mockSnapdom,
}))

vi.mock('../utils/dom', () => ({
  waitForPageLoad: vi.fn(() => Promise.resolve()),
  waitForImages: vi.fn(() => Promise.resolve()),
  getPageDimensions: vi.fn(() => ({ width: 1920, height: 1080 })),
}))

vi.mock('@/core/utils/config', () => ({
  appPageConfig: {
    value: {
      width: 1920,
      height: 1080,
    },
  },
}))

const drawImage = vi.fn()
const clearRect = vi.fn()
const fillRect = vi.fn()
const getImageData = vi.fn(() => ({
  data: new Uint8ClampedArray([255, 255, 255, 255]),
}))

beforeEach(() => {
  document.body.innerHTML = ''
  mockSnapdom.mockReset()
  mockSnapdom.mockResolvedValue({
    toPng: vi.fn(async () => createLoadedImage()),
  })
  drawImage.mockClear()
  clearRect.mockClear()
  fillRect.mockClear()
  getImageData.mockClear()

  vi.spyOn(window.HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
    clearRect,
    drawImage,
    fillRect,
    getImageData,
    imageSmoothingEnabled: true,
    imageSmoothingQuality: 'high',
  } as unknown as CanvasRenderingContext2D))
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  delete window.__RUNTIME_PREVIEW_CONTEXT__
  delete window.__RUNTIME_PRELOADED_CONFIG__
})

describe('PageCaptureService', () => {
  it('底部缩略图模式下应捕获运行时页面源节点，而不是布局容器', async () => {
    renderRuntimeLayout(`
      <div class="runtime-page-print-source" data-runtime-route-path="/current" style="width: 1920px; height: 1080px;">
        <h3 style="width: 465px; height: 48px; line-height: 48px;">AI创作PPT的基础框架</h3>
      </div>
    `)

    const service = new PageCaptureService()
    await service.captureCurrentPage({ routePath: '/current', scale: 2 })

    const capturedElement = mockSnapdom.mock.calls[0][0] as HTMLElement

    expect(capturedElement.className).toBe('runtime-export-capture-sandbox')
    expect(capturedElement.textContent).toContain('AI创作PPT的基础框架')
    expect(capturedElement.textContent).not.toContain('底部缩略图')
    expect(capturedElement.textContent).not.toContain('画布上一页')
    expect(capturedElement.querySelector('h3')?.style.whiteSpace).toBe('nowrap')
    expect(capturedElement.querySelector('h3')?.style.wordBreak).toBe('keep-all')
    expect(document.querySelector('.runtime-export-capture-sandbox')).toBeNull()
  })

  it('存在多个页面源时应按 routePath 捕获目标路由', async () => {
    renderRuntimeLayout(`
      <div class="runtime-page-print-source" data-runtime-route-path="/page-1" style="width: 1920px; height: 1080px;">
        <section>第一页内容</section>
      </div>
      <div class="runtime-page-print-source" data-runtime-route-path="/page-2" style="width: 1920px; height: 1080px;">
        <section>第二页内容</section>
      </div>
    `)

    const service = new PageCaptureService()
    await service.captureCurrentPage({ routePath: '/page-2' })

    const capturedElement = mockSnapdom.mock.calls[0][0] as HTMLElement
    const clonedSource = capturedElement.querySelector<HTMLElement>('.runtime-page-print-source')

    expect(clonedSource?.dataset.runtimeRoutePath).toBe('/page-2')
    expect(capturedElement.textContent).toContain('第二页内容')
    expect(capturedElement.textContent).not.toContain('第一页内容')
  })

  it('创建截图沙箱时应复制 canvas 位图到克隆节点', async () => {
    renderRuntimeLayout(`
      <div class="runtime-page-print-source" data-runtime-route-path="/chart" style="width: 1920px; height: 1080px;">
        <canvas class="echarts-canvas" width="120" height="80" style="width: 120px; height: 80px;"></canvas>
      </div>
    `)

    const sourceCanvas = document.querySelector<HTMLCanvasElement>('.echarts-canvas')
    const service = new PageCaptureService()
    await service.captureCurrentPage({ routePath: '/chart' })

    expect(sourceCanvas).not.toBeNull()
    expect(drawImage).toHaveBeenCalledWith(sourceCanvas, 0, 0)
  })

  it('截图沙箱中应隐藏正文滚动容器的滚动条', async () => {
    renderRuntimeLayout(`
      <div class="runtime-page-print-source" data-runtime-route-path="/scrollbar" style="width: 1920px; height: 1080px;">
        <main class="content-page-body" style="width: 100%; height: 720px; overflow: auto;">
          <div style="width: 1940px; height: 760px;">正文内容</div>
        </main>
      </div>
    `)

    const service = new PageCaptureService()
    await service.captureCurrentPage({ routePath: '/scrollbar' })

    const capturedElement = mockSnapdom.mock.calls[0][0] as HTMLElement
    const clonedBody = capturedElement.querySelector<HTMLElement>('.content-page-body')

    expect(clonedBody?.style.overflowX).toBe('hidden')
    expect(clonedBody?.style.overflowY).toBe('hidden')
    expect(clonedBody?.style.getPropertyValue('scrollbar-width')).toBe('none')
  })

  it('截图沙箱中应将 manifest 图片资源改写为 Runtime 代理地址', async () => {
    const assetUrl = 'https://backend.example.com/public/assets/1/hash-cover.png'
    let capturedImageSrc = ''
    let capturedBackgroundImage = ''
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant_1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/cover' },
      assetBaseUrl: 'https://backend.example.com/public/assets/1',
      traceId: 'req-1',
    }
    window.__RUNTIME_PRELOADED_CONFIG__ = {
      manifest: {
        artifact_id: 'artifact-1',
        tenant_id: 'tenant_1',
        preview_kind: 'project',
        owner_scope: {
          scope_type: 'project',
          workspace_id: '1',
          project_id: '2',
        },
        entry_descriptor: { entry_type: 'route', route: '/cover' },
        asset_base_url: 'https://backend.example.com/public/assets/1',
        modules: {},
        assets: {
          cover: 'hash-cover.png',
        },
        asset_metadata: {
          cover: {
            file_hash: 'hash-cover.png',
            render_type: 'image',
          },
        },
      },
    }
    renderRuntimeLayout(`
      <div class="runtime-page-print-source" data-runtime-route-path="/cover" style="width: 1920px; height: 1080px;">
        <img class="cover-image" src="${assetUrl}" />
        <section class="cover-bg" style="width: 100px; height: 100px; background-image: url('${assetUrl}');"></section>
      </div>
    `)

    const proxyUrl = 'https://runtime.example.com/__runtime-snapdom-resource-proxy?artifactId=artifact-1&token=preview-token&url='
    mockSnapdom.mockImplementationOnce(async (element: HTMLElement) => {
      capturedImageSrc = element.querySelector<HTMLImageElement>('.cover-image')?.src || ''
      capturedBackgroundImage = element.querySelector<HTMLElement>('.cover-bg')?.style.backgroundImage || ''
      return {
        toPng: vi.fn(async () => createLoadedImage()),
      }
    })
    const service = new PageCaptureService()
    await service.captureCurrentPage({ routePath: '/cover', proxyUrl })

    const proxiedImageUrl = new URL(capturedImageSrc)

    expect(proxiedImageUrl.origin).toBe('https://runtime.example.com')
    expect(proxiedImageUrl.pathname).toBe('/__runtime-snapdom-resource-proxy')
    expect(proxiedImageUrl.searchParams.get('artifactId')).toBe('artifact-1')
    expect(proxiedImageUrl.searchParams.get('token')).toBe('preview-token')
    expect(proxiedImageUrl.searchParams.get('url')).toBe(assetUrl)
    expect(capturedBackgroundImage).toContain('https://runtime.example.com/__runtime-snapdom-resource-proxy')
    expect(capturedBackgroundImage).toContain(encodeURIComponent(assetUrl))
  })
})

/**
 * 构造底部缩略图模式的运行时布局。
 * @param pageSourceHtml 页面源节点 HTML
 */
function renderRuntimeLayout(pageSourceHtml: string): void {
  document.body.innerHTML = `
    <div class="responsive-layout">
      <main class="main-content main-content--bottom-preview">
        <div class="page-content-wrapper">
          <div class="canvas-navigation-buttons">画布上一页</div>
          ${pageSourceHtml}
        </div>
      </main>
      <div class="bottom-preview-wrapper">底部缩略图</div>
    </div>
  `
}

/**
 * 创建已加载的图片元素，模拟 snapdom 的 PNG 输出。
 */
function createLoadedImage(): HTMLImageElement {
  const image = document.createElement('img')
  Object.defineProperties(image, {
    complete: { value: true },
    naturalWidth: { value: 3840 },
    naturalHeight: { value: 2160 },
  })
  return image
}
