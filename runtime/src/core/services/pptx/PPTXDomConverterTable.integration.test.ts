// @vitest-environment jsdom

/**
 * 文件用途：通过真实 pptxgenjs 输出验证 HTML 合并表格与 Runtime Kit DataTable 都会生成 PowerPoint 原生表格 OOXML。
 */

import { strFromU8, unzipSync } from 'fflate'
import PptxGenJS from 'pptxgenjs'
import { createApp, nextTick, type App } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import DataTable from '@runtime-kit/public/components/data/DataTable.v1.vue'
import { PPTXDomConverter } from './PPTXDomConverter'
import type { PptxSlideLike } from './PPTXDomConverter.types'

const SLIDE_WIDTH_IN = 13.333
const SLIDE_HEIGHT_IN = 7.5

let mountedApp: App<Element> | null = null

afterEach(() => {
  mountedApp?.unmount()
  mountedApp = null
  document.body.innerHTML = ''
})

/**
 * 准备 pptxgenjs 实例与首页 slide。
 * @returns 实例与 slide，供转换与写出共用
 */
function createPptxSlide(): { pptx: PptxGenJS, slide: PptxGenJS.Slide } {
  const pptx = new PptxGenJS()
  pptx.defineLayout({ name: 'TEST', width: SLIDE_WIDTH_IN, height: SLIDE_HEIGHT_IN })
  pptx.layout = 'TEST'
  return { pptx, slide: pptx.addSlide() }
}

/**
 * 对 #page 执行可编辑转换，并解包返回 slide1.xml 文本。
 * @param pptx pptxgenjs 实例
 * @param slide 目标 slide
 * @returns slide1.xml 内容
 */
async function convertPageToSlideXml(pptx: PptxGenJS, slide: PptxGenJS.Slide): Promise<string> {
  const converter = new PPTXDomConverter()
  await converter.convertPage({
    slide: slide as unknown as PptxSlideLike,
    pageElement: document.getElementById('page') as HTMLElement,
    pageIndex: 1,
    pageTitle: '表格导出',
    pageRoute: '/table',
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

  const output = await pptx.write({ outputType: 'uint8array', compression: true }) as Uint8Array
  return strFromU8(unzipSync(output)['ppt/slides/slide1.xml'])
}

/**
 * 统计 XML 中某个片段出现次数。
 * @param xml slide XML
 * @param needle 待统计片段
 */
function countOccurrences(xml: string, needle: string): number {
  return xml.split(needle).length - 1
}

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
    const { pptx, slide } = createPptxSlide()

    const slideXml = await convertPageToSlideXml(pptx, slide)

    expect(slideXml).toContain('<a:tbl>')
    expect(slideXml).toContain('gridSpan="2"')
    expect(slideXml).toContain('rowSpan="2"')
    expect(slideXml).toContain('hMerge="1"')
    expect(slideXml).toContain('vMerge="1"')
    expect(slideXml).toContain('typeface="Microsoft YaHei"')
    expect(slideXml).not.toContain('Web Presentation Sans')
  })
})

describe('PPTXDomConverter Runtime Kit DataTable integration', () => {
  /**
   * 在 #page 中挂载真实 DataTable 组件，使断言覆盖「组件产出 DOM 标记 → 原生表格 OOXML」全链路。
   */
  async function mountDataTablePage(): Promise<void> {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; font-family: 'Web Presentation Sans', sans-serif;"></div>
    `
    mountedApp = createApp(DataTable, {
      rows: [
        ['指标', 'Q1'],
        ['收入', '128 万'],
      ],
      width: 600,
      height: 180,
      style: { position: 'absolute', left: '100px', top: '80px' },
      styles: {
        cell: { style: { background: '#f8fafc', color: '#0f172a' } },
        rows: { 0: { style: { background: '#e2e8f0', fontWeight: 700 } } },
      },
    })
    mountedApp.mount(document.getElementById('page') as HTMLElement)
    await nextTick()
  }

  it('应把 DataTable 导出为原生 PPT 表格而不是局部截图', async () => {
    await mountDataTablePage()
    const { pptx, slide } = createPptxSlide()

    const slideXml = await convertPageToSlideXml(pptx, slide)

    expect(slideXml).toContain('<a:tbl>')
    expect(slideXml).not.toContain('<p:pic>')
    expect(countOccurrences(slideXml, '<a:gridCol')).toBe(2)
    expect(countOccurrences(slideXml, '<a:tr ')).toBe(2)
  })

  it('应按行列索引写出全部单元格文本', async () => {
    await mountDataTablePage()
    const { pptx, slide } = createPptxSlide()

    const slideXml = await convertPageToSlideXml(pptx, slide)

    expect(slideXml).toContain('<a:t>指标</a:t>')
    expect(slideXml).toContain('<a:t>Q1</a:t>')
    expect(slideXml).toContain('<a:t>收入</a:t>')
    expect(slideXml).toContain('<a:t>128 万</a:t>')
  })

  it('应保留单元格背景与粗体，并替换平台字体', async () => {
    await mountDataTablePage()
    const { pptx, slide } = createPptxSlide()

    const slideXml = await convertPageToSlideXml(pptx, slide)

    expect(slideXml).toContain('val="E2E8F0"')
    expect(slideXml).toContain('val="F8FAFC"')
    expect(slideXml).toContain('b="1"')
    expect(slideXml).toContain('typeface="Microsoft YaHei"')
    expect(slideXml).not.toContain('Web Presentation Sans')
  })

  it('DataTable v1 不支持合并单元格，不应写出任何合并标记', async () => {
    await mountDataTablePage()
    const { pptx, slide } = createPptxSlide()

    const slideXml = await convertPageToSlideXml(pptx, slide)

    expect(slideXml).not.toContain('gridSpan=')
    expect(slideXml).not.toContain('rowSpan=')
    expect(slideXml).not.toContain('hMerge=')
    expect(slideXml).not.toContain('vMerge=')
  })
})
