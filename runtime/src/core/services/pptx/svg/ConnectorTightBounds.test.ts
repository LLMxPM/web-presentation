// @vitest-environment jsdom

/**
 * 文件用途：验证连接线紧边界守卫以 data-runtime-kit-connector 显式契约为准、历史 connector-svg 类名兜底，
 * 且未声明契约的普通 SVG 不会误入紧边界导出路径。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { buildConnectorSvgExportPayload } from './ConnectorTightBounds'
import type { PPTXDomConverterLayout } from '../PPTXDomConverterLayout'
import type { PPTXSvgSerializer } from '../PPTXSvgSerializer'
import { convert, createSlideMock, decodeSvgDataUrl } from '../PPTXDomConverter.test-support'

/** 守卫在触达 layout 与序列化器之前就返回，因此负例可以安全传入空桩件。 */
const unusedLayout = {} as unknown as PPTXDomConverterLayout
const unusedSerializer = {} as unknown as PPTXSvgSerializer

/**
 * 构造根 SVG 属性可替换的空 SVG 节点。
 * @param attributes 根 SVG 属性片段
 */
function createSvg(attributes: string): SVGSVGElement {
  const host = document.createElement('div')
  host.innerHTML = `<svg ${attributes}></svg>`
  return host.firstElementChild as unknown as SVGSVGElement
}

beforeEach(() => {
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('连接线紧边界守卫', () => {
  it('未声明契约也不带历史类名的 SVG 不应进入紧边界路径', () => {
    const svg = createSvg('viewBox="0 0 120 60"')

    expect(buildConnectorSvgExportPayload(svg, unusedLayout, unusedSerializer)).toBeNull()
  })

  it('未知版本的契约标记不得通过守卫', () => {
    const svg = createSvg('data-runtime-kit-connector="v2"')

    expect(buildConnectorSvgExportPayload(svg, unusedLayout, unusedSerializer)).toBeNull()
  })

  it('未知版本标记仍可由历史类名兜底，但缺少可渲染路径时返回空', () => {
    const svg = createSvg('class="connector-svg" data-runtime-kit-connector="v2"')

    expect(buildConnectorSvgExportPayload(svg, unusedLayout, unusedSerializer)).toBeNull()
  })
})

describe('连接线紧边界导出', () => {
  /**
   * 渲染一条竖直连线页面，并按 part2 既有夹具固定各节点测量值。
   * @param attributes 根 SVG 属性片段
   */
  function renderConnectorPage(attributes: string): void {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="position: relative; width: 600px; height: 300px;">
          <svg ${attributes} style="position: absolute; left: 0; top: 0; width: 100%; height: 100%; overflow: visible;">
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
    const svgElement = document.querySelector('svg') as SVGSVGElement
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
      value: vi.fn(() => ({ x: 300, y: 50, width: 0, height: 200 })),
      configurable: true,
    })
  }

  it('仅带显式契约、不带 connector-svg 类名时仍应按紧边界导出', async () => {
    renderConnectorPage('data-runtime-kit-connector="v1"')
    const slide = createSlideMock()

    await convert(slide)

    const imageOptions = slide.addImage.mock.calls[0]?.[0] as { x: number, y: number, w: number, h: number, data: string }
    const serializedSvg = decodeSvgDataUrl(imageOptions.data)
    const inchPerPx = 13.333 / 192

    expect(imageOptions.x).toBeCloseTo(38.8 * inchPerPx, 4)
    expect(imageOptions.y).toBeCloseTo(15.8 * (7.5 / 108), 4)
    expect(imageOptions.w).toBeCloseTo(2.4 * inchPerPx, 4)
    expect(imageOptions.h).toBeCloseTo(22.4 * (7.5 / 108), 3)
    expect(serializedSvg).toContain('viewBox="288 38 24 224"')
  })

  it('历史 connector-svg 类名兜底应导出同样的紧边界结果', async () => {
    renderConnectorPage('class="connector-svg"')
    const slide = createSlideMock()

    await convert(slide)

    const imageOptions = slide.addImage.mock.calls[0]?.[0] as { w: number, h: number, data: string }

    expect(imageOptions.w).toBeCloseTo(2.4 * (13.333 / 192), 4)
    expect(imageOptions.h).toBeCloseTo(22.4 * (7.5 / 108), 3)
    expect(decodeSvgDataUrl(imageOptions.data)).toContain('viewBox="288 38 24 224"')
  })
})
