/** 文件功能：通过真实 Vite resolver 验证远程页面 Kit 门禁、alias 还原与冷副本快照恢复。 */
// @vitest-environment node
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import manifest from '../../runtime-kit/manifest/runtime-kit.manifest.json'
import { buildRemoteModuleId, type RuntimeModuleResolverConfig } from '../shared/runtime-preview'
import runtimeSaaSPreview from './runtime-saas-preview'

const auth = vi.hoisted(() => ({ jwtVerify: vi.fn() }))
vi.mock('jose', () => ({ createRemoteJWKSet: vi.fn(() => vi.fn()), jwtVerify: auth.jwtVerify }))

const icon = '@runtime-kit/public/components/primitives/Icon.v1.vue'
const privatePath = 'internal/renderers/model3d/motion/sha256-bytes'
const root = process.cwd()
const importer = buildRemoteModuleId('kit-probe', 'src/views/Page.vue', 'current-token')
let server: ViteDevServer | undefined
let resolver: RuntimeModuleResolverConfig
const fetchMock = vi.fn()

/** 固定签名声明只替代 JWT 与 Backend 网络，保留真实插件、缓存和 Vite 解析顺序。 */
function payload() {
  return {
    exp: Math.floor(Date.now() / 1000) + 300, jti: 'kit-probe-jti', tenant_id: 'tenant-1',
    artifact_id: 'kit-probe', preview_kind: 'page', scope_type: 'project', workspace_id: '1', project_id: '2',
    entry_descriptor: { entry_type: 'module', module_path: 'src/views/Page.vue' },
    asset_base_url: 'https://preview.example/assets', trace_id: 'kit-probe-trace',
  }
}

/** 创建不监听端口的真实 Vite 服务，使用与产品一致的 Kit 和 @ alias。 */
async function resolveImport(source: string, from = importer) {
  server ||= await createServer({
    configFile: false, root, logLevel: 'silent',
    plugins: [runtimeSaaSPreview({ jwksUrl: 'https://backend.example/jwks', backendApiBaseUrl: 'https://backend.example' })],
    resolve: { alias: { '@runtime-kit': resolve(root, 'src/runtime-kit'), '@': resolve(root, 'src') } },
    server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true },
  })
  return server.environments.client.pluginContainer.resolveId(source, from)
}

beforeEach(() => {
  resolver = { runtime_kit_manifest_version: manifest.version, runtime_kit_exports: manifest.exports.filter(item => item.import_path === icon) }
  auth.jwtVerify.mockReset().mockResolvedValue({ payload: payload() })
  fetchMock.mockReset().mockImplementation(async (url: string) => {
    let body: unknown
    if (String(url).endsWith('/preview-service-token')) {
      body = { service_token: 'service-token', expires_in: 300, artifact_id: 'kit-probe' }
    } else if (String(url).endsWith('/config-bundle')) {
      body = { module_resolver: resolver }
    } else if (String(url).endsWith('/manifest')) {
      const claims = payload()
      body = {
        artifact_id: claims.artifact_id, tenant_id: claims.tenant_id, preview_kind: claims.preview_kind,
        owner_scope: { scope_type: 'project', workspace_id: '1', project_id: '2' },
        entry_descriptor: claims.entry_descriptor, modules: { 'src/views/Page.vue': 'hash' }, assets: {},
      }
    } else throw new Error(`未预期的 Backend 请求：${url}`)
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(async () => {
  await server?.close()
  server = undefined
  vi.unstubAllGlobals()
})

describe('真实 Vite 远程预览 Kit 导入', () => {
  it('没有先访问 HTML 的冷副本也能恢复快照，放行合法的公开入口', async () => {
    await expect(resolveImport(icon)).resolves.toMatchObject({ id: expect.stringContaining('/runtime-kit/public/components/primitives/Icon.v1.vue') })
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/config-bundle'))).toBe(true)
  })

  it.each([
    `@runtime-kit/${privatePath}`,
    `@/runtime-kit/${privatePath}`,
    `../runtime-kit/${privatePath}`,
    resolve(root, 'src/runtime-kit', privatePath),
    '@runtime-kit/public/components/primitives/Icon.vue',
    '@runtime-kit/public/components/assets/AssetImage.v1.vue',
    '@runtime-kit/../core/utils/colorResolver',
    '@/core/utils/colorResolver',
  ])('拒绝原始、相对或 alias 展开后的未授权入口：%s', async source => {
    await expect(resolveImport(source)).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
  })

  it('Backend 显式空快照不能回退成本地全部能力', async () => {
    resolver.runtime_kit_exports = []
    await expect(resolveImport(icon)).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
  })

  it('真实预览链路拒绝 Backend 声明的不匹配清单版本', async () => {
    resolver.runtime_kit_manifest_version = 'other-version'
    await expect(resolveImport(icon)).rejects.toThrow('manifest 版本不匹配')
  })

  it('门禁缓存命中也不能用旧票据替代本次请求验签', async () => {
    await resolveImport(icon)
    auth.jwtVerify.mockRejectedValueOnce(new Error('invalid current token'))
    await expect(resolveImport(icon, buildRemoteModuleId('kit-probe', 'src/views/Other.vue', 'invalid-token')))
      .rejects.toMatchObject({ statusCode: 401 })
  })

  it('Runtime 自身仍可依赖内部实现，不触发用户源码门禁', async () => {
    await expect(resolveImport(`@runtime-kit/${privatePath}`, resolve(root, 'src/core/trusted.ts')))
      .resolves.toMatchObject({ id: expect.stringContaining('sha256-bytes.ts') })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
