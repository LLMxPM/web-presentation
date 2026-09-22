/**
 * 文件用途：验证运行时配置注入、预加载配置优先级与资源路径解析逻辑。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildConfigUrl,
  getRuntimeConfigContext,
  resolveResourcePath,
  setRuntimeConfigContext,
  setRuntimePreloadedConfig,
  setRuntimePreviewContext,
  setRuntimePreviewToken,
  shouldNavigateToPreviewEntryPath,
} from './path'

beforeEach(() => {
  vi.stubGlobal('window', {})
})

afterEach(() => {
  setRuntimeConfigContext(undefined)
  setRuntimePreviewContext(undefined)
  setRuntimePreviewToken(undefined)
  setRuntimePreloadedConfig(undefined)
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('runtime path helpers', () => {
  it('应优先使用 window 注入的项目配置根地址', () => {
    setRuntimeConfigContext({
      projectId: 18,
      projectConfigBaseUrl: 'https://window.example/projects/18/configs/'
    })

    expect(getRuntimeConfigContext()?.projectId).toBe(18)
    expect(buildConfigUrl('app')).toBe('https://window.example/projects/18/configs/app.config.yaml')
  })

  it('未注入配置根地址时应回退到本地相对路径', () => {
    expect(buildConfigUrl('themes')).toBe('./config/themes.config.yaml')
  })

  it('已有显式 hash 路由时不应再覆盖到预览入口', () => {
    expect(shouldNavigateToPreviewEntryPath('/cover', '#/__presenter-display?channel=demo&route=%2Fcover')).toBe(false)
    expect(shouldNavigateToPreviewEntryPath('/cover', '#/__presenter?channel=demo&route=%2Fcover')).toBe(false)
    expect(shouldNavigateToPreviewEntryPath('/cover', '#/chapter')).toBe(false)
  })

  it('缺少显式 hash 路由时应导航到预览入口', () => {
    expect(shouldNavigateToPreviewEntryPath('/cover', '')).toBe(true)
    expect(shouldNavigateToPreviewEntryPath('/cover', '#')).toBe(true)
    expect(shouldNavigateToPreviewEntryPath('/cover', '#/')).toBe(true)
    expect(shouldNavigateToPreviewEntryPath('', '')).toBe(false)
  })

  it('应优先使用 manifest 资源映射解析资源路径', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_1',
      tenantId: 'tenant_1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_1',
      projectId: 'project_1',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://assets.example/releases/release_1',
      traceId: 'trace_1',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_1',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_1',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/releases/release_1',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_1',
          workspace_id: 'workspace_1',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_1',
        modules: {},
        assets: {
          'img/logo/ppt-e.png': 'hashed/logo-a1b2c3.png'
        }
      }
    })

    expect(resolveResourcePath('img/logo/ppt-e.png')).toBe('https://assets.example/releases/release_1/hashed/logo-a1b2c3.png')
  })

  it('页面可视化编辑 artifact 应沿用预览资源回源策略', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_visual_edit',
      tenantId: 'tenant_1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: 'workspace_1',
      projectId: 'project_1',
      entryDescriptor: { entry_type: 'module', module_path: 'src/views/PGdemo.vue' },
      assetBaseUrl: 'https://assets.example/visual-edit',
      traceId: 'trace_visual_edit',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_visual_edit',
        artifact_kind: 'page_visual_edit_preview',
        tenant_id: 'tenant_1',
        preview_kind: 'page',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_1',
          workspace_id: 'workspace_1',
        },
        entry_descriptor: { entry_type: 'module', module_path: 'src/views/PGdemo.vue' },
        modules: {},
        assets: {
          'img/hero.png': 'hashed/hero-visual-edit.png',
        },
      },
    })

    expect(resolveResourcePath('img/hero.png')).toBe(
      'https://assets.example/visual-edit/hashed/hero-visual-edit.png',
    )
  })

  it('manifest key 大小写不一致时不应命中映射，而是按原路径回退', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_case',
      tenantId: 'tenant_case',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_case',
      projectId: 'project_case',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://assets.example/releases/release_case',
      traceId: 'trace_case',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_case',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_case',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/releases/release_case',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_case',
          workspace_id: 'workspace_case',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_case',
        modules: {},
        assets: {
          'top.svg': 'hashed/top-a1b2c3.svg'
        }
      }
    })

    expect(resolveResourcePath('Top.svg')).toBe('./Top.svg')
  })

  it('manifest key 带目录前缀时不应支持 basename 兜底匹配', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_basename',
      tenantId: 'tenant_basename',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_basename',
      projectId: 'project_basename',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://assets.example/releases/release_basename',
      traceId: 'trace_basename',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_basename',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_basename',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/releases/release_basename',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_basename',
          workspace_id: 'workspace_basename',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_basename',
        modules: {},
        assets: {
          'icons/Top.svg': 'hashed/top-z9y8x7.svg'
        }
      }
    })

    expect(resolveResourcePath('Top.svg')).toBe('./Top.svg')
  })

  it('preview artifact 未命中 manifest 时应回退到本地相对路径', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_2',
      tenantId: 'tenant_2',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_2',
      projectId: 'project_2',
      entryDescriptor: { entry_type: 'route', route: '/overview' },
      assetBaseUrl: 'https://assets.example/releases/release_2/',
      traceId: 'trace_2',
    })

    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_2',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_2',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/releases/release_2/',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_2',
          workspace_id: 'workspace_2',
        },
        entry_descriptor: { entry_type: 'route', route: '/overview' },
        project_id: 'project_2',
        modules: {},
        assets: {},
      }
    })

    expect(resolveResourcePath('./fonts/demo.woff2')).toBe('./fonts/demo.woff2')
  })

  it('应保留 data 与 blob 资源地址，供内建组件安全示例直连使用', () => {
    const dataUrl = 'data:text/plain,hello'
    const blobUrl = 'blob:https://runtime.example/asset-1'

    expect(resolveResourcePath(dataUrl)).toBe(dataUrl)
    expect(resolveResourcePath(blobUrl)).toBe(blobUrl)
  })

  it('build_release 模式应解析为产物内 __build_assets 相对路径', () => {
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_build_release',
        artifact_kind: 'build_release',
        tenant_id: 'tenant_release',
        preview_kind: 'project',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_release',
          workspace_id: 'workspace_release',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_release',
        modules: {},
        assets: {
          'img/logo/ppt-e.png': '__build_assets/logo-a1b2c3.png'
        }
      }
    })

    expect(resolveResourcePath('img/logo/ppt-e.png')).toBe('./__build_assets/logo-a1b2c3.png')
  })
})
