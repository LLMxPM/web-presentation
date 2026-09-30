/**
 * 文件用途：验证 SaaS 预览入口的资源基址选择、内联 JSON 安全序列化，以及服务令牌换票恢复能力。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RuntimePreviewArtifactManifest, RuntimePreviewContext } from '../shared/runtime-preview'
import {
  buildPreviewTailwindStylesheetHref,
  collectPreviewTailwindSources,
} from '../tailwind/preview-tailwind'
import runtimeSaaSPreview, {
  assertManifestMatchesContext,
  buildPreviewHtml,
  resolvePreviewAssetBase,
  sendPreviewError,
  serializeForInlineScript,
} from './runtime-saas-preview'
import { isAllowedSnapdomProxyResourceUrl } from './runtime-snapdom-resource-proxy'

const joseMocks = vi.hoisted(() => ({
  createRemoteJWKSet: vi.fn(() => vi.fn()),
  jwtVerify: vi.fn(),
}))

vi.mock('jose', () => joseMocks)
vi.mock('../utils/runtime-logger', () => ({ logRuntimeServer: vi.fn(), isRuntimeAccessLogEnabled: () => false }))
vi.mock('./runtime-capacity', () => ({
  recordRuntimeWorkload: vi.fn(),
  registerRuntimeCapacityProvider: vi.fn(() => () => {}),
}))

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

  it('指纹门禁错误必须保留 409/PREVIEW_VERSION_SKEW，不得收成 500（M05 组合 F）', () => {
    const chunks: string[] = []
    const res = {
      statusCode: 0,
      setHeader: vi.fn(),
      end: (body: string) => {
        chunks.push(body)
      },
    } as unknown as Parameters<typeof sendPreviewError>[0]
    const skew = Object.assign(new Error('预览副本版本指纹不匹配'), {
      statusCode: 409,
      code: 'PREVIEW_VERSION_SKEW',
    })
    sendPreviewError(res, skew)
    expect(res.statusCode).toBe(409)
    expect(chunks.join('')).toContain('PREVIEW_VERSION_SKEW')
    expect(chunks.join('')).toContain('HTTP 409')
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

describe('runtime saas preview 服务令牌可恢复', () => {
  const fetchMock = vi.fn()
  const PREVIEW_TOKEN = 'preview-token-value'
  const SERVICE_TOKEN = 'service-token-value-should-not-leak'

  /** 构造通过验签的 PreviewContextToken 声明。 */
  function previewTokenPayload() {
    return {
      jti: 'preview-artifact-artifact-1-1',
      tenant_id: 'tenant_1',
      artifact_id: 'artifact-1',
      preview_kind: 'page',
      scope_type: 'project',
      workspace_id: '1',
      project_id: '2',
      entry_descriptor: { entry_type: 'module', module_path: 'src/views/Foo.vue' },
      asset_base_url: 'https://backend.example.com/assets/1',
      trace_id: 'req-1',
    }
  }

  /** 构造与上下文匹配的 artifact 清单。 */
  function matchingManifest(): RuntimePreviewArtifactManifest {
    return {
      artifact_id: 'artifact-1',
      tenant_id: 'tenant_1',
      preview_kind: 'page',
      owner_scope: { scope_type: 'project', workspace_id: '1', project_id: '2' },
      entry_descriptor: { entry_type: 'module', module_path: 'src/views/Foo.vue' },
      modules: { 'src/views/Foo.vue': { hash: 'entry-hash' } },
      assets: {},
    }
  }

  /** 构造插件实例。 */
  function createPlugin() {
    return runtimeSaaSPreview({
      jwksUrl: 'https://backend.example.com/.well-known/jwks.json',
      previewAudience: 'runtime-preview',
      backendApiBaseUrl: 'http://backend:8000',
    })
  }

  /** 以普通函数形式调用插件 load 钩子（测试内不依赖 Vite PluginContext）。 */
  function callLoad(plugin: ReturnType<typeof createPlugin>, id: string): Promise<string | null> {
    return (plugin.load as (moduleId: string) => Promise<string | null>).call({}, id)
  }

  /** 以普通函数形式调用插件 resolveId 钩子。 */
  function callResolveId(
    plugin: ReturnType<typeof createPlugin>,
    source: string,
    importer?: string,
  ): Promise<string | null> {
    return (plugin.resolveId as (src: string, imp?: string) => Promise<string | null>).call({}, source, importer)
  }

  /**
   * 按 URL 分发 Backend 内部接口的 fetch 替身：
   * 换票、manifest、模块源码各自返回稳定响应。
   */
  function mockBackendFetch(options: { exchangeStatus?: number; exchangeBody?: unknown } = {}) {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const target = String(url)
      if (target.includes('/internal/runtime/preview-service-token')) {
        if (options.exchangeStatus && options.exchangeStatus >= 400) {
          return new Response(
            JSON.stringify(options.exchangeBody || { code: 'PREVIEW_CONTEXT_INVALID', message: '预览上下文令牌非法或已过期。' }),
            { status: options.exchangeStatus, headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response(
          JSON.stringify({
            service_token: SERVICE_TOKEN,
            token_type: 'Bearer',
            expires_in: 300,
            artifact_id: 'artifact-1',
            scope: 'runtime-artifact-read',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (target.includes('/manifest')) {
        return new Response(JSON.stringify(matchingManifest()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (target.includes('/config-bundle')) {
        return new Response(JSON.stringify({ routes: { routes: [] }, theme: {}, styles: {} }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (target.includes('/modules')) {
        return new Response('<template><div>foo</div></template>', {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        })
      }
      return new Response('not found', { status: 404 })
    })
    return fetchMock
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', fetchMock)
    joseMocks.jwtVerify.mockResolvedValue({ payload: previewTokenPayload() })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('serviceTokenCache 未命中时仍应换票并加载远程模块', async () => {
    mockBackendFetch()
    const plugin = createPlugin()
    const moduleSource = await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value')

    expect(moduleSource).toBe('<template><div>foo</div></template>')
    // 必须发生换票：说明授权来自请求 + Backend，而非进程内缓存
    const exchangeCall = fetchMock.mock.calls.find(([url]) => String(url).includes('preview-service-token'))
    expect(exchangeCall).toBeTruthy()
    const exchangeBody = JSON.parse(String((exchangeCall![1] as RequestInit).body))
    expect(exchangeBody).toEqual({ preview_token: 'preview-token-value' })
    // 后续回源请求使用换得的服务令牌
    const manifestCall = fetchMock.mock.calls.find(([url]) => String(url).includes('manifest'))
    expect((manifestCall![1] as RequestInit).headers).toMatchObject({
      Authorization: `Bearer ${SERVICE_TOKEN}`,
    })
  })

  it('同副本缓存命中后不应重复换票', async () => {
    mockBackendFetch()
    const plugin = createPlugin()

    await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value')
    await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value')

    const exchangeCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('preview-service-token'))
    expect(exchangeCalls).toHaveLength(1)
  })

  it('过期 preview token 应被拒绝', async () => {
    joseMocks.jwtVerify.mockRejectedValue(Object.assign(new Error('JWT expired'), { name: 'JWTExpired' }))
    const plugin = createPlugin()

    await expect(
      callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=expired-token'),
    ).rejects.toMatchObject({
      statusCode: 401,
      code: 'PREVIEW_CONTEXT_INVALID',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('换票被 Backend 拒绝（过期 preview token）时模块加载失败且不缓存令牌', async () => {
    mockBackendFetch({ exchangeStatus: 401, exchangeBody: { code: 'PREVIEW_CONTEXT_INVALID', message: '预览上下文令牌非法或已过期。' } })
    const plugin = createPlugin()

    await expect(
      callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value'),
    ).rejects.toMatchObject({ statusCode: 401, code: 'PREVIEW_CONTEXT_INVALID' })
  })

  it('预览 HTML 不得包含 Runtime 服务令牌', async () => {
    mockBackendFetch()
    const plugin = createPlugin()
    const middlewares: Array<(req: unknown, res: unknown, next: () => void) => Promise<void> | void> = []
    const server = {
      middlewares: {
        use(handler: (req: unknown, res: unknown, next: () => void) => Promise<void> | void) {
          middlewares.push(handler)
        },
      },
    }
    const configureServer = plugin.configureServer
    if (typeof configureServer === 'function') {
      configureServer.call({} as never, server as never)
    }
    expect(middlewares).toHaveLength(1)

    const chunks: string[] = []
    const response = {
      statusCode: 0,
      headers: {} as Record<string, string>,
      setHeader(name: string, value: string) {
        this.headers[name.toLowerCase()] = value
        return this
      },
      end(chunk?: string) {
        if (chunk) chunks.push(chunk)
        return this
      },
    }
    const request = {
      method: 'GET',
      url: '/__preview',
      headers: {
        'x-runtime-preview-context': PREVIEW_TOKEN,
        'x-runtime-service-token': SERVICE_TOKEN,
      },
    }

    await middlewares[0](request, response, vi.fn())

    const html = chunks.join('')
    expect(response.statusCode).toBe(200)
    expect(html).toContain('__RUNTIME_PREVIEW_TOKEN__')
    expect(html).toContain('preview-token-value')
    // 浏览器只获得最小权限预览票据，绝不出现服务级令牌
    expect(html).not.toContain(SERVICE_TOKEN)
    expect(html).not.toContain('service-token-value-should-not-leak')
  })

  it('Vue SFC 子请求丢失 ctx 时 resolveId 应回填预览令牌', async () => {
    const plugin = createPlugin()
    const resolved = await callResolveId(
      plugin,
      '/@runtime-preview/artifact-1/src/views/Foo.vue?vue&type=style&index=0&lang.css',
      '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value',
    )

    expect(resolved).toBe(
      '/@runtime-preview/artifact-1/src/views/Foo.vue?vue&type=style&index=0&lang.css&ctx=preview-token-value',
    )
    // 回填后的子请求不依赖进程内 previewTokenCache 也能解析出 ctx
    expect(String(resolved)).toContain('ctx=preview-token-value')
    expect(String(resolved)).toContain('vue&type=style')
  })

  it('无 ctx 的模块请求不得回退到进程内 previewToken 缓存（C3）', async () => {
    mockBackendFetch()
    const plugin = createPlugin()
    // 先用合法请求把票据写入进程内缓存（模拟他人/先前请求留下的缓存条目）
    await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value')

    // 同一 artifact、同一模块、不带 ctx：必须 401，绝不能用缓存票据冒充鉴权
    await expect(
      callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue'),
    ).rejects.toMatchObject({ statusCode: 401, code: 'PREVIEW_CONTEXT_REQUIRED' })

    // resolveId 同样不得从缓存回填无 importer 票据的模块 ID
    const resolvedWithoutImporter = await callResolveId(
      plugin,
      '/@runtime-preview/artifact-1/src/views/Bar.vue',
    )
    expect(String(resolvedWithoutImporter || '')).not.toContain('ctx=')
  })

  it('artifact 失效（Backend 404）后不得再命中旧缓存', async () => {
    let manifestFetchCount = 0
    let moduleGone = false
    fetchMock.mockImplementation(async (url: string) => {
      const target = String(url)
      if (target.includes('/internal/runtime/preview-service-token')) {
        return new Response(
          JSON.stringify({
            service_token: SERVICE_TOKEN,
            token_type: 'Bearer',
            expires_in: 300,
            artifact_id: 'artifact-1',
            scope: 'runtime-artifact-read',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (target.includes('/manifest')) {
        manifestFetchCount += 1
        return new Response(JSON.stringify(matchingManifest()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (target.includes('/modules')) {
        if (moduleGone) {
          return new Response(
            JSON.stringify({ code: 'ARTIFACT_NOT_FOUND', message: 'preview artifact 不存在。' }),
            { status: 404, headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response('<template><div>foo</div></template>', {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        })
      }
      return new Response('not found', { status: 404 })
    })

    const plugin = createPlugin()
    const moduleId = '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value'

    // 第一次加载成功，manifest 进入缓存
    await callLoad(plugin, moduleId)
    expect(manifestFetchCount).toBe(1)

    // 同副本缓存命中，不再回源 manifest
    await callLoad(plugin, moduleId)
    expect(manifestFetchCount).toBe(1)

    // artifact 失效：模块回源 404，应清理对应缓存条目
    moduleGone = true
    await expect(callLoad(plugin, moduleId)).rejects.toMatchObject({ statusCode: 404 })
    moduleGone = false

    // 失效后不得继续命中旧 manifest 缓存，必须重新回源
    await callLoad(plugin, moduleId)
    expect(manifestFetchCount).toBe(2)
  })

  it('换票不产生新的计算缓存身份：token 轮换后仍命中同一缓存条目', async () => {
    const manifestFetchCount = { value: 0 }
    fetchMock.mockImplementation(async (url: string) => {
      const target = String(url)
      if (target.includes('/internal/runtime/preview-service-token')) {
        return new Response(
          JSON.stringify({
            service_token: SERVICE_TOKEN,
            token_type: 'Bearer',
            expires_in: 300,
            artifact_id: 'artifact-1',
            scope: 'runtime-artifact-read',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (target.includes('/manifest')) {
        manifestFetchCount.value += 1
        return new Response(JSON.stringify(matchingManifest()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (target.includes('/modules')) {
        return new Response('<template><div>foo</div></template>', {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        })
      }
      return new Response('not found', { status: 404 })
    })

    const plugin = createPlugin()
    // 同一 artifact、同一内容，但 ctx 预览令牌轮换
    await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-value')
    await callLoad(plugin, '/@runtime-preview/artifact-1/src/views/Foo.vue?ctx=preview-token-rotated')

    // 计算缓存身份是 artifact + 内容，不含 token：换票后命中同一 manifest 缓存
    expect(manifestFetchCount.value).toBe(1)
  })
})
