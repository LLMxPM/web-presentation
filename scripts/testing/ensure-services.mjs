/**
 * 文件功能：检测或启动 backend/editor/runtime 服务，并校验 Backend 的 E2E 测试指纹。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.4/§3.7：
 * - 先等待 /api/auth/me 返回 401/200，再校验 /api/testing/e2e-readiness 指纹；
 *   任一指纹不匹配立即失败，不能把指向开发库、关闭 mock 或使用非 E2E Redis 的服务当作测试环境；
 * - 新启动的 Backend 由 buildE2eBackendEnv() 注入环境；复用现有 Backend 仅在指纹完全匹配时允许；
 * - ensure-services 启动的服务日志统一写入 test-results/e2e/services/。
 */
import fs from 'node:fs'
import path from 'node:path'

import { spawnPersistentBackground, sleep } from './process-utils.mjs'
import { resolveServiceUrls } from './service-env.mjs'
import { buildE2eBackendEnv, E2E_DATABASE_MARKER } from './e2e-database-env.mjs'

const urls = resolveServiceUrls()
const SERVICE_LOG_DIR = path.join(process.cwd(), 'test-results', 'e2e', 'services')

async function main() {
  const shouldStartBackend = String(process.env.TESTING_START_BACKEND || '').toLowerCase() === 'true'
  const shouldStartEditor = String(process.env.TESTING_START_EDITOR || '').toLowerCase() === 'true'
  const shouldStartRuntime = String(process.env.TESTING_START_RUNTIME || '').toLowerCase() === 'true'
  const shouldReuseBackend = String(process.env.TESTING_REUSE_BACKEND || '').toLowerCase() === 'true'

  await ensureBackendReady({ shouldStart: shouldStartBackend, allowReuse: shouldReuseBackend || !shouldStartBackend })
  await ensureServiceReady({
    label: 'editor',
    url: urls.editor,
    shouldStart: shouldStartEditor,
    start: () =>
      spawnPersistentBackground('pnpm', ['--dir', 'editor', 'dev', '--host', '127.0.0.1', '--port', '5173'], {
        cwd: process.cwd(),
        env: process.env,
        ...serviceLogStdio('editor'),
      }),
  })
  await ensureServiceReady({
    label: 'runtime',
    url: urls.runtime,
    shouldStart: shouldStartRuntime,
    start: () =>
      spawnPersistentBackground('pnpm', ['--dir', 'runtime', 'dev', '--host', '127.0.0.1', '--port', '7373'], {
        cwd: process.cwd(),
        env: buildE2eRuntimeEnv(urls),
        ...serviceLogStdio('runtime'),
      }),
  })
  console.log('[testing] backend/editor/runtime are ready')
}

/** 为 ensure-services 启动的服务打开独立日志文件，保留控制台摘要便于失败诊断。 */
function serviceLogStdio(label) {
  fs.mkdirSync(SERVICE_LOG_DIR, { recursive: true })
  const out = fs.openSync(path.join(SERVICE_LOG_DIR, `${label}.out.log`), 'a')
  const err = fs.openSync(path.join(SERVICE_LOG_DIR, `${label}.err.log`), 'a')
  return { stdio: ['ignore', out, err] }
}

/**
 * Backend 就绪检查：端口可达只是前提，必须再校验测试指纹完全匹配。
 * @param {{ shouldStart: boolean, allowReuse: boolean }} options 启动与复用策略
 */
async function ensureBackendReady({ shouldStart, allowReuse }) {
  const reachable = await isAuthEndpointReachable(urls.backend)
  if (reachable) {
    if (!allowReuse) {
      throw new Error(`backend is already reachable at ${urls.backend}. Refusing to reuse it unless TESTING_REUSE_BACKEND=true.`)
    }
    await assertBackendTestFingerprint('复用现有 Backend')
    console.log(`[testing] reuse running backend: ${urls.backend}`)
    return
  }

  if (!shouldStart) {
    throw new Error(`backend is not reachable at ${urls.backend}. Set TESTING_START_BACKEND=true to start it automatically.`)
  }

  console.log(`[testing] starting backend: ${urls.backend}`)
  spawnPersistentBackground('uv', ['run', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: path.join(process.cwd(), 'backend'),
    env: buildE2eBackendEnv({
      AI_TEST_MODE: process.env.AI_TEST_MODE || 'mock',
    }),
    ...serviceLogStdio('backend'),
  })
  await waitForAuthEndpoint(urls.backend)
  await assertBackendTestFingerprint('新启动的 Backend')
}

/** 等待 /api/auth/me 返回 401/200，作为 Backend HTTP 就绪的语义信号。 */
async function waitForAuthEndpoint(backendUrl, { timeoutMs = 60_000, intervalMs = 1_000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    if (await isAuthEndpointReachable(backendUrl)) {
      return
    }
    lastError = new Error(`/api/auth/me 尚未就绪：${backendUrl}`)
    await sleep(intervalMs)
  }
  throw lastError || new Error(`Timed out while waiting for ${backendUrl}`)
}

