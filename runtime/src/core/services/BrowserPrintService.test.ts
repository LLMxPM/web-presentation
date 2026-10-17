// @vitest-environment jsdom

/**
 * 文件用途：验证浏览器打印服务的打印文档构建、分页收集与异常清理行为。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'
import { BrowserPrintService } from './BrowserPrintService'

interface RouterStub {
  currentRoute: {
    value: {
      fullPath: string
      path: string
      meta?: { runtimeProject?: boolean }
    }
  }
  push: (route: string) => Promise<void>
}

const mockStage = vi.hoisted(() => ({
  preparePage: vi.fn(),
  dispose: vi.fn(),
}))

vi.mock('./export/OffscreenPageStage', async importOriginal => {
  const actual = await importOriginal<typeof import('./export/OffscreenPageStage')>()
  return {
    ...actual,
    createOffscreenPageStage: () => ({
      preparePage: mockStage.preparePage,
      capture: vi.fn(),
      dispose: mockStage.dispose,
    }),
  }
})

const mockRoutes = vi.hoisted(() => ({
  value: [] as Array<{
    path: string
    name: string
    pageNumber?: number
    level: number
    hidden: boolean
    order?: number
  }>,
}))

vi.mock('@/core/utils/config', async () => {
  return {
    appPageConfig: {
      value: {
        width: 1920,
        height: 1080,
      },
    },
  }
})

vi.mock('@/core/utils/route-generator', async () => {
  return {
    getRouteInfosSortedByPageNumber: () => {
      return [...mockRoutes.value]
        .filter(route => route.pageNumber !== undefined)
        .sort((a, b) => (a.pageNumber || 0) - (b.pageNumber || 0))
    },
    getVisibleRouteInfos: () => {
      return [...mockRoutes.value]
        .filter(route => !route.hidden)
        .sort((a, b) => (a.order || 0) - (b.order || 0))
    },
  }
})

function renderCurrentPage(text: string, routePath = '/current'): void {
  document.querySelector('main')?.remove()
  document.body.insertAdjacentHTML('afterbegin', `
    <main>
      <div class="page-content-wrapper">
        <div class="fixed-ratio-container" style="transform: scale(0.5); box-shadow: 0 0 4px #000;">
          <div class="runtime-page-print-source" data-runtime-route-path="${routePath}">
            <section class="slide-page" style="width: 1920px; height: 1080px;">${text}</section>
          </div>
        </div>
      </div>
    </main>
  `)
}

function stubIframePrint(): ReturnType<typeof vi.fn> {
  const printSpy = vi.fn()
  const originalCreateElement = document.createElement.bind(document)

  vi.spyOn(document, 'createElement').mockImplementation((tagName: string, options?: ElementCreationOptions) => {
    const element = originalCreateElement(tagName, options)

    if (tagName.toLowerCase() === 'iframe') {
      setTimeout(() => {
        const iframe = element as HTMLIFrameElement
        if (iframe.contentWindow) {
          iframe.contentWindow.print = printSpy
          iframe.contentWindow.focus = vi.fn()
        }
      }, 0)
    }

    return element
  })

  return printSpy
}

beforeEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  mockStage.preparePage.mockReset()
  mockStage.dispose.mockReset()
  mockRoutes.value = [
    { path: '/page-2', name: '第二页', pageNumber: 2, level: 0, hidden: false, order: 2 },
    { path: '/page-1', name: '第一页', pageNumber: 1, level: 0, hidden: false, order: 1 },
  ]
  document.documentElement.style.setProperty('--theme-text-primary', '#123456')
  document.documentElement.style.setProperty('--tw-color-text-primary', '#123456')
  renderCurrentPage('当前页')
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

/** 构造离屏舞台返回的页面节点，不依赖真实 iframe。 */
function createPreparedPage(route: string, content: string) {
  const element = document.createElement('div')
  element.className = 'runtime-page-print-source'
  element.dataset.runtimeRoutePath = route
  element.textContent = content
  return { element, cleanup: vi.fn() }
}

