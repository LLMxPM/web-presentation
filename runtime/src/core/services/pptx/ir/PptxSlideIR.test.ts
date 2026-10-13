// @vitest-environment jsdom

/**
 * 文件用途：验证 PPTXDomConverter 生成纯数据 PptxSlideIR 以及 PptxSlideProjector 投射到 Slide 的解耦流水线。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import PptxGenJS from 'pptxgenjs'
import { PPTXDomConverter } from '@/core/services/pptx/PPTXDomConverter'
import { DEFAULT_PPTX_SHAPE_TYPES } from '@/core/services/pptx/ir/PptxSlideIR.types'
import { projectSlideIRToSlide } from '@/core/services/pptx/writer/PptxSlideProjector'
import { PptxPackageWriter } from '@/core/services/pptx/writer/PptxPackageWriter'
import { createSlideMock } from '@/core/services/pptx/PPTXDomConverter.test-support'

describe('PptxSlideIR 提取与投射流水线', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('省略 shapeTypes 时使用的默认形状枚举必须与 PptxGenJS 实际枚举一致', () => {
    const realShapeTypes = new PptxPackageWriter().getShapeTypes(new PptxGenJS())

    expect(DEFAULT_PPTX_SHAPE_TYPES).toEqual(realShapeTypes)
  })

  it('应在不传入 PptxGenJS Slide 的情况下独立产出包含背景、图元、渐变指令和报告的 PptxSlideIR', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #0f172a;">
        <div
          style="width: 600px; height: 160px; background-image: linear-gradient(90deg, #2563eb 0%, #7c3aed 100%); border-radius: 16px;"
        >
          <h1 style="width: 480px; height: 64px; font-size: 36px; color: #ffffff;">独立 IR 标题</h1>
        </div>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    const converter = new PPTXDomConverter()

    const slideIR = await converter.extractSlideIR({
      pageElement,
      pageIndex: 2,
      pageTitle: '第二页架构',
      pageRoute: '/page-2',
      speakerNotes: '演讲者备注内容',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,unused'),
    })

    expect(slideIR.pageIndex).toBe(2)
    expect(slideIR.pageTitle).toBe('第二页架构')
    expect(slideIR.speakerNotes).toBe('演讲者备注内容')
    expect(slideIR.background).toEqual({
      color: '0F172A',
      transparency: 0,
    })
    expect(slideIR.gradientFills).toHaveLength(1)
    expect(slideIR.primitives.some(item => item.kind === 'shape')).toBe(true)
    expect(slideIR.primitives.some(item => item.kind === 'text' && item.text === '独立 IR 标题')).toBe(true)
    expect(slideIR.report.items.length).toBeGreaterThanOrEqual(2)

    const slideMock = {
      ...createSlideMock(),
      addNotes: vi.fn(),
    }
    const collectedGradients: unknown[] = []
    projectSlideIRToSlide(slideIR, slideMock, instruction => collectedGradients.push(instruction))

    expect(slideMock.addNotes).toHaveBeenCalledWith('演讲者备注内容')
    expect(slideMock.background).toEqual({
      color: '0F172A',
      transparency: 0,
    })
    expect(slideMock.addShape).toHaveBeenCalledTimes(1)
    expect(slideMock.addText).toHaveBeenCalledWith('独立 IR 标题', expect.objectContaining({
      color: 'FFFFFF',
    }))
    expect(collectedGradients).toHaveLength(1)
  })
})