/** 探测 /api/auth/me 是否返回 401（未登录）或 200（已登录）。 */
async function isAuthEndpointReachable(backendUrl) {
  try {
    const response = await fetch(`${backendUrl.replace(/\/$/, '')}/api/auth/me`, { method: 'GET' })
    return response.status === 200 || response.status === 401
  } catch {
    return false
  }
}

/**
 * 校验 Backend 测试就绪指纹；任一指纹不匹配立即失败，不能继续使用该 Backend。
 * @param {string} origin 触发校验的来源描述，用于错误信息
 */
async function assertBackendTestFingerprint(origin) {
  const readinessUrl = `${urls.backend.replace(/\/$/, '')}/api/testing/e2e-readiness`
  const prepareHint = '请停止该服务后以 TESTING_START_BACKEND=true 重新执行 pnpm run test:e2e:prepare。'
  let response
  try {
    response = await fetch(readinessUrl)
  } catch (error) {
    throw new Error(`${origin}的测试指纹校验失败：无法访问 ${readinessUrl}（${error.message}）。${prepareHint}`)
  }
  if (response.status === 404) {
    throw new Error(`${origin}未启用 AI_TEST_MODE=mock（就绪端点返回 404），不能作为 E2E 测试环境。${prepareHint}`)
  }
  if (!response.ok) {
    throw new Error(`${origin}的测试指纹校验失败：${readinessUrl} 返回 HTTP ${response.status}。${prepareHint}`)
  }

  const readiness = await response.json()
  const problems = []
  if (readiness.test_mode !== 'mock') problems.push(`test_mode=${readiness.test_mode}（期望 mock）`)
  if (readiness.database_profile !== 'e2e') {
    problems.push(`database_profile=${readiness.database_profile}（期望 e2e，数据库名必须包含 ${E2E_DATABASE_MARKER}）`)
  }
  if (readiness.redis_profile !== 'e2e') problems.push(`redis_profile=${readiness.redis_profile}（期望 e2e）`)
  if (typeof readiness.seed_version !== 'number') problems.push('seed_version 缺失')
  if (typeof readiness.scenario_version !== 'string') problems.push('scenario_version 缺失')
  if (readiness.smoke_data_ready !== true) problems.push('smoke_data_ready=false（请先执行 pnpm run test:seed:smoke）')

  if (problems.length) {
    throw new Error(`${origin}的测试指纹不匹配：${problems.join('；')}。${prepareHint}`)
  }
  console.log(`[testing] backend fingerprint ok (${origin}，seed_version=${readiness.seed_version}，scenario_version=${readiness.scenario_version})`)
}

/**
 * 构造 Runtime 的 E2E 环境，确保预览令牌验签和内部回源始终指向同一套测试 Backend。
 * @param {{ backend: string, runtime: string }} urls 测试服务的公开地址
 * @returns {NodeJS.ProcessEnv} 供 Runtime 子进程使用的环境变量
 */
function buildE2eRuntimeEnv(urls) {
  const backendUrl = urls.backend.replace(/\/$/, '')
  return {
    ...process.env,
    RUNTIME_PREVIEW_JWKS_URL: `${backendUrl}/.well-known/jwks.json`,
    RUNTIME_BACKEND_API_BASE_URL: backendUrl,
    RUNTIME_PUBLIC_BASE_URL: urls.runtime.replace(/\/$/, ''),
  }
}

/** Editor/Runtime 等非指纹敏感服务的 HTTP 就绪检查与自动启动。 */
async function ensureServiceReady({ label, url, shouldStart, start }) {
  try {
    await waitForHttpReady(url)
    console.log(`[testing] reuse running ${label}: ${url}`)
    return
  } catch {
    if (!shouldStart) {
      throw new Error(`${label} is not reachable at ${url}. Set TESTING_START_${label.toUpperCase()}=true to start it automatically.`)
    }
  }

  console.log(`[testing] starting ${label}: ${url}`)
  start()
  await waitForHttpReady(url)
}

/** 等待 HTTP 服务就绪，超时默认 60s。 */
async function waitForHttpReady(url, { timeoutMs = 60_000, intervalMs = 1_000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { method: 'GET' })
      if (response.ok || response.status === 404) {
        return
      }
      lastError = new Error(`Unexpected status ${response.status} for ${url}`)
    } catch (error) {
      lastError = error
    }
    await sleep(intervalMs)
  }
  throw lastError || new Error(`Timed out while waiting for ${url}`)
}

main().catch((error) => {
  console.error('[testing] failed to ensure services', error)
  process.exitCode = 1
})
