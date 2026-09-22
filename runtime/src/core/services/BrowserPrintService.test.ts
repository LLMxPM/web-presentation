// @vitest-environment jsdom

/**
 * 文件用途：验证浏览器打印服务的打印文档构建、分页收集与异常清理行为。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import type { Router } from 'vue-router'
import { BrowserPrintService } from './BrowserPrintService'

interface RouterStub {
  currentRoute: {
    value: {
      fullPath: string
      path: string
    }
  }
  push: (route: string) => Promise<void>
}

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

  it('应按页码顺序收集所有页面并生成分页打印文档', async () => {
    stubIframePrint()
    const pushedRoutes: string[] = []
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async (route: string) => {
        pushedRoutes.push(route)
        router.currentRoute.value.fullPath = route
        router.currentRoute.value.path = route
        renderCurrentPage(route === '/page-1' ? '第一页内容' : '第二页内容', route)
        await nextTick()
      }),
    } satisfies RouterStub
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printAllPages({ mode: 'all', method: 'browser-print' })
    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null
    const pages = Array.from(iframe?.contentDocument?.querySelectorAll('.print-page') ?? [])

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(pushedRoutes.slice(0, 2)).toEqual(['/page-1', '/page-2'])
    expect(router.push).toHaveBeenLastCalledWith('/origin')
    expect(pages).toHaveLength(2)
    expect(pages[0].textContent).toContain('第一页内容')
    expect(pages[1].textContent).toContain('第二页内容')
  })

  it('缺少页码目录时应回退到可见路由目录继续收集页面', async () => {
    stubIframePrint()
    mockRoutes.value = [
      { path: '/page-2', name: '第二页', level: 0, hidden: false, order: 2 },
      { path: '/page-1', name: '第一页', level: 0, hidden: false, order: 1 },
    ]

    const pushedRoutes: string[] = []
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async (route: string) => {
        pushedRoutes.push(route)
        router.currentRoute.value.fullPath = route
        router.currentRoute.value.path = route
        renderCurrentPage(route === '/page-1' ? '第一页内容' : '第二页内容', route)
        await nextTick()
      }),
    } satisfies RouterStub

    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printAllPages({ mode: 'all', method: 'browser-print' })

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(pushedRoutes.slice(0, 2)).toEqual(['/page-1', '/page-2'])
  })

  it('应等待目标路由 DOM 渲染完成后再克隆页面', async () => {
    stubIframePrint()
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async (route: string) => {
        router.currentRoute.value.fullPath = route
        router.currentRoute.value.path = route

        if (route === '/page-1') {
          renderCurrentPage('第一页内容', route)
          return
        }

        window.setTimeout(() => {
          renderCurrentPage('第二页延迟内容', route)
        }, 120)
      }),
    } satisfies RouterStub
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    const result = await service.printAllPages({ mode: 'all', method: 'browser-print' })
    const iframe = document.getElementById('runtime-browser-print-frame') as HTMLIFrameElement | null
    const pages = Array.from(iframe?.contentDocument?.querySelectorAll('.print-page') ?? [])

    expect(result.pageCount).toBe(2)
    expect(pages[0].textContent).toContain('第一页内容')
    expect(pages[1].textContent).toContain('第二页延迟内容')
  })

  it('所有页面均无法收集时应清理临时 iframe', async () => {
    stubIframePrint()
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const router = {
      currentRoute: {
        value: {
          fullPath: '/origin',
          path: '/origin',
        },
      },
      push: vi.fn(async (route: string) => {
        router.currentRoute.value.fullPath = route
        router.currentRoute.value.path = route
        document.body.innerHTML = '<main></main>'
      }),
    } satisfies RouterStub
    const service = new BrowserPrintService()
    service.setRouter(router as unknown as Router)

    await expect(service.printAllPages({ mode: 'all', method: 'browser-print' })).rejects.toThrow('没有成功收集任何可打印页面')
    expect(document.getElementById('runtime-browser-print-frame')).toBeNull()
  })
})
