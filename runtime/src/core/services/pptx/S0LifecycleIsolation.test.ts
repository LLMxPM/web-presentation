// @vitest-environment jsdom

/**
 * 文件用途：验证 S0 阶段生命周期与取消隔离（退出条件 1 & 2：取消期间零下载、取消后重试状态不串扰）。
 */

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
        convertPage: ReturnType<typeof vi.fn>
      }
    }

    privateService.packageWriter.generatePresentationBytes = generateBytesSpy
    privateService.packageWriter.savePptxBlob = saveBlobSpy
    privateService.converter.convertPage = vi.fn(async () => ({
      pageIndex: 1,
      pageTitle: '测试页',
      pageRoute: '/test',
      items: [],
    }))
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
    // 在 convertPage 期间触发取消
    const privateService = service as unknown as {
      converter: { convertPage: ReturnType<typeof vi.fn> }
    }
    privateService.converter.convertPage.mockImplementation(async () => {
      runningTask = service.getCurrentTask()
      service.cancelExport()
      return { pageIndex: 1, pageTitle: '测试', pageRoute: '/test', items: [] }
    })

    await expect(service.exportCurrentPage({ mode: 'current' })).rejects.toThrow('用户取消导出')

    // 退出条件 1：取消期间零下载
    expect(saveBlobSpy).not.toHaveBeenCalled()

    // 取消不记为 FAILED
    expect(runningTask).not.toBeNull()
    expect(runningTask?.status).toBe(ExportStatus.CANCELLED)
    expect(service.isTaskCancelled(runningTask?.id)).toBe(true)
  })

  it('任务 1 取消后立即发起任务 2，任务 1 的 finally 不得清理任务 2 的运行态，且状态不串扰', async () => {
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

    let resolveTask1Conversion!: () => void
    const task1Promise = new Promise<void>(resolve => {
      resolveTask1Conversion = resolve
    })

    const privateService = service as unknown as {
      converter: { convertPage: ReturnType<typeof vi.fn> }
    }

    let callCount = 0
    privateService.converter.convertPage.mockImplementation(async () => {
      callCount += 1
      if (callCount === 1) {
        // 任务 1 挂起
        await task1Promise
      }
      return { pageIndex: 1, pageTitle: `页面 ${callCount}`, pageRoute: '/test', items: [] }
    })

    // 发起任务 1
    const run1Promise = service.exportCurrentPage({ mode: 'current' })

    // 取消任务 1
    const task1 = service.getCurrentTask()
    expect(task1).not.toBeNull()
    service.cancelExport(task1?.id)

    // 退出条件 2：取消后可立即发起任务 2
    const run2Promise = service.exportCurrentPage({ mode: 'current' })
    const task2 = service.getCurrentTask()
    expect(task2).not.toBeNull()
    expect(task2?.id).not.toBe(task1?.id)
    expect(service.isCurrentlyExporting()).toBe(true)

    // 让任务 1 迟到恢复并进入 finally
    resolveTask1Conversion()
    await expect(run1Promise).rejects.toThrow('用户取消导出')

    // 关键断言：任务 1 的迟到 finally 不得清理正在运行的任务 2
    expect(service.isCurrentlyExporting()).toBe(true)
    expect(service.getCurrentTask()?.id).toBe(task2?.id)

    // 任务 2 正常完成
    const result2 = await run2Promise
    expect(result2.success).toBe(true)
    expect(result2.taskId).toBe(task2?.id)
    expect(saveBlobSpy).toHaveBeenCalledTimes(1) // 仅任务 2 触发了一次下载，任务 1 零下载
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
