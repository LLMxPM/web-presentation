/** 文件用途：验证真实 iframe 节点、原生列表和组合产物，以及页面容错的原子提交边界。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from './PPTXDomConverter'
import { createEmptySlideIR, createSlideMock } from './PPTXDomConverter.test-support'
import { appendEditablePptxPage, appendRasterizedPptxPage, PptxPageExtractionError } from './PptxPageAssembler'
import { isHTMLElement, isSVGElement } from './dom/PPTXDomEnvironment'
import { patchGroupInSlideXml } from './writer/OoxmlGroupPatcher'
import { extractNormalizedChartData } from './extractors/EchartsDataExtractor'
import { parseRuntimeKitChartPayload } from './PPTXRuntimeKitExportDom'
import type { PptxSlideExtractOptions } from './ir/PptxSlideIR.types'

const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l8sAAAAASUVORK5CYII='
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 构造固定画布提取上下文；浏览器布局与截图分别由样例控制。 */
function options(pageElement: HTMLElement): PptxSlideExtractOptions {
  return {
    pageElement, pageIndex: 1, pageTitle: '复核页', pageRoute: '/review',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5,
    captureElementAsPng: async () => png,
  }
}

/** 在真实 iframe Window 下创建元素，避免 createHTMLDocument 与宿主共享构造器的假跨窗口测试。 */
function iframePage(content: string): HTMLElement {
  const frame = document.createElement('iframe')
  document.body.appendChild(frame)
  frame.contentDocument!.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">${content}</div>`
  return frame.contentDocument!.getElementById('page') as HTMLElement
}

/** 构造有独立对象名的 XML 图元，用于检查组扫描不会跨越其他形状。 */
function shape(name: string, id: number): string {
  return `<p:sp><p:nvSpPr><p:cNvPr id="${id}" name="${name}"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="10" cy="10"/></a:xfrm></p:spPr></p:sp>`
}

