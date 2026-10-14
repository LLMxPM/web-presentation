/** 文件用途：验证真实 Flex 测量不会被无布局估算覆盖，并检查 PPTX 实包中的标题坐标和无布局回退。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from '../PPTXDomConverter'
import { PPTXDomConverterLayout } from '../PPTXDomConverterLayout'
import { PPTXCssParser } from '../PPTXCssParser'
import { projectSlideIRToSlide } from '../writer/PptxSlideProjector'
import { DEFAULT_PPTX_SHAPE_TYPES, type PptxSlideExtractOptions } from '../ir/PptxSlideIR.types'
import { createSlideMock } from '../PPTXDomConverter.test-support'

afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 提供真实浏览器布局测量；这些坐标已经包含 gap、margin 和父级对齐。 */
function box(element: Element, x: number, y: number, width: number, height: number): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}),
  })
}

/** 使用固定设计画布，确保转换阶段的像素到英寸换算可直接对拍。 */
function options(pageElement: HTMLElement): PptxSlideExtractOptions {
  return { pageElement, pageIndex: 1, pageTitle: 'Flex 测量回归', pageRoute: '/flex',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5,
    captureElementAsPng: vi.fn(),
  }
}

/** 初始化页面测量上下文，无布局回退仍需要完整的画布比例。 */
function createLayout(): PPTXDomConverterLayout {
  const layout = new PPTXDomConverterLayout(new PPTXCssParser())
  layout.beginPage({ ...options(document.body), slide: createSlideMock(), shapeTypes: DEFAULT_PPTX_SHAPE_TYPES })
  layout.setRootBox({ left: 0, top: 0, width: 1920, height: 1080 })
  return layout
}

describe('PPTX Flex 真实测量优先', () => {
  it('MSV 首项位于 Flex 容器顶部时保留 y=153，实包与 IR 使用同一坐标', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
      <div class="stack" style="display:flex;flex-direction:column;justify-content:center;gap:24px;width:1047.609375px;height:833.453125px">
        <p style="width:1047.609375px;height:35.1875px;font-size:22px;line-height:35.2px;margin:0 0 18px">原图 2(b) · MULTI-SAMPLE VERIFICATION</p>
        <p style="width:1047.609375px;height:96px;font-size:38px;margin:0">两组多数都存在且相容</p>
      </div></div>`
    const page = document.getElementById('page')!
    const stack = page.querySelector('.stack')!
    const paragraphs = stack.querySelectorAll('p')
    box(page, 0, 0, 1920, 1080)
    box(stack, 811.390625, 153, 1047.609375, 833.453125)
    box(paragraphs[0], 811.390625, 153, 1047.609375, 35.1875)
    box(paragraphs[1], 811.390625, 230.1875, 1047.609375, 96)
    const ir = await new PPTXDomConverter().extractSlideIR(options(page))
    const title = ir.primitives.find(item => item.kind === 'text' && JSON.stringify(item.text).includes('MULTI-SAMPLE VERIFICATION'))!
    expect(title.options?.y).toBeCloseTo(153 / 1080 * 7.5, 4)
    expect(title.options?.h).toBeCloseTo(35.1875 / 1080 * 7.5, 4)
    const pptx = new PptxGenJS()
    projectSlideIRToSlide(ir, pptx.addSlide())
    const xml = strFromU8(unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)['ppt/slides/slide1.xml'])
    const doc = new DOMParser().parseFromString(xml, 'application/xml')
    const shape = Array.from(doc.getElementsByTagName('p:sp')).find(node => node.textContent?.includes('MULTI-SAMPLE VERIFICATION'))!
    const offset = shape.getElementsByTagName('a:off')[0]
    expect(Number(offset.getAttribute('y')) / 914400).toBeCloseTo(153 / 1080 * 7.5, 4)
  })

  it('真实横向 Flex 的首项与父级左边重合时，也不根据剩余宽度重新居中', () => {
    document.body.innerHTML = '<div style="display:flex;justify-content:center;width:600px;height:100px"><p style="width:200px;height:40px">真实左侧位置</p></div>'
    const parent = document.body.firstElementChild!
    const child = parent.firstElementChild!
    box(parent, 40, 80, 600, 100)
    box(child, 40, 110, 200, 40)
    const layout = createLayout()
    expect(layout.measureElementPixels(child)).toEqual({ left: 40, top: 110, width: 200, height: 40 })
  })

  it('没有真实矩形的无布局环境仍按 CSS 尺寸估算 Flex 居中坐标', () => {
    document.body.innerHTML = '<div style="display:flex;flex-direction:column;justify-content:center;width:600px;height:200px"><p style="width:200px;height:40px;margin:0">无布局回退</p></div>'
    const child = document.querySelector('p')!
    const layout = createLayout()
    expect(layout.measureElementPixels(child)).toEqual({ left: 0, top: 80, width: 200, height: 40 })
  })
})
