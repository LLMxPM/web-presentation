// @vitest-environment jsdom

/**
 * 文件用途：验证 PPTX DOM 转换器对宽度保护、圆角几何、字体映射、对齐推断及图表/公式 SVG 的转换逻辑。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { convert, createSlideMock } from './PPTXDomConverter.test-support'

describe('PPTXDomConverter', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    delete window.__RUNTIME_PREVIEW_CONTEXT__
    delete window.__RUNTIME_PREVIEW_TOKEN__
    delete window.__RUNTIME_PRELOADED_CONFIG__
    delete window.__RUNTIME_PUBLIC_BASE_URL__
  })

  it('应将所有 PPT 文本框设置为不自动调整', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 32px; font-size: 16px;">普通文本</p>
        <span class="rounded-full px-3 py-1" style="display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标文本</span>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('普通文本', expect.objectContaining({
      fit: 'none',
    }))
    expect(slide.addText).toHaveBeenCalledWith('徽标文本', expect.objectContaining({
      fit: 'none',
      shape: 'roundRect',
    }))
  })

  it('应给文本框增加宽度冗余以避免末字换行', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="position: absolute; left: 120px; top: 40px; width: 360px; height: 32px; font-size: 16px;">左对齐文本</p>
        <p style="position: absolute; left: 120px; top: 90px; width: 360px; height: 32px; font-size: 16px; text-align: center;">居中文本</p>
        <p style="position: absolute; left: 120px; top: 140px; width: 360px; height: 32px; font-size: 16px; text-align: right;">右对齐文本</p>
        <span class="rounded-full px-3 py-1" style="position: absolute; left: 120px; top: 190px; display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标</span>
      </div>
    `

    await convert(slide)
    const inchPerPx = 13.333 / 1920
    const originalX = 120 * inchPerPx
    const originalWidth = 360 * inchPerPx
    const originalBadgeWidth = 96 * inchPerPx
    const leftCall = slide.addText.mock.calls.find(([text]) => text === '左对齐文本')?.[1]
    const centerCall = slide.addText.mock.calls.find(([text]) => text === '居中文本')?.[1]
    const rightCall = slide.addText.mock.calls.find(([text]) => text === '右对齐文本')?.[1]
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '徽标')?.[1]

    expect(leftCall?.w as number).toBeGreaterThan(originalWidth)
    expect(leftCall?.x as number).toBeCloseTo(originalX, 3)
    expect(centerCall?.w as number).toBeGreaterThan(originalWidth)
    expect((centerCall?.x as number) + (centerCall?.w as number) / 2).toBeCloseTo(originalX + originalWidth / 2, 3)
    expect(rightCall?.w as number).toBeGreaterThan(originalWidth)
    expect((rightCall?.x as number) + (rightCall?.w as number)).toBeCloseTo(originalX + originalWidth, 3)
    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      align: 'center',
    }))
    expect(badgeCall?.w as number).toBeGreaterThan(originalBadgeWidth)
    expect((badgeCall?.x as number) + (badgeCall?.w as number) / 2).toBeCloseTo(originalX + originalBadgeWidth / 2, 3)
  })

  it('flex 行中的块级 rounded-full 胶囊应使用增强宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="display: flex; align-items: center; justify-content: space-between; width: 520px; height: 64px;">
          <div class="text-xl font-semibold text-secondary" style="font-size: 20px; line-height: 28px;">形式一 · 已知首项与末项</div>
          <div id="badge" class="rounded-full bg-accent1 px-4 py-2 text-lg text-invert" style="background: #2563eb; border-radius: 9999px; padding: 8px 16px; font-size: 18px; line-height: 28px; color: #ffffff;">首末相加</div>
        </div>
      </div>
    `

    const badge = document.getElementById('badge') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })
    vi.spyOn(badge, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 128, 44))

    await convert(slide)

    const badgeOptions = slide.addText.mock.calls.find(([text]) => text === '首末相加')?.[1] as Record<string, unknown>
    const originalWidth = (128 / 1920) * 13.333

    expect(badgeOptions).toEqual(expect.objectContaining({ shape: 'roundRect' }))
    expect(Number(badgeOptions.w)).toBeGreaterThan(originalWidth + 0.09)
  })

  it('flex 行中的内容宽度 rounded-rect 文本形状应使用增强宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="row" class="flex items-center gap-4" style="display: flex; align-items: center; column-gap: 16px; width: 640px; height: 100px;">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent2 text-2xl font-bold text-invert" style="display: flex; align-items: center; justify-content: center; width: 56px; height: 56px; background: #16a34a; border-radius: 16px; font-size: 24px; line-height: 32px; font-weight: 700; color: #ffffff;">3</div>
          <div id="card" class="rounded-2xl border border-border bg-background-subtle px-6 py-5 text-[25px] font-semibold" style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 16px; padding: 20px 24px; font-size: 25px; line-height: 30px; font-weight: 600;">对应相加，提炼一般式</div>
        </div>
      </div>
    `

    const card = document.getElementById('card') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })
    vi.spyOn(card, 'getBoundingClientRect').mockReturnValue(createRect(72, 10, 300, 80))

    await convert(slide)

    const cardOptions = slide.addText.mock.calls.find(([text]) => text === '对应相加，提炼一般式')?.[1] as Record<string, unknown>
    const originalWidth = (300 / 1920) * 13.333

    expect(cardOptions).toEqual(expect.objectContaining({ shape: 'roundRect' }))
    expect(Number(cardOptions.w)).toBeGreaterThan(originalWidth + 0.1)
  })

  it('应按实际圆角半径导出 roundRect，避免普通圆角全部变成 full', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="width: 800px; height: 320px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 12px;"></section>
        <span style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标</span>
      </div>
    `

    await convert(slide)

    const cardShapeOptions = slide.addShape.mock.calls.find(([shapeName]) => shapeName === 'roundRect')?.[1] as Record<string, unknown>
    const badgeTextOptions = slide.addText.mock.calls.find(([text]) => text === '徽标')?.[1] as Record<string, unknown>
    const expectedRadiusIn = 12 * (13.333 / 1920)

    expect(Number(cardShapeOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
    expect(Number(badgeTextOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
  })

  it('应将 rounded-full 正圆导出为原生 ellipse', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="rounded-full"
          style="width: 96px; height: 96px; background: #2563eb; border-radius: 9999px;"
        ></div>
        <span
          class="rounded-full px-3 py-1"
          style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;"
        >徽标</span>
      </div>
    `

    await convert(slide)

    expect(slide.addShape).toHaveBeenCalledWith('ellipse', expect.objectContaining({
      fill: expect.objectContaining({ color: '2563EB' }),
    }))
    expect(slide.addText).toHaveBeenCalledWith('徽标', expect.objectContaining({
      shape: 'roundRect',
    }))
  })

  it('含文本的 rounded-full 正圆不应被宽度保护拉伸为椭圆', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="rounded-full p-2"
          style="position: absolute; left: 120px; top: 80px; display: inline-block; width: 40px; height: 40px; padding: 8px; background: #2563eb; border-radius: 9999px; color: #ffffff; font-size: 16px;"
        >1</span>
      </div>
    `

    await convert(slide)
    const circleOptions = slide.addText.mock.calls.find(([text]) => text === '1')?.[1] as Record<string, unknown>
    const expectedCenterX = ((120 + 20) / 1920) * 13.333
    const expectedCenterY = ((80 + 20) / 1080) * 7.5

    expect(circleOptions.shape).toBe('ellipse')
    expect(Number(circleOptions.w)).toBeCloseTo(Number(circleOptions.h), 4)
    expect(Number(circleOptions.x) + Number(circleOptions.w) / 2).toBeCloseTo(expectedCenterX, 3)
    expect(Number(circleOptions.y) + Number(circleOptions.h) / 2).toBeCloseTo(expectedCenterY, 3)
  })

  it('明确固定尺寸的普通圆角正方形不应被宽度保护拉伸', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="w-10 h-10 rounded-lg"
          style="position: absolute; left: 180px; top: 120px; display: inline-block; width: 40px; height: 40px; background: #f1f5f9; border: 1px solid #94a3b8; border-radius: 8px; color: #0f172a; font-size: 16px;"
        >A</span>
      </div>
    `

    await convert(slide)
    const squareOptions = slide.addText.mock.calls.find(([text]) => text === 'A')?.[1] as Record<string, unknown>
    const expectedRadiusIn = 8 * (13.333 / 1920)

    expect(squareOptions.shape).toBe('roundRect')
    expect(Number(squareOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
    expect(Number(squareOptions.w)).toBeCloseTo(Number(squareOptions.h), 4)
  })

  it('应将纯 translate 定位的环形节点保持为可编辑对象', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="position: relative; width: 420px; height: 420px;">
          <div
            class="absolute flex flex-col items-center gap-1"
            style="position: absolute; left: 50%; top: 8%; transform: translate(-50%, -50%); width: 180px; height: 86px; display: flex; flex-direction: column; align-items: center;"
          >
            <div
              class="rounded-full"
              style="width: 56px; height: 56px; background: rgba(124, 58, 237, 0.1); border: 2px solid rgba(124, 58, 237, 0.3); border-radius: 9999px; display: flex; align-items: center; justify-content: center;"
            >
              <span style="display: inline-block; width: 36px; height: 22px; color: #7c3aed; font-size: 16px; font-weight: 700;">创作</span>
            </div>
            <span style="display: block; width: 120px; height: 22px; color: #64748b; font-size: 14px;">AI 生成和改写</span>
          </div>
        </div>
      </div>
    `

    await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addImage).not.toHaveBeenCalled()
    expect(slide.addShape).toHaveBeenCalledWith('ellipse', expect.objectContaining({
      fill: expect.objectContaining({ color: '7C3AED' }),
    }))
    expect(slide.addText).toHaveBeenCalledWith('创作', expect.objectContaining({
      color: '7C3AED',
    }))
    expect(slide.addText).toHaveBeenCalledWith('AI 生成和改写', expect.objectContaining({
      color: '64748B',
    }))
  })

  it('应对内容宽度驱动的反色 inline 文本追加更积极的宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="card" class="bg-background-invert-100 border border-border p-4 rounded" style="width: 420px; height: 56px; padding: 16px; background: #1e293b; border: 1px solid #334155; border-radius: 4px;">
          <span id="label" class="text-invert-100" style="color: #f8fafc;">反色背景 100 (bg-background-invert-100)</span>
        </div>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const cardElement = document.getElementById('card') as HTMLElement
    const labelElement = document.getElementById('label') as HTMLElement
    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1920,
      bottom: 1080,
      width: 1920,
      height: 1080,
      toJSON: () => ({}),
    })
    vi.spyOn(cardElement, 'getBoundingClientRect').mockReturnValue({
      x: 100,
      y: 80,
      top: 80,
      left: 100,
      right: 520,
      bottom: 136,
      width: 420,
      height: 56,
      toJSON: () => ({}),
    })
    vi.spyOn(labelElement, 'getBoundingClientRect').mockReturnValue({
      // 父容器左边界 100px + border 1px + padding 16px，文字并未越出内容区。
      x: 117,
      y: 96,
      top: 96,
      left: 117,
      right: 357,
      bottom: 120,
      width: 240,
      height: 24,
      toJSON: () => ({}),
    })

    await convert(slide)

    const labelOptions = slide.addText.mock.calls.find(([text]) => text === '反色背景 100 (bg-background-invert-100)')?.[1] as Record<string, unknown>
    const inchPerPx = 13.333 / 1920
    const originalX = 117 * inchPerPx
    const originalWidth = 240 * inchPerPx

    expect(labelOptions?.w as number).toBeGreaterThan(originalWidth + 0.17)
    expect(labelOptions?.x as number).toBeCloseTo(originalX, 3)
  })

  it('应将 CSS 系统字体别名映射为 PPT 可识别字体', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">主题能力</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">Runtime badge</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: '思源黑体', -apple-system, sans-serif;">主题字体</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: 'Web Presentation Sans', sans-serif;">平台默认字体</p>
        <code style="display: block; width: 360px; height: 32px; font-size: 16px; font-family: 'Web Presentation Mono', monospace;">const runtime = true</code>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('主题能力', expect.objectContaining({
      fontFace: 'Microsoft YaHei',
    }))
    expect(slide.addText).toHaveBeenCalledWith('Runtime badge', expect.objectContaining({
      fontFace: 'Segoe UI',
    }))
    expect(slide.addText).toHaveBeenCalledWith('主题字体', expect.objectContaining({
      fontFace: '思源黑体',
    }))
    expect(slide.addText).toHaveBeenCalledWith('平台默认字体', expect.objectContaining({
      fontFace: 'Microsoft YaHei',
    }))
    expect(slide.addText).toHaveBeenCalledWith('const runtime = true', expect.objectContaining({
      fontFace: 'Consolas',
    }))
  })

  it('应还原 flex 布局中的左右居中和上下居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: center; width: 480px; height: 160px; font-size: 32px;">居中文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('居中文本', expect.objectContaining({
      align: 'center',
      valign: 'middle',
    }))
  })

  it('应识别 Tailwind text-center 类名并让子文本继承居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="text-center" style="width: 560px; height: 180px;">
          <strong style="display: block; width: 320px; height: 72px; color: #2563eb; font-size: 36px;">类名居中</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('类名居中', expect.objectContaining({
      align: 'center',
    }))
  })

  it('应识别 Tailwind items-center 和 justify-between 类名', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="width: 560px; height: 180px;">
          <span style="display: block; width: 160px; height: 48px; color: #0f172a; font-size: 24px;">左侧</span>
          <strong style="display: block; width: 160px; height: 48px; color: #2563eb; font-size: 24px;">右侧</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('左侧', expect.objectContaining({
      align: 'left',
      valign: 'middle',
    }))
    expect(slide.addText).toHaveBeenCalledWith('右侧', expect.objectContaining({
      align: 'left',
      valign: 'middle',
    }))
  })

  it('应在 flex justify-between 测量缺失时按右侧位置导出代码标签', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between bg-background-invert p-3 rounded border" style="width: 500px; height: 60px; background: #0f172a; border: 1px solid #334155; border-radius: 4px;">
          <span class="text-invert" style="display: block; width: 120px; height: 24px;">Invert 默认</span>
          <code class="text-invert text-xs px-2 py-1 rounded" style="display: block; width: 80px; height: 20px;">text-invert</code>
        </div>
      </div>
    `

    await convert(slide)
    const spanOptions = slide.addText.mock.calls.find(([text]) => text === 'Invert 默认')?.[1] as Record<string, unknown>
    const codeOptions = slide.addText.mock.calls.find(([text]) => text === 'text-invert')?.[1] as Record<string, unknown>
    const expectedCodeX = (408 / 1920) * 13.333
    const expectedCodeW = (80 / 1920) * 13.333

    expect(codeOptions).toEqual(expect.objectContaining({
      shape: 'rect',
      align: 'center',
      valign: 'middle',
      margin: [3, 3, 1.5, 1.5],
    }))
    expect(codeOptions.isTextBox).toBeUndefined()
    expect(slide.addText).not.toHaveBeenCalledWith('Invert 默认 text-invert', expect.any(Object))
    expect(Number(codeOptions.x)).toBeCloseTo(expectedCodeX, 4)
    expect(Number(codeOptions.w)).toBeCloseTo(expectedCodeW, 4)
    expect(Number(codeOptions.x)).toBeGreaterThan(Number(spanOptions.x))
  })

  it('不应把 flex 容器里的 absolute 顶部装饰条重算到页面中间', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="relative h-full w-full bg-background flex flex-col items-center justify-center"
          style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 1920px; height: 1080px; background: #ffffff;"
        >
          <div
            class="absolute top-0 left-0 right-0 h-2 bg-background-invert"
            style="position: absolute; top: 0; left: 0; width: 1920px; height: 8px; background: #111827;"
          ></div>
          <div style="width: 360px; height: 96px;">
            <h1 style="width: 360px; height: 56px; font-size: 32px; color: #0f172a;">Attention Is All You Need</h1>
          </div>
          <div
            class="absolute bottom-0 left-0 right-0 h-2 bg-background-invert"
            style="position: absolute; left: 0; bottom: 0; width: 1920px; height: 8px; background: #111827;"
          ></div>
        </div>
      </div>
    `

    await convert(slide)
    const stripCalls = slide.addShape.mock.calls.filter(([, options]) => {
      const fill = (options as { fill?: { color?: unknown } }).fill
      return fill?.color === '111827'
    })
    const topStripOptions = stripCalls[0]?.[1] as Record<string, unknown>

    expect(stripCalls.length).toBeGreaterThanOrEqual(2)
    expect(Number(topStripOptions.y)).toBeCloseTo(0, 4)
    expect(Number(topStripOptions.h)).toBeCloseTo((8 / 1080) * 7.5, 4)
  })

  it('absolute 子元素不应参与 flex 子项分布兜底计算', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="display: flex; align-items: center; justify-content: space-between; position: relative; width: 500px; height: 60px;">
          <div style="position: absolute; left: 0; top: 0; width: 500px; height: 8px; background: #111827;"></div>
          <span style="display: block; width: 120px; height: 24px; color: #0f172a; font-size: 16px;">左侧</span>
          <code style="display: block; width: 80px; height: 20px; color: #2563eb; font-size: 12px;">右侧</code>
        </div>
      </div>
    `

    await convert(slide)
    const leftOptions = slide.addText.mock.calls.find(([text]) => text === '左侧')?.[1] as Record<string, unknown>
    const rightOptions = slide.addText.mock.calls.find(([text]) => text === '右侧')?.[1] as Record<string, unknown>
    const expectedRightX = (420 / 1920) * 13.333

    expect(Number(leftOptions.x)).toBeCloseTo(0, 4)
    expect(Number(rightOptions.x)).toBeCloseTo(expectedRightX, 4)
    expect(Number(rightOptions.x)).toBeGreaterThan(Number(leftOptions.x))
  })

  it('应将圆角徽标导出为带文本和内边距的 PPT 形状', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="width: 560px; height: 180px;">
          <span class="rounded-full px-3 py-1" style="display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; color: #1e40af; font-size: 12px;">主题能力</span>
          <a style="display: inline-block; width: 96px; height: 24px; color: #2563eb; font-size: 14px;">查看展示</a>
        </div>
      </div>
    `

    const report = await convert(slide)
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '主题能力')?.[1]

    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      fill: expect.objectContaining({ color: 'BFDBFE' }),
      margin: [4.5, 4.5, 1.5, 1.5],
      align: 'center',
      valign: 'middle',
    }))
    expect(slide.addShape).not.toHaveBeenCalledWith('roundRect', expect.objectContaining({
      fill: expect.objectContaining({ color: 'BFDBFE' }),
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: '主题能力',
        result: 'editable-text',
        reason: '带背景文本转为 PPT text shape',
      }),
      expect.objectContaining({
        label: expect.stringContaining('span.rounded-full.px-3.py-1'),
        result: 'editable-shape',
        reason: '背景、边框和圆角由 PPT 文本形状绘制',
      }),
    ]))
  })

  it('应保持卡片描述段落居左且不受资源徽标居中影响', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <article class="overflow-hidden rounded-lg border border-border bg-background-subtle" style="width: 720px; height: 260px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;">
          <div class="p-5 bg-accent5-100" style="width: 720px; height: 160px; padding: 20px; background: #fef3c7;">
            <div class="mb-3 flex items-center" style="display: flex; align-items: center; width: 680px; height: 32px;">
              <span class="app-icon inline-flex items-center justify-center mr-2 size-5" style="display: inline-flex; width: 20px; height: 20px;"></span>
              <h3 class="font-heading text-lg font-semibold text-accent5-800" style="width: 240px; height: 28px; font-size: 18px; font-weight: 600;">LaTeX 公式</h3>
            </div>
            <p class="font-body text-sm leading-relaxed text-accent5-700" style="width: 680px; height: 40px; font-size: 14px; color: #854d0e;">展示公式文本资源的块级和行内排版能力。</p>
          </div>
          <div class="p-4" style="width: 720px; height: 80px; padding: 16px;">
            <div class="flex items-center justify-between gap-3" style="display: flex; align-items: center; justify-content: space-between; width: 688px; height: 28px;">
              <span class="rounded-full px-3 py-1 text-xs font-medium bg-accent5-200 text-accent5-800" style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #fde68a; border-radius: 9999px; font-size: 12px;">资源渲染</span>
              <a class="whitespace-nowrap text-sm font-medium text-link" style="display: inline-block; width: 96px; height: 24px; font-size: 14px;">查看展示</a>
            </div>
          </div>
        </article>
      </div>
    `

    await convert(slide)
    const descriptionCall = slide.addText.mock.calls.find(([text]) => text === '展示公式文本资源的块级和行内排版能力。')?.[1]
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '资源渲染')?.[1]
    const originalBadgeWidth = (96 / 1920) * 13.333

    expect(descriptionCall).toEqual(expect.objectContaining({
      align: 'left',
    }))
    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      align: 'center',
      valign: 'middle',
    }))
    expect(badgeCall?.w as number).toBeGreaterThan(originalBadgeWidth)
  })

  it('应将 line-height 等于高度的单行文本识别为上下居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 64px; line-height: 64px; text-align: center; font-size: 24px;">单行居中</p>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('单行居中', expect.objectContaining({
      align: 'center',
      valign: 'middle',
    }))
  })

  it('应还原 table-cell 的居左居下和垂直居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: table-cell; width: 420px; height: 180px; vertical-align: bottom; text-align: left; font-size: 24px;">左下文本</div>
        <div style="display: table-cell; width: 420px; height: 180px; vertical-align: middle; text-align: right; font-size: 24px;">右中文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('左下文本', expect.objectContaining({
      align: 'left',
      valign: 'bottom',
    }))
    expect(slide.addText).toHaveBeenCalledWith('右中文本', expect.objectContaining({
      align: 'right',
      valign: 'middle',
    }))
  })

  it('应还原 column flex 的右下对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; flex-direction: column; justify-content: flex-end; align-items: flex-end; width: 480px; height: 160px; font-size: 28px;">右下文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('右下文本', expect.objectContaining({
      align: 'right',
      valign: 'bottom',
    }))
  })

  it('应让拆分出的子文本继承父级垂直布局对齐，水平仍按文本自身对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: flex-end; width: 560px; height: 180px;">
          <strong style="display: block; width: 320px; height: 72px; color: #2563eb; font-size: 36px;">继承居中</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('继承居中', expect.objectContaining({
      align: 'left',
      valign: 'bottom',
    }))
  })

  it('应让子文本显式对齐覆盖父级继承对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: center; width: 560px; height: 180px;">
          <span style="display: block; width: 320px; height: 72px; text-align: right; vertical-align: bottom; font-size: 28px;">覆盖对齐</span>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('覆盖对齐', expect.objectContaining({
      align: 'right',
      valign: 'bottom',
    }))
  })

  it('应将 Mermaid SVG 转为 SVG 图片块', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="mermaid-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50"><rect width="100" height="50" fill="#fff" /></svg>
        </div>
      </div>
    `

    const report = await convert(slide)

    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.stringMatching(/^data:image\/svg\+xml;base64,/),
    }))
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'mermaid',
      result: 'svg',
      editable: false,
    }))
  })

  it('应将含 foreignObject 的 Mermaid 图表降级为局部截图，避免 PowerPoint 丢字', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="mermaid-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50">
            <foreignObject x="0" y="0" width="100" height="50">
              <div xmlns="http://www.w3.org/1999/xhtml">流程标题</div>
            </foreignObject>
          </svg>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(addImageCall.data).toBe('data:image/png;base64,capture')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'mermaid',
      result: 'screenshot',
      reason: 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图',
    }))
  })

  it('应将含 foreignObject 的 Draw.io 图表降级为局部截图，避免 PowerPoint 丢字', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="drawio-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50">
            <foreignObject x="0" y="0" width="100" height="50">
              <div xmlns="http://www.w3.org/1999/xhtml">节点标签</div>
            </foreignObject>
          </svg>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(addImageCall.data).toBe('data:image/png;base64,capture')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'drawio',
      result: 'screenshot',
      reason: 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图',
    }))
  })

  it('应按 LaTeX 实际 SVG 盒子导出，避免被外层 viewer 拉伸', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section class="latex-viewer" style="width: 420px; height: 180px; display: flex; align-items: center; justify-content: center;">
          <div class="latex-viewer__content">
            <mjx-container>
              <svg viewBox="0 0 160 40"></svg>
            </mjx-container>
          </div>
        </section>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const viewerElement = document.querySelector('.latex-viewer') as HTMLElement
    const svgElement = viewerElement.querySelector('svg') as SVGSVGElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
    vi.spyOn(viewerElement, 'getBoundingClientRect').mockReturnValue(createRect(120, 160, 420, 180))
    vi.spyOn(svgElement, 'getBoundingClientRect').mockReturnValue(createRect(250, 230, 160, 40))

    await convert(slide)
    const imageOptions = slide.addImage.mock.calls[0]?.[0] as {
      x: number
      y: number
      w: number
      h: number
      data: string
    }
    const inchPerPx = 13.333 / 1920

    expect(imageOptions.data).toMatch(/^data:image\/svg\+xml;base64,/)
    expect(imageOptions.x).toBeCloseTo(250 * inchPerPx, 4)
    expect(imageOptions.y).toBeCloseTo(230 * (7.5 / 1080), 4)
    expect(imageOptions.w).toBeCloseTo(160 * inchPerPx, 4)
    expect(imageOptions.h).toBeCloseTo(40 * (7.5 / 1080), 4)
  })

  it('应导出 LaTeX viewer 中的全部 MathJax SVG，而不是只导出第一段公式', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section class="latex-viewer" style="width: 640px; height: 420px;">
          <div class="latex-viewer__content">
            <mjx-container><svg id="formula-a" viewBox="0 0 300 48"></svg></mjx-container>
            <mjx-container><svg id="formula-b" viewBox="0 0 280 48"></svg></mjx-container>
            <mjx-container><svg id="formula-c" viewBox="0 0 320 48"></svg></mjx-container>
          </div>
        </section>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const viewerElement = document.querySelector('.latex-viewer') as HTMLElement
    const svgElements = Array.from(viewerElement.querySelectorAll('svg')) as SVGSVGElement[]
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
    vi.spyOn(viewerElement, 'getBoundingClientRect').mockReturnValue(createRect(120, 160, 640, 420))
    vi.spyOn(svgElements[0], 'getBoundingClientRect').mockReturnValue(createRect(180, 190, 300, 48))
    vi.spyOn(svgElements[1], 'getBoundingClientRect').mockReturnValue(createRect(190, 260, 280, 48))
    vi.spyOn(svgElements[2], 'getBoundingClientRect').mockReturnValue(createRect(170, 330, 320, 48))

    const report = await convert(slide)
    const imageCalls = slide.addImage.mock.calls.map(call => call[0] as {
      x: number
      y: number
      w: number
      h: number
      data: string
    })
    const inchPerPx = 13.333 / 1920

    expect(imageCalls).toHaveLength(3)
    expect(imageCalls.every(options => /^data:image\/svg\+xml;base64,/.test(options.data))).toBe(true)
    expect(imageCalls.map(options => Math.round(options.y / (7.5 / 1080)))).toEqual([190, 260, 330])
    expect(imageCalls.map(options => Math.round(options.w / inchPerPx))).toEqual([300, 280, 320])
    expect(report.items.filter(item => item.sourceType === 'formula' && item.result === 'svg')).toHaveLength(3)
  })
})
