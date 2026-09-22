// @vitest-environment jsdom

/**
 * 文件用途：验证可编辑 PPTX 导出服务对演讲者备注等 slide 级信息的写入逻辑。
 */

import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import type { PageInfo } from '@/core/types/pdf-export'
import type { PptxExportReportPage } from '@/core/types/pptx-export'
import { PPTXExportService } from './PPTXExportService'
import type { PptxGradientFillInstruction } from './pptx/PPTXDomConverter'

interface PptxExportServicePrivate {
  converter: {
    convertPage: Mock
  }
  addPageToPresentation: (
    pptx: PptxMock,
    pageElement: HTMLElement,
    page: PageInfo,
    pageIndex: number,
    gradientFills: PptxGradientFillInstruction[],
  ) => Promise<PptxExportReportPage>
  createPresentation: () => {
    theme: {
      headFontFace?: string
      bodyFontFace?: string
    }
  }
  waitForPageReady: (expectedRoutePath?: string) => Promise<void>
}

afterEach(() => {
  Reflect.deleteProperty(document, 'getAnimations')
  document.body.innerHTML = ''
})

interface PptxMock {
  addSlide: Mock
  ShapeType: {
    rect: string
    roundRect: string
    ellipse: string
    line: string
  }
}

describe('PPTXExportService', () => {
  it('创建 PPTX 时应使用目标电脑常见的中文主题字体', () => {
    const service = new PPTXExportService() as unknown as PptxExportServicePrivate

    expect(service.createPresentation().theme).toEqual(expect.objectContaining({
      headFontFace: 'Microsoft YaHei',
      bodyFontFace: 'Microsoft YaHei',
    }))
  })

  it('添加页面时应将演讲者备注写入 PPTX slide', async () => {
    const service = createServiceWithConverter()
    const slide = createSlideMock()
    const pptx = createPptxMock(slide)
    const pageElement = document.createElement('section')

    await service.addPageToPresentation(pptx, pageElement, {
      route: '/intro',
      title: '开场',
      order: 1,
      meta: {
        speakerNotes: '  开场先说明项目背景  ',
      },
    }, 1, [])

    expect(slide.addNotes).toHaveBeenCalledWith('开场先说明项目背景')
    expect(service.converter.convertPage).toHaveBeenCalledWith(expect.objectContaining({
      slide,
      pageElement,
      pageTitle: '开场',
      pageRoute: '/intro',
    }))
  })

  it('空白演讲者备注不应写入 PPTX slide', async () => {
    const service = createServiceWithConverter()
    const slide = createSlideMock()
    const pptx = createPptxMock(slide)

    await service.addPageToPresentation(pptx, document.createElement('section'), {
      route: '/empty-notes',
      title: '空备注',
      order: 1,
      meta: {
        speakerNotes: '   ',
      },
    }, 1, [])

    expect(slide.addNotes).not.toHaveBeenCalled()
  })

  it('页面就绪检查应等待有限次入场动画结束', async () => {
    const service = new PPTXExportService() as unknown as PptxExportServicePrivate
    let animationFinished = false
    const animation = {
      playState: 'running',
      effect: {
        getTiming: () => ({ iterations: 1 }),
      },
      finished: new Promise<void>(resolve => window.setTimeout(() => {
        animationFinished = true
        resolve()
      }, 20)),
    } as unknown as Animation
    Object.defineProperty(document, 'getAnimations', {
      value: () => [animation],
      configurable: true,
    })

    await service.waitForPageReady()

    expect(animationFinished).toBe(true)
  })
})

/**
 * 创建带有转换器 mock 的 PPTX 导出服务。
 * @returns 暴露私有导出入口的服务实例
 */
function createServiceWithConverter(): PptxExportServicePrivate {
  const service = new PPTXExportService() as unknown as PptxExportServicePrivate
  service.converter = {
    convertPage: vi.fn(async ({ pageIndex, pageTitle, pageRoute }) => ({
      pageIndex,
      pageTitle,
      pageRoute,
      items: [],
    })),
  }
  return service
}

/**
 * 创建最小 slide mock。
 * @returns PPTX slide mock
 */
function createSlideMock() {
  return {
    addNotes: vi.fn(),
  }
}

/**
 * 创建最小 PPTX mock。
 * @param slide slide mock
 * @returns PPTX mock
 */
function createPptxMock(slide: ReturnType<typeof createSlideMock>): PptxMock {
  return {
    addSlide: vi.fn(() => slide),
    ShapeType: {
      rect: 'rect',
      roundRect: 'roundRect',
      ellipse: 'ellipse',
      line: 'line',
    },
  }
}
