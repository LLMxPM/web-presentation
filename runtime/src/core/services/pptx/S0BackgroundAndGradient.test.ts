// @vitest-environment jsdom

/**
 * 文件用途：验证 S0 阶段背景、渐变几何与图元关联（退出条件 5：根渐变、圆角渐变和有子内容的渐变容器正确输出，无重复遮盖）。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { PPTXDomConverter } from './PPTXDomConverter'
import { createSlideMock } from './PPTXDomConverter.test-support'
import type { PptxSlideLike } from './PPTXDomConverter.types'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('S0 背景、渐变与图元关联', () => {
  it('页面根节点的 linear-gradient 必须纳入视觉提取，生成对应的渐变图元与补丁指令', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background-image: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);">
        <h1 style="color: #ffffff;">根渐变标题</h1>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    const converter = new PPTXDomConverter()

    const slideIR = await converter.extractSlideIR({
      pageElement,
      pageIndex: 1,
      pageTitle: '根渐变页',
      pageRoute: '/root-gradient',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,test'),
    })

    // 退出条件 5.1：根渐变正确输出
    expect(slideIR.gradientFills.length).toBeGreaterThanOrEqual(1)
    const rootFill = slideIR.gradientFills.find(fill => fill.direction === 'bottom')
    expect(rootFill).toBeDefined()
    expect(rootFill?.stops).toHaveLength(2)

    // 图元中包含全屏形状
    const rootShape = slideIR.primitives.find(p => p.kind === 'shape' && (p.options?.w as number) >= 13)
    expect(rootShape).toBeDefined()
  })

  it('圆角渐变容器必须生成带 rectRadius 的 roundRect 形状，而非机械降级为普通 rect', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          id="rounded-card"
          style="width: 500px; height: 200px; background-image: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%); border-radius: 24px;"
        >
          <span style="color: #ffffff;">卡片内容</span>
        </div>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    const converter = new PPTXDomConverter()
    const slideMock = createSlideMock()

    await converter.convertPage({
      slide: slideMock as unknown as PptxSlideLike,
      pageElement,
      pageIndex: 1,
      pageTitle: '圆角渐变',
      pageRoute: '/rounded-gradient',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      shapeTypes: {
        rect: 'rect',
        roundRect: 'roundRect',
        ellipse: 'ellipse',
        line: 'line',
      },
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,test'),
    })

    // 退出条件 5.2：圆角渐变复用 roundRect 几何与圆角参数
    expect(slideMock.addShape).toHaveBeenCalledWith(
      'roundRect',
      expect.objectContaining({
        rectRadius: expect.any(Number),
      }),
    )
    expect(slideMock.addShape).not.toHaveBeenCalledWith('rect', expect.anything())
  })

  it('带有子内容的渐变容器不得在渐变上方重复叠加纯色填充遮盖渐变', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          id="gradient-container"
          style="width: 600px; height: 300px; background-image: linear-gradient(90deg, #ec4899 0%, #f43f5e 100%); background-color: #ffffff;"
        >
          <h2 style="display: block; width: 600px; height: 50px; color: #ffffff;">容器标题</h2>
          <p style="display: block; width: 600px; height: 50px; color: #ffffff;">段落描述文字</p>
        </div>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    const converter = new PPTXDomConverter()
    const slideMock = createSlideMock()

    await converter.convertPage({
      slide: slideMock as unknown as PptxSlideLike,
      pageElement,
      pageIndex: 1,
      pageTitle: '渐变子内容',
      pageRoute: '/gradient-children',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      shapeTypes: {
        rect: 'rect',
        roundRect: 'roundRect',
        ellipse: 'ellipse',
        line: 'line',
      },
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,test'),
    })

    // 退出条件 5.3：渐变容器正确输出且没有重复纯色填充遮盖
    // addShape 应该仅有 1 次（渐变形状），不得再次添加纯白底色的遮挡形状
    const shapeCalls = slideMock.addShape.mock.calls
    expect(shapeCalls).toHaveLength(1)

    // 文本正常输出为透明文本框，无多余 shape
    expect(slideMock.addText).toHaveBeenCalledWith(
      expect.stringContaining('容器标题'),
      expect.not.objectContaining({
        fill: expect.anything(),
      }),
    )
  })

  it('报告条目与真实图元应包含 S0 诊断增量字段（severity、primitiveIds 等）', async () => {
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 300px; height: 100px; background-color: #22c55e; border-radius: 8px; color: #ffffff;">
          带背景文本
        </div>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    const converter = new PPTXDomConverter()

    const slideIR = await converter.extractSlideIR({
      pageElement,
      pageIndex: 1,
      pageTitle: '诊断字段验证',
      pageRoute: '/diagnostic-test',
      pageWidthPx: 1920,
      pageHeightPx: 1080,
      slideWidthIn: 13.333,
      slideHeightIn: 7.5,
      captureElementAsPng: vi.fn(async () => 'data:image/png;base64,test'),
    })

    const items = slideIR.report.items
    expect(items.length).toBeGreaterThan(0)

    // 检查每个报告条目具备 S0 增量诊断字段
    for (const item of items) {
      expect(item.severity).toBeDefined()
      expect(['info', 'warning', 'error']).toContain(item.severity)
    }

    // 同一文本形状展开的文字与形状报告条目，应关联相同的 primitiveIds（解决 D09）
    const textItem = items.find(i => i.result === 'editable-text')
    const shapeItem = items.find(i => i.result === 'editable-shape')
    expect(textItem).toBeDefined()
    expect(shapeItem).toBeDefined()
    if (textItem?.primitiveIds && shapeItem?.primitiveIds) {
      expect(textItem.primitiveIds).toEqual(shapeItem.primitiveIds)
    }
  })
})
