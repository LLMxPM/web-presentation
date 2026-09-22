// @vitest-environment jsdom

/**
 * 文件用途：验证 PPTX DOM 转换器对外部资源、背景图、视频封面和复杂 CSS 的转换逻辑。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PptxGradientFillInstruction } from './PPTXDomConverter'
import { convert, createSlideMock, decodeSvgDataUrl, stubDetachedImageSize } from './PPTXDomConverter.test-support'

/**
 * 创建可断言调用目标的局部截图 mock。
 */
function createCaptureElementAsPngMock() {
  return vi.fn(async (element: HTMLElement) => {
    void element
    return 'data:image/png;base64,capture'
  })
}

describe('PPTXDomConverter', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    delete window.__RUNTIME_PREVIEW_CONTEXT__
    delete window.__RUNTIME_PREVIEW_TOKEN__
    delete window.__RUNTIME_PRELOADED_CONFIG__
    delete window.__RUNTIME_PUBLIC_BASE_URL__
  })

  it('应跳过 Connector 的 marker path，并按真实连线路径紧边界导出', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="position: relative; width: 600px; height: 300px;">
          <svg class="connector-svg" style="position: absolute; left: 0; top: 0; width: 100%; height: 100%; overflow: visible;">
            <defs>
              <marker id="arrow-end-test">
                <path d="M0,0 L0,6 L9,3 z" fill="#2563eb"></path>
              </marker>
            </defs>
            <path d="M 300 50 L 300 250" stroke="#2563eb" stroke-width="2" fill="none" marker-end="url(#arrow-end-test)"></path>
          </svg>
        </section>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const containerElement = document.querySelector('section') as HTMLElement
    const svgElement = document.querySelector('.connector-svg') as SVGSVGElement
    const pathElement = svgElement.querySelectorAll('path')[1] as SVGPathElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 192, 108))
    vi.spyOn(containerElement, 'getBoundingClientRect').mockReturnValue(createRect(10, 12, 60, 30))
    vi.spyOn(svgElement, 'getBoundingClientRect').mockReturnValue(createRect(10, 12, 60, 30))
    vi.spyOn(pathElement, 'getBoundingClientRect').mockReturnValue(createRect(40, 17, 0, 0))
    Object.defineProperty(pathElement, 'getBBox', {
      value: vi.fn(() => ({
        x: 300,
        y: 50,
        width: 0,
        height: 200,
      })),
      configurable: true,
    })

    await convert(slide)
    const imageOptions = slide.addImage.mock.calls[0]?.[0] as {
      x: number
      y: number
      w: number
      h: number
      data: string
    }
    const serializedSvg = decodeSvgDataUrl(imageOptions.data)
    const inchPerPx = 13.333 / 192

    expect(imageOptions.x).toBeCloseTo(38.8 * inchPerPx, 4)
    expect(imageOptions.y).toBeCloseTo(15.8 * (7.5 / 108), 4)
    expect(imageOptions.w).toBeCloseTo(2.4 * inchPerPx, 4)
    expect(imageOptions.h).toBeCloseTo(22.4 * (7.5 / 108), 3)
    expect(serializedSvg).toContain('viewBox="288 38 24 224"')
    expect(serializedSvg).toContain('width="24"')
    expect(serializedSvg).toContain('height="224"')
  })

  it('应读取外部 SVG 源文件并作为 SVG 源嵌入', async () => {
    const slide = createSlideMock()
    const svgSource = '<svg viewBox="0 0 120 60"><rect width="120" height="60" fill="#2563eb"/></svg>'
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      headers: {
        get: (name: string) => name.toLowerCase() === 'content-type' ? 'image/svg+xml' : '',
      },
      text: async () => svgSource,
    })))
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <img class="theme-logo" src="/assets/chart.svg" style="width: 320px; height: 160px;" />
      </div>
    `

    const report = await convert(slide)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/chart\.svg$/))
    expect(addImageCall.data).toMatch(/^data:image\/svg\+xml;base64,/)
    expect(decodeSvgDataUrl(addImageCall.data)).toBe(svgSource)
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'svg',
      result: 'svg',
      reason: 'SVG 源文件原样嵌入为可移动缩放图片块',
    }))
  })

  it('应通过 Runtime 代理读取 manifest 图片并内嵌为 data URL', async () => {
    const slide = createSlideMock()
    const assetHash = '5c1add7d570de71de7febd09afb603a16f8f81e5c61a0a2d8b96f4aa9f0a6d1f'
    const assetBaseUrl = 'http://127.0.0.1:8000/public/assets/1'
    const assetUrl = `${assetBaseUrl}/${assetHash}`
    const pngHeader = new Uint8Array([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      expect(String(url)).toContain('__runtime-snapdom-resource-proxy')
      return new Response(pngHeader, {
        headers: {
          'content-type': 'application/octet-stream',
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant_1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/test' },
      assetBaseUrl,
      traceId: 'req-1',
    }
    window.__RUNTIME_PREVIEW_TOKEN__ = 'preview-token'
    window.__RUNTIME_PUBLIC_BASE_URL__ = 'https://runtime.example.com/runtime/'
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
        entry_descriptor: { entry_type: 'route', route: '/test' },
        asset_base_url: assetBaseUrl,
        modules: {},
        assets: {
          'theme/logo.png': assetHash,
        },
        asset_metadata: {
          'theme/logo.png': {
            file_hash: assetHash,
            render_type: 'image',
          },
        },
      },
    }
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <img class="theme-logo" src="${assetUrl}" style="width: 320px; height: 160px; object-fit: contain;" />
      </div>
    `

    const report = await convert(slide)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>
    const fetchedUrl = new URL(String(fetchMock.mock.calls[0]?.[0]))

    expect(fetchedUrl.origin).toBe('https://runtime.example.com')
    expect(fetchedUrl.pathname).toBe('/runtime/__runtime-snapdom-resource-proxy')
    expect(fetchedUrl.searchParams.get('artifactId')).toBe('artifact-1')
    expect(fetchedUrl.searchParams.get('token')).toBe('preview-token')
    expect(fetchedUrl.searchParams.get('url')).toBe(assetUrl)
    expect(addImageCall.path).toBeUndefined()
    expect(addImageCall.data).toBe('data:image/png;base64,iVBORw0KGgo=')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'image',
      result: 'image',
      reason: '图片作为可移动缩放图片块',
    }))
  })

  it('外部图片无法读取时应降级为局部截图', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    const imageUrl = 'https://cdn.example.com/no-cors.png'
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('CORS blocked')
    }))
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <img class="remote-image" src="${imageUrl}" style="width: 320px; height: 160px;" />
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(addImageCall.path).toBeUndefined()
    expect(addImageCall.data).toBe('data:image/png;base64,capture')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'image',
      result: 'screenshot',
      reason: `图片 URL 无法读取，降级为局部截图：${imageUrl}`,
    }))
  })

  it('应将内联 SVG 的 currentColor、描边和文字样式内联到源文件', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <style>
        #page .accent-path {
          stroke: rgb(15, 23, 42);
          stroke-width: 3px;
          stroke-linecap: round;
        }
      </style>
      <div id="page" style="width: 1920px; height: 1080px; color: rgb(37, 99, 235);">
        <svg viewBox="0 0 100 50" style="width: 300px; height: 150px; color: rgb(37, 99, 235);">
          <path class="accent-path" d="M 4 44 L 50 6 L 96 44" fill="currentColor" />
        </svg>
      </div>
    `

    await convert(slide)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>
    const serializedSvg = decodeSvgDataUrl(addImageCall.data)

    expect(serializedSvg).toContain('fill="#2563EB"')
    expect(serializedSvg).toContain('stroke="#0F172A"')
    expect(serializedSvg).toContain('stroke-width="3px"')
  })

  it('应还原 CSS 变量、HSL 背景和 dashed 边框', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="--card-bg: hsl(210 40% 96%); width: 420px; height: 220px; background-color: var(--card-bg); border-top: 4px dashed rgba(15, 23, 42, 0.4);"></section>
      </div>
    `

    await convert(slide)

    expect(slide.addShape).toHaveBeenCalledWith('rect', expect.objectContaining({
      fill: expect.objectContaining({ color: 'F1F5F9' }),
    }))
    expect(slide.addShape).toHaveBeenCalledWith('line', expect.objectContaining({
      line: expect.objectContaining({
        color: '0F172A',
        dashType: 'dash',
        transparency: 60,
      }),
    }))
  })

  it('应还原 CSS Color 4 颜色函数和主题相对颜色', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; --accent: #60a5fa;">
        <section style="
          width: 420px;
          height: 220px;
          background-color: rgb(from var(--accent) calc(r + (255 - r) * .3) calc(g + (255 - g) * .3) calc(b + (255 - b) * .3) / .5);
          border: 2px solid color-mix(in srgb, var(--accent) 70%, black);
          color: oklch(62.3% 0.214 259.815);
        ">
          <span style="display: block; width: 220px; height: 48px; color: color(srgb 0.1 0.2 0.3 / 0.8); font-size: 24px;">主题色</span>
        </section>
      </div>
    `

    await convert(slide)

    expect(slide.addShape).toHaveBeenCalledWith('rect', expect.objectContaining({
      fill: expect.objectContaining({
        color: '90C0FC',
        transparency: 50,
      }),
      line: expect.objectContaining({ color: '4373AF' }),
    }))
    expect(slide.addText).toHaveBeenCalledWith('主题色', expect.objectContaining({
      color: '1A334D',
      transparency: 20,
    }))
  })

  it('应优先使用视频封面作为图片块', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section class="video-viewer" style="width: 640px; height: 360px;">
          <video poster="/assets/video-cover.png"></video>
        </section>
      </div>
    `

    const report = await convert(slide)

    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      path: '/assets/video-cover.png',
    }))
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'video',
      result: 'image',
    }))
  })

  it('应将全屏 CSS 背景图导出为图片块', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    stubDetachedImageSize(1920, 1080)
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="background-image" style="width: 1920px; height: 1080px; background-image: url('/src/assets/runtime-shell/background.png'); background-size: cover; background-position: center; background-repeat: no-repeat;"></div>
        <div class="gradient-overlay" style="width: 1920px; height: 1080px; background-image: linear-gradient(90deg, rgba(0,0,0,.9), rgba(0,0,0,.5));"></div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      path: '/src/assets/runtime-shell/background.png',
      sizing: expect.objectContaining({
        type: 'cover',
      }),
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'image',
        result: 'image',
        reason: 'CSS 背景图导出为图片块',
      }),
    ]))
  })

  it('应为 cover 背景图写入保留原图比例的代理尺寸，避免 pptxgenjs 拉伸', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    const backgroundDataUrl = `data:image/svg+xml;base64,${window.btoa('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900"></svg>')}`
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="background-image"
          style="width: 768px; height: 1080px; background-image: url('${backgroundDataUrl}'); background-size: cover; background-position: center; background-repeat: no-repeat;"
        ></div>
      </div>
    `

    await convert(slide, captureElementAsPng)

    const imageOptions = slide.addImage.mock.calls[0]?.[0] as {
      w: number
      h: number
      sizing?: { type: string; w: number; h: number }
    }

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(imageOptions.sizing).toEqual(expect.objectContaining({
      type: 'cover',
    }))
    expect(imageOptions.w / imageOptions.h).toBeCloseTo(1200 / 900, 2)
    expect(imageOptions.h).not.toBe(imageOptions.sizing?.h)
  })

  it('应继续导出背景图容器中的标题叠层内容', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    stubDetachedImageSize(1200, 900)
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="left-section"
          style="position: relative; width: 768px; height: 1080px; background-image: url('/src/assets/runtime-shell/background.png'); background-size: cover; background-position: center; background-repeat: no-repeat;"
        >
          <div
            class="title-content"
            style="position: relative; z-index: 10; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;"
          >
            <div class="page-header" style="width: 360px; height: 180px; text-align: center;">
              <h1 class="page-title" style="width: 360px; height: 88px; margin: 0; color: #ffffff; font-size: 72px; line-height: 88px;">目录</h1>
              <div class="divider" style="width: 96px; height: 4px; margin: 24px auto 0; background-color: #ffffff;"></div>
              <p class="page-subtitle" style="width: 360px; height: 32px; margin: 16px 0 0; color: #ffffff; font-size: 24px; line-height: 32px;">Contents</p>
            </div>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const exportedTexts = slide.addText.mock.calls.map(call => String(call[0]))

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      path: '/src/assets/runtime-shell/background.png',
      sizing: expect.objectContaining({
        type: 'cover',
      }),
    }))
    expect(exportedTexts).toEqual(expect.arrayContaining(['目录', 'Contents']))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'image',
        result: 'image',
        reason: 'CSS 背景图导出为图片块',
      }),
      expect.objectContaining({
        result: 'editable-text',
      }),
    ]))
  })

  it('应将线性渐变蒙版导出为单个 PPT 原生渐变形状', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    const gradientFills: PptxGradientFillInstruction[] = []
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; --tw-color-bg-invert: #000000;">
        <div class="gradient-overlay" style="width: 1920px; height: 1080px; background-image: linear-gradient(to right, rgb(from var(--tw-color-bg-invert) r g b / 1) 0%, rgb(from var(--tw-color-bg-invert) r g b / 0.5) 100%);"></div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng, instruction => gradientFills.push(instruction))
    const shapeCalls = slide.addShape.mock.calls
    const gradientShape = shapeCalls[0]?.[1] as Record<string, unknown>

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(shapeCalls).toHaveLength(1)
    expect(gradientShape.objectName).toMatch(/^pptx-gradient-p1-1-/)
    expect(gradientShape.fill).toEqual(expect.objectContaining({
      color: '000000',
      transparency: 25,
    }))
    expect(gradientFills).toHaveLength(1)
    expect(gradientFills[0]).toEqual(expect.objectContaining({
      pageIndex: 1,
      objectName: gradientShape.objectName,
      direction: 'right',
    }))
    expect(gradientFills[0].stops[0].color).toEqual(expect.objectContaining({
      hex: '000000',
      alpha: 1,
    }))
    expect(gradientFills[0].stops[1].color).toEqual(expect.objectContaining({
      hex: '000000',
      alpha: 0.5,
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'shape',
        result: 'editable-shape',
        reason: 'linear-gradient 导出为 PPT 原生渐变形状',
      }),
    ]))
  })

  it('线性渐变容器包含文本时应继续导出可编辑文本', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    const gradientFills: PptxGradientFillInstruction[] = []
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="width: 520px; height: 220px; background-image: linear-gradient(to bottom, #ffffff, #dbeafe);">
          <h2 style="width: 360px; height: 48px; color: #1d4ed8; font-size: 32px;">渐变卡片标题</h2>
          <p style="width: 360px; height: 32px; color: #334155; font-size: 20px;">渐变容器说明</p>
        </section>
      </div>
    `

    const report = await convert(slide, captureElementAsPng, instruction => gradientFills.push(instruction))
    const exportedTexts = slide.addText.mock.calls.map(call => String(call[0]))

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(gradientFills).toHaveLength(1)
    expect(exportedTexts).toEqual(expect.arrayContaining(['渐变卡片标题', '渐变容器说明']))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'shape',
        result: 'editable-shape',
        reason: 'linear-gradient 导出为 PPT 原生渐变形状',
      }),
      expect.objectContaining({
        sourceType: 'title',
        result: 'editable-text',
        label: '渐变卡片标题',
      }),
      expect.objectContaining({
        sourceType: 'body',
        result: 'editable-text',
        label: '渐变容器说明',
      }),
    ]))
  })

  it('无文本复杂 CSS 容器应降级为局部截图并写入报告', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="width: 420px; height: 220px; background-image: radial-gradient(circle, #111827, #2563eb); background-size: cover;">
          <div style="width: 120px; height: 80px; background-color: rgba(255, 255, 255, 0.2);"></div>
        </section>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      data: 'data:image/png;base64,capture',
    }))
    expect((slide.addImage.mock.calls[0]?.[0] as Record<string, unknown>).sizing).toBeUndefined()
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'complex-css',
      result: 'screenshot',
      reason: '复杂 CSS 容器降级为局部截图',
    }))
  })

  it('复杂 CSS 容器包含文本时应优先保留可编辑文本', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="width: 420px; height: 220px; background-image: radial-gradient(circle, #111827, #2563eb); background-size: cover;">
          <span style="display: block; width: 200px; height: 32px; color: #ffffff; font-size: 24px;">复杂背景</span>
        </section>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addText).toHaveBeenCalledWith('复杂背景', expect.objectContaining({
      color: 'FFFFFF',
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'complex-css',
        result: 'skipped',
        reason: '复杂 CSS 容器包含可编辑内容，已展开子元素避免文本丢失',
      }),
      expect.objectContaining({
        sourceType: 'body',
        result: 'editable-text',
        label: '复杂背景',
      }),
    ]))
  })

  it('纯 2D 旋转胶囊应保持原始盒模型并同步旋转背景、SVG 和文字', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="position: relative; width: 1920px; height: 1080px;">
        <div
          id="tilted-badge"
          class="rounded-full"
          style="position: absolute; left: -150px; top: 110px; display: flex; align-items: center; gap: 12px; width: 320px; height: 64px; padding: 12px 24px; box-sizing: border-box; border: 3px solid #2563eb; border-radius: 9999px; background: #f59e0b; transform: matrix(0.990268, -0.139173, 0.139173, 0.990268, 0, 0); transform-origin: 50% 50%;"
        >
          <span style="display: inline-flex; width: 28px; height: 28px; color: #ffffff;">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="28" height="28" style="width: 28px; height: 28px;">
              <path d="M8 10 L28 10 L38 24 L28 38 L8 38 Z" fill="none" stroke="currentColor" stroke-width="2" />
            </svg>
          </span>
          <span style="display: inline-block; width: 150px; height: 28px; color: #ffffff; font-size: 20px; white-space: nowrap;">不到 1 元！</span>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    const badgeShape = slide.addShape.mock.calls.find(([shapeName]) => shapeName === 'roundRect')?.[1] as Record<string, number>
    const iconImage = slide.addImage.mock.calls[0]?.[0] as Record<string, number>
    const badgeText = slide.addText.mock.calls.find(([text]) => text === '不到 1 元！')?.[1] as Record<string, number>

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(badgeShape).toEqual(expect.objectContaining({ rotate: -8 }))
    expect(badgeShape.x).toBeLessThan(0)
    expect(badgeShape.w).toBeGreaterThan(badgeShape.h)
    expect(iconImage).toEqual(expect.objectContaining({ rotate: -8 }))
    expect(badgeText).toEqual(expect.objectContaining({ rotate: -8 }))
    expect((document.getElementById('tilted-badge') as HTMLElement).style.transform).toContain('matrix(')
    expect(report.items).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ result: 'screenshot' }),
    ]))
  })

  it('含文字的 skew 变换应整岛截图避免拆分后丢失视觉效果', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="skew-card" style="width: 320px; height: 120px; background: #2563eb; transform: skewX(12deg);">
          <span style="color: #ffffff; font-size: 24px;">倾斜文字</span>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng).toHaveBeenCalledWith(document.getElementById('skew-card'))
    expect(slide.addText).not.toHaveBeenCalledWith('倾斜文字', expect.any(Object))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'complex-css',
        result: 'screenshot',
        reason: '不支持的 CSS 2D transform 降级为局部截图',
      }),
    ]))
  })

  it('应将同一容器下多个 3D 子分支整体截图', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="perspective-row" style="display: flex; align-items: center; justify-content: center; width: 1400px; height: 500px; padding: 71px; gap: 32px; overflow: hidden;">
          <div style="width: 439px; height: 386px; transform: perspective(1200px) rotateY(25deg); transform-style: preserve-3d;">
            <figure class="image-viewer" style="width: 100%; height: 100%;">
              <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover;">
            </figure>
          </div>
          <div style="width: 398px; height: 358px; transform: perspective(1200px) rotateY(0deg); transform-style: preserve-3d;">
            <figure class="image-viewer" style="width: 100%; height: 100%;">
              <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover;">
            </figure>
          </div>
          <div style="width: 439px; height: 386px; transform: perspective(1200px) rotateY(-25deg); transform-style: preserve-3d;">
            <figure class="image-viewer" style="width: 100%; height: 100%;">
              <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover;">
            </figure>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(document.getElementById('perspective-row'))
    expect(slide.addImage).toHaveBeenCalledTimes(1)
    expect(report.items).toEqual([
      expect.objectContaining({
        sourceType: 'complex-css',
        result: 'screenshot',
        reason: '3D CSS 视觉降级为局部截图',
      }),
    ])
  })

  it('应将单张 3D 卡片截图为最小卡片宿主', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="outer" style="width: 900px; height: 520px; padding: 80px;">
          <div id="single-card" style="width: 420px; height: 320px; overflow: hidden; border-radius: 24px; transform: perspective(1200px) rotateY(-24deg);">
            <figure class="image-viewer" style="width: 100%; height: 100%;">
              <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover;">
            </figure>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(document.getElementById('single-card'))
    expect(captureElementAsPng.mock.calls[0]?.[0]).not.toBe(document.getElementById('outer'))
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'complex-css',
      result: 'screenshot',
      reason: '3D CSS 视觉降级为局部截图',
    }))
  })

  it('应在媒体容器包含 3D 图片时优先截图媒体容器', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <figure id="media-wrapper" class="image-viewer" style="width: 360px; height: 240px; overflow: hidden; border-radius: 18px;">
          <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover; transform: perspective(1000px) rotateY(18deg);">
        </figure>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(document.getElementById('media-wrapper'))
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'complex-css',
      result: 'screenshot',
      reason: '3D CSS 视觉降级为局部截图',
    }))
  })

  it('应将 3D 文本容器整体截图', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="text-card" style="width: 420px; height: 180px; color: #0f172a; font-size: 36px; transform: perspective(900px) rotateX(18deg);">
          3D 文本卡片
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(document.getElementById('text-card'))
    expect(slide.addText).not.toHaveBeenCalled()
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'complex-css',
      result: 'screenshot',
    }))
  })

  it('父容器含 3D 子树和文本时应保留文本可编辑', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section id="mixed-row" style="display: flex; align-items: center; gap: 32px; width: 900px; height: 320px;">
          <div id="mixed-card" style="width: 320px; height: 220px; transform: perspective(1000px) rotateY(-22deg);">
            <figure class="image-viewer" style="width: 100%; height: 100%;">
              <img src="data:image/png;base64,test" style="width: 100%; height: 100%; object-fit: cover;">
            </figure>
          </div>
          <p style="width: 360px; height: 48px; color: #334155; font-size: 24px;">旁边文字保持可编辑</p>
        </section>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(document.getElementById('mixed-card'))
    expect(captureElementAsPng.mock.calls[0]?.[0]).not.toBe(document.getElementById('mixed-row'))
    expect(slide.addText).toHaveBeenCalledWith('旁边文字保持可编辑', expect.objectContaining({
      color: '334155',
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'complex-css',
        result: 'screenshot',
        reason: '3D CSS 视觉降级为局部截图',
      }),
      expect.objectContaining({
        sourceType: 'body',
        result: 'editable-text',
      }),
    ]))
  })

  it('多张 3D 示例卡片含标题时应拆分截图并保留标题可编辑', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="example-grid" class="grid grid-cols-2 gap-12" style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 48px; width: 960px; height: 720px;">
          <div class="example-card" style="width: 456px; height: 320px;">
            <h2 style="width: 456px; height: 48px; color: #0f172a; font-size: 30px;">左侧倾斜30°</h2>
            <div style="width: 456px; height: 256px; display: flex; align-items: center; justify-content: center;">
              <div id="wrapper-a" class="perspective-3d-wrapper" style="width: 300px; height: 200px;">
                <div class="perspective-3d-stage" style="width: 300px; height: 200px; perspective: 800px;">
                  <div class="perspective-3d-content" style="width: 300px; height: 200px; transform: rotateX(0deg) rotateY(30deg) rotateZ(0deg);">
                    <div style="width: 300px; height: 200px;"><p>rotateY: 30°</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="example-card" style="width: 456px; height: 320px;">
            <h2 style="width: 456px; height: 48px; color: #0f172a; font-size: 30px;">上仰倾斜20°</h2>
            <div style="width: 456px; height: 256px; display: flex; align-items: center; justify-content: center;">
              <div id="wrapper-b" class="perspective-3d-wrapper" style="width: 300px; height: 200px;">
                <div class="perspective-3d-stage" style="width: 300px; height: 200px; perspective: 900px;">
                  <div class="perspective-3d-content" style="width: 300px; height: 200px; transform: rotateX(-20deg) rotateY(0deg) rotateZ(0deg);">
                    <div style="width: 300px; height: 200px;"><p>rotateX: -20°</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="example-card" style="width: 456px; height: 320px;">
            <h2 style="width: 456px; height: 48px; color: #0f172a; font-size: 30px;">复合旋转</h2>
            <div style="width: 456px; height: 256px; display: flex; align-items: center; justify-content: center;">
              <div id="wrapper-c" class="perspective-3d-wrapper" style="width: 300px; height: 200px;">
                <div class="perspective-3d-stage" style="width: 300px; height: 200px; perspective: 1000px;">
                  <div class="perspective-3d-content" style="width: 300px; height: 200px; transform: rotateX(15deg) rotateY(25deg) rotateZ(5deg);">
                    <div style="width: 300px; height: 200px;"><p>rotateX: 15°</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="example-card" style="width: 456px; height: 320px;">
            <h2 style="width: 456px; height: 48px; color: #0f172a; font-size: 30px;">强透视效果</h2>
            <div style="width: 456px; height: 256px; display: flex; align-items: center; justify-content: center;">
              <div id="wrapper-d" class="perspective-3d-wrapper" style="width: 300px; height: 200px;">
                <div class="perspective-3d-stage" style="width: 300px; height: 200px; perspective: 500px;">
                  <div class="perspective-3d-content" style="width: 300px; height: 200px; transform: rotateX(0deg) rotateY(-40deg) rotateZ(0deg);">
                    <div style="width: 300px; height: 200px;"><p>rotateY: -40°</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const capturedTargets = captureElementAsPng.mock.calls.map(call => call[0])

    expect(capturedTargets).toEqual([
      document.getElementById('wrapper-a'),
      document.getElementById('wrapper-b'),
      document.getElementById('wrapper-c'),
      document.getElementById('wrapper-d'),
    ])
    expect(capturedTargets).not.toContain(document.getElementById('example-grid'))
    expect(slide.addText).toHaveBeenCalledWith('左侧倾斜30°', expect.any(Object))
    expect(slide.addText).toHaveBeenCalledWith('上仰倾斜20°', expect.any(Object))
    expect(slide.addText).toHaveBeenCalledWith('复合旋转', expect.any(Object))
    expect(slide.addText).toHaveBeenCalledWith('强透视效果', expect.any(Object))
    expect(slide.addText).not.toHaveBeenCalledWith('rotateY: 30°', expect.any(Object))
    expect(report.items.filter(item => item.sourceType === 'complex-css' && item.result === 'screenshot')).toHaveLength(4)
  })

  it('单个 3D island 视觉外溢时应提升到外层包裹避免裁剪', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="overflow-card" style="width: 560px; height: 360px;">
          <h2 style="width: 560px; height: 48px; color: #0f172a; font-size: 30px;">透视示例标题</h2>
          <div id="overflow-holder" style="width: 480px; height: 280px; display: flex; align-items: center; justify-content: center;">
            <div id="overflow-wrapper" style="width: 300px; height: 200px;">
              <div id="overflow-stage" style="width: 300px; height: 200px; perspective: 800px;">
                <div id="overflow-content" style="width: 300px; height: 200px; transform: rotateX(15deg) rotateY(25deg) rotateZ(18deg);">
                  <div style="width: 300px; height: 200px;"><p>外溢 3D 内容</p></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const holderElement = document.getElementById('overflow-holder') as HTMLElement
    const wrapperElement = document.getElementById('overflow-wrapper') as HTMLElement
    const stageElement = document.getElementById('overflow-stage') as HTMLElement
    const contentElement = document.getElementById('overflow-content') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })
    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
    vi.spyOn(holderElement, 'getBoundingClientRect').mockReturnValue(createRect(80, 80, 480, 280))
    vi.spyOn(wrapperElement, 'getBoundingClientRect').mockReturnValue(createRect(170, 120, 300, 200))
    vi.spyOn(stageElement, 'getBoundingClientRect').mockReturnValue(createRect(170, 120, 300, 200))
    vi.spyOn(contentElement, 'getBoundingClientRect').mockReturnValue(createRect(130, 92, 380, 256))

    await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(captureElementAsPng.mock.calls[0]?.[0]).toBe(holderElement)
    expect(captureElementAsPng.mock.calls[0]?.[0]).not.toBe(wrapperElement)
    expect(captureElementAsPng.mock.calls[0]?.[0]).not.toBe(document.getElementById('overflow-card'))
    expect(slide.addText).toHaveBeenCalledWith('透视示例标题', expect.any(Object))
    expect(slide.addText).not.toHaveBeenCalledWith('外溢 3D 内容', expect.any(Object))
  })

  it('纯 matrix3d 位移不应触发 3D 截图降级', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = createCaptureElementAsPngMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 360px; height: 80px; color: #0f172a; font-size: 24px; transform: matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 24, 12, 0, 1);">
          纯位移文本
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addText).toHaveBeenCalledWith('纯位移文本', expect.objectContaining({
      color: '0F172A',
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'body',
        result: 'editable-text',
      }),
    ]))
  })
})
