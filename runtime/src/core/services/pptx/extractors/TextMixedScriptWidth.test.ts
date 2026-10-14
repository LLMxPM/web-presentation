/** 文件功能：复现页面 395 的 Flex 直属文本导出，验证数字混排、符号补偿及单行扩宽的布局边界。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PPTXDomConverter } from '../PPTXDomConverter'

const PAGE395_TEXT = '核心动作是“配对”——把 100 个不同的数，变成 50 组相同的和。'
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

/** 构造测量矩形；与真实页面的圆点、间距和文本包围盒一致。 */
function rect(x: number, y: number, width: number, height: number): DOMRect {
  return { x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON: () => ({}) }
}

/** 模拟真实 Flex 行及 Range 测量，可选择紧列、相邻图元和已发生换行的文字。 */
function fixture({ width = 982, text = PAGE395_TEXT, multiline = false, peer = false } = {}) {
  document.body.innerHTML = `<div id="page" style="width:1920px;height:1080px"><ul style="width:${width}px;height:200px">
    <li style="display:flex;gap:15px;font-size:22.5px;line-height:36.5625px"><span style="width:10px;height:10px;background:blue"></span>${text}</li>
    ${peer ? '<div id="peer" style="width:30px;height:30px;background:red"></div>' : ''}</ul></div>`
  const page = document.getElementById('page')!
  const list = page.querySelector('ul')!
  const row = page.querySelector('li')!
  const bullet = row.querySelector('span')!
  const textNode = row.lastChild!
  vi.spyOn(page, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 1920, 1080))
  vi.spyOn(list, 'getBoundingClientRect').mockReturnValue(rect(824, 600, width, 200))
  vi.spyOn(row, 'getBoundingClientRect').mockReturnValue(rect(824, 710.75, width, multiline ? 73.125 : 36.5625))
  vi.spyOn(bullet, 'getBoundingClientRect').mockReturnValue(rect(824, 723.25, 10, 10))
  if (peer) vi.spyOn(page.querySelector('#peer')!, 'getBoundingClientRect').mockReturnValue(rect(1529, 713.75, 30, 30))
  vi.spyOn(document, 'createRange').mockImplementation(() => {
    let selected: Node | null = null
    return {
      selectNodeContents: (node: Node) => { selected = node },
      getClientRects: () => selected === textNode
        ? [rect(849, 713.75, 642.265625, 30), ...(multiline ? [rect(849, 750.3125, 120, 30)] : [])]
        : [],
    } as unknown as Range
  })
  return page
}

/** 提取目标可编辑文本，确保没有截图降级或 DOM 修改。 */
async function extract(page: HTMLElement) {
  const original = page.outerHTML
  const capture = vi.fn<(element: HTMLElement) => Promise<string>>()
  const ir = await new PPTXDomConverter().extractSlideIR({ pageElement: page, pageIndex: 1, pageTitle: '混排宽度', pageRoute: '/mixed',
    pageWidthPx: 1920, pageHeightPx: 1080, slideWidthIn: 13.333, slideHeightIn: 7.5, captureElementAsPng: capture })
  expect(capture).not.toHaveBeenCalled()
  expect(page.outerHTML).toBe(original)
  const primitive = ir.primitives.find(item => item.kind === 'text' && typeof item.text === 'string' && item.text.includes('核心动作'))
  if (!primitive || primitive.kind !== 'text') throw new Error('未找到测试目标文本图元')
  return primitive
}

/** 还原导出英寸，检查字宽和容器的几何关系。 */
function pixels(value: unknown): number { return Number(value) / 13.333 * 1920 }

describe('PPTX 中文数字混排的单行宽度', () => {
  it('395 页单行覆盖约 684.3px 的导出字体字宽，保持字号和原生文本', async () => {
    const primitive = await extract(fixture())
    expect(pixels(primitive.options?.w)).toBeGreaterThan(684.3)
    expect(pixels(primitive.options?.x)).toBeCloseTo(849, 1)
    expect(primitive.options?.fontSize).toBe(11.3)
    expect(primitive.text).toBe(PAGE395_TEXT)
    expect(primitive.options?.fit).toBe('none')
  })

  it('只有中文加数字、没有英文字母也能使用 Flex 行的剩余空间', async () => {
    const primitive = await extract(fixture({ text: '核心动作包含 100 个数字，分成 50 组' }))
    expect(pixels(primitive.options?.w)).toBeGreaterThan(900)
    expect(pixels(primitive.options?.x) + pixels(primitive.options?.w)).toBeLessThanOrEqual(1806.02)
  })

  it('紧列不会为了容纳目标字体越过容器或侵入左侧圆点', async () => {
    const primitive = await extract(fixture({ width: 680 }))
    expect(pixels(primitive.options?.x)).toBeGreaterThanOrEqual(842.48)
    expect(pixels(primitive.options?.x) + pixels(primitive.options?.w)).toBeLessThanOrEqual(1504.02)
    expect(pixels(primitive.options?.w)).toBeLessThan(684.3)
    expect(primitive.options?.wrap).not.toBe(false)
    expect(primitive.options?.fontSize).toBe(11.3)
  })

  it('同高度相邻图元限制扩宽，保留间隔', async () => {
    const primitive = await extract(fixture({ peer: true }))
    expect(pixels(primitive.options?.x) + pixels(primitive.options?.w)).toBeLessThan(1529)
    expect(primitive.options?.fontSize).toBe(11.3)
  })

  it('浏览器已折成两行的同一句话保留原框，不借用空白或增加符号数字补偿', async () => {
    const primitive = await extract(fixture({ multiline: true }))
    expect(pixels(primitive.options?.w)).toBeCloseTo(642.265625, 1)
    expect(pixels(primitive.options?.x)).toBeCloseTo(849, 1)
  })
})
