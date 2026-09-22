// @vitest-environment jsdom

/**
 * 文件用途：验证 PDF 截图拼接服务的路由捕获参数、页面比例和导出后路由恢复行为。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'
import { PDFExportService } from './PDFExportService'

interface RouterStub {
  currentRoute: {
    value: {
      fullPath: string
      path: string
      meta?: {
        runtimeProject?: boolean
      }
    }
  }
  push: (route: string) => Promise<void>
}

interface MockPdfOptions {
  orientation: 'landscape' | 'portrait'
  unit: string
  format: [number, number]
  compress: boolean
  putOnlyUsedFonts: boolean
  floatPrecision: number
}

interface MockPdfInstance {
  options: MockPdfOptions
  internal: {
    pageSize: {
      getWidth: () => number
      getHeight: () => number
    }
  }
}

const mockCaptureCurrentPage = vi.hoisted(() => vi.fn())
const mockCaptureRoute = vi.hoisted(() => vi.fn())
const mockRoutes = vi.hoisted(() => ({
  value: [] as Array<{
    path: string
    name: string
    pageNumber?: number
    order?: number
    level: number
    hidden: boolean
  }>,
}))
const mockAppPageConfig = vi.hoisted(() => ({
  value: {
    width: 1920,
    height: 1080,
  },
}))
const mockPdfRuntime = vi.hoisted(() => ({
  constructSpy: vi.fn(),
  instances: [] as MockPdfInstance[],
}))

const mockDisposeCapture = vi.hoisted(() => vi.fn())
vi.mock('./RuntimeCaptureContext', () => ({
  createRuntimeCaptureContext: () => ({
    capture: (path: string, options: unknown) => {
      mockCaptureRoute(path)
      return mockCaptureCurrentPage(options)
    },
    dispose: mockDisposeCapture,
  }),
}))

vi.mock('./PageCaptureService', () => ({
  pageCaptureService: {
    captureCurrentPage: mockCaptureCurrentPage,
  },
}))

vi.mock('@/core/utils/config', () => ({
  appConfig: {
    value: {
      app: {
        title: '测试项目',
      },
    },
  },
  appPageConfig: mockAppPageConfig,
}))

vi.mock('@/core/utils/route-generator', () => ({
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
}))

vi.mock('jspdf', () => {
  class MockJsPDF implements MockPdfInstance {
    options: MockPdfOptions
    addPage = vi.fn()
    addImage = vi.fn()
    save = vi.fn()
    internal: MockPdfInstance['internal']

    constructor(options: MockPdfOptions) {
      this.options = options
      this.internal = {
        pageSize: {
          getWidth: () => options.format[0],
          getHeight: () => options.format[1],
        },
      }
      mockPdfRuntime.constructSpy(options)
      mockPdfRuntime.instances.push(this)
    }
  }

  return {
    default: MockJsPDF,
  }
})

const drawImage = vi.fn()

beforeEach(() => {
  document.body.innerHTML = ''
  mockCaptureCurrentPage.mockReset()
  mockCaptureRoute.mockReset()
  mockCaptureCurrentPage.mockResolvedValue(createCanvas())
  mockPdfRuntime.constructSpy.mockClear()
  mockPdfRuntime.instances.length = 0
  mockRoutes.value = [
    { path: '/page-2', name: '第二页', pageNumber: 2, order: 2, level: 0, hidden: false },
    { path: '/page-1', name: '第一页', pageNumber: 1, order: 1, level: 0, hidden: false },
  ]
  mockAppPageConfig.value = {
    width: 1920,
    height: 1080,
  }

  Object.defineProperty(document, 'readyState', {
    configurable: true,
    get: () => 'complete',
  })

  vi.spyOn(window.HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
    drawImage,
    imageSmoothingEnabled: true,
    imageSmoothingQuality: 'high',
  } as unknown as CanvasRenderingContext2D))
  vi.spyOn(window.HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,test')
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  delete window.__RUNTIME_PREVIEW_CONTEXT__
  delete window.__RUNTIME_PREVIEW_TOKEN__
  delete window.__RUNTIME_PUBLIC_BASE_URL__
  window.history.replaceState({}, '', '/')
})

describe('PDFExportService', () => {
  it('导出所有页面时应按页码顺序传入 routePath 且不改变交互窗口路由', async () => {
    const router = createRouterStub('/origin')
    const service = new PDFExportService()
    service.setRouter(router as unknown as Router)
    renderRoute('/origin')

    const result = await service.exportAllPages({ mode: 'all', method: 'canvas-pdf' })

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(mockCaptureCurrentPage.mock.calls.map(call => call[0].routePath)).toEqual(['/page-1', '/page-2'])
    expect(router.push).not.toHaveBeenCalled()
    expect(router.currentRoute.value.fullPath).toBe('/origin')
    expect(mockDisposeCapture).toHaveBeenCalled()
  })

  it('全部页面缺少页码目录时应回退到可见路由目录', async () => {
    mockRoutes.value = [
      { path: '/page-2', name: '第二页', order: 2, level: 0, hidden: false },
      { path: '/page-1', name: '第一页', order: 1, level: 0, hidden: false },
    ]

    const router = createRouterStub('/origin')
    const service = new PDFExportService()
    service.setRouter(router as unknown as Router)
    renderRoute('/origin')

    const result = await service.exportAllPages({ mode: 'all', method: 'canvas-pdf' })

    expect(result.success).toBe(true)
    expect(result.pageCount).toBe(2)
    expect(mockCaptureCurrentPage.mock.calls.map(call => call[0].routePath)).toEqual(['/page-1', '/page-2'])
  })

  it('创建 PDF 时应使用项目画布比例，而不是当前布局容器尺寸', async () => {
    mockAppPageConfig.value = {
      width: 1920,
      height: 1080,
    }
    document.body.innerHTML = `
      <main>
        <div class="page-content-wrapper" style="width: 1208px; height: 432px;">
          <div class="runtime-page-print-source" data-runtime-route-path="/current" style="width: 1920px; height: 1080px;"></div>
        </div>
      </main>
    `

    const service = new PDFExportService()
    service.setRouter({
      currentRoute: {
        value: {
          fullPath: '/current',
          path: '/current',
        },
      },
      push: vi.fn(),
    } as unknown as Router)

    await service.exportCurrentPage({ mode: 'current', method: 'canvas-pdf' })

    const pdfOptions = mockPdfRuntime.constructSpy.mock.calls[0][0]
    expect(pdfOptions.orientation).toBe('landscape')
    expect(pdfOptions.format[0]).toBeCloseTo(297, 4)
    expect(pdfOptions.format[1]).toBeCloseTo(167.0625, 4)
  })

  it('Backend 代理预览页中应使用 Runtime 公开基址生成截图资源代理', async () => {
    window.history.replaceState({}, '', '/preview/artifacts/artifact-1?token=preview-token')
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant_1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/current' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-1',
    }
    window.__RUNTIME_PREVIEW_TOKEN__ = 'preview-token'
    window.__RUNTIME_PUBLIC_BASE_URL__ = 'https://runtime.example.com/runtime/'
    renderRoute('/current')

    const service = new PDFExportService()
    service.setRouter({
      currentRoute: {
        value: {
          fullPath: '/current',
          path: '/current',
        },
      },
      push: vi.fn(),
    } as unknown as Router)

    await service.exportCurrentPage({ mode: 'current', method: 'canvas-pdf' })

    const captureOptions = mockCaptureCurrentPage.mock.calls[0][0]
    const proxyUrl = new URL(captureOptions.proxyUrl)
    expect(proxyUrl.origin).toBe('https://runtime.example.com')
    expect(proxyUrl.pathname).toBe('/runtime/__runtime-snapdom-resource-proxy')
    expect(proxyUrl.href).not.toContain('/preview/artifacts/')
    expect(proxyUrl.href).not.toContain(window.location.origin)
    expect(window.location.pathname).toBe('/preview/artifacts/artifact-1')
    expect(window.location.search).toBe('?token=preview-token')
    expect(proxyUrl.searchParams.get('artifactId')).toBe('artifact-1')
    expect(proxyUrl.searchParams.get('token')).toBe('preview-token')
    expect(proxyUrl.href.endsWith('url=')).toBe(true)
  })

  it('预览模式缺少 Runtime 公开基址时应回退当前 origin', async () => {
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant_1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/current' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-1',
    }
    window.__RUNTIME_PREVIEW_TOKEN__ = 'preview-token'
    renderRoute('/current')

    const service = new PDFExportService()
    service.setRouter({
      currentRoute: {
        value: {
          fullPath: '/current',
          path: '/current',
        },
      },
      push: vi.fn(),
    } as unknown as Router)

    await service.exportCurrentPage({ mode: 'current', method: 'canvas-pdf' })

    const captureOptions = mockCaptureCurrentPage.mock.calls[0][0]
    const proxyUrl = new URL(captureOptions.proxyUrl)
    expect(proxyUrl.origin).toBe(window.location.origin)
    expect(proxyUrl.pathname).toBe('/__runtime-snapdom-resource-proxy')
    expect(proxyUrl.searchParams.get('artifactId')).toBe('artifact-1')
    expect(proxyUrl.searchParams.get('token')).toBe('preview-token')
    expect(proxyUrl.href.endsWith('url=')).toBe(true)
  })

  it('Runtime 项目导出当前页时应保留 fullPath 查询参数', async () => {
    const router = {
      currentRoute: {
        value: {
          fullPath: '/current?period=2026',
          path: '/current',
          meta: { runtimeProject: true },
        },
      },
      push: vi.fn(),
    }
    const service = new PDFExportService()
    service.setRouter(router as unknown as Router)

    await service.exportCurrentPage({ mode: 'current', method: 'canvas-pdf' })

    expect(mockCaptureRoute).toHaveBeenCalledWith('/current?period=2026')
    expect(mockCaptureCurrentPage.mock.calls[0][0].routePath).toBe('/current')
  })
})

/**
 * 创建导出测试用路由桩。
 * @param originalRoute 初始路由
 */
function createRouterStub(originalRoute: string): RouterStub {
  const router = {
    currentRoute: {
      value: {
        fullPath: originalRoute,
        path: originalRoute,
      },
    },
    push: vi.fn(async (route: string) => {
      router.currentRoute.value.fullPath = route
      router.currentRoute.value.path = route
      renderRoute(route)
    }),
  }

  return router
}

/**
 * 渲染指定路由对应的页面源节点。
 * @param route 页面路由
 */
function renderRoute(route: string): void {
  document.body.innerHTML = `
    <main>
      <div class="page-content-wrapper">
        <div class="runtime-page-print-source" data-runtime-route-path="${route}" style="width: 1920px; height: 1080px;">
          ${route}
        </div>
      </div>
    </main>
  `
}

/**
 * 创建一张模拟截图 canvas。
 */
function createCanvas(): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = 3840
  canvas.height = 2160
  return canvas
}
