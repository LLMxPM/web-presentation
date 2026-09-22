// @vitest-environment jsdom

/**
 * 文件用途：通过真实 pptxgenjs 输出验证 HTML 合并表格会生成 PowerPoint 原生表格 OOXML。
 */

import { strFromU8, unzipSync } from 'fflate'
import PptxGenJS from 'pptxgenjs'
import { describe, expect, it } from 'vitest'
import { PPTXDomConverter } from './PPTXDomConverter'
import type { PptxSlideLike } from './PPTXDomConverter.types'

describe('PPTXDomConverter HTML table integration', () => {
  it('应生成带横向与纵向合并标记的原生 PPT 表格', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table style="width: 600px; height: 180px; border-collapse: collapse; font-family: 'Web Presentation Sans', sans-serif;">
          <tbody>
            <tr style="width: 600px; height: 90px;">
              <th rowspan="2" style="width: 180px; height: 180px; border: 1px solid #94a3b8;">区域</th>
              <th colspan="2" style="width: 420px; height: 90px; border: 1px solid #94a3b8;">季度收入</th>
            </tr>
            <tr style="width: 600px; height: 90px;">
              <td style="width: 200px; height: 90px; border: 1px solid #94a3b8;">Q1</td>
              <td style="width: 220px; height: 90px; border: 1px solid #94a3b8;">Q2</td>
            </tr>
          </tbody>
        </table>
      </div>
    `
    const pptx = new PptxGenJS()
    pptx.defineLayout({ name: 'TEST', width: 13.333, height: 7.5 })
    pptx.layout = 'TEST'
    const slide = pptx.addSlide()
    const converter = new PPTXDomConverter()

    await converter.convertPage({
      slide: slide as unknown as PptxSlideLike,
      pageElement: document.getElementById('page') as HTMLElement,
      pageIndex: 1,
      pageTitle: 'HTML 表格',
      pageRoute: '/table',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      shapeTypes: {
        rect: pptx.ShapeType.rect,
        roundRect: pptx.ShapeType.roundRect,
        ellipse: pptx.ShapeType.ellipse,
        line: pptx.ShapeType.line,
      },
      captureElementAsPng: async () => 'data:image/png;base64,test',
    })

    const output = await pptx.write({ outputType: 'uint8array', compression: true }) as Uint8Array
    const slideXml = strFromU8(unzipSync(output)['ppt/slides/slide1.xml'])

    expect(slideXml).toContain('<a:tbl>')
    expect(slideXml).toContain('gridSpan="2"')
    expect(slideXml).toContain('rowSpan="2"')
    expect(slideXml).toContain('hMerge="1"')
    expect(slideXml).toContain('vMerge="1"')
    expect(slideXml).toContain('typeface="Microsoft YaHei"')
    expect(slideXml).not.toContain('Web Presentation Sans')
  })
})
