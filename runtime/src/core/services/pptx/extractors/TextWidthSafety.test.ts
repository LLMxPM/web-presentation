/** 文件用途：回归 PPTX 扩宽的可见障碍、已有越界、胶囊总预算和预览缩放，验证原生导出不引入碰撞或位置漂移。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { strFromU8, unzipSync } from 'fflate'
import { PPTXDomConverter } from '../PPTXDomConverter'
import { projectSlideIRToSlide } from '../writer/PptxSlideProjector'

const QUOTED = '决定了“一致性”能否代表进步。'
const PIXELS_PER_INCH = 1920 / 13.333
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 提供浏览器实测矩形；可按预览比例缩放，设计画布和源 CSS 尺寸保持不变。 */
function measure(element: Element, x: number, y: number, width: number, height: number, scale = 1): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    x: x * scale, y: y * scale, left: x * scale, top: y * scale, right: (x + width) * scale, bottom: (y + height) * scale,
    width: width * scale, height: height * scale, toJSON: () => ({}),
  })
}

/** 构造具有真实空白的画布；透明包裹和图元可由具体回归设置。 */
function fixture(content: string, scale = 1) {
  document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px;position:relative">
    <section style="position:absolute;left:100px;top:100px;width:900px;height:200px">${content}</section></div>`
  const page = document.getElementById('page')!
  const container = page.querySelector('section')!
  measure(page, 0, 0, 1920, 1080, scale)
  measure(container, 100, 100, 900, 200, scale)
  return { page, container, target: page.querySelector('#target')! }
}

/** 提取可编辑 IR 并确认导出未修改 DOM、未触发截图。 */
async function extract(page: HTMLElement) {
  const original = page.outerHTML
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const ir = await new PPTXDomConverter().extractSlideIR({ pageElement: page, pageIndex: 1, pageTitle: '扩宽安全', pageRoute: '/safety',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5, captureElementAsPng: capture })
  expect(capture).not.toHaveBeenCalled()
  expect(page.outerHTML).toBe(original)
  return ir
}

/** 将原生图元的英寸尺寸还原成设计像素，避免测试把预览缩放误认为版式变化。 */
function pixels(value: unknown): number { return Number(value) * PIXELS_PER_INCH }

describe('PPTX 扩宽安全边界', () => {
  it.each(['svg', 'wrapped-shape', 'full-page-wrapper'])('%s 即使事件穿透，实际可见图元仍阻止圆角卡片侵入', async kind => {
    const peer = kind === 'svg'
      ? '<svg id="peer" style="position:absolute;left:556px;top:0;width:30px;height:54px;pointer-events:none" viewBox="0 0 30 54"><rect width="30" height="54" fill="blue"/></svg>'
      : '<div id="wrapper" style="position:absolute;inset:0;pointer-events:none"><div id="peer" style="position:absolute;left:556px;top:0;width:30px;height:54px;background:blue"></div></div>'
    const { page, container, target } = fixture(`<p id="target" style="width:550px;height:54px;font-size:38px;line-height:54px;margin:0;background:#fee;border-radius:10px">${QUOTED}</p>${peer}`)
    measure(target, 100, 100, 550, 54)
    const wrapper = page.querySelector('#wrapper')
    if (wrapper && kind === 'full-page-wrapper') {
      page.appendChild(wrapper)
      measure(wrapper, 0, 0, 1920, 1080)
    } else if (wrapper) measure(wrapper, 100, 100, 900, 200)
    const peerElement = page.querySelector('#peer')!
    measure(peerElement, 656, 100, 30, 54)
    const ir = await extract(page)
    const text = ir.primitives.find(item => item.kind === 'text' && item.text === QUOTED)!
    expect(text.options?.shape).toBe('roundRect')
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
    expect(pixels(text.options?.x) + pixels(text.options?.w)).toBeLessThan(656)
    expect(text.options?.fontSize).toBe(19)
    const pptx = new PptxGenJS()
    projectSlideIRToSlide(ir, pptx.addSlide())
    const xml = strFromU8(unzipSync(await pptx.write({ outputType: 'uint8array' }) as Uint8Array)['ppt/slides/slide1.xml'])
    expect(xml).toContain(`<a:t>${QUOTED}</a:t>`)
    expect(xml).toContain('wrap="square"')
    expect(container.contains(target)).toBe(true)
  })

  it('透明事件穿透包裹中的实际文字也参与防碰撞', async () => {
    const { page, target } = fixture(`<p id="target" style="width:550px;height:54px;font-size:38px;line-height:54px;margin:0">${QUOTED}</p>
      <div style="position:absolute;inset:0;pointer-events:none"><span id="peer">可见标签</span></div>`)
    measure(target, 100, 100, 550, 54)
    measure(page.querySelector('#peer')!, 656, 100, 100, 54)
    const text = (await extract(page)).primitives.find(item => item.kind === 'text' && item.text === QUOTED)!
    expect(pixels(text.options?.x) + pixels(text.options?.w)).toBeLessThan(656)
  })

  it('空的整页透明包裹不阻止扩宽', async () => {
    const { page, target } = fixture(`<p id="target" style="width:550px;height:54px;font-size:38px;line-height:54px;margin:0">${QUOTED}</p>`)
    measure(target, 100, 100, 550, 54)
    const wrapper = document.createElement('div')
    wrapper.style.cssText = 'position:absolute;inset:0;pointer-events:none'
    page.appendChild(wrapper)
    measure(wrapper, 0, 0, 1920, 1080)
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(550)
  })

  it.each(['left', 'center', 'right'])('已有越界的无显式宽度 %s 标签保留原位置和宽度', async align => {
    const { page, container, target } = fixture(`<span id="target" style="position:absolute;left:100px;top:0;font-size:16px;line-height:30px;white-space:nowrap;text-align:${align}">越界标签</span>`)
    container.style.width = '120px'
    measure(container, 100, 100, 120, 60)
    measure(target, 200, 100, 64, 30)
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.x)).toBeCloseTo(200, 1)
    expect(pixels(text.options?.w)).toBeCloseTo(64, 1)
    expect(text.options?.fontSize).toBe(8)
  })

  it.each(['A/B/C', 'runtime-kit.manifest.json', '“引用”', '+ × ⋯ ='])('小胶囊的 %s 复合补偿不能突破总宽度上限', async textContent => {
    const { page, target } = fixture(`<span id="target" style="display:inline-block;width:60px;height:24px;background:blue;border-radius:9999px;font-size:12px;line-height:24px;letter-spacing:2px;white-space:nowrap;text-align:center">${textContent}</span>`)
    measure(target, 100, 100, 60, 24)
    const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
    expect(pixels(text.options?.w)).toBeGreaterThan(60)
    expect(pixels(text.options?.w)).toBeLessThanOrEqual(60 * 1.12 + 0.02)
    expect(text.options?.fontSize).toBe(6)
  })

  it('同一胶囊在不同预览缩放下具有相同原生圆角、字号和扩宽量', async () => {
    const widths: number[] = []
    const radii: number[] = []
    for (const scale of [1, 0.5, 2]) {
      const { page, target } = fixture('<span id="target" style="display:inline-block;width:200px;height:80px;border-radius:9999px;background:blue;font-size:8px;line-height:80px;text-align:center">标签</span>', scale)
      measure(target, 100, 100, 200, 80, scale)
      // 模拟实际文字行，避免无布局环境把放大后的盒高直接与未缩放 CSS 行高比较。
      vi.spyOn(document, 'createRange').mockImplementation(() => {
        let node: Node | null = null
        return {
          selectNodeContents: (selected: Node) => { node = selected },
          getClientRects: () => node === target.firstChild
            ? [{ left: 100 * scale, top: 136 * scale, width: 16 * scale, height: 8 * scale, right: 116 * scale, bottom: 144 * scale }]
            : [],
        } as unknown as Range
      })
      const text = (await extract(page)).primitives.find(item => item.kind === 'text')!
      widths.push(pixels(text.options?.w))
      radii.push(pixels(text.options?.rectRadius))
      expect(text.options?.fontSize).toBe(4)
    }
    expect(widths[0]).toBeGreaterThan(220)
    for (let index = 1; index < widths.length; index++) {
      expect(widths[index]).toBeCloseTo(widths[0], 1)
      expect(radii[index]).toBeCloseTo(radii[0], 1)
    }
  })
})
