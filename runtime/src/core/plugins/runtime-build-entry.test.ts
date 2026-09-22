/**
 * 文件用途：验证 Runtime backend build 入口脚本与 index.html 的生成逻辑。
 */

import { describe, expect, it } from 'vitest'
import type { RuntimePreloadedConfigBundle } from '../shared/runtime-preview'

import {
  createBuildEntrySource,
  createBuildIndexHtmlSource,
  createDiagnosticsBuildEntrySource,
} from './runtime-build-entry'

const MOCK_PRELOADED_CONFIG: RuntimePreloadedConfigBundle = {
  app: { app: { title: '示例应用' } },
  routes: { routes: [{ route: 'cover', component: '@/views/Cover.vue' }] },
}

describe('runtime build entry', () => {
  it('应先注入预加载配置，再通过动态导入启动构建态主入口', () => {
    const entrySource = createBuildEntrySource(MOCK_PRELOADED_CONFIG)

    expect(entrySource).toContain("window.__RUNTIME_PRELOADED_CONFIG__ = ")
    expect(entrySource).toContain("void import('./build-release-main').catch((error) => {")
    expect(entrySource.indexOf('window.__RUNTIME_PRELOADED_CONFIG__ = ')).toBeLessThan(
      entrySource.indexOf("void import('./build-release-main').catch((error) => {"),
    )
    expect(entrySource).not.toContain("import './main'")
  })

  it('应生成指向构建态入口脚本的 index.html', () => {
    const htmlSource = createBuildIndexHtmlSource()

    expect(htmlSource).toContain('<script type="module" src="/src/__build_entry__.ts"></script>')
    expect(htmlSource).toContain('<div id="app"></div>')
  })

  it('应生成不拉起完整 Runtime Shell 的诊断态轻量入口', () => {
    const entrySource = createDiagnosticsBuildEntrySource(MOCK_PRELOADED_CONFIG)

    expect(entrySource).toContain("window.__RUNTIME_PRELOADED_CONFIG__ = ")
    expect(entrySource).toContain('BUILD_RELEASE_VIEW_MODULES')
    expect(entrySource).toContain('BUILD_DIAGNOSTICS_MODULE_LOADERS')
    expect(entrySource).toContain("import './styles/global.css'")
    expect(entrySource).not.toContain('build-release-main')
    expect(entrySource).not.toContain('ResponsiveLayout')
    expect(entrySource).not.toContain('PDFExportService')
    expect(entrySource).not.toContain('PageCaptureService')
  })
})
