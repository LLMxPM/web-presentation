// @vitest-environment jsdom

/**
 * 文件用途：验证导出运行器的方式×范围分派、取消语义，以及取消后迟到结果被整体丢弃、不覆盖状态也不补发事件。
 */

import { createApp, defineComponent, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ExportProgress } from '@/core/types/export-common'
import type { ExportRunRequest, ExportRunListener } from './useExportRunner'
import { useExportRunner } from './useExportRunner'

const serviceSpies = vi.hoisted(() => ({
  exportPdfCurrentPage: vi.fn(),
  exportPdfAllPages: vi.fn(),
  cancelPdfExport: vi.fn(),
  printCurrentPage: vi.fn(),
  printAllPages: vi.fn(),
  cancelPrint: vi.fn(),
  exportPptxCurrentPage: vi.fn(),
  exportPptxAllPages: vi.fn(),
  cancelPptxExport: vi.fn(),
  setRouter: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: { value: { fullPath: '/' } },
  }),
}))

vi.mock('@/core/services/PDFExportService', () => ({
  pdfExportService: {
    exportCurrentPage: serviceSpies.exportPdfCurrentPage,
    exportAllPages: serviceSpies.exportPdfAllPages,
    cancelExport: serviceSpies.cancelPdfExport,
    setRouter: serviceSpies.setRouter,
  },
}))

vi.mock('@/core/services/BrowserPrintService', () => ({
  browserPrintService: {
    printCurrentPage: serviceSpies.printCurrentPage,
    printAllPages: serviceSpies.printAllPages,
    cancelPrint: serviceSpies.cancelPrint,
    setRouter: serviceSpies.setRouter,
  },
}))

vi.mock('@/core/services/PPTXExportService', () => ({
  pptxExportService: {
    exportCurrentPage: serviceSpies.exportPptxCurrentPage,
    exportAllPages: serviceSpies.exportPptxAllPages,
    cancelExport: serviceSpies.cancelPptxExport,
    setRouter: serviceSpies.setRouter,
  },
}))

type RunnerApi = ReturnType<typeof useExportRunner>

/** 受控 Promise，用于精确编排服务调用的 settle 时机。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/**
 * 在真实组件上下文中挂载运行器，使 useRouter 与 onMounted 正常生效。
 * @param listener 运行事件回调
 * @returns 运行器实例与其宿主应用
 */
function mountRunner(listener: ExportRunListener = {}) {
  let api!: RunnerApi
  const host = defineComponent({
    setup() {
      api = useExportRunner(listener)
      return () => null
    },
  })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(host)
  app.mount(container)

  return { api, app, container }
}

/** 构造一次导出请求。 */
function request(overrides: Partial<ExportRunRequest> = {}): ExportRunRequest {
  return {
    method: 'pptx-editable',
    mode: 'current',
    filename: undefined,
    ...overrides,
  }
}

afterEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('useExportRunner 分派', () => {
  it.each([
    ['pptx-editable', 'current', 'exportPptxCurrentPage'],
    ['pptx-editable', 'all', 'exportPptxAllPages'],
    ['browser-print', 'current', 'printCurrentPage'],
    ['browser-print', 'all', 'printAllPages'],
    ['canvas-pdf', 'current', 'exportPdfCurrentPage'],
    ['canvas-pdf', 'all', 'exportPdfAllPages'],
  ] as const)('方式 %s + 范围 %s 应调用 %s', async (method, mode, spyName) => {
    serviceSpies[spyName].mockResolvedValue({ success: true, taskId: 't', method, pageCount: 1 })
    const { api, app } = mountRunner()

    await api.startExport(request({ method, mode }))

    expect(serviceSpies[spyName]).toHaveBeenCalledTimes(1)
    const options = serviceSpies[spyName].mock.calls[0][0]
    expect(options).toMatchObject({ mode })
    if (method !== 'pptx-editable') {
      expect(options.method).toBe(method)
    }
    app.unmount()
  })

  it('挂载时应把当前路由注入三个导出服务单例', () => {
    const { app } = mountRunner()

    expect(serviceSpies.setRouter).toHaveBeenCalledTimes(3)
    app.unmount()
  })

  it('导出进行中重复发起应被忽略，不得并发调用服务', async () => {
    const pending = deferred<{ success: boolean; taskId: string; method: 'pptx-editable' }>()
    serviceSpies.exportPptxCurrentPage.mockReturnValue(pending.promise)
    const { api, app } = mountRunner()

    const first = api.startExport(request())
    await nextTick()
    await api.startExport(request())

    expect(serviceSpies.exportPptxCurrentPage).toHaveBeenCalledTimes(1)
    pending.resolve({ success: true, taskId: 't', method: 'pptx-editable' })
    await first
    app.unmount()
  })
})

