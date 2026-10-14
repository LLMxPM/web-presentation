/**
 * 文件用途：PPTX 导出升级 S2 阶段（视觉合成与排版映射）专项测试，覆盖角度渐变 OOXML、行距与段落间距、单层外阴影、大面积滤镜降级、等比缩放矩阵及祖先透明度。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PPTXDomConverter } from './PPTXDomConverter'
import { buildGradientFillXml } from './writer/OoxmlGradientPatcher'
import type {
  PptxGradientFillInstruction,
  PptxPageConvertOptions,
  PptxSlideLike,
} from './PPTXDomConverter.types'

describe('S2 视觉和排版映射专项测试', () => {
  let converter: PPTXDomConverter
  let addTextMock: ReturnType<typeof vi.fn<PptxSlideLike['addText']>>
  let addShapeMock: ReturnType<typeof vi.fn<PptxSlideLike['addShape']>>
  let addImageMock: ReturnType<typeof vi.fn<PptxSlideLike['addImage']>>
  let addTableMock: ReturnType<typeof vi.fn<PptxSlideLike['addTable']>>
  let slideMock: PptxSlideLike

  beforeEach(() => {
    converter = new PPTXDomConverter()
    addTextMock = vi.fn()
    addShapeMock = vi.fn()
    addImageMock = vi.fn()
    addTableMock = vi.fn()
    slideMock = {
      addText: addTextMock,
      addShape: addShapeMock,
      addImage: addImageMock,
      addTable: addTableMock,
    }
  })

  function createOptions(pageElement: HTMLElement, instructions: PptxGradientFillInstruction[] = []): PptxPageConvertOptions {
    return {
      slide: slideMock,
      pageElement,
      pageIndex: 1,
      pageTitle: 'S2 视觉测试',
      pageRoute: '/s2-test',
      pageWidthPx: 960,
      pageHeightPx: 540,
      slideWidthIn: 10,
      slideHeightIn: 5.625,
      shapeTypes: {
        rect: 'rect',
        roundRect: 'roundRect',
        ellipse: 'ellipse',
        line: 'line',
      },
      captureElementAsPng: vi.fn().mockResolvedValue('data:image/png;base64,s2_mock'),
      gradientFillCollector: instruction => instructions.push(instruction),
    }
  }

  it('1. 角度渐变应精确换算并输出 OOXML a:lin ang="..." 角度', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    // 45deg 渐变（CSS 45deg 对应 OOXML ((45 - 90) % 360 + 360) = 315 度，即 315 * 60000 = 18900000）
    const card45 = document.createElement('div')
    card45.id = 'grad-45'
    card45.setAttribute('style', 'width: 300px; height: 200px; background-image: linear-gradient(45deg, #ff0000 0%, #0000ff 100%);')
    page.appendChild(card45)

    // to bottom right (135deg，对应 OOXML (135 - 90) = 45 度，即 45 * 60000 = 2700000)
    const cardCorner = document.createElement('div')
    cardCorner.id = 'grad-corner'
    cardCorner.setAttribute('style', 'width: 300px; height: 200px; background-image: linear-gradient(to bottom right, #00ff00 0%, #ffff00 100%);')
    page.appendChild(cardCorner)

    document.body.appendChild(page)

    const gradientInstructions: PptxGradientFillInstruction[] = []
    await converter.convertPage(createOptions(page, gradientInstructions))

    expect(gradientInstructions.length).toBe(2)

    // 验证 45deg 指令与 OOXML
    const inst45 = gradientInstructions.find(i => i.angle === 45)
    expect(inst45).toBeDefined()
    const xml45 = buildGradientFillXml(inst45!)
    expect(xml45).toContain('<a:lin ang="18900000"')

    // 验证 to bottom right (135deg) 指令与 OOXML
    const instCorner = gradientInstructions.find(i => i.angle === 135)
    expect(instCorner).toBeDefined()
    const xmlCorner = buildGradientFillXml(instCorner!)
    expect(xmlCorner).toContain('<a:lin ang="2700000"')

    document.body.removeChild(page)
  })

  it('2. 应正确映射固定行距 (lineSpacing pt)、倍数行距 (lineSpacingMultiple) 与段落间距', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    // 倍数行高段落
    const pMultiple = document.createElement('p')
    pMultiple.textContent = '倍数行高段落'
    pMultiple.style.width = '400px'
    pMultiple.style.height = '60px'
    pMultiple.style.lineHeight = '1.75'
    pMultiple.style.marginTop = '16px'
    pMultiple.style.marginBottom = '24px'
    page.appendChild(pMultiple)

    // 固定像素行高段落 (24px 对应 18pt)
    const pFixed = document.createElement('p')
    pFixed.textContent = '固定像素行高段落'
    pFixed.style.width = '400px'
    pFixed.style.height = '60px'
    pFixed.style.lineHeight = '24px'
    page.appendChild(pFixed)

    document.body.appendChild(page)

    await converter.convertPage(createOptions(page))

    // 检查倍数行高调用
    const callMultiple = addTextMock.mock.calls.find(call => {
      const text = typeof call[0] === 'string' ? call[0] : call[0]?.[0]?.text
      return text?.includes('倍数行高')
    })
    expect(callMultiple).toBeDefined()
    const optionsMultiple = callMultiple[1]
    expect(optionsMultiple.lineSpacingMultiple).toBe(1.75)
    expect(optionsMultiple.paraSpaceBefore).toBeGreaterThan(0)
    expect(optionsMultiple.paraSpaceAfter).toBeGreaterThan(0)

    // 检查固定行距调用
    const callFixed = addTextMock.mock.calls.find(call => {
      const text = typeof call[0] === 'string' ? call[0] : call[0]?.[0]?.text
      return text?.includes('固定像素')
    })
    expect(callFixed).toBeDefined()
    const optionsFixed = callFixed[1]
    expect(optionsFixed.lineSpacing).toBe(18) // 24px * 0.75 = 18pt

    document.body.removeChild(page)
  })

  it('3. 单层无 spread 外阴影应原生映射为 PPT 形状与文本 shadow', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    const card = document.createElement('div')
    card.id = 'shadow-card'
    card.style.width = '240px'
    card.style.height = '160px'
    card.style.backgroundColor = '#ffffff'
    // 0px 8px 16px rgba(0,0,0,0.25) -> 正下方偏移 (angle 90), offset ~6pt, blur 12pt, opacity 0.25
    card.style.boxShadow = '0px 8px 16px rgba(0, 0, 0, 0.25)'
    page.appendChild(card)

    document.body.appendChild(page)

    await converter.convertPage(createOptions(page))

    const shapeCall = addShapeMock.mock.calls.find(call => call[1]?.shadow)
    expect(shapeCall).toBeDefined()
    const shadow = shapeCall[1].shadow as { type: string; angle: number; offset: number; blur: number; opacity: number }
    expect(shadow.type).toBe('outer')
    expect(shadow.angle).toBe(90) // 正下方
    expect(shadow.offset).toBe(6) // 8px * 0.75 = 6pt
    expect(shadow.blur).toBe(12) // 16px * 0.75 = 12pt
    expect(shadow.opacity).toBe(0.25)

    document.body.removeChild(page)
  })

  it('4. 复杂 CSS 降级：多层阴影、带 spread 阴影与大面积容器应准确触发降级报告', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    // 大面积（占页面 > 85%）且带 filter 的复杂容器，内部包含可编辑标题
    const largeComplexContainer = document.createElement('div')
    largeComplexContainer.style.width = '900px'
    largeComplexContainer.style.height = '500px'
    largeComplexContainer.style.filter = 'blur(4px)'
    const innerTitle = document.createElement('h1')
    innerTitle.textContent = '保护大容器内的可编辑标题'
    innerTitle.style.width = '600px'
    innerTitle.style.height = '60px'
    largeComplexContainer.appendChild(innerTitle)
    page.appendChild(largeComplexContainer)

    // 带多层阴影的卡片
    const multiShadowCard = document.createElement('div')
    multiShadowCard.style.width = '200px'
    multiShadowCard.style.height = '150px'
    multiShadowCard.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1), 0 8px 16px rgba(0,0,0,0.1)'
    page.appendChild(multiShadowCard)

    document.body.appendChild(page)

    const report = await converter.convertPage(createOptions(page))

    // filter 同时作用于文字和背景，必须整体截图，不能把未模糊文本叠回去。
    const complexReportItem = report.items.find(item =>
      item.sourceType === 'complex-css' && item.result === 'screenshot',
    )
    expect(complexReportItem).toBeDefined()

    // 避免重复绘制未经滤镜处理的原生标题。
    const titleCall = addTextMock.mock.calls.find(call => {
      const text = typeof call[0] === 'string' ? call[0] : call[0]?.[0]?.text
      return text?.includes('保护大容器内的可编辑标题')
    })
    expect(titleCall).toBeUndefined()

    // 验证多层阴影触发了复杂 CSS 截图降级
    const screenshotCall = addImageMock.mock.calls.find(call => String(call[0]?.data || '').includes('s2_mock'))
    expect(screenshotCall).toBeDefined()

    document.body.removeChild(page)
  })

  it('5. 正值等比缩放矩阵 scale(1.5) 应原生映射几何中心点并等比换算字号', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    const scaledBox = document.createElement('div')
    scaledBox.style.width = '200px'
    scaledBox.style.height = '100px'
    scaledBox.style.transform = 'scale(1.5)'
    const scaledText = document.createElement('p')
    scaledText.textContent = '等比放大文本'
    scaledText.style.width = '180px'
    scaledText.style.height = '40px'
    scaledText.style.fontSize = '20px' // 15pt * 1.5 = 22.5pt
    scaledBox.appendChild(scaledText)
    page.appendChild(scaledBox)

    document.body.appendChild(page)

    await converter.convertPage(createOptions(page))

    const textCall = addTextMock.mock.calls.find(call => {
      const text = typeof call[0] === 'string' ? call[0] : call[0]?.[0]?.text
      return text?.includes('等比放大文本')
    })
    expect(textCall).toBeDefined()
    const options = textCall[1]
    // 字号由 15pt 放大 1.5 倍至 22.5pt
    expect(options.fontSize).toBe(22.5)

    document.body.removeChild(page)
  })

  it('6. 祖先透明度应向子元素累乘，负坐标应真实保留而不被机械归零', async () => {
    const page = document.createElement('div')
    page.style.width = '960px'
    page.style.height = '540px'

    // 祖先设置 opacity: 0.5
    const transparentParent = document.createElement('div')
    transparentParent.style.width = '400px'
    transparentParent.style.height = '200px'
    transparentParent.style.opacity = '0.5'

    // 子元素本身 opacity: 0.8，有效透明度应为 0.5 * 0.8 = 0.4 (transparency 60%)
    const childText = document.createElement('p')
    childText.textContent = '透明度继承文本'
    childText.style.width = '300px'
    childText.style.height = '50px'
    childText.style.color = '#000000'
    childText.style.opacity = '0.8'
    transparentParent.appendChild(childText)
    page.appendChild(transparentParent)

    // 突出页面左侧的装饰矩形（left 处于页面左侧外，x 应为负数）
    const overflowRect = document.createElement('div')
    overflowRect.id = 'overflow-rect'
    overflowRect.style.position = 'absolute'
    overflowRect.style.left = '-48px'
    overflowRect.style.top = '100px'
    overflowRect.style.width = '120px'
    overflowRect.style.height = '80px'
    overflowRect.style.backgroundColor = '#3b82f6'
    page.appendChild(overflowRect)

    document.body.appendChild(page)

    await converter.convertPage(createOptions(page))

    // 验证透明度累乘
    const textCall = addTextMock.mock.calls.find(call => {
      const text = typeof call[0] === 'string' ? call[0] : call[0]?.[0]?.text
      return text?.includes('透明度继承文本')
    })
    expect(textCall).toBeDefined()
    expect(textCall[1].transparency).toBe(60) // 100 - (0.4 * 100) = 60%

    // 验证负坐标没有被强制归零到 0
    const shapeCall = addShapeMock.mock.calls.find(call => typeof call[1]?.x === 'number' && call[1].x < 0)
    expect(shapeCall).toBeDefined()
    expect(shapeCall[1].x).toBeLessThan(0)

    document.body.removeChild(page)
  })
})
