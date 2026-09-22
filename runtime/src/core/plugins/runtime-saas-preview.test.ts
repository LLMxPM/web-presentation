/**
 * 文件用途：验证 SaaS 预览入口的资源基址选择与内联 JSON 安全序列化逻辑。
 */

import { describe, expect, it } from 'vitest'

import type { RuntimePreviewArtifactManifest, RuntimePreviewContext } from '../shared/runtime-preview'
import {
  buildPreviewTailwindStylesheetHref,
  collectPreviewTailwindSources,
} from '../tailwind/preview-tailwind'
import {
  assertManifestMatchesContext,
  buildPreviewHtml,
  resolvePreviewAssetBase,
  serializeForInlineScript,
} from './runtime-saas-preview'
import { isAllowedSnapdomProxyResourceUrl } from './runtime-snapdom-resource-proxy'

describe('runtime saas preview helpers', () => {
  it('应优先使用 Backend 透传的浏览器可访问 Runtime 地址', () => {
    expect(resolvePreviewAssetBase('https://runtime.example.com/', 'http://127.0.0.1:7373')).toBe(
      'https://runtime.example.com',
    )
    expect(resolvePreviewAssetBase('', 'http://127.0.0.1:7373/')).toBe('http://127.0.0.1:7373')
  })

  it('应对内联 script 中的 JSON 做安全转义', () => {
    const serialized = serializeForInlineScript({
      title: '</script><script>alert(1)</script>',
      body: 'A&B',
    })

    expect(serialized).toContain('\\u003C/script\\u003E')
    expect(serialized).toContain('\\u0026')
    expect(serialized).not.toContain('</script>')
  })

  it('预览 HTML 应注入 artifact Tailwind CSS 链接并放在应用入口前', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-1',
      tenantId: 'tenant_1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'module', module_path: 'src/views/CoverPage.vue' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-1',
    }
    const html = buildPreviewHtml({
      assetBase: 'https://runtime.example.com',
      publicContext: context,
      previewToken: 'preview-token',
      configBundle: {},
    })
    const href = buildPreviewTailwindStylesheetHref({
      assetBase: 'https://runtime.example.com',
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
    })

    expect(html).toContain(`rel="stylesheet" href="${href}"`)
    expect(html).toContain('window.__RUNTIME_PUBLIC_BASE_URL__ = "https://runtime.example.com";')
    expect(html.indexOf(href)).toBeGreaterThan(html.indexOf('/@vite/client'))
    expect(html.indexOf(href)).toBeLessThan(html.indexOf('/src/main.ts'))
  })

  it('整项目预览 HTML 应沿用 Runtime 公开基址加载 Vite 模块', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-project',
      tenantId: 'tenant_1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-project',
    }

    const html = buildPreviewHtml({
      assetBase: 'https://presentation.example.com/runtime',
      publicContext: context,
      previewToken: 'preview-token',
      configBundle: {},
    })

    expect(html).toContain('src="https://presentation.example.com/runtime/@vite/client"')
    expect(html).toContain('src="https://presentation.example.com/runtime/src/main.ts"')
    expect(html).toContain('href="https://presentation.example.com/runtime/__preview-tailwind.css')
  })

  it('应抓取 manifest 模块和未入 manifest 的独立入口模块用于 Tailwind 编译', async () => {
    const fetchedPaths: string[] = []
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-1',
      tenant_id: 'tenant_1',
      preview_kind: 'page',
      owner_scope: {
        scope_type: 'project',
        workspace_id: '1',
        project_id: '2',
      },
      entry_descriptor: { entry_type: 'module', module_path: 'src/views/CoverPage.vue' },
      modules: {
        'src/workspace-components/cmp_cover/v/1.vue': { hash: 'component-hash' },
      },
      assets: {},
    }

    const sources = await collectPreviewTailwindSources({
      artifactId: 'artifact-1',
      manifest,
      entryDescriptor: manifest.entry_descriptor,
      backendClient: {
        async fetchModuleSource(_artifactId, modulePath) {
          fetchedPaths.push(modulePath)
          return `<template><div class="pt-16 ${modulePath.includes('CoverPage') ? 'bg-cover' : 'text-invert'}"></div></template>`
        },
      },
    })

    expect(fetchedPaths).toEqual([
      'src/workspace-components/cmp_cover/v/1.vue',
      'src/views/CoverPage.vue',
    ])
    expect(sources.map(source => source.logicalPath)).toEqual(fetchedPaths)
    expect(sources[0].contentHash).toBe('component-hash')
    expect(sources[1].contentHash).toBeTruthy()
  })

  it('应允许 Runtime Kit 组件预览上下文不携带工作空间组件版本号', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-runtime-kit',
      tenantId: 'tenant_1',
      previewKind: 'component',
      scopeType: 'runtime_kit_component',
      workspaceId: '1',
      entryDescriptor: { entry_type: 'component_host' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-runtime-kit',
      componentPreviewMode: 'saved',
      componentSource: 'runtime_kit',
      runtimeKitComponentName: 'Icon.v1',
      runtimeKitManifestVersion: '1.0.0',
    }
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-runtime-kit',
      tenant_id: 'tenant_1',
      preview_kind: 'component',
      owner_scope: {
        scope_type: 'runtime_kit_component',
        workspace_id: '1',
        runtime_kit_component_name: 'Icon.v1',
        runtime_kit_manifest_version: '1.0.0',
      },
      entry_descriptor: { entry_type: 'component_host' },
      modules: {},
      assets: {},
    }

    expect(() => assertManifestMatchesContext(manifest, context)).not.toThrow()
  })

  it('应拒绝 Runtime Kit 组件预览的错误 scope 或组件声明', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-runtime-kit',
      tenantId: 'tenant_1',
      previewKind: 'component',
      scopeType: 'runtime_kit_component',
      workspaceId: '1',
      entryDescriptor: { entry_type: 'component_host' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-runtime-kit',
      componentPreviewMode: 'saved',
      componentSource: 'runtime_kit',
      runtimeKitComponentName: 'Icon.v1',
      runtimeKitManifestVersion: '1.0.0',
    }
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-runtime-kit',
      tenant_id: 'tenant_1',
      preview_kind: 'component',
      owner_scope: {
        scope_type: 'workspace_component',
        workspace_id: '1',
        runtime_kit_component_name: 'Icon.v1',
        runtime_kit_manifest_version: '1.0.0',
      },
      entry_descriptor: { entry_type: 'component_host' },
      modules: {},
      assets: {},
    }

    expect(() => assertManifestMatchesContext(manifest, context)).toThrow('预览清单与预览上下文不一致')

    expect(() => assertManifestMatchesContext({
      ...manifest,
      owner_scope: {
        ...manifest.owner_scope,
        scope_type: 'runtime_kit_component',
        runtime_kit_component_name: 'DefaultContentPage',
      },
    }, context)).toThrow('Runtime Kit 组件能力声明不一致')
  })

  it('应校验资源预览上下文的 asset_id', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-asset',
      tenantId: 'tenant_1',
      previewKind: 'asset',
      scopeType: 'workspace_asset',
      workspaceId: '1',
      entryDescriptor: { entry_type: 'asset_host' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-asset',
      assetId: '42',
    }
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-asset',
      tenant_id: 'tenant_1',
      preview_kind: 'asset',
      owner_scope: {
        scope_type: 'workspace_asset',
        workspace_id: '1',
        asset_id: '42',
      },
      entry_descriptor: { entry_type: 'asset_host' },
      modules: {},
      assets: {},
    }

    expect(() => assertManifestMatchesContext(manifest, context)).not.toThrow()
    expect(() => assertManifestMatchesContext({
      ...manifest,
      owner_scope: {
        ...manifest.owner_scope,
        asset_id: '43',
      },
    }, context)).toThrow('资源预览 asset_id 不一致')
  })

  it('截图资源代理只允许当前 artifact manifest 声明的资源 URL', () => {
    const context: RuntimePreviewContext = {
      artifactId: 'artifact-assets',
      tenantId: 'tenant_1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: '1',
      projectId: '2',
      entryDescriptor: { entry_type: 'route', route: '/cover' },
      assetBaseUrl: 'https://backend.example.com/assets/1',
      traceId: 'req-assets',
    }
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-assets',
      tenant_id: 'tenant_1',
      preview_kind: 'page',
      owner_scope: {
        scope_type: 'project',
        workspace_id: '1',
        project_id: '2',
      },
      entry_descriptor: context.entryDescriptor,
      asset_base_url: 'https://backend.example.com/assets/1',
      modules: {},
      assets: {
        hero: 'hash hero.png',
        remoteLogo: 'https://cdn.example.com/logo.png',
      },
      asset_metadata: {
        hero: {
          file_hash: 'hash hero.png',
          render_type: 'image',
        },
      },
    }

    expect(isAllowedSnapdomProxyResourceUrl(
      'https://backend.example.com/assets/1/hash%20hero.png',
      manifest,
      context,
    )).toBe(true)
    expect(isAllowedSnapdomProxyResourceUrl(
      'https://cdn.example.com/logo.png',
      manifest,
      context,
    )).toBe(true)
    expect(isAllowedSnapdomProxyResourceUrl(
      'https://backend.example.com/assets/1/not-in-manifest.png',
      manifest,
      context,
    )).toBe(false)
    expect(isAllowedSnapdomProxyResourceUrl(
      'https://evil.example.com/logo.png',
      manifest,
      context,
    )).toBe(false)
  })
})