describe('useExportRunner 取消语义', () => {
  it('取消后迟到的成功结果必须被丢弃：不覆盖取消态、不补发 export-complete', async () => {
    const pending = deferred<{ success: boolean; taskId: string; method: 'pptx-editable'; pageCount: number }>()
    serviceSpies.exportPptxAllPages.mockReturnValue(pending.promise)
    const onComplete = vi.fn()
    const onError = vi.fn()
    const { api, app } = mountRunner({ onComplete, onError })

    const running = api.startExport(request({ mode: 'all' }))
    await nextTick()
    api.cancelExport('pptx-editable')

    expect(serviceSpies.cancelPptxExport).toHaveBeenCalledTimes(1)
    expect(api.isExporting.value).toBe(false)
    expect(api.exportResult.value).toMatchObject({ success: false, error: '用户取消导出', method: 'pptx-editable' })

    // 服务在取消之后才真正结束，其结果不得回写。
    pending.resolve({ success: true, taskId: 'late', method: 'pptx-editable', pageCount: 9 })
    await running
    await nextTick()

    expect(api.exportResult.value).toMatchObject({ success: false, error: '用户取消导出' })
    expect(onComplete).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(api.isExporting.value).toBe(false)
    app.unmount()
  })

  it('取消后迟到的失败结果也不得补发 export-error', async () => {
    const pending = deferred<unknown>()
    serviceSpies.exportPdfAllPages.mockReturnValue(pending.promise)
    const onError = vi.fn()
    const { api, app } = mountRunner({ onError })

    const running = api.startExport(request({ method: 'canvas-pdf', mode: 'all' }))
    await nextTick()
    api.cancelExport('canvas-pdf')

    pending.reject(new Error('迟到的失败'))
    await running
    await nextTick()

    expect(api.exportResult.value).toMatchObject({ error: '用户取消导出', method: 'canvas-pdf' })
    expect(onError).not.toHaveBeenCalled()
    app.unmount()
  })

  it('取消后到达的进度上报不得再写入 progress', async () => {
    let reportProgress: ((progress: ExportProgress) => void) | undefined
    const pending = deferred<unknown>()
    serviceSpies.exportPptxAllPages.mockImplementation((_options: unknown, onProgress: (p: ExportProgress) => void) => {
      reportProgress = onProgress
      return pending.promise
    })
    const { api, app } = mountRunner()

    const running = api.startExport(request({ mode: 'all' }))
    await nextTick()

    reportProgress?.({ current: 1, total: 3, percentage: 33, currentPageTitle: '第一页', currentPageRoute: '/p1' })
    expect(api.progress.value.percentage).toBe(33)

    api.cancelExport('pptx-editable')
    reportProgress?.({ current: 2, total: 3, percentage: 66, currentPageTitle: '第二页', currentPageRoute: '/p2' })

    expect(api.progress.value.percentage).toBe(33)
    pending.resolve(null)
    await running
    app.unmount()
  })

  it('取消后可以立即发起新的导出，且旧运行仍被判定为过期', async () => {
    const stale = deferred<unknown>()
    const fresh = deferred<{ success: boolean; taskId: string; method: 'pptx-editable'; pageCount: number }>()
    serviceSpies.exportPptxAllPages
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(fresh.promise)
    const onComplete = vi.fn()
    const { api, app } = mountRunner({ onComplete })

    const staleRun = api.startExport(request({ mode: 'all' }))
    await nextTick()
    api.cancelExport('pptx-editable')

    const freshRun = api.startExport(request({ mode: 'all' }))
    await nextTick()
    expect(api.isExporting.value).toBe(true)

    fresh.resolve({ success: true, taskId: 'new', method: 'pptx-editable', pageCount: 2 })
    await freshRun
    stale.resolve({ success: true, taskId: 'stale', method: 'pptx-editable', pageCount: 99 })
    await staleRun
    await nextTick()

    expect(api.exportResult.value).toMatchObject({ success: true, taskId: 'new', pageCount: 2 })
    expect(onComplete).toHaveBeenCalledTimes(1)
    app.unmount()
  })

  it('未在导出中时调用取消应为空操作，不得写入取消结果', () => {
    const { api, app } = mountRunner()

    api.cancelExport('pptx-editable')

    expect(serviceSpies.cancelPptxExport).not.toHaveBeenCalled()
    expect(api.exportResult.value).toBeNull()
    app.unmount()
  })
})

