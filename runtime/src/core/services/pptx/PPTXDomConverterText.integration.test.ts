// @vitest-environment jsdom

/**
 * 文件用途：通过真实 pptxgenjs 输出验证普通 HTML 文本 padding 会写入 PowerPoint 文本框边距。
 */

import { strFromU8, unzipSync } from 'fflate'
import PptxGenJS from 'pptxgenjs'
import { describe, expect, it } from 'vitest'
import { PPTXDomConverter } from './PPTXDomConverter'
import type { PptxSlideLike } from './PPTXDomConverter.types'

describe('PPTXDomConverter text integration', () => {
  it('应将 padding-left 写入 PPT 文本框 marL', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 800px; height: 40px; padding-left: 24px; font-size: 16px;">缩进文本</div>
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
      pageTitle: '文本缩进',
      pageRoute: '/text-indent',
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

    expect(slideXml).toContain('lIns="152400"')
    expect(slideXml).toContain('rIns="0"')
  })

  it('应在单个 PPT 文本框中生成多个带样式的文本 run', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 800px; height: 80px; color: #0f172a; font-size: 16px;">
          <span style="color: #7c3aed;">"model"</span>: <span style="color: #16a34a;">"xxx"</span><br>
          <strong style="font-weight: 700; color: #dc2626;">下一行</strong>
        </div>
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
      pageTitle: '富文本',
      pageRoute: '/rich-text',
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

    expect(slideXml.match(/<p:sp>/g)).toHaveLength(1)
    expect(slideXml.match(/<a:r>/g)?.length).toBeGreaterThanOrEqual(4)
    expect(slideXml).toContain('<a:srgbClr val="7C3AED"/>')
    expect(slideXml).toContain('<a:srgbClr val="16A34A"/>')
    expect(slideXml).toContain('<a:srgbClr val="DC2626"/>')
    expect(slideXml).toContain('<a:br/>')
  })

  it('含文本的 rounded-full 正圆应生成宽高一致的 ellipse', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="rounded-full p-2"
          style="display: inline-block; width: 40px; height: 40px; padding: 8px; background: #2563eb; border-radius: 9999px; color: #ffffff; font-size: 16px;"
        >1</span>
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
      pageTitle: '圆形文本',
      pageRoute: '/circle-text',
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
    const extent = /<a:ext cx="(\d+)" cy="(\d+)"\/>/.exec(slideXml)

    expect(slideXml).toContain('<a:prstGeom prst="ellipse">')
    expect(extent).not.toBeNull()
    expect(extent?.[1]).toBe(extent?.[2])
  })

  it('普通圆角正方形应生成宽高一致且保留圆角的 roundRect', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="w-10 h-10 rounded-lg"
          style="display: inline-block; width: 40px; height: 40px; background: #f1f5f9; border-radius: 8px; color: #0f172a; font-size: 16px;"
        >A</span>
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
      pageTitle: '圆角正方形文本',
      pageRoute: '/rounded-square-text',
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
    const extent = /<a:ext cx="(\d+)" cy="(\d+)"\/>/.exec(slideXml)

    expect(slideXml).toContain('<a:prstGeom prst="roundRect">')
    expect(slideXml).toContain('<a:gd name="adj"')
    expect(extent).not.toBeNull()
    expect(extent?.[1]).toBe(extent?.[2])
  })

  it('纯 2D 旋转胶囊应写入原生 rot 并保留画布外负坐标', async () => {
    document.body.innerHTML = `
      <div id="page" style="position: relative; width: 1920px; height: 1080px;">
        <span
          class="rounded-full"
          style="position: absolute; left: -150px; top: 110px; display: inline-block; width: 320px; height: 64px; padding: 12px 24px; box-sizing: border-box; background: #f59e0b; border: 3px solid #2563eb; border-radius: 9999px; color: #ffffff; font-size: 20px; transform: rotate(-8deg);"
        >不到 1 元！</span>
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
      pageTitle: '旋转胶囊',
      pageRoute: '/rotated-capsule',
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
    const offset = /<a:xfrm rot="-480000"><a:off x="(-?\d+)" y="(-?\d+)"\/>/.exec(slideXml)

    expect(slideXml).toContain('<a:prstGeom prst="roundRect">')
    expect(offset).not.toBeNull()
    expect(Number(offset?.[1])).toBeLessThan(0)
  })
})
