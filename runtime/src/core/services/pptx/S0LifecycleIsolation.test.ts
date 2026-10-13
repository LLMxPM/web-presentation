// @vitest-environment jsdom

/**
 * 文件用途：验证 S0 阶段生命周期与取消隔离（退出条件 1 & 2：取消期间零下载、取消后重试状态不串扰）。
 */

import { createEmptySlideIR } from './PPTXDomConverter.test-support'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'
import { ExportStatus } from '@/core/types/export-common'
import { PPTXExportService } from '../PPTXExportService'
import { createSlideMock } from './PPTXDomConverter.test-support'

describe('S0 生命周期与取消隔离', () => {
  let service: PPTXExportService
  let saveBlobSpy: ReturnType<typeof vi.fn>
  let generateBytesSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    service = new PPTXExportService()
    saveBlobSpy = vi.fn()
    generateBytesSpy = vi.fn(async () => new Uint8Array([1, 2, 3]))

    // 注入受控的 packageWriter 监控点
    const privateService = service as unknown as {
      packageWriter: {
        generatePresentationBytes: typeof generateBytesSpy
        savePptxBlob: typeof saveBlobSpy
        createPresentation: () => ReturnType<typeof createSlideMock>
        getShapeTypes: () => { rect: string; roundRect: string; ellipse: string; line: string }
        resolveSlideLayout: () => { widthIn: number; heightIn: number }
      }
      converter: {
        extractSlideIR: ReturnType<typeof vi.fn>
      }
    }

    privateService.packageWriter.generatePresentationBytes = generateBytesSpy
    privateService.packageWriter.savePptxBlob = saveBlobSpy
    privateService.converter.extractSlideIR = vi.fn(async options => createEmptySlideIR(options))
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('单页导出取消后必须零下载，且任务状态保持 CANCELLED 而非 FAILED', async () => {
    document.body.innerHTML = '<div class="runtime-page-print-source" data-runtime-route-path="/test" style="width: 1920px; height: 1080px;"><h1>测试内容</h1></div>'

    service.setRouter({
      currentRoute: {
        value: {
          path: '/test',
          fullPath: '/test',
          meta: {},
        },
      },
    } as unknown as Router)

    let runningTask: ReturnType<typeof service.getCurrentTask> = null
    // 在 extractSlideIR 期间触发取消
    const privateService = service as unknown as {
      converter: { extractSlideIR: ReturnType<typeof vi.fn> }
    }
    privateService.converter.extractSlideIR.mockImplementation(async options => {
      runningTask = service.getCurrentTask()
      service.cancelExport()
      return createEmptySlideIR(options)
    })

    await expect(service.exportCurrentPage({ mode: 'current' })).rejects.toThrow('用户取消导出')

    // 退出条件 1：取消期间零下载
    expect(saveBlobSpy).not.toHaveBeenCalled()

    // 取消不记为 FAILED
    expect(runningTask).not.toBeNull()
    expect(runningTask?.status).toBe(ExportStatus.CANCELLED)
    expect(service.isTaskCancelled(runningTask?.id)).toBe(true)
  })

  it('取消后保持互斥直到旧任务释放，释放后才允许重试', async () => {
    document.body.innerHTML = '<div class="runtime-page-print-source" data-runtime-route-path="/test" style="width:1920px;height:1080px"></div>'
    service.setRouter({ currentRoute: { value: { path: '/test', fullPath: '/test', meta: {} } } } as unknown as Router)
    let release!: () => void
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    const gate = new Promise<void>(resolve => { release = resolve })
    const converter = (service as unknown as { converter: { extractSlideIR: ReturnType<typeof vi.fn> } }).converter
    converter.extractSlideIR.mockImplementationOnce(async options => {
      entered()
      await gate
      return createEmptySlideIR(options)
    })
    const first = service.exportCurrentPage({ mode: 'current' })
    await started
    service.cancelExport()
    expect(service.isCurrentlyExporting()).toBe(true)
    await expect(service.exportCurrentPage({ mode: 'current' })).rejects.toThrow('已有导出任务')
    release()
    await expect(first).rejects.toThrow('用户取消导出')
    expect(service.isCurrentlyExporting()).toBe(false)
    expect((await service.exportCurrentPage({ mode: 'current' })).success).toBe(true)
    expect(saveBlobSpy).toHaveBeenCalledTimes(1)
  })

  it('打包字节生成期间取消，不得调用 savePptxBlob 提交文件', async () => {
    document.body.innerHTML = '<div class="runtime-page-print-source" data-runtime-route-path="/test" style="width: 1920px; height: 1080px;"><h1>测试内容</h1></div>'

    service.setRouter({
      currentRoute: {
        value: {
          path: '/test',
          fullPath: '/test',
          meta: {},
        },
      },
    } as unknown as Router)

    generateBytesSpy.mockImplementation(async () => {
      // 正在生成 zip 字节时用户点击取消
      service.cancelExport()
      return new Uint8Array([1, 2, 3])
    })

    await expect(service.exportCurrentPage({ mode: 'current' })).rejects.toThrow('用户取消导出')
    expect(generateBytesSpy).toHaveBeenCalledTimes(1)
    expect(saveBlobSpy).not.toHaveBeenCalled()
  })
})