describe('useExportRunner 正常完成与失败', () => {
  it('成功时应写入结果、结束导出态并触发 export-complete', async () => {
    serviceSpies.exportPptxCurrentPage.mockResolvedValue({
      success: true,
      taskId: 'ok',
      method: 'pptx-editable',
      pageCount: 1,
    })
    const onStart = vi.fn()
    const onComplete = vi.fn()
    const { api, app } = mountRunner({ onStart, onComplete })

    await api.startExport(request())

    expect(onStart).toHaveBeenCalledTimes(1)
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ taskId: 'ok' }))
    expect(api.exportResult.value).toMatchObject({ success: true, taskId: 'ok' })
    expect(api.isExporting.value).toBe(false)
    app.unmount()
  })

  it('失败时应写入按方式收窄的失败结果并触发 export-error', async () => {
    serviceSpies.printAllPages.mockRejectedValue(new Error('打印失败'))
    const onError = vi.fn()
    const { api, app } = mountRunner({ onError })

    await api.startExport(request({ method: 'browser-print', mode: 'all' }))

    expect(api.exportResult.value).toMatchObject({
      success: false,
      method: 'browser-print',
      error: '打印失败',
    })
    expect(onError).toHaveBeenCalledWith(expect.any(Error))
    expect(api.isExporting.value).toBe(false)
    app.unmount()
  })

  it('非 Error 抛出应归一化为「导出失败」', async () => {
    serviceSpies.exportPdfCurrentPage.mockRejectedValue('字符串异常')
    const { api, app } = mountRunner()

    await api.startExport(request({ method: 'canvas-pdf' }))

    expect(api.exportResult.value).toMatchObject({ success: false, error: '导出失败' })
    app.unmount()
  })

  it('resetRun 应清空结果与进度', async () => {
    serviceSpies.exportPptxAllPages.mockImplementation(
      (_options: unknown, onProgress: (p: ExportProgress) => void) => {
        onProgress({ current: 1, total: 2, percentage: 50, currentPageTitle: '页', currentPageRoute: '/p' })
        return Promise.resolve({ success: true, taskId: 't', method: 'pptx-editable', pageCount: 2 })
      },
    )
    const { api, app } = mountRunner()

    await api.startExport(request({ mode: 'all' }))
    expect(api.exportResult.value).not.toBeNull()
    expect(api.progress.value.percentage).toBe(50)

    api.resetRun()

    expect(api.exportResult.value).toBeNull()
    expect(api.progress.value).toMatchObject({ current: 0, total: 0, percentage: 0, currentPageTitle: '' })
    app.unmount()
  })
})
