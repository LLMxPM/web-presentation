/**
 * 文件用途：验证预览链路 Runtime 服务令牌的换票恢复、缓存加速与脱敏行为。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildPreviewCacheKey,
  PreviewBoundedCache,
  PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN,
} from './runtime-preview-cache'
import {
  PreviewServiceTokenError,
  readFreshCacheEntry,
  readJwtExpiresAtMs,
  redactJwtForLog,
  resolveRuntimeServiceToken,
  type ServiceTokenCache,
  type ServiceTokenCacheEntry,
} from './runtime-preview-service-token'

/** 构造带 exp 声明的测试用 JWT 形态字符串（不参与签名校验）。 */
function buildFakeJwt(expiresAtSeconds: number): string {
  const payload = Buffer.from(JSON.stringify({ exp: expiresAtSeconds }), 'utf8').toString('base64url')
  return `eyJhbGciOiJub25lIn0.${payload}.signature`
}

/** 构造 Backend 换票成功响应。 */
function exchangeOkResponse(serviceToken: string, expiresIn: number, artifactId: string): Response {
  return new Response(
    JSON.stringify({
      service_token: serviceToken,
      token_type: 'Bearer',
      expires_in: expiresIn,
      artifact_id: artifactId,
      scope: 'runtime-artifact-read',
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

/** 构造测试用服务令牌缓存，并按稳定内容身份键预置条目。 */
function createServiceTokenCache(
  entries: Array<[string, ServiceTokenCacheEntry]> = [],
): ServiceTokenCache {
  const cache = new PreviewBoundedCache<ServiceTokenCacheEntry>({ maxEntries: 50, ttlMs: 600_000 })
  for (const [artifactId, entry] of entries) {
    cache.set(buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN), entry, {
      artifactId,
    })
  }
  return cache
}

describe('runtime preview service token recovery', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('缓存有效时应直接复用，不发起换票请求', async () => {
    const cache = createServiceTokenCache([
      ['artifact-1', { token: 'cached-service-token', expiresAtMs: Date.now() + 120_000 }],
    ])

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })

    expect(resolved.token).toBe('cached-service-token')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('缓存未命中时应凭 previewToken 向 Backend 换票并写入缓存', async () => {
    const cache = createServiceTokenCache()
    const exchangedToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 300)
    fetchMock.mockResolvedValueOnce(exchangeOkResponse(exchangedToken, 300, 'artifact-1'))

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000/',
      serviceTokenCache: cache,
    })

    expect(resolved.token).toBe(exchangedToken)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://backend:8000/internal/runtime/preview-service-token')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ preview_token: 'preview-token' })

    // 换票结果应可缓存加速
    const cached = readFreshCacheEntry(cache, 'artifact-1')
    expect(cached?.token).toBe(exchangedToken)
  })

  it('缓存条目临近过期时应重新换票', async () => {
    const cache = createServiceTokenCache([
      ['artifact-1', { token: 'stale-token', expiresAtMs: Date.now() + 5_000 }],
    ])
    const exchangedToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 300)
    fetchMock.mockResolvedValueOnce(exchangeOkResponse(exchangedToken, 300, 'artifact-1'))

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })

    expect(resolved.token).toBe(exchangedToken)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('本次请求自带令牌可使用但不得写入缓存（防缓存投毒）', async () => {
    const cache = createServiceTokenCache()
    const headerToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 600)

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
      headerServiceToken: headerToken,
    })

    expect(resolved.token).toBe(headerToken)
    expect(fetchMock).not.toHaveBeenCalled()
    // 请求头令牌未经验签，绝不能入缓存——否则可被用于跨用户缓存投毒。
    expect(readFreshCacheEntry(cache, 'artifact-1')).toBeNull()
  })

  it('伪造的远期 exp 请求头令牌不得钉死缓存，应换票获取真令牌', async () => {
    const cache = createServiceTokenCache()
    const forged = buildFakeJwt(Math.floor(Date.now() / 1000) + 10 * 365 * 24 * 3600)
    const exchangedToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 300)
    fetchMock.mockResolvedValueOnce(exchangeOkResponse(exchangedToken, 300, 'artifact-1'))

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
      headerServiceToken: forged,
    })

    // 远期 exp 视为异常，不使用、不缓存，回退换票。
    expect(resolved.token).toBe(exchangedToken)
    expect(readFreshCacheEntry(cache, 'artifact-1')?.token).toBe(exchangedToken)
    expect(readFreshCacheEntry(cache, 'artifact-1')?.token).not.toBe(forged)
  })

  it('过期 preview token 被 Backend 拒绝时应抛出结构化错误', async () => {
    const cache = createServiceTokenCache()
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ code: 'PREVIEW_CONTEXT_INVALID', message: '预览上下文令牌非法或已过期。' }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await expect(resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'expired-preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })).rejects.toMatchObject({
      name: 'PreviewServiceTokenError',
      statusCode: 401,
      code: 'PREVIEW_CONTEXT_INVALID',
    })
    expect(cache.size).toBe(0)
  })

  it('换票响应 artifact 不一致时应拒绝使用', async () => {
    const cache = createServiceTokenCache()
    fetchMock.mockResolvedValueOnce(exchangeOkResponse('service-token', 300, 'other-artifact'))

    await expect(resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })).rejects.toBeInstanceOf(PreviewServiceTokenError)
  })

  it('缺少 previewToken 时应拒绝换票', async () => {
    await expect(resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: '',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: createServiceTokenCache(),
    })).rejects.toMatchObject({ statusCode: 401, code: 'PREVIEW_CONTEXT_REQUIRED' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('应能解析 JWT 过期时间并将令牌脱敏为日志摘要', () => {
    const expSeconds = Math.floor(Date.now() / 1000) + 120
    const token = buildFakeJwt(expSeconds)

    expect(readJwtExpiresAtMs(token)).toBe(expSeconds * 1000)
    expect(readJwtExpiresAtMs('not-a-jwt')).toBeNull()

    const redacted = redactJwtForLog(token)
    expect(redacted).not.toContain(token)
    expect(redacted).not.toContain('signature')
    expect(redacted).toContain('jwt(')
  })

  it('无法解析过期时间的请求头令牌应视为缺失并回退换票，且不写缓存', async () => {
    const cache = createServiceTokenCache()
    const exchangedToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 300)
    fetchMock.mockResolvedValueOnce(exchangeOkResponse(exchangedToken, 300, 'artifact-1'))

    const resolved = await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
      headerServiceToken: 'opaque-header-token',
    })

    expect(resolved.token).toBe(exchangedToken)
    expect(readFreshCacheEntry(cache, 'artifact-1')?.token).toBe(exchangedToken)
  })

  it('换票不改变服务令牌缓存的稳定内容身份', async () => {
    const cache = createServiceTokenCache()
    const firstToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 300)
    const secondToken = buildFakeJwt(Math.floor(Date.now() / 1000) + 600)
    fetchMock
      .mockResolvedValueOnce(exchangeOkResponse(firstToken, 300, 'artifact-1'))
      .mockResolvedValueOnce(exchangeOkResponse(secondToken, 600, 'artifact-1'))

    await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })
    // 模拟 TTL 过期后重新换票：缓存身份键不变，仅值被覆盖
    cache.clear()
    await resolveRuntimeServiceToken({
      artifactId: 'artifact-1',
      previewToken: 'preview-token-rotated',
      backendApiBaseUrl: 'http://backend:8000',
      serviceTokenCache: cache,
    })

    const stableKey = buildPreviewCacheKey('artifact-1', PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN)
    expect(readFreshCacheEntry(cache, 'artifact-1')?.token).toBe(secondToken)
    // 键由 artifact + 内容身份构成，不含任何 token 原文
    expect(stableKey).toContain('artifact-1')
    expect(stableKey).not.toContain('preview-token')
    expect(stableKey).not.toContain(firstToken)
    expect(stableKey).not.toContain(secondToken)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
