/* eslint-disable vue/one-component-per-file */
/**
 * 文件用途：验证 Draw.io 渲染器在外层高度不完整时的自适应兜底能力。
 *
 * @vitest-environment jsdom
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DrawioViewer from './DrawioViewer.vue'

const DRAWIO_XML = '<mxfile><diagram name="demo"><mxGraphModel /></diagram></mxfile>'
const DRAWIO_XML_WITH_PAGE_PADDING = `
<mxfile>
  <diagram name="platform">
    <mxGraphModel page="1" pageWidth="1600" pageHeight="900">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="title" value="Title" vertex="1" parent="1">
          <mxGeometry x="10" y="20" width="1360" height="640" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
`

/**
 * 等待组件内部异步加载、GraphViewer 处理和缩放重试完成。
 */
async function waitForDrawioRender(): Promise<void> {
  for (let index = 0; index < 12; index += 1) {
    await new Promise(resolve => window.setTimeout(resolve, 25))
    await nextTick()
  }
}

afterEach(() => {
  delete window.GraphViewer
  Reflect.deleteProperty(SVGElement.prototype, 'getBBox')
})

describe('DrawioViewer', () => {
  it('有 Draw.io 来源但 GraphViewer 尚未输出 SVG 时初始状态应为 loading', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      src: '/slow.drawio',
      height: 240,
    })
    app.mount(host)
    await nextTick()

    expect(host.querySelector<HTMLElement>('.drawio-viewer')?.dataset.runtimeDrawioState).toBe('loading')

    app.unmount()
    host.remove()
  })

  it('传入 content 时应直接渲染 XML 而不请求 src', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    window.GraphViewer = {
      processElements: vi.fn(() => {
        document.querySelectorAll('.mxgraph').forEach(element => {
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
          svg.style.minWidth = '406px'
          svg.style.minHeight = '206px'
          svg.appendChild(group)
          element.appendChild(svg)
        })
      }),
    }
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      value: vi.fn(() => ({
        x: 0,
        y: 0,
        width: 400,
        height: 200,
      }) as DOMRect),
      configurable: true,
    })
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function getClientWidth() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 400
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 400
      return 400
    })
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function getClientHeight() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 240
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 240
      return 240
    })

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      src: '/should-not-fetch.drawio',
      content: DRAWIO_XML,
      height: 240,
    })
    app.mount(host)

    await waitForDrawioRender()

    expect(fetchSpy).not.toHaveBeenCalled()
    const svg = host.querySelector<SVGSVGElement>('.drawio-viewer svg')
    expect(svg).not.toBeNull()
    expect(svg?.style.minWidth).toBe('0px')
    expect(svg?.style.minHeight).toBe('0px')
    expect(host.querySelector<HTMLElement>('.drawio-viewer')?.dataset.runtimeDrawioState).toBe('ready')

    app.unmount()
    host.remove()
    fetchSpy.mockRestore()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })

  it('父级没有明确高度且使用百分比高度时，应按图表比例补充可渲染高度', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(DRAWIO_XML, { status: 200 }),
    )

    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function getClientWidth() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 400
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 400
      return 400
    })
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function getClientHeight() {
      const element = this as HTMLElement
      if (element.classList?.contains('drawio-viewer')) {
        if (element.style.height.endsWith('%')) return 0
        return parseInt(element.style.height || '0', 10) || 0
      }
      if (element.classList?.contains('drawio-viewer__container')) {
        const root = element.closest<HTMLElement>('.drawio-viewer')
        if (root?.style.height.endsWith('%')) return 0
        return parseInt(root?.style.height || '0', 10) || 0
      }
      return 0
    })
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      value: vi.fn(() => ({
        x: 0,
        y: 0,
        width: 400,
        height: 200,
      }) as DOMRect),
      configurable: true,
    })

    window.GraphViewer = {
      processElements: vi.fn(() => {
        document.querySelectorAll('.mxgraph').forEach(element => {
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
          svg.appendChild(group)
          element.appendChild(svg)
        })
      }),
    }

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      src: '/demo.drawio',
      height: '100%',
      minHeight: 0,
    })
    app.mount(host)

    await waitForDrawioRender()

    const viewer = host.querySelector<HTMLElement>('.drawio-viewer')
    const svg = host.querySelector<SVGSVGElement>('.drawio-viewer svg')
    const group = host.querySelector<SVGGElement>('.drawio-viewer svg g')

    expect(fetchSpy).toHaveBeenCalledWith('./demo.drawio')
    expect(viewer?.style.height).toBe('200px')
    expect(svg).not.toBeNull()
    expect(svg?.getAttribute('viewBox')).toBe('0 0 400 200')
    expect(group?.getAttribute('transform')).toBe('translate(0, 0) scale(1)')

    app.unmount()
    host.remove()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })

  it('XML 几何边界与 SVG 实际边界不同时，应按被变换节点的坐标系居中', async () => {
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function getClientWidth() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 400
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 400
      return 400
    })
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function getClientHeight() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 200
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 200
      return 200
    })
    const identityMatrix = {
      a: 1,
      b: 0,
      c: 0,
      d: 1,
      e: 0,
      f: 0,
      inverse: vi.fn(),
      multiply: vi.fn(),
    } as unknown as DOMMatrix
    vi.mocked(identityMatrix.inverse).mockReturnValue(identityMatrix)
    vi.mocked(identityMatrix.multiply).mockReturnValue(identityMatrix)

    window.GraphViewer = {
      processElements: vi.fn(() => {
        document.querySelectorAll('.mxgraph').forEach(element => {
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
          const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
          const foreignObject = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject')
          foreignObject.setAttribute('width', '100%')
          foreignObject.setAttribute('height', '100%')
          Object.defineProperty(group, 'getCTM', { value: vi.fn(() => identityMatrix) })
          Object.defineProperty(group, 'getBBox', {
            value: vi.fn(() => ({ x: 0, y: 0, width: 1600, height: 900 }) as DOMRect),
          })
          Object.defineProperty(rect, 'getCTM', { value: vi.fn(() => identityMatrix) })
          Object.defineProperty(rect, 'getBBox', {
            value: vi.fn(() => ({ x: 5, y: 10, width: 1380, height: 660 }) as DOMRect),
          })
          group.append(rect, foreignObject)
          svg.appendChild(group)
          element.appendChild(svg)
        })
      }),
    }

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      content: DRAWIO_XML_WITH_PAGE_PADDING,
      height: 200,
    })
    app.mount(host)

    await waitForDrawioRender()

    const group = host.querySelector<SVGGElement>('.drawio-viewer svg g')
    const transform = group?.getAttribute('transform') || ''
    const matched = transform.match(/^translate\(([-\de.]+), ([-\de.]+)\) scale\(([-\de.]+)\)$/)

    expect(matched).not.toBeNull()
    expect(Number(matched?.[1])).toBeCloseTo(-1.449, 3)
    expect(Number(matched?.[2])).toBeCloseTo(1.449, 3)
    expect(Number(matched?.[3])).toBeCloseTo(0.29, 3)

    app.unmount()
    host.remove()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })

  it('应清理 GraphViewer 链接并通过事件捕获打开内部预览', async () => {
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function getClientWidth() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 400
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 400
      return 400
    })
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function getClientHeight() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 200
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 200
      return 200
    })
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      value: vi.fn(() => ({
        x: 0,
        y: 0,
        width: 400,
        height: 200,
      }) as DOMRect),
      configurable: true,
    })

    window.GraphViewer = {
      processElements: vi.fn(() => {
        document.querySelectorAll('.mxgraph').forEach(element => {
          const anchor = document.createElement('a')
          anchor.href = 'https://viewer.diagrams.net/#'
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
          svg.appendChild(group)
          anchor.appendChild(svg)
          element.appendChild(anchor)
        })
      }),
    }

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      content: DRAWIO_XML,
      height: 200,
    })
    app.mount(host)

    await waitForDrawioRender()

    const anchor = host.querySelector<HTMLAnchorElement>('.drawio-viewer a')
    const svg = host.querySelector<SVGSVGElement>('.drawio-viewer svg')
    const allowed = svg?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    await nextTick()

    expect(anchor?.getAttribute('href')).toBeNull()
    expect(allowed).toBe(false)
    expect(document.body.querySelector('.drawio-viewer__preview')).not.toBeNull()
    expect(document.body.querySelector('.drawio-viewer__preview-container svg')).not.toBeNull()

    app.unmount()
    host.remove()
    document.body.querySelector('.drawio-viewer__preview')?.remove()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })

  it('预览层应支持下载 SVG 图片', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:drawio-preview')
    const revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function getClientWidth() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 400
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 400
      return 400
    })
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function getClientHeight() {
      if ((this as HTMLElement).classList?.contains('drawio-viewer')) return 200
      if ((this as HTMLElement).classList?.contains('drawio-viewer__container')) return 200
      return 200
    })
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      value: vi.fn(() => ({
        x: 0,
        y: 0,
        width: 400,
        height: 200,
      }) as DOMRect),
      configurable: true,
    })

    window.GraphViewer = {
      processElements: vi.fn(() => {
        document.querySelectorAll('.mxgraph').forEach(element => {
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
          const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
          svg.appendChild(group)
          element.appendChild(svg)
        })
      }),
    }

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(DrawioViewer, {
      content: DRAWIO_XML,
      src: '/docs/platform.drawio',
      height: 200,
    })
    app.mount(host)

    await waitForDrawioRender()
    host.querySelector<SVGSVGElement>('.drawio-viewer svg')?.dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true }),
    )
    await nextTick()

    document.body.querySelector<HTMLButtonElement>('.drawio-viewer__preview-button')?.click()

    expect(createObjectUrlSpy).toHaveBeenCalledWith(expect.any(Blob))
    expect(anchorClickSpy).toHaveBeenCalled()
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:drawio-preview')

    app.unmount()
    host.remove()
    document.body.querySelector('.drawio-viewer__preview')?.remove()
    createObjectUrlSpy.mockRestore()
    revokeObjectUrlSpy.mockRestore()
    anchorClickSpy.mockRestore()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })
})
