/** 文件功能：回归开发/E2E 状态探测的地址与依赖隔离，确保准备后不会误查开发服务。 */
import { afterEach, expect, it, vi } from 'vitest'
import { collectStatusReport } from '../../../.agents/skills/dev-start-test/scripts/status.mjs'
import { resolveStatusTargets } from '../../../.agents/skills/dev-start-test/scripts/lib/service-targets.mjs'
import { resolveServiceUrls } from '../../../scripts/testing/service-env.mjs'

afterEach(() => vi.unstubAllGlobals())

it('E2E 探测与测试入口使用相同覆盖地址，不读取开发数据库或旧 Renderer 地址', async () => {
  const systemEnv = {
    E2E_API_BASE_URL: 'http://127.0.0.1:18000', E2E_BASE_URL: 'http://127.0.0.1:15173',
    E2E_RUNTIME_BASE_URL: 'http://127.0.0.1:17373/runtime/', E2E_RENDERER_BASE_URL: 'http://127.0.0.1:17400',
    BACKEND_PUBLIC_BASE_URL: 'http://127.0.0.1:28000', RENDERER_BASE_URL: 'http://127.0.0.1:27400',
    E2E_DATABASE_URL: 'sqlite+aiosqlite:///isolated_e2e.db', E2E_REDIS_URL: 'memory://e2e',
    DATABASE_URL: 'postgresql://dev:secret@development:5432/dev', REDIS_URL: 'redis://development:6379',
  }
  const fetch = vi.fn(async (url: string) => new Response(JSON.stringify(
    url.endsWith('/api/testing/e2e-readiness') ? { test_mode: 'mock', smoke_data_ready: true } : { role: 'all' },
  ), { status: url.endsWith('/api/auth/me') ? 401 : 200, headers: { 'content-type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const report = await collectStatusReport({ e2e: true, systemEnv })
  expect(resolveStatusTargets({ e2e: true, systemEnv }).urls).toEqual(resolveServiceUrls(systemEnv))
  expect(report.services.backend.url).toBe(systemEnv.E2E_API_BASE_URL)
  expect(report.services.editor.url).toBe(systemEnv.E2E_BASE_URL)
  expect(report.services.renderer.url).toBe(systemEnv.E2E_RENDERER_BASE_URL)
  expect(report.services.runtime.ready).toBe(true)
  expect(fetch.mock.calls.map(([url]) => url)).toContain('http://127.0.0.1:17373/__runtime_readyz')
  expect(fetch.mock.calls.every(([url]) => !/:(?:28000|27400|8000|5173|7373|7400)(?:\/|$)/.test(url))).toBe(true)
  expect(report.dependencies.postgres.status).toBe('skipped')
  expect(report.dependencies.redis.status).toBe('skipped')
  expect(JSON.stringify(report)).not.toContain('secret')
})

it('未配置 E2E 时使用隔离默认值，忽略开发库与通用 Renderer 地址', () => {
  const targets = resolveStatusTargets({ e2e: true, systemEnv: { DATABASE_URL: 'sqlite:///dev.db', RENDERER_BASE_URL: 'http://old:27400' } })
  expect(targets.databaseUrl).toContain('/web_presentation_e2e')
  expect(targets.redisUrl).toBe('redis://127.0.0.1:6379/15')
  expect(targets.urls.renderer).toBe('http://127.0.0.1:7400')
})
