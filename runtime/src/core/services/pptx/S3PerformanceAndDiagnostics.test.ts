/**
 * 文件用途：PPTX 导出升级 S3 阶段（性能和诊断）专项测试，覆盖任务级资源缓存复用、整页截图容错 (rasterize-ready-page)、默认 fail-fast、取消优先保护、阶段耗时与脱敏诊断报告。
 */

import { createEmptySlideIR } from './PPTXDomConverter.test-support'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PptxResourceSession } from './session/PptxResourceSession'
import { PPTXExportService } from '@/core/services/PPTXExportService'
import { elementRasterizer } from '@/core/services/export/ElementRasterizer'
import type { Router } from 'vue-router'
import type { PptxExportOptions } from '@/core/types/pptx-export'

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

describe('S3 性能和诊断专项测试', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('1. 任务级资源缓存与复用', () => {
    let session: PptxResourceSession

    beforeEach(() => {
      session = new PptxResourceSession('task-perf-1')
    })

    it('同一资源重复读取时应命中任务缓存，避免重复网络请求', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: {
          get: (header: string) => (header.toLowerCase() === 'content-type' ? 'image/png' : null),
        },
        arrayBuffer: async () => new ArrayBuffer(128),
      })
      vi.stubGlobal('fetch', mockFetch)

      const targetUrl = 'https://example.com/assets/logo.png'

      // 首次读取：触发实际网络请求
      const data1 = await session.resolveImage(targetUrl)
      expect(data1).toContain('data:image/png;base64,')
      expect(mockFetch).toHaveBeenCalledTimes(1)

      // 第二次读取相同资源：直接命中任务缓存
      const data2 = await session.resolveImage(targetUrl)
      expect(data2).toBe(data1)
      expect(mockFetch).toHaveBeenCalledTimes(1) // 请求次数没有增加

      // 验证性能指标记录
      const metrics = session.getMetrics()
      expect(metrics.fetchCount).toBe(1)
      expect(metrics.cacheHits).toBe(1)
      expect(metrics.totalResourceBytes).toBeGreaterThan(0)

      session.dispose()
      vi.unstubAllGlobals()
    })

    it('诊断报告中应将 URL 敏感查询参数（token/key/secret）安全脱敏', () => {
      const sensitiveUrl = 'https://example.com/image.png?token=secret123456&version=1.0'
      const sanitized = session.sanitizeUrl(sensitiveUrl)
      expect(sanitized).not.toContain('secret123456')
      expect(sanitized).toContain('token=%5BREDACTED%5D')
      expect(sanitized).toContain('version=1.0')
    })
  })

  describe('2. 整页容错与阶段耗时编排', () => {
    let service: PPTXExportService
    let routerMock: any

    beforeEach(() => {
      service = new PPTXExportService()
      routerMock = {
        currentRoute: {
          value: {
            path: '/page-1',
            fullPath: '/page-1',
            meta: {
              title: '测试页面 1',
              speakerNotes: '本页测试备注',
            },
          },
        },
      } as unknown as Router
      service.setRouter(routerMock)

      // Mock packageWriter 写入流程
      const slideMock = {
        addNotes: vi.fn(),
        addImage: vi.fn(),
      }
      const pptxMock = {
        addSlide: vi.fn(() => slideMock),
      }
      ;(service as any).packageWriter = {
        createPresentation: vi.fn(() => pptxMock),
        resolveSlideLayout: () => ({ widthIn: 10, heightIn: 5.625 }),
        getShapeTypes: () => ({ rect: 'rect', roundRect: 'roundRect', ellipse: 'ellipse', line: 'line' }),
        writePresentationFile: vi.fn(async () => {}),
      }
    })

    it('rasterize-ready-page 策略下，原生 DOM 转换异常应降级为整页高清截图交付且保持页数备注完整', async () => {
      const page1Element = document.createElement('div')
      const page2Element = document.createElement('div')

      mockCollectAllExportPages.mockResolvedValue([
        { route: '/page-1', title: '第 1 页', order: 1, meta: { speakerNotes: '第一页演讲备注' } },
        { route: '/page-2', title: '第 2 页', order: 2, meta: { speakerNotes: '第二页演讲备注' } },
      ])
      mockPreparePage
        .mockResolvedValueOnce({ element: page1Element, cleanup: mockCleanupPage })
        .mockResolvedValueOnce({ element: page2Element, cleanup: mockCleanupPage })

      // 模拟第 1 页转换成功，第 2 页转换崩溃
      vi.spyOn((service as any).converter, 'extractSlideIR').mockImplementation(async (options: any) => {
        if (options.pageIndex === 2) {
          throw new Error('模拟组件语法或复杂子树崩溃')
        }
        return {
          ...createEmptySlideIR(options),
          report: {
          pageIndex: options.pageIndex,
          pageTitle: options.pageTitle,
          pageRoute: options.pageRoute,
          items: [
            {
              pageIndex: options.pageIndex,
              pageTitle: options.pageTitle,
              pageRoute: options.pageRoute,
              sourceType: 'title',
              result: 'editable-text',
              editable: true,
              label: '正常标题',
            },
          ],
        } }
      })

      // 模拟截图器
      const captureSpy = vi.spyOn(elementRasterizer, 'captureElementAsPng').mockResolvedValue('data:image/png;base64,full_page_screenshot')

      const options: PptxExportOptions = {
        mode: 'all',
        pageErrorStrategy: 'rasterize-ready-page',
        rasterScale: 2,
      }

      const result = await service.exportAllPages(options)

      // 验证交付成功，且总页数为 2
      expect(result.success).toBe(true)
      expect(result.pageCount).toBe(2)

      // 验证报告包含 2 页
      expect(result.report?.pages).toHaveLength(2)

      // 验证第 2 页被正确记录为整页截图降级
      const page2Report = result.report?.pages.find(p => p.pageIndex === 2)
      expect(page2Report).toBeDefined()
      expect(page2Report?.items[0].result).toBe('screenshot')
      expect(page2Report?.items[0].fallbackScope).toBe('page')
      expect(page2Report?.items[0].code).toBe('PAGE_CONVERSION_FALLBACK')

      // 验证截图器被调用进行全页截图
      expect(captureSpy).toHaveBeenCalledWith(page2Element, expect.objectContaining({ scale: 2 }))

      // 验证指标包含整页截图降级记录
      expect(result.report?.metrics?.rasterizedPageIndices).toContain(2)

      // 验证阶段耗时记录
      expect(result.report?.timings?.preparationTimeMs).toBeDefined()
      expect(result.report?.timings?.conversionTimeMs).toBeDefined()
      expect(result.report?.timings?.packagingTimeMs).toBeDefined()
      expect(result.report?.timings?.totalDurationMs).toBeGreaterThanOrEqual(0)
    })

    it('默认 fail-fast 策略下，页面转换异常应立即中止任务并抛错', async () => {
      mockCollectAllExportPages.mockResolvedValue([
        { route: '/page-1', title: '第 1 页', order: 1 },
      ])
      mockPreparePage.mockResolvedValue({ element: document.createElement('div'), cleanup: mockCleanupPage })

      vi.spyOn((service as any).converter, 'extractSlideIR').mockRejectedValue(new Error('转换器不可恢复错误'))

      const options: PptxExportOptions = {
        mode: 'all',
        pageErrorStrategy: 'fail-fast',
      }

      await expect(service.exportAllPages(options)).rejects.toThrow('转换器不可恢复错误')
    })

    it('任务取消优先：取消状态下即使配置了 rasterize-ready-page 也绝对不触发截图容错', async () => {
      mockCollectAllExportPages.mockResolvedValue([
        { route: '/page-1', title: '第 1 页', order: 1 },
      ])
      const captureSpy = vi.spyOn(elementRasterizer, 'captureElementAsPng')

      // 模拟在运行前已被用户取消
      vi.spyOn((service as any).taskRunner, 'isTaskCancelled').mockReturnValue(true)

      const options: PptxExportOptions = {
        mode: 'all',
        pageErrorStrategy: 'rasterize-ready-page',
      }

      await expect(service.exportAllPages(options)).rejects.toThrow('用户取消导出')
      expect(captureSpy).not.toHaveBeenCalled()
    })
  })
})
