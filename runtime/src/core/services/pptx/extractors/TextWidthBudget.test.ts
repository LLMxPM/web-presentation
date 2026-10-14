/** 文件用途：用实际几何与 PPTX 实包验证标点宽度保护、局部扩宽边界、对齐锚点、正常换行及字号保持。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from '../PPTXDomConverter'
import { projectSlideIRToSlide } from '../writer/PptxSlideProjector'
import type { PptxSlidePrimitiveIR } from '../ir/PptxSlideIR.types'

const QUOTED = '决定了“一致性”能否代表进步。'
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 设置浏览器已有的排版坐标，保持设计画布一比一的测量尺度。 */
function box(element: Element, x: number, y: number, w: number, h: number): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({ x, y, width: w, height: h, left: x, top: y, right: x + w, bottom: y + h, toJSON: () => ({}) })
}

/** 创建带有可用空白的文本列，调用方可添加相邻图元或改变列尺寸。 */
function fixture(width = 650, align = 'left', text = QUOTED, textWidth = 550): { page: HTMLElement; column: HTMLElement; paragraph: HTMLElement } {
  document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px"><section style="width:${width}px;height:200px">
    <p style="width:${textWidth}px;height:54px;font-size:38px;font-family:system-ui;line-height:54px;margin:0;text-align:${align}">${text}</p></section></div>`
  const page = document.getElementById('page')!
  const column = page.querySelector('section')!
  const paragraph = page.querySelector('p')!
  box(page, 0, 0, 1920, 1080)
  box(column, 100, 100, width, 200)
  box(paragraph, align === 'right' ? 100 + width - textWidth : align === 'center' ? 100 + (width - textWidth) / 2 : 100, 100, textWidth, 54)
  return { page, column, paragraph }
}

/** 提取保持可编辑的文本；记录截图调用和 DOM 原样，以防宽度策略改写页面或触发降级。 */
async function extract(page: HTMLElement): Promise<PptxSlidePrimitiveIR[]> {
  const original = page.outerHTML
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const ir = await new PPTXDomConverter().extractSlideIR({ pageElement: page, pageIndex: 1, pageTitle: '宽度保护', pageRoute: '/width',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5, captureElementAsPng: capture })
  expect(capture).not.toHaveBeenCalled()
  expect(page.outerHTML).toBe(original)
  return ir.primitives
}

/** 将物理英寸转换回设计像素，便于和容器及相邻对象直接对拍。 */
function pixels(value: unknown): number { return Number(value) / 13.333 * 1920 }

describe('PPTX 标点与文本扩宽预算', () => {
  it('弯引号的保护量足以容纳已实测的 570px 字宽，字号及文字保持原样', async () => {
    const { page } = fixture(650, 'left', QUOTED, 532)
    const primitives = await extract(page)
    const text = primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(570)
    expect(text.options?.fontSize).toBe(19)
    expect(text.options?.fontFace).toBe('Microsoft YaHei')
    expect(text.options?.fit).toBe('none')
    const pptx = new PptxGenJS()
    projectSlideIRToSlide({ pageIndex: 1, pageTitle: '宽度保护', pageRoute: '/width', primitives, gradientFills: [], report: { pageIndex: 1, pageTitle: '宽度保护', pageRoute: '/width', items: [] } }, pptx.addSlide())
    const xml = strFromU8(unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)['ppt/slides/slide1.xml'])
    expect(xml).toContain(`<a:t>${QUOTED}</a:t>`)
    expect(xml).toContain('wrap="square"')
    expect(xml).not.toContain('normAutofit')
    expect(xml).not.toContain('<a:br')
  })

  it('纯中文括号同样获得额外保护量，普通文字的余量保持较小', async () => {
    const plain = (await extract(fixture(650, 'left', '决定了一致性能否代表进步。').page)).find(item => item.kind === 'text')!
    const bracketed = (await extract(fixture(650, 'left', '决定了（【《一致性》】）能否代表进步。').page)).find(item => item.kind === 'text')!
    expect(pixels(bracketed.options?.w)).toBeGreaterThan(pixels(plain.options?.w))
  })

  it('没有足够空间时只扩展到列边界，保持字号与自然换行', async () => {
    const text = (await extract(fixture(560).page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeCloseTo(560, 1)
    expect(text.options?.fontSize).toBe(19)
    expect(text.options?.wrap).not.toBe(false)
  })

  it('容器 padding 与 border 不计入可借用空白', async () => {
    const { page, column, paragraph } = fixture(620)
    column.style.cssText = 'width:620px;height:200px;padding:20px;border:5px solid black;box-sizing:border-box'
    box(paragraph, 125, 125, 550, 54)
    const text = (await extract(page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.x) + pixels(text.options?.w)).toBeLessThanOrEqual(695.02)
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
  })

  it('相邻对象即使处于另一层透明包裹也能阻止文本扩宽越界', async () => {
    const { page, column, paragraph } = fixture(650)
    const row = document.createElement('div')
    row.style.cssText = 'display:flex;width:650px;height:200px'
    const wrapper = document.createElement('div')
    column.replaceChildren(row); row.appendChild(wrapper); wrapper.appendChild(paragraph)
    const peer = document.createElement('div')
    peer.style.cssText = 'width:60px;height:54px;background:blue'
    row.appendChild(peer)
    box(row, 100, 100, 650, 200)
    box(wrapper, 100, 100, 550, 54)
    box(peer, 668, 100, 60, 54)
    const text = (await extract(page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.x) + pixels(text.options?.w)).toBeLessThanOrEqual(668.02)
  })

  it.each(['center', 'right'])('扩宽仍保持 %s 对齐锚点，边界不足时减少余量', async align => {
    const { page, paragraph } = fixture(570, align)
    const rect = paragraph.getBoundingClientRect()
    const text = (await extract(page)).find(item => item.kind === 'text')!
    const x = pixels(text.options?.x)
    const width = pixels(text.options?.w)
    expect(x).toBeGreaterThanOrEqual(99.98)
    expect(x + width).toBeLessThanOrEqual(670.02)
    expect(align === 'center' ? x + width / 2 : x + width).toBeCloseTo(align === 'center' ? rect.left + rect.width / 2 : rect.right, 1)
  })

  it('大量引号和括号仍有宽度上限，不把整段推向页面边缘', async () => {
    const text = (await extract(fixture(1500, 'left', '“（引用）”'.repeat(100)).page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeLessThanOrEqual(550 * 1.15 + 0.02)
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
  })

  it('已经越出容器的对象不被缩窄或移回边界', async () => {
    const { page, paragraph } = fixture(550)
    box(paragraph, 90, 100, 580, 54)
    const text = (await extract(page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.x)).toBeCloseTo(90, 1)
    expect(pixels(text.options?.w)).toBeCloseTo(580, 1)
  })

  it('全屏透明装饰层（如 pointer-events-none absolute inset-0）不阻断文本扩宽', async () => {
    const { page } = fixture(650)
    const decorator = document.createElement('div')
    decorator.style.cssText = 'position:absolute;left:0;top:0;width:1920px;height:1080px;pointer-events:none'
    box(decorator, 0, 0, 1920, 1080)
    page.insertBefore(decorator, page.firstChild)
    const text = (await extract(page)).find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
  })

  it('居中胶囊贴左边时允许非对称向右扩宽，不被归零', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
      <div id="container" style="width:600px;height:100px;position:relative">
        <span class="rounded-full px-4 py-2" style="position:absolute;left:0;top:20px;display:inline-block;width:180px;height:40px;background:#2563eb;border-radius:9999px;font-size:16px;color:#fff;text-align:center">高一数学 · 教学课件</span>
      </div>
    </div>`
    const page = document.getElementById('page')!
    const container = document.getElementById('container')!
    const badge = page.querySelector('span')!
    box(page, 0, 0, 1920, 1080)
    box(container, 100, 20, 600, 100)
    box(badge, 100, 20, 180, 40)
    const primitives = await extract(page)
    const text = primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(180)
    expect(pixels(text.options?.x)).toBeCloseTo(100, 1)
  })

  it('贴右内容驱动文本在右侧贴边时允许向左借位扩宽', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
      <div style="width:1800px;height:60px;position:relative">
        <span style="position:absolute;left:1600px;top:10px;height:30px;font-size:16px">右页脚 · 第1页</span>
      </div>
    </div>`
    const page = document.getElementById('page')!
    const footer = page.querySelector('span')!
    box(page, 0, 0, 1920, 1080)
    box(footer, 1600, 10, 200, 30)
    const primitives = await extract(page)
    const text = primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(200)
    expect(pixels(text.options?.x) + pixels(text.options?.w)).toBeLessThanOrEqual(1800.02)
    expect(pixels(text.options?.x)).toBeLessThan(1600)
  })

  it('两相邻并排胶囊扩宽后保持安全间隔，绝不互相侵入重叠', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
      <div id="bar" style="width:800px;height:60px;position:relative">
        <span id="badge1" class="rounded-full px-4 py-2" style="position:absolute;left:100px;top:10px;display:inline-block;width:180px;height:40px;background:#2563eb;border-radius:9999px;font-size:16px;color:#fff;text-align:center">高一数学</span>
        <span id="badge2" class="rounded-full px-4 py-2" style="position:absolute;left:292px;top:10px;display:inline-block;width:160px;height:40px;background:#16a34a;border-radius:9999px;font-size:16px;color:#fff;text-align:center">教学课件</span>
      </div>
    </div>`
    const page = document.getElementById('page')!
    const bar = document.getElementById('bar')!
    const badge1 = document.getElementById('badge1')!
    const badge2 = document.getElementById('badge2')!
    box(page, 0, 0, 1920, 1080)
    box(bar, 100, 10, 800, 60)
    box(badge1, 100, 10, 180, 40)
    box(badge2, 292, 10, 160, 40)
    const primitives = await extract(page)
    const t1 = primitives.find(item => item.kind === 'text' && (item.text === '高一数学' || item.options?.text === '高一数学'))!
    const t2 = primitives.find(item => item.kind === 'text' && (item.text === '教学课件' || item.options?.text === '教学课件'))!
    const right1 = pixels(t1.options?.x) + pixels(t1.options?.w)
    const left2 = pixels(t2.options?.x)
    expect(right1).toBeLessThan(left2)
    expect(left2 - right1).toBeGreaterThanOrEqual(1)
  })

  it('胶囊扩宽补偿量依据胶囊自身几何尺寸自适应封顶，窄小胶囊不过度膨胀', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
      <div id="container" style="width:800px;height:100px;position:relative">
        <span id="smallBadge" class="rounded-full px-2 py-1" style="position:absolute;left:50px;top:10px;display:inline-block;width:60px;height:24px;background:#2563eb;border-radius:9999px;font-size:12px;color:#fff;text-align:center">标签</span>
        <span id="largeBadge" class="rounded-full px-4 py-2" style="position:absolute;left:200px;top:10px;display:inline-block;width:180px;height:40px;background:#16a34a;border-radius:9999px;font-size:16px;color:#fff;text-align:center">重点内容展示胶囊</span>
      </div>
    </div>`
    const page = document.getElementById('page')!
    const container = document.getElementById('container')!
    const smallBadge = document.getElementById('smallBadge')!
    const largeBadge = document.getElementById('largeBadge')!
    box(page, 0, 0, 1920, 1080)
    box(container, 0, 0, 800, 100)
    box(smallBadge, 50, 10, 60, 24)
    box(largeBadge, 200, 10, 180, 40)
    const primitives = await extract(page)
    const smallText = primitives.find(item => item.kind === 'text' && (item.text === '标签' || item.options?.text === '标签'))!
    const largeText = primitives.find(item => item.kind === 'text' && (item.text === '重点内容展示胶囊' || item.options?.text === '重点内容展示胶囊'))!

    const smallExtra = pixels(smallText.options?.w) - 60
    const largeExtra = pixels(largeText.options?.w) - 180

    // 小胶囊扩宽必须严格受到自身尺寸封顶，不超过 8px（约为自身的 12%）
    expect(smallExtra).toBeGreaterThan(0)
    expect(smallExtra).toBeLessThanOrEqual(8)

    // 大胶囊具备足够的 DrawingML 圆角内缩与字号自适应补偿空间
    expect(largeExtra).toBeGreaterThan(smallExtra)
  })

  it('带有字间距与数学符号省略号的单行文本（如 1 + 2 + 3 + ⋯ + 100）获得充分复合保护，防止 PPT 折行', async () => {
    document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px;position:relative">
      <div style="position:absolute;left:0;top:0;width:1920px;height:1080px">
        <span id="formula" style="position:absolute;left:88px;bottom:140px;font-size:24px;font-weight:600;letter-spacing:8.4px">1 + 2 + 3 + ⋯ + 100</span>
      </div>
    </div>`
    const page = document.getElementById('page')!
    const formula = document.getElementById('formula')!
    box(page, 0, 0, 1920, 1080)
    box(formula, 88, 900, 350, 36)

    const primitives = await extract(page)
    const text = primitives.find(item => item.kind === 'text' && (item.text?.includes('1 + 2 + 3') || item.options?.text?.includes('1 + 2 + 3')))!
    expect(text).toBeDefined()

    const extraPx = pixels(text.options?.w) - 350
    // 原先只有 10.8px 的微弱保护，现在复合保护量应在 30px ~ 55px 之间，足以覆盖 DrawingML spc 累积与微软雅黑字形展开
    expect(extraPx).toBeGreaterThanOrEqual(30)
    expect(extraPx).toBeLessThanOrEqual(55)

    // 右侧有空间时，文本框在适度保护下不会被异常拉满到全屏宽
    expect(pixels(text.options?.w)).toBeLessThan(420)
  })

  it('含有多个数学运算符的表达式能够获得对应符号排版保护', async () => {
    const { page } = fixture(650, 'left', 'a + b - c × d ÷ e = 0', 300)
    const primitives = await extract(page)
    const text = primitives.find(item => item.kind === 'text')!
    const extraPx = pixels(text.options?.w) - 300
    expect(extraPx).toBeGreaterThanOrEqual(15)
  })
})



