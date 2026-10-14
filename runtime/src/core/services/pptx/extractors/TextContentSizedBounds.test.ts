/** 文件功能：复现页面 396 的内容宽度 Flex 包裹，验证最小宽度、真实上界、裁切与相邻对象的扩宽语义。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PPTXDomConverter } from '../PPTXDomConverter'

const PAGE396_TEXT = '由对称性，每一对的和都相等，共 n 对'
interface FixtureOptions { wrapperClass?: string; wrapperStyle?: string; layout?: 'flex' | 'grid'; multiline?: boolean; peer?: boolean }
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 使用实际页面几何构造 DOMRect，避免 jsdom 的零布局影响边界判断。 */
function rect(x: number, y: number, width: number, height: number): DOMRect {
  return { x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}) }
}

/** 建立带编号、标题与下方公式的卡片；透明包裹按标题内容收缩，卡片右侧留有空白。 */
function fixture({ wrapperClass = 'min-w-0', wrapperStyle = '', layout = 'flex', multiline = false, peer = false }: FixtureOptions = {}) {
  document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px">
    <section style="display:${layout};width:1204px;height:127px;gap:25px;padding:20px 35px;border:1px solid black;background:#eee">
      <span id="number" style="width:50px;height:50px;background:blue;border-radius:50%">4</span>
      <div id="wrapper" class="${wrapperClass}" style="${wrapperStyle}">
        <p id="target" style="font-size:22.5px;font-weight:600;line-height:35px;margin:0">${PAGE396_TEXT}</p>
        <p id="formula" style="font-size:30px;line-height:40px;margin:10px 0 0">2Sn = n(a1 + an)</p>
      </div>
      ${peer ? '<div id="peer" style="width:30px;height:35px;background:red"></div>' : ''}
    </section></div>`
  const page = document.getElementById('page')!
  const target = page.querySelector('#target')!
  const formula = page.querySelector('#formula')!
  vi.spyOn(page, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 1920, 1080))
  vi.spyOn(page.querySelector('section')!, 'getBoundingClientRect').mockReturnValue(rect(73, 670.625, 1204, 127))
  vi.spyOn(page.querySelector('#number')!, 'getBoundingClientRect').mockReturnValue(rect(109, 696.625, 50, 50))
  vi.spyOn(page.querySelector('#wrapper')!, 'getBoundingClientRect').mockReturnValue(rect(184, 691.625, 385.5, 85))
  vi.spyOn(target, 'getBoundingClientRect').mockReturnValue(rect(184, 691.625, 385.5, 35))
  vi.spyOn(formula, 'getBoundingClientRect').mockReturnValue(rect(184, 736.625, 385.5, 40))
  if (peer) vi.spyOn(page.querySelector('#peer')!, 'getBoundingClientRect').mockReturnValue(rect(578, 691.625, 30, 35))
  vi.spyOn(document, 'createRange').mockImplementation(() => {
    let node: Node | null = null
    return {
      selectNodeContents: (selected: Node) => { node = selected },
      getClientRects: () => node === target.firstChild
        ? [rect(184, 693.625, 385.5, 30), ...(multiline ? [rect(184, 728.625, 100, 30)] : [])]
        : node === formula.firstChild ? [rect(184, 739, 250, 36)] : [],
    } as unknown as Range
  })
  return page
}

/** 提取标题的可编辑文本，确认边界修正不改写 DOM 或触发截图。 */
async function extract(page: HTMLElement) {
  const original = page.outerHTML
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const ir = await new PPTXDomConverter().extractSlideIR({ pageElement: page, pageIndex: 1, pageTitle: '内容宽度边界', pageRoute: '/396',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5, captureElementAsPng: capture })
  expect(capture).not.toHaveBeenCalled()
  expect(page.outerHTML).toBe(original)
  const target = ir.primitives.find(item => item.kind === 'text' && item.text === PAGE396_TEXT)
  if (!target || target.kind !== 'text') throw new Error('未找到页面 396 的目标标题')
  return target
}

/** 将英寸还原成画布像素，和字体审计及原始坐标对拍。 */
function pixels(value: unknown): number { return Number(value) / 13.333 * 1920 }

describe('PPTX 内容宽度包裹的边界', () => {
  it.each([
    { wrapperClass: 'min-w-0' },
    { wrapperClass: 'min-w-[200px]' },
    { wrapperClass: '', wrapperStyle: 'min-width:0' },
    { wrapperClass: '', wrapperStyle: 'min-width:200px' },
  ])('最小宽度 $wrapperClass/$wrapperStyle 不锁死 396 页的透明 Flex 包裹', async options => {
    const target = await extract(fixture(options))
    expect(pixels(target.options?.w)).toBeGreaterThan(389.8)
    expect(pixels(target.options?.w)).toBeLessThan(410)
    expect(pixels(target.options?.x)).toBeCloseTo(184, 1)
    expect(target.options?.fontSize).toBe(11.3)
    expect(target.options?.bold).toBe(true)
    expect(target.options?.fit).toBe('none')
  })

  it.each([
    { wrapperClass: 'w-[385.5px]' },
    { wrapperClass: 'max-w-[385.5px]' },
    { wrapperClass: 'md:w-[385.5px]' },
    { wrapperClass: '', wrapperStyle: 'width:385.5px' },
    { wrapperClass: '', wrapperStyle: 'max-width:385.5px' },
    { wrapperClass: '', wrapperStyle: 'flex-basis:385.5px' },
  ])('实际尺寸约束 $wrapperClass/$wrapperStyle 继续限制文本扩宽', async options => {
    const target = await extract(fixture(options))
    expect(pixels(target.options?.w)).toBeCloseTo(385.5, 1)
    expect(pixels(target.options?.x)).toBeCloseTo(184, 1)
  })

  it.each(['background:blue', 'padding-right:1px', 'overflow-x:hidden', 'overflow-x:clip'])('带 %s 的包裹保留自身边界', async wrapperStyle => {
    const target = await extract(fixture({ wrapperStyle }))
    expect(pixels(target.options?.x) + pixels(target.options?.w)).toBeLessThanOrEqual(569.52)
  })

  it.each([
    { layout: 'grid' as const },
    { wrapperStyle: 'flex-grow:1' },
  ])('网格单元或已分配宽度的 Flex 子项保留自身边界', async options => {
    const target = await extract(fixture(options))
    expect(pixels(target.options?.w)).toBeCloseTo(385.5, 1)
  })

  it('透明包裹放宽后仍避开编号和同高度相邻图元', async () => {
    const target = await extract(fixture({ peer: true }))
    expect(pixels(target.options?.x)).toBeGreaterThan(159)
    expect(pixels(target.options?.x) + pixels(target.options?.w)).toBeLessThan(578)
  })

  it('浏览器实际多行仍保留原始框宽，不通过透明包裹扩宽重排', async () => {
    const target = await extract(fixture({ multiline: true }))
    expect(pixels(target.options?.w)).toBeCloseTo(385.5, 1)
    expect(pixels(target.options?.x)).toBeCloseTo(184, 1)
  })
})
