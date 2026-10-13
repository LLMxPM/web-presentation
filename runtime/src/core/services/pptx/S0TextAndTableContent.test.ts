// @vitest-environment jsdom

/**
 * 文件用途：验证 S0 阶段文本、换行与表格解析（退出条件 3 & 4：表格“甲换行乙”及局部加粗保留、隐藏文字不进入 XML）。
 */

import { strFromU8, unzipSync } from 'fflate'
import PptxGenJS from 'pptxgenjs'
import { afterEach, describe, expect, it } from 'vitest'
import { PPTXDomConverter } from './PPTXDomConverter'
import { PPTXDomRichTextParser } from './PPTXDomRichTextParser'
import type { PptxSlideLike } from './PPTXDomConverter.types'

const SLIDE_WIDTH_IN = 13.333
const SLIDE_HEIGHT_IN = 7.5

afterEach(() => {
  document.body.innerHTML = ''
})

function createPptxSlide(): { pptx: PptxGenJS; slide: PptxGenJS.Slide } {
  const pptx = new PptxGenJS()
  pptx.defineLayout({ name: 'TEST', width: SLIDE_WIDTH_IN, height: SLIDE_HEIGHT_IN })
  pptx.layout = 'TEST'
  return { pptx, slide: pptx.addSlide() }
}

async function convertPageToSlideXml(pptx: PptxGenJS, slide: PptxGenJS.Slide): Promise<string> {
  const converter = new PPTXDomConverter()
  await converter.convertPage({
    slide: slide as unknown as PptxSlideLike,
    pageElement: document.getElementById('page') as HTMLElement,
    pageIndex: 1,
    pageTitle: '表格与文本导出',
    pageRoute: '/content-test',
    pageWidthPx: 1920,
    pageHeightPx: 1080,
    slideWidthIn: SLIDE_WIDTH_IN,
    slideHeightIn: SLIDE_HEIGHT_IN,
    shapeTypes: {
      rect: pptx.ShapeType.rect,
      roundRect: pptx.ShapeType.roundRect,
      ellipse: pptx.ShapeType.ellipse,
      line: pptx.ShapeType.line,
    },
    captureElementAsPng: async () => 'data:image/png;base64,test',
  })

  const output = (await pptx.write({ outputType: 'uint8array', compression: true })) as Uint8Array
  return strFromU8(unzipSync(output)['ppt/slides/slide1.xml'])
}

describe('S0 文本与表格内容保留', () => {
  it('表格中“甲换行乙”与局部加粗必须保留在真实 OOXML 中', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table style="width: 800px; height: 200px; border-collapse: collapse;">
          <tbody>
            <tr style="width: 800px; height: 200px;">
              <td style="width: 400px; height: 200px;">甲<br>乙</td>
              <td style="width: 400px; height: 200px;">常规文本 <b>加粗重点</b> 尾部说明</td>
            </tr>
          </tbody>
        </table>
      </div>
    `
    const { pptx, slide } = createPptxSlide()
    const slideXml = await convertPageToSlideXml(pptx, slide)

    // 退出条件 3：表格“甲换行乙”保留（生成多个 a:r 或换行 a:br）
    expect(slideXml).toContain('甲')
    expect(slideXml).toContain('乙')
    // 单元格 1 内“甲”与“乙”位于不同行（通过 a:br 或独立 a:p）
    expect(slideXml).toMatch(/甲[\s\S]*?(?:<a:br|<a:p)[\s\S]*?乙/)

    // 局部加粗保留（<b> 对应 <a:rPr b="1">）
    expect(slideXml).toContain('加粗重点')
    expect(slideXml).toMatch(/<a:rPr[^>]*\bb="1"[^>]*>[\s\S]*?<a:t>加粗重点<\/a:t>/)
  })

  it('隐藏 inline（display:none / visibility:hidden / hidden 属性）绝对不能进入 PPTX OOXML', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="display: block; width: 800px; height: 60px; font-size: 20px;">
          可见文字首段
          <span style="display: none;">隐藏文字_DISPLAY_NONE</span>
          <span style="visibility: hidden;">隐藏文字_VISIBILITY_HIDDEN</span>
          <span hidden>隐藏文字_HIDDEN_ATTR</span>
          可见文字尾段
        </p>
        <table style="width: 600px; height: 120px; border-collapse: collapse;">
          <tbody>
            <tr style="width: 600px; height: 120px;">
              <td style="width: 600px; height: 120px;">
                单元格可见
                <span style="display: none;">表格隐藏_SECRET</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    `
    const { pptx, slide } = createPptxSlide()
    const slideXml = await convertPageToSlideXml(pptx, slide)

    // 退出条件 4：隐藏文字不进入 XML
    expect(slideXml).toContain('可见文字首段')
    expect(slideXml).toContain('可见文字尾段')
    expect(slideXml).toContain('单元格可见')

    expect(slideXml).not.toContain('隐藏文字_DISPLAY_NONE')
    expect(slideXml).not.toContain('隐藏文字_VISIBILITY_HIDDEN')
    expect(slideXml).not.toContain('隐藏文字_HIDDEN_ATTR')
    expect(slideXml).not.toContain('表格隐藏_SECRET')
  })

  it('连续 br 标签应保留空行语义，不应被合并为单次换行', () => {
    const parser = new PPTXDomRichTextParser()
    const container = document.createElement('div')
    container.innerHTML = '第一段<br><br>第二段'
    document.body.appendChild(container)

    const result = parser.parse(container, () => ({}))
    expect(result).not.toBeNull()

    // 包含连续换行：第一段\n\n第二段
    expect(result?.text).toBe('第一段\n\n第二段')

    // runs 中包含空行 run
    const runs = result?.runs ?? []
    expect(runs.some(run => run.text === '' && run.options?.softBreakBefore)).toBe(true)
  })
})
