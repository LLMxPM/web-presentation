/** 文件用途：验证 overflow 越界和圆角裁切仍输出可编辑文本、形状、表格，实包检查避免以图片描述冒充文本。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from '../PPTXDomConverter'
import { projectSlideIRToSlide } from '../writer/PptxSlideProjector'

afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 设置明确的越界测量值；jsdom 没有布局，测试需区分正文区与外层页面坐标。 */
function box(element: Element, x: number, y: number, width: number, height: number): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}),
  })
}

/** 模拟真实项目的正文与页码；页码可相对正文或外层页面定位，导出均应保持文本。 */
function fixture(style = ''): { page: HTMLElement; main: HTMLElement; footer: HTMLElement } {
  document.body.innerHTML = `<div id="page" style="position:relative;width:960px;height:540px">
    <main style="overflow:hidden;width:960px;height:440px;${style}">
      <p style="width:400px;height:60px;font-size:24px">正文保持可编辑</p>
      <div id="footer" style="position:absolute;bottom:16px;width:80px;height:24px;font-size:24px"><span>2 / 18</span></div>
    </main></div>`
  const page = document.getElementById('page')!
  const main = page.querySelector('main')!
  const footer = document.getElementById('footer')!
  box(page, 0, 0, 960, 540)
  box(main, 0, 0, 960, 440)
  box(main.querySelector('p')!, 48, 48, 400, 60)
  box(footer, 800, 500, 80, 24)
  box(footer.querySelector('span')!, 800, 500, 80, 24)
  return { page, main, footer }
}

/** 写入真实 PPTX，读取原生文字和图元，同时检查未发生截图、跳过或 DOM 修改。 */
async function exportNativePage(page: HTMLElement): Promise<{ doc: Document; xml: string; texts: string[] }> {
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const originalHtml = page.outerHTML
  const ir = await new PPTXDomConverter().extractSlideIR({
    pageElement: page, pageIndex: 1, pageTitle: '可编辑优先回归', pageRoute: '/overflow',
    pageWidthPx: 960, pageHeightPx: 540, slideWidthIn: 10, slideHeightIn: 5.625,
    captureElementAsPng: capture,
  })
  expect(capture).not.toHaveBeenCalled()
  expect(ir.report.items.some(item => item.result === 'screenshot' || item.result === 'skipped')).toBe(false)
  expect(page.outerHTML).toBe(originalHtml)
  const pptx = new PptxGenJS()
  projectSlideIRToSlide(ir, pptx.addSlide())
  const files = unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)
  const xml = strFromU8(files['ppt/slides/slide1.xml'])
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  expect(doc.getElementsByTagName('p:pic')).toHaveLength(0)
  return { doc, xml, texts: Array.from(doc.getElementsByTagName('a:t')).map(node => node.textContent || '') }
}

describe('PPTX overflow 可编辑性优先', () => {
  it.each(['', 'position:relative'])('定位页码越界仍保留正文与页码原生文本（%s）', async style => {
    const { page } = fixture(style)
    const { texts } = await exportNativePage(page)
    expect(texts).toEqual(expect.arrayContaining(['正文保持可编辑', '2 / 18']))
  })

  it.each(['hidden', 'clip', 'auto', 'scroll'])('%s 容器内真正越界的文本形状仍可编辑', async overflow => {
    const { page, main, footer } = fixture(`overflow:${overflow};position:relative;border-radius:32px;background:#eef2ff`)
    footer.remove()
    const paragraph = main.querySelector('p')!
    paragraph.style.cssText = 'width:400px;height:80px;position:absolute;top:430px;background:#ff0000;font-size:24px'
    box(paragraph, 48, 430, 400, 80)
    const { doc, xml, texts } = await exportNativePage(page)
    expect(texts).toContain('正文保持可编辑')
    expect(doc.getElementsByTagName('p:sp').length).toBeGreaterThanOrEqual(2)
    expect(xml).toContain('FF0000')
  })

  it('圆角容器中触及角落的对象继续生成原生形状与文本', async () => {
    const { page, main, footer } = fixture('border-radius:32px;background:#eef2ff')
    footer.remove()
    box(main.querySelector('p')!, 0, 0, 400, 60)
    const { xml, texts } = await exportNativePage(page)
    expect(texts).toContain('正文保持可编辑')
    expect(xml).toContain('prst="roundRect"')
  })

  it('超出容器的原生表格仍写入 a:tbl，表格文字保持完整', async () => {
    const { page, main, footer } = fixture('position:relative')
    footer.remove()
    main.innerHTML = '<table style="position:absolute;top:430px;width:400px;height:100px;border-collapse:collapse"><tr style="width:400px;height:100px"><td style="width:400px;height:100px">越界表格</td></tr></table>'
    const table = main.querySelector('table')!
    box(table, 48, 430, 400, 100)
    box(table.querySelector('tr')!, 48, 430, 400, 100)
    box(table.querySelector('td')!, 48, 430, 400, 100)
    const { doc, texts } = await exportNativePage(page)
    expect(doc.getElementsByTagName('a:tbl')).toHaveLength(1)
    expect(texts).toContain('越界表格')
  })
})
