/** 文件功能：回归 E2E 构建身份隔离与 Runtime 就绪检查，防止任务因 Worker 未启动而一直 pending。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildE2eBackendEnv } from '../../../scripts/testing/e2e-database-env.mjs'
import {
  assertE2eRuntimeReady,
  buildE2eRuntimeEnv,
  runtimeProbeUrl,
  RUNTIME_HEALTH_PATH,
  RUNTIME_READINESS_PATH,
} from '../../../scripts/testing/e2e-runtime-env.mjs'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** 模拟开发环境中的高优先级凭据文件与角色，要求 E2E 显式覆盖这些配置。 */
function stubInheritedEnvironment() {
  vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', 'inherited-production-credential')
  vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '/production/build-secret')
  vi.stubEnv('RUNTIME_BUILD_WORKER_ID', 'production-worker')
  vi.stubEnv('RUNTIME_ROLE', 'preview')
  vi.stubEnv('E2E_DATABASE_URL', 'sqlite+aiosqlite:///fixture_e2e.db')
  vi.stubEnv('E2E_API_BASE_URL', 'http://127.0.0.1:18000')
  vi.stubEnv('E2E_RUNTIME_BASE_URL', 'http://127.0.0.1:17373/runtime/')
}

describe('E2E 构建身份', () => {
  it.each(['', '   '])('未提供专用凭据时仍能启动 Worker，并隔离继承配置（%j）', credential => {
    stubInheritedEnvironment()
    vi.stubEnv('E2E_BUILD_WORKER_CREDENTIAL', credential)
    vi.stubEnv('E2E_BUILD_WORKER_ID', '')
    const backend = buildE2eBackendEnv()
    const runtime = buildE2eRuntimeEnv()

    expect(runtime.RUNTIME_BUILD_WORKER_CREDENTIAL).toBeTruthy()
    expect(runtime.RUNTIME_BUILD_WORKER_CREDENTIAL).not.toBe('inherited-production-credential')
    expect(backend.RUNTIME_BUILD_WORKER_CREDENTIAL).toBe(runtime.RUNTIME_BUILD_WORKER_CREDENTIAL)
    expect(backend.RUNTIME_BUILD_WORKER_CREDENTIAL_FILE).toBe('')
    expect(runtime.RUNTIME_BUILD_WORKER_CREDENTIAL_FILE).toBe('')
    expect(runtime.RUNTIME_BUILD_WORKER_ID).not.toBe('production-worker')
    expect(runtime.RUNTIME_ROLE).toBe('all')
    expect(runtime.RUNTIME_BACKEND_API_BASE_URL).toBe(backend.BACKEND_PUBLIC_BASE_URL)
    expect(runtime.RUNTIME_PREVIEW_JWKS_URL).toBe('http://127.0.0.1:18000/.well-known/jwks.json')
    expect(runtime.RUNTIME_SERVER_BASE_PATH).toBe('/runtime/')
  })

  it('专用凭据和 Worker ID 的覆盖在两端保持一致', () => {
    stubInheritedEnvironment()
    vi.stubEnv('E2E_BUILD_WORKER_CREDENTIAL', ' custom-e2e-credential ')
    vi.stubEnv('E2E_BUILD_WORKER_ID', ' custom-e2e-worker ')
    const backend = buildE2eBackendEnv()
    const runtime = buildE2eRuntimeEnv()

    expect(backend.RUNTIME_BUILD_WORKER_CREDENTIAL).toBe('custom-e2e-credential')
    expect(runtime.RUNTIME_BUILD_WORKER_CREDENTIAL).toBe(backend.RUNTIME_BUILD_WORKER_CREDENTIAL)
    expect(runtime.RUNTIME_BUILD_WORKER_ID).toBe('custom-e2e-worker')
  })
})

/** 模拟 Runtime 的探针返回；只用当前公共协议，不依赖真实服务或开发配置。 */
function stubReadiness(payload: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status })))
}

describe('Runtime 探针地址', () => {
  it.each([
    ['http://127.0.0.1:17373', 'http://127.0.0.1:17373/__runtime_healthz'],
    ['http://127.0.0.1:17373/', 'http://127.0.0.1:17373/__runtime_healthz'],
    ['http://127.0.0.1:17373/runtime/', 'http://127.0.0.1:17373/__runtime_healthz'],
    ['http://127.0.0.1:17373/runtime', 'http://127.0.0.1:17373/__runtime_healthz'],
  ])('存活与就绪探针都必须落在服务根，丢弃 base path 且不产生双斜杠（%s）', (runtimeUrl, expected) => {
    expect(runtimeProbeUrl(runtimeUrl, RUNTIME_HEALTH_PATH)).toBe(expected)
    expect(runtimeProbeUrl(runtimeUrl, RUNTIME_READINESS_PATH))
      .toBe(expected.replace('__runtime_healthz', '__runtime_readyz'))
  })
})

describe('E2E Runtime 就绪校验', () => {
  it('完整执行面与构建 Worker 就绪后通过，探针使用服务根路径', async () => {
    stubReadiness({ status: 'ok', checks: { buildWorker: { ready: true } } })
    vi.spyOn(console, 'log').mockImplementation(() => {})

    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373/runtime/')).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:17373/__runtime_readyz', {
      signal: expect.any(AbortSignal),
    })
  })

  it.each([
    { status: 200, payload: { status: 'ok', checks: {} } },
    { status: 200, payload: { status: 'ok', checks: { buildWorker: { ready: false } } } },
    { status: 503, payload: { status: 'unavailable', checks: { buildWorker: { ready: true } } } },
  ])('拒绝仅存活、缺少 Worker 或其他执行面未就绪的副本：%j', async ({ status, payload }) => {
    stubReadiness(payload, status)
    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373')).rejects.toThrow('E2E 构建就绪条件')
  })

  it('Worker 未启动时保留探针原因和 prepare 提示', async () => {
    stubReadiness({
      status: 'unavailable',
      checks: { buildWorker: { ready: false, detail: '构建 Worker 领取循环未在运行。' } },
    }, 503)
    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373')).rejects.toThrow(
      /构建 Worker 领取循环未在运行。.*test:e2e:prepare/,
    )
  })

  it('不支持就绪协议的旧服务快速失败', async () => {
    stubReadiness({}, 404)
    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373')).rejects.toThrow('HTTP 404')
  })

  it('探针响应不是 JSON 时快速失败', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Vite</html>')))
    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373')).rejects.toThrow('未返回合法 JSON')
  })

  it('探针网络失败时快速给出准备提示', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))
    await expect(assertE2eRuntimeReady('http://127.0.0.1:17373')).rejects.toThrow(/无法访问.*test:e2e:prepare/)
  })
})
