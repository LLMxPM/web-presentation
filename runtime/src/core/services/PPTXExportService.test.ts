// @vitest-environment jsdom

/**
 * 文件用途：验证可编辑 PPTX 导出服务对演讲者备注、离屏 1:1 舞台采集（方案 A 与全页导出）及局部快速光栅化的协同逻辑。
 */

import { createEmptySlideIR } from './pptx/PPTXDomConverter.test-support'

import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import type { Router } from 'vue-router'
import type { PageInfo } from '@/core/types/export-common'
import type { PptxExportReportPage } from '@/core/types/pptx-export'
import { PPTXExportService } from './PPTXExportService'
import type { PptxGradientFillInstruction } from './pptx/PPTXDomConverter'

const mockPreparePage = vi.hoisted(() => vi.fn())
const mockDisposeStage = vi.hoisted(() => vi.fn())
const mockCleanupPage = vi.hoisted(() => vi.fn())
const mockCollectAllExportPages = vi.hoisted(() => vi.fn())

vi.mock('@/core/services/export/OffscreenPageStage', () => ({
  createOffscreenPageStage: () => ({
    preparePage: (route: string) => mockPreparePage(route),
    capture: vi.fn(),
    dispose: mockDisposeStage,
  }),
}))

vi.mock('@/core/utils/export-pages', () => ({
  collectAllExportPages: (router: unknown) => mockCollectAllExportPages(router),
}))

interface PptxExportServicePrivate {
  converter: {
    extractSlideIR: Mock
  }
  packageWriter: {
    createPresentation: () => PptxMock
    getShapeTypes: (pptx: PptxMock) => PptxMock['ShapeType']
    resolveSlideLayout: () => { widthIn: number; heightIn: number }
    writePresentationFile: Mock
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
  vi.clearAllMocks()
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

  it('添加页面时应把裁剪后的演讲者备注交给转换器写入 slide', async () => {
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

    expect(service.converter.extractSlideIR).toHaveBeenCalledWith(expect.objectContaining({
      pageElement,
      pageTitle: '开场',
      pageRoute: '/intro',
      speakerNotes: '开场先说明项目背景',
    }))
  })

  it('空白演讲者备注应归一化为 null，不写入 PPTX slide', async () => {
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
    expect(service.converter.extractSlideIR).toHaveBeenCalledWith(expect.objectContaining({
      speakerNotes: null,
    }))
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

  it('单页导出在平台项目路由（meta.runtimeProject）下应通过离屏 1:1 舞台采集（方案 A）', async () => {
    const offscreenElement = document.createElement('div')
    mockPreparePage.mockResolvedValue({
      element: offscreenElement,
      cleanup: mockCleanupPage,
    })

    const service = createServiceWithConverterAndWriter()
    const routerPush = vi.fn()
    ;(service as unknown as PPTXExportService).setRouter({
      currentRoute: {
        value: {
          fullPath: '/slide-1?theme=dark',
          path: '/slide-1',
          meta: {
            runtimeProject: true,
            title: '第一页',
          },
        },
      },
      push: routerPush,
    } as unknown as Router)

    const result = await (service as unknown as PPTXExportService).exportCurrentPage({ mode: 'current' })

    expect(result.success).toBe(true)
    expect(mockPreparePage).toHaveBeenCalledWith('/slide-1?theme=dark')
    expect(service.converter.extractSlideIR).toHaveBeenCalledWith(expect.objectContaining({
      pageElement: offscreenElement,
      pageRoute: '/slide-1',
    }))
    expect(routerPush).not.toHaveBeenCalled()
    expect(mockCleanupPage).toHaveBeenCalledTimes(1)
    expect(mockDisposeStage).toHaveBeenCalledTimes(1)
  })

  it('导出所有页面时应通过离屏舞台逐页准备 DOM，不调用主窗口 router.push', async () => {
    const page1Element = document.createElement('div')
    const page2Element = document.createElement('div')
    mockCollectAllExportPages.mockResolvedValue([
      { route: '/page-1', title: '页面一', order: 1 },
      { route: '/page-2', title: '页面二', order: 2 },
    ])
    mockPreparePage
      .mockResolvedValueOnce({ element: page1Element, cleanup: mockCleanupPage })
      .mockResolvedValueOnce({ element: page2Element, cleanup: mockCleanupPage })

    const service = createServiceWithConverterAndWriter()
    const routerPush = vi.fn()
    ;(service as unknown as PPTXExportService).setRouter({
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
          meta: { runtimeProject: true },
        },
      },
      push: routerPush,
    } as unknown as Router)

    const progressUpdates: number[] = []
    const result = await (service as unknown as PPTXExportService).exportAllPages(
      { mode: 'all' },
      progress => progressUpdates.push(progress.current),
    )

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(mockPreparePage.mock.calls.map(call => call[0])).toEqual(['/page-1', '/page-2'])
    expect(progressUpdates).toEqual([1, 2])
    expect(routerPush).not.toHaveBeenCalled()
    expect(mockCleanupPage).toHaveBeenCalledTimes(2)
    expect(mockDisposeStage).toHaveBeenCalledTimes(1)
  })
})

/**
 * 创建带有转换器 mock 的 PPTX 导出服务。
 * @returns 暴露私有导出入口的服务实例
 */
function createServiceWithConverter(): PptxExportServicePrivate {
  const service = new PPTXExportService() as unknown as PptxExportServicePrivate
  service.converter = {
    extractSlideIR: vi.fn(async options => createEmptySlideIR(options)),
  }
  return service
}

/**
 * 创建同时带有转换器与写入器 mock 的 PPTX 导出服务。
 */
function createServiceWithConverterAndWriter(): PptxExportServicePrivate {
  const service = createServiceWithConverter()
  const slide = createSlideMock()
  const pptx = createPptxMock(slide)
  service.packageWriter = {
    createPresentation: () => pptx,
    getShapeTypes: item => item.ShapeType,
    resolveSlideLayout: () => ({ widthIn: 13.333, heightIn: 7.5 }),
    writePresentationFile: vi.fn(async () => undefined),
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