describe('PPTX 实现复核回归', () => {
  it('无限动画的透明帧先恢复静态样式，再判断可见性，完成后恢复动画声明', async () => {
    const page = document.createElement('div')
    page.style.cssText = 'width:1920px;height:1080px'
    page.innerHTML = '<p style="width:400px;height:80px;animation:blink 1s infinite">循环动画文字</p>'
    document.body.appendChild(page)
    const paragraph = page.querySelector('p')!
    const originalStyle = paragraph.style.cssText
    Object.defineProperty(paragraph, 'getAnimations', { value: () => [{ effect: { getTiming: () => ({ iterations: Infinity }) } }] })
    const getStyle = window.getComputedStyle.bind(window)
    vi.spyOn(window, 'getComputedStyle').mockImplementation(element => {
      const style = getStyle(element)
      if (element === paragraph && paragraph.style.animation !== 'none') {
        return new Proxy(style, { get: (target, key) => key === 'opacity' ? '0' : key === 'animationName' ? 'blink' : Reflect.get(target, key) })
      }
      return style
    })
    const ir = await new PPTXDomConverter().extractSlideIR(options(page))
    expect(ir.primitives.some(primitive => primitive.kind === 'text' && JSON.stringify(primitive.text).includes('循环动画文字'))).toBe(true)
    expect(paragraph.style.cssText).toBe(originalStyle)
  })

  it('真实 iframe 中的嵌套文本、富文本、表格和 SVG 均进入 IR', async () => {
    const page = iframePage(`<section style="display:flex;width:1000px;height:700px">
      <p style="width:400px;height:80px;font-size:24px">前缀<strong style="font-weight:700">重点</strong></p>
      <table style="width:400px;height:100px"><tr style="width:400px;height:100px"><td style="width:400px;height:100px">甲<br>乙</td></tr></table>
      <svg xmlns="http://www.w3.org/2000/svg" style="width:100px;height:100px"><rect width="100" height="100" fill="red"/></svg>
    </section>`)
    expect(page instanceof HTMLElement).toBe(false)
    const svg = page.querySelector('svg')!
    expect(isHTMLElement(svg)).toBe(false)
    expect(isSVGElement(svg)).toBe(true)
    const ir = await new PPTXDomConverter().extractSlideIR(options(page))
    expect(ir.primitives.some(primitive => primitive.kind === 'text' && JSON.stringify(primitive.text).includes('重点'))).toBe(true)
    expect(ir.primitives.some(primitive => primitive.kind === 'table')).toBe(true)
    expect(ir.primitives.some(primitive => primitive.kind === 'image' && String(primitive.options.data).startsWith('data:image/svg'))).toBe(true)
  })

  it('真实 iframe 的图片和局部截图不因跨窗口类型判断被跳过', async () => {
    const page = iframePage(`<img src="${png}" style="width:100px;height:100px"><div style="width:100px;height:100px;transform:scaleX(2)">截图内容</div>`)
    const capture = vi.fn(async () => png)
    const ir = await new PPTXDomConverter().extractSlideIR({ ...options(page), captureElementAsPng: capture })
    expect(ir.primitives.filter(primitive => primitive.kind === 'image')).toHaveLength(2)
    expect(capture).toHaveBeenCalledOnce()
  })

  it('列表保留已挂载元素的 CSS，生成两个完整段落并保持第二项富文本', async () => {
    const page = document.createElement('div')
    page.style.cssText = 'width:1920px;height:1080px'
    page.innerHTML = '<style>.review-list li { color: rgb(255,0,0); font-size:24px }</style><ul class="review-list" style="width:500px;height:150px"><li>第一项</li><li>第二项<strong style="font-weight:700">重点</strong></li></ul>'
    document.body.appendChild(page)
    const pptx = new PptxGenJS()
    const ir = await new PPTXDomConverter().extractSlideIR(options(page))
    const primitive = ir.primitives.find(item => item.kind === 'text')!
    expect(JSON.stringify(primitive)).toContain('FF0000')
    const { projectSlideIRToSlide } = await import('./writer/PptxSlideProjector')
    projectSlideIRToSlide(ir, pptx.addSlide())
    const bytes = await pptx.write({ outputType: 'uint8array' }) as Uint8Array
    const xml = strFromU8(unzipSync(bytes)['ppt/slides/slide1.xml'])
    const doc = new DOMParser().parseFromString(xml, 'application/xml')
    const paragraphs = Array.from(doc.getElementsByTagName('a:p')).filter(node => node.getElementsByTagName('a:t').length)
    expect(paragraphs.map(node => node.textContent)).toEqual(['第一项', '第二项重点'])
    expect(paragraphs[1].getElementsByTagName('a:buChar')).toHaveLength(1)
  })

  it('组合扫描只包装连续成员，每个原始图元保持唯一', () => {
    const xml = `<p:spTree>${shape('outside', 2)}${shape('a', 3)}${shape('b', 4)}</p:spTree>`
    const instruction = { pageIndex: 1, groupId: 'g', groupName: '组合', x: 0, y: 0, w: 1, h: 1, memberObjectNames: ['a', 'b'] }
    const patched = patchGroupInSlideXml(xml, instruction, 3)
    const doc = new DOMParser().parseFromString(`<root xmlns:p="urn:p" xmlns:a="urn:a">${patched}</root>`, 'application/xml')
    expect(doc.getElementsByTagName('parsererror')).toHaveLength(0)
    const group = doc.getElementsByTagName('p:grpSp')[0]
    expect(group.getElementsByTagName('p:sp')).toHaveLength(2)
    expect(group.textContent).not.toContain('outside')
    expect(Array.from(doc.getElementsByTagName('p:cNvPr')).map(node => node.getAttribute('id'))).toEqual(['2', '5', '3', '4'])
    for (const name of ['outside', 'a', 'b']) expect(patched.match(new RegExp(`name="${name}"`, 'g'))).toHaveLength(1)
    expect(patchGroupInSlideXml(xml, { ...instruction, memberObjectNames: ['outside', 'b'] }, 9)).toBe(xml)
  })

  it('重复文本与相同角色仍分配不同图元名称', async () => {
    const page = document.createElement('div')
    page.style.cssText = 'width:1920px;height:1080px'
    page.innerHTML = '<section style="width:800px;height:300px"><p style="width:300px;height:40px">重复</p><p style="width:300px;height:40px">重复</p></section>'
    document.body.appendChild(page)
    const ir = await new PPTXDomConverter().extractSlideIR(options(page))
    const names = ir.primitives.map(primitive => primitive.options?.objectName)
    expect(new Set(names).size).toBe(names.length)
  })

  it('提取失败不会创建空白 slide，截图成功后只增加原页数和备注', async () => {
    const page = document.createElement('div')
    const pptx = new PptxGenJS()
    const converter = new PPTXDomConverter()
    const context = { ...options(page), speakerNotes: '原页面备注' }
    vi.spyOn(converter, 'extractSlideIR').mockRejectedValueOnce(new Error('提取失败')).mockResolvedValueOnce(createEmptySlideIR(context))
    await expect(appendEditablePptxPage(pptx, converter, context, [])).rejects.toBeInstanceOf(PptxPageExtractionError)
    await appendRasterizedPptxPage(pptx, context, { route: '/review', title: '复核页', order: 1 }, new Error('提取失败'))
    await appendEditablePptxPage(pptx, converter, { ...context, pageIndex: 2 }, [])
    const files = unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)
    expect(Object.keys(files).filter(file => /^ppt\/slides\/slide\d+\.xml$/.test(file))).toHaveLength(2)
    expect(strFromU8(files['ppt/notesSlides/notesSlide1.xml'])).toContain('原页面备注')
  })

  it('投射失败不冒充可恢复提取失败，取消截图不提交 slide', async () => {
    const page = document.createElement('div')
    const converter = new PPTXDomConverter()
    const context = options(page)
    vi.spyOn(converter, 'extractSlideIR').mockResolvedValue({ ...createEmptySlideIR(context), primitives: [{ kind: 'shape', shapeType: 'rect' }] })
    const error = new Error('投射失败')
    const pptx = { addSlide: () => ({ ...createSlideMock(), addShape: () => { throw error } }) } as unknown as PptxGenJS
    await expect(appendEditablePptxPage(pptx, converter, context, [])).rejects.toBe(error)
    const controller = new AbortController()
    const addSlide = vi.fn()
    await expect(appendRasterizedPptxPage({ addSlide } as unknown as PptxGenJS, {
      ...context, signal: controller.signal, captureElementAsPng: async () => { controller.abort(); return png },
    }, { route: '/review', title: '复核页', order: 1 }, error)).rejects.toThrow('用户取消导出')
    expect(addSlide).not.toHaveBeenCalled()
  })

  it('不支持的图表语义与坏契约安全回退，不把缺失值当作零', () => {
    expect(extractNormalizedChartData({ xAxis: { data: ['甲'] }, series: [{ type: 'line', data: [null] }] })).toBeNull()
    expect(extractNormalizedChartData({ xAxis: { data: ['甲'] }, series: [{ type: 'bar', stack: 'sum', data: [1] }] })).toBeNull()
    expect(extractNormalizedChartData({ xAxis: { data: ['甲'] }, series: [{ type: 'bar', data: [1], label: { formatter: () => '标签' } }] })).toBeNull()
    const element = document.createElement('div')
    element.setAttribute('data-runtime-kit-chart', 'v1')
    for (const payload of [
      { version: 'v1', chartType: 'unknown', categories: ['甲'], series: [{ name: '数值', values: [1] }] },
      { version: 'v1', chartType: 'line', categories: ['甲'], series: [{ name: '数值', values: [1, 2] }] },
    ]) {
      element.setAttribute('data-runtime-kit-chart-data', JSON.stringify(payload))
      expect(parseRuntimeKitChartPayload(element)).toBeNull()
    }
  })

  it('同父级定位图元按层级绘制，滤镜不绕过已识别的渐变背景', async () => {
    const page = document.createElement('div')
    page.style.cssText = 'width:1920px;height:1080px'
    page.innerHTML = '<div style="position:absolute;z-index:100;width:200px;height:200px;background:red"></div><div style="position:absolute;z-index:1;width:200px;height:200px;background:blue"></div><div style="width:300px;height:100px;filter:blur(4px);background-image:linear-gradient(to right,red,blue)">有滤镜的文本</div>'
    document.body.appendChild(page)
    const capture = vi.fn(async () => png)
    const ir = await new PPTXDomConverter().extractSlideIR({ ...options(page), captureElementAsPng: capture })
    expect(ir.primitives.filter(primitive => primitive.kind === 'shape').map(primitive => (primitive.options?.fill as { color: string }).color)).toEqual(['0000FF', 'FF0000'])
    expect(capture).toHaveBeenCalledOnce()
    expect(ir.gradientFills).toHaveLength(0)
    expect(ir.primitives.some(primitive => primitive.kind === 'text')).toBe(false)
  })
})
