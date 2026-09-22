// @vitest-environment jsdom

/**
 * 文件用途：为项目中 core 模块的统一对外接口构建单元测试。
 * 验证对外部导出的各个功能模块是否正确且可用。
 */

import { describe, expect, it, vi, beforeAll } from 'vitest'

describe('Core 模块对外接口 (External API)', () => {
  let CoreAPI: typeof import('./index')

  beforeAll(async () => {
    // 模拟全局 fetch，防止模块级初始化的路由器和配置加载由于无效的相对路径报错
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('')
    }))

    // 动态导入以确保在 mock 之后再执行模块顶层代码
    CoreAPI = await import('./index')
  }, 30_000)

  it('应正确导出组合式 API (Composables)', () => {
    expect(CoreAPI.useTheme).toBeTypeOf('function')
  })

  it('应正确导出配置管理相关方法与对象 (Config)', () => {
    expect(CoreAPI.initializeConfig).toBeTypeOf('function')
    expect(CoreAPI.reloadAllConfigs).toBeTypeOf('function')
    expect(CoreAPI.appConfig).toBeDefined()
    expect(CoreAPI.routeConfigs).toBeDefined()
    expect(CoreAPI.iconConfig).toBeDefined()
  })

  it('应正确导出核心功能服务实例 (Services)', () => {
    // 验证 pdfExportService
    expect(CoreAPI.pdfExportService).toBeDefined()
    expect(CoreAPI.pdfExportService.exportCurrentPage).toBeTypeOf('function')
    expect(CoreAPI.pdfExportService.exportAllPages).toBeTypeOf('function')

    // 验证 browserPrintService
    expect(CoreAPI.browserPrintService).toBeDefined()
    expect(CoreAPI.browserPrintService.printCurrentPage).toBeTypeOf('function')
    expect(CoreAPI.browserPrintService.printAllPages).toBeTypeOf('function')

    // 验证 pageCaptureService
    expect(CoreAPI.pageCaptureService).toBeDefined()
    expect(CoreAPI.pageCaptureService.captureElement).toBeTypeOf('function')
    expect(CoreAPI.pageCaptureService.captureCurrentPage).toBeTypeOf('function')
  })

  it('应正确导出图标系统相关方法与注册表 (Icon)', () => {
    expect(CoreAPI.iconRegistry).toBeDefined()
    expect(CoreAPI.getIcon).toBeTypeOf('function')
    expect(CoreAPI.hasIcon).toBeTypeOf('function')
  })

  it('应正确导出事件总线 (EventBus)', () => {
    expect(CoreAPI.eventBus).toBeDefined()
    expect(CoreAPI.eventBus.on).toBeTypeOf('function')
    expect(CoreAPI.eventBus.emit).toBeTypeOf('function')
  })

  it('应正确导出路由相关功能 (Router)', () => {
    // createAppRouter 在 router/index.ts 中执行并默认导出其返回结果（异步包装产生 Promise）
    expect(CoreAPI.createAppRouter).toBeInstanceOf(Promise)
  })

  it('应通过 Utils 命名空间暴露工具库', () => {
    expect(CoreAPI.Utils).toBeDefined()
    expect(CoreAPI.Utils).toBeTypeOf('object')
  })
})
