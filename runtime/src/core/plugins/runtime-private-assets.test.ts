/** 文件功能：回归预览素材 token、导出资源身份转换及构建凭据只发送给 Backend 内网。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createBuildBackendClient } from './runtime-build-runner'
import {
  buildSnapdomProxyFetchHeaders,
  isAllowedSnapdomProxyResourceUrl,
  resolveSnapdomProxySourceUrl,
} from './runtime-snapdom-resource-proxy'
import type { RuntimePreviewArtifactManifest, RuntimePreviewContext } from '../shared/runtime-preview'

const base = 'https://files.example/preview/artifacts/rt_1/assets'
const manifest: RuntimePreviewArtifactManifest = {
  artifact_id: 'rt_1', tenant_id: 'tenant_1', preview_kind: 'page',
  owner_scope: { scope_type: 'project', workspace_id: '1', project_id: '2' },
  entry_descriptor: { entry_type: 'route', route: '/home' }, modules: {},
  assets: { logo: 'hash1' }, asset_base_url: base,
}
const context: RuntimePreviewContext = {
  artifactId: 'rt_1', tenantId: 'tenant_1', previewKind: 'page', scopeType: 'project',
  workspaceId: '1', projectId: '2', entryDescriptor: manifest.entry_descriptor,
  assetBaseUrl: base, traceId: 'review',
}

afterEach(() => vi.unstubAllGlobals())

describe('private resource delivery', () => {
  it('导出允许带浏览器 token 的同一资源身份，仍拒绝其它 artifact 与额外查询变体', () => {
    expect(isAllowedSnapdomProxyResourceUrl(`${base}/hash1?token=P`, manifest, context)).toBe(true)
    expect(isAllowedSnapdomProxyResourceUrl(`${base}/hash1?token=P&other=1`, manifest, context)).toBe(false)
    expect(isAllowedSnapdomProxyResourceUrl(base.replace('rt_1', 'rt_2') + '/hash1?token=P', manifest, context)).toBe(false)
    const url = resolveSnapdomProxySourceUrl(`${base}/hash1?token=P`, manifest, context, 'http://backend:8000')
    expect(url).toBe('http://backend:8000/internal/runtime/preview-artifacts/rt_1/assets/hash1')
    expect(buildSnapdomProxyFetchHeaders(`${base}/hash1?token=P`, 'S', 'P', manifest, context).Authorization).toBe('Bearer S')
    expect(buildSnapdomProxyFetchHeaders('https://external.example/hash1', 'S', 'P', manifest, context).Authorization).toBeUndefined()
  })

  it('构建和诊断只向配置的内部 Backend 发送 S，不跟随重定向泄露身份', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3])))
    vi.stubGlobal('fetch', fetch)
    const client = createBuildBackendClient({ backendApiBaseUrl: 'http://backend:8000', serviceToken: 'S' })
    expect(await client.fetchAssetBinary(`${base}/hash1?token=P`)).toEqual(Buffer.from([1, 2, 3]))
    expect(fetch).toHaveBeenCalledWith('http://backend:8000/internal/runtime/preview-artifacts/rt_1/assets/hash1', expect.objectContaining({
      headers: { Authorization: 'Bearer S', Accept: '*/*' }, redirect: 'error',
    }))
    await expect(client.fetchAssetBinary('https://external.example/arbitrary')).rejects.toMatchObject({ code: 'BUILD_ASSET_URL_INVALID' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
