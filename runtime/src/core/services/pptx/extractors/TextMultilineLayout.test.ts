/** 文件用途：验证实际多行、显式换行、富文本、文本形状和直属片段的 PPTX 导出宽度，防止扩宽重排段落。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from '../PPTXDomConverter'
import { projectSlideIRToSlide } from '../writer/PptxSlideProjector'

afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 建立浏览器测量矩形，用真实几何驱动导出，覆盖 CSS 固定高度失真情形。 */
function rect(x: number, y: number, width: number, height: number): DOMRect {
  return { x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}) }
}

/** 创建有额外空白的文本容器；仅扩宽策略变化，不依赖相邻图元阻止扩宽。 */
function fixture(content = '决定了“一致性”能否代表进步。', extraStyle = '', height = 54) {
  document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px"><section style="width:900px;height:300px">
    <p style="width:550px;height:${height}px;font-size:38px;line-height:54px;margin:0;${extraStyle}">${content}</p></section></div>`
  const page = document.getElementById('page')!
  const paragraph = page.querySelector('p')!
  vi.spyOn(page, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 1920, 1080))
  vi.spyOn(page.querySelector('section')!, 'getBoundingClientRect').mockReturnValue(rect(100, 100, 900, 300))
  vi.spyOn(paragraph, 'getBoundingClientRect').mockReturnValue(rect(100, 100, 550, height))
  return { page, paragraph }
}

/** 模拟各文字节点的行片段；不同字号的同一行可以含多个矩形，不应按 run 数量判成多行。 */
function textRects(entries: [Node, DOMRect[]][]): void {
  const measurements = new Map(entries)
  vi.spyOn(document, 'createRange').mockImplementation(() => {
    let node: Node | null = null
    return {
      selectNodeContents: (selected: Node) => { node = selected },
      getClientRects: () => measurements.get(node!) ?? [],
    } as unknown as Range
  })
}

/** 导出原生 IR，确认保留 DOM 和可编辑性。 */
async function extract(page: HTMLElement) {
  const original = page.outerHTML
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const ir = await new PPTXDomConverter().extractSlideIR({ pageElement: page, pageIndex: 1, pageTitle: '多行宽度', pageRoute: '/multiline',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5, captureElementAsPng: capture })
  expect(capture).not.toHaveBeenCalled()
  expect(page.outerHTML).toBe(original)
  return ir
}

/** 将导出英寸还原为设计像素，检查位置和框尺寸。 */
function pixels(value: unknown): number { return Number(value) / 13.333 * 1920 }

describe('PPTX 多行文本保留原宽度', () => {
  it.each(['left', 'center', 'right'])('固定高度里的实际两行保持 %s 对齐原框，pre-wrap 不误判为单行', async align => {
    const { page, paragraph } = fixture(undefined, `white-space:pre-wrap;text-align:${align}`)
    textRects([[paragraph.firstChild!, [rect(100, 108, 530, 38), rect(100, 162, 300, 38)]]])
    const ir = await extract(page)
    const text = ir.primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.x)).toBeCloseTo(100, 1)
    expect(pixels(text.options?.w)).toBeCloseTo(550, 1)
    expect(pixels(text.options?.h)).toBeCloseTo(54, 1)
    expect(text.options?.fontSize).toBe(19)
    const pptx = new PptxGenJS()
    projectSlideIRToSlide(ir, pptx.addSlide())
    const xml = strFromU8(unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)['ppt/slides/slide1.xml'])
    expect(xml).toContain('wrap="square"')
    expect(xml).toContain('<a:t>决定了“一致性”能否代表进步。</a:t>')
    expect(xml).not.toContain('<a:br')
    expect(xml).not.toContain('normAutofit')
  })

  it('富文本跨节点自动折成两行时不增加宽度', async () => {
    const { page, paragraph } = fixture('决定了<strong>“一致性”</strong>能否代表进步。')
    textRects([
      [paragraph.firstChild!, [rect(100, 108, 152, 38)]],
      [paragraph.querySelector('strong')!.firstChild!, [rect(252, 108, 190, 38)]],
      [paragraph.lastChild!, [rect(442, 108, 190, 38), rect(100, 162, 114, 38)]],
    ])
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeCloseTo(550, 1)
    expect(Array.isArray(text.text)).toBe(true)
  })

  it('紧行距中两行字形矩形相互重叠也不误判为单行', async () => {
    const { page, paragraph } = fixture(undefined, 'line-height:12px')
    textRects([[paragraph.firstChild!, [rect(100, 108, 530, 38), rect(100, 120, 300, 38)]]])
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeCloseTo(550, 1)
  })

  it('实际只有一行的高文本框与不同字号富文本仍保留有界补偿', async () => {
    const { page, paragraph } = fixture('决定了<strong style="font-size:20px">“一致性”</strong>能否代表进步。', '', 200)
    textRects([
      [paragraph.firstChild!, [rect(100, 108, 152, 38)]],
      [paragraph.querySelector('strong')!.firstChild!, [rect(252, 126, 100, 20)]],
      [paragraph.lastChild!, [rect(352, 108, 260, 38)]],
    ])
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
    expect(pixels(text.options?.h)).toBeCloseTo(200, 1)
  })

  it('带背景圆角的多行文本形状不为了字宽补偿改变外形', async () => {
    const { page, paragraph } = fixture(undefined, 'background:#eff6ff;border-radius:999px;padding:4px', 108)
    textRects([[paragraph.firstChild!, [rect(104, 108, 530, 38), rect(104, 162, 300, 38)]]])
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(text.options?.shape).toBe('roundRect')
    expect(pixels(text.options?.w)).toBeCloseTo(550, 1)
    expect(pixels(text.options?.x)).toBeCloseTo(100, 1)
  })

  it('横向 Flex 中多行直属文字既不借用祖先空白，也不追加复杂 token 保护', async () => {
    const { page, paragraph } = fixture('<span style="display:inline-block;width:16px;height:24px">•</span>runtime-kit.manifest.json 决定了“一致性”能否代表进步。', 'display:flex', 54)
    paragraph.style.width = ''
    const bullet = paragraph.querySelector('span')!
    const node = paragraph.lastChild!
    vi.spyOn(bullet, 'getBoundingClientRect').mockReturnValue(rect(100, 108, 16, 24))
    textRects([[bullet.firstChild!, [rect(100, 108, 16, 24)]], [node, [rect(124, 108, 300, 38), rect(124, 162, 200, 38)]]])
    const texts = (await extract(page)).primitives.filter(item => item.kind === 'text')
    const text = texts.find(item => typeof item.text === 'string' && item.text.includes('runtime-kit.manifest.json'))!
    expect(pixels(text.options?.x)).toBeCloseTo(124, 1)
    expect(pixels(text.options?.w)).toBeCloseTo(300, 1)
  })

  it('显式换行与无 Range 布局的高段落同样保留原宽度', async () => {
    for (const [content, style] of [['第一行“引用”<br>第二行内容', 'white-space:pre-wrap'], ['决定了“一致性”能否代表进步。', 'white-space:pre-wrap']]) {
      const { page } = fixture(content, style, 160)
      const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
      expect(pixels(text.options?.w)).toBeCloseTo(550, 1)
    }
  })
})