describe('BrowserPrintService', () => {
  it('应将当前页面克隆到专用打印 iframe 并触发浏览器打印', async () => {
    stubIframePrint()
    const service = new BrowserPrintService()

    const result = await service.printCurrentPage({ mode: 'current', method: 'browser-print' })
    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null

    expect(result.success).toBe(true)
    expect(result.method).toBe('browser-print')
    expect(result.pageCount).toBe(1)
    expect(iframe).not.toBeNull()
    expect(iframe?.contentDocument?.querySelectorAll('.print-page')).toHaveLength(1)
    expect(iframe?.contentDocument?.body.textContent).toContain('当前页')
    expect(iframe?.contentDocument?.head.textContent).toContain('--theme-text-primary: #123456;')
    expect(iframe?.contentDocument?.head.textContent).toContain('--tw-color-text-primary: #123456;')
    expect(iframe?.contentDocument?.head.textContent).toContain('.runtime-page-print-source')
    expect(iframe?.contentDocument?.head.textContent).toContain('zoom:')
    expect(iframe?.contentDocument?.head.textContent).toContain('transform: none !important')
  })

  it('应复制 canvas 位图到打印 iframe，避免 ECharts 图表空白', async () => {
    stubIframePrint()
    renderCurrentPage('<canvas class="echarts-canvas" width="120" height="80" style="width: 120px; height: 80px;"></canvas>')

    const sourceCanvas = document.querySelector<HTMLCanvasElement>('.echarts-canvas')
    const drawImage = vi.fn()
    const clearRect = vi.fn()
    vi.spyOn(window.HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
      clearRect,
      drawImage,
    } as unknown as CanvasRenderingContext2D))

    const service = new BrowserPrintService()
    await service.printCurrentPage({ mode: 'current', method: 'browser-print' })

    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null
    const clonedCanvas = iframe?.contentDocument?.querySelector<HTMLCanvasElement>('.echarts-canvas')

    expect(sourceCanvas).not.toBeNull()
    expect(clonedCanvas).not.toBeNull()
    expect(clonedCanvas?.width).toBe(120)
    expect(clonedCanvas?.height).toBe(80)
    expect(clearRect).toHaveBeenCalledWith(0, 0, 120, 80)
    expect(drawImage).toHaveBeenCalledWith(sourceCanvas, 0, 0)
  })

  it('应按页码顺序在离屏舞台收集所有页面，且不导航主画布', async () => {
    stubIframePrint()
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async () => undefined),
    } satisfies RouterStub
    const preparedRoutes: string[] = []
    mockStage.preparePage.mockImplementation(async (route: string) => {
      preparedRoutes.push(route)
      return createPreparedPage(route, route === '/page-1' ? '第一页内容' : '第二页内容')
    })
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printAllPages({ mode: 'all', method: 'browser-print' })
    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null
    const pages = Array.from(iframe?.contentDocument?.querySelectorAll('.print-page') ?? [])

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(preparedRoutes).toEqual(['/page-1', '/page-2'])
    expect(pages).toHaveLength(2)
    expect(pages[0].textContent).toContain('第一页内容')
    expect(pages[1].textContent).toContain('第二页内容')
    expect(router.push).not.toHaveBeenCalled()
    expect(router.currentRoute.value.fullPath).toBe('/origin')
    expect(mockStage.dispose).toHaveBeenCalled()
  })

  it('缺少页码目录时应回退到可见路由目录继续收集页面', async () => {
    stubIframePrint()
    mockRoutes.value = [
      { path: '/page-2', name: '第二页', level: 0, hidden: false, order: 2 },
      { path: '/page-1', name: '第一页', level: 0, hidden: false, order: 1 },
    ]
    const preparedRoutes: string[] = []
    mockStage.preparePage.mockImplementation(async (route: string) => {
      preparedRoutes.push(route)
      return createPreparedPage(route, route)
    })
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async () => undefined),
    } satisfies RouterStub

    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printAllPages({ mode: 'all', method: 'browser-print' })

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(preparedRoutes).toEqual(['/page-1', '/page-2'])
    expect(router.push).not.toHaveBeenCalled()
  })

  it('取消打印后应停止后续离屏准备并清理舞台与临时 iframe', async () => {
    stubIframePrint()
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async () => undefined),
    } satisfies RouterStub
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    let preparedCount = 0
    mockStage.preparePage.mockImplementation(async (route: string) => {
      preparedCount += 1
      if (preparedCount === 2) {
        service.cancelPrint()
        throw new Error('用户取消导出')
      }
      return createPreparedPage(route, '第一页内容')
    })

    await expect(service.printAllPages({ mode: 'all', method: 'browser-print' }))
      .rejects.toThrow('用户取消导出')

    expect(preparedCount).toBe(2)
    expect(mockStage.dispose).toHaveBeenCalled()
    expect(document.getElementById('runtime-browser-print-frame')).toBeNull()
    expect(service.isCurrentlyPrinting()).toBe(false)
  })

  it('离屏页面准备失败时应清理临时 iframe 与舞台且不触发打印', async () => {
    const printSpy = stubIframePrint()
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async () => undefined),
    } satisfies RouterStub
    mockStage.preparePage.mockRejectedValue(new Error('导出页面视觉资源未就绪'))
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    await expect(service.printAllPages({ mode: 'all', method: 'browser-print' }))
      .rejects.toThrow('导出页面视觉资源未就绪')

    expect(printSpy).not.toHaveBeenCalled()
    expect(document.getElementById('runtime-browser-print-frame')).toBeNull()
    expect(mockStage.dispose).toHaveBeenCalled()
  })

  it('项目路由打印当前页时使用离屏舞台并保留 fullPath', async () => {
    stubIframePrint()
    mockStage.preparePage.mockResolvedValue(createPreparedPage('/current', '离屏当前页'))
    const router = {
      currentRoute: {
        value: {
          fullPath: '/current?period=2026',
          path: '/current',
          meta: { runtimeProject: true },
        },
      },
      push: vi.fn(async () => undefined),
    } satisfies RouterStub
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printCurrentPage({ mode: 'current', method: 'browser-print' })
    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null

    expect(result.success).toBe(true)
    expect(mockStage.preparePage).toHaveBeenCalledWith('/current?period=2026', expect.objectContaining({
      signal: expect.any(AbortSignal),
    }))
    expect(iframe?.contentDocument?.body.textContent).toContain('离屏当前页')
    expect(router.push).not.toHaveBeenCalled()
    expect(mockStage.dispose).toHaveBeenCalled()
  })
})
