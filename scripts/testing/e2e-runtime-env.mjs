/** 文件功能：为 E2E 的 Backend 与 Runtime 提供共享构建身份、Runtime 环境、探针地址和构建就绪校验。 */
import { resolveServiceUrls } from './service-env.mjs'

/** Runtime 存活探针路径，与 runtime/src/core/plugins/runtime-health.ts 保持一致。 */
export const RUNTIME_HEALTH_PATH = '/__runtime_healthz'

/** Runtime 就绪探针路径，与 runtime/src/core/plugins/runtime-health.ts 保持一致。 */
export const RUNTIME_READINESS_PATH = '/__runtime_readyz'

/**
 * 构造 Runtime 探针地址。
 *
 * 探针必须落在服务根：runtime-health 插件以 enforce:'pre' 注册中间件，早于 Vite 的 base
 * 处理，因此它按未经 base 剥离的 pathname 精确匹配 `/__runtime_healthz`、`/__runtime_readyz`。
 * dev 下 Vite base 还带版本段，用 `${runtimeUrl}/__runtime_healthz` 拼接会在配置了 base path
 * 时得到 `/runtime//__runtime_healthz` 而 404。前导斜杠的 URL 解析会丢弃 base path，正是所需语义。
 * @param {string} runtimeUrl Runtime 服务地址，可带 base path
 * @param {string} path 以 / 开头的探针路径
 * @returns {string} 探针绝对地址
 */
export function runtimeProbeUrl(runtimeUrl, path) {
  return new URL(path, runtimeUrl).href
}

/** 测试构建凭据只接受 E2E 专用覆盖，并清空优先级更高的开发或生产 secret 文件配置。 */
export function buildE2eBuildWorkerEnv() {
  return {
    RUNTIME_BUILD_WORKER_CREDENTIAL: process.env.E2E_BUILD_WORKER_CREDENTIAL?.trim()
      || 'e2e-build-only-no-production-credential',
    RUNTIME_BUILD_WORKER_CREDENTIAL_FILE: '',
    RUNTIME_BUILD_WORKER_ID: process.env.E2E_BUILD_WORKER_ID?.trim() || 'runtime-build-e2e',
  }
}

/** 构造完整 E2E 执行环境；预览验签、内部回源与构建领取必须指向同一套测试 Backend。 */
export function buildE2eRuntimeEnv(urls = resolveServiceUrls()) {
  const backendUrl = urls.backend.replace(/\/$/, '')
  return {
    ...process.env,
    ...buildE2eBuildWorkerEnv(),
    RUNTIME_ROLE: 'all',
    RUNTIME_PREVIEW_JWKS_URL: `${backendUrl}/.well-known/jwks.json`,
    RUNTIME_BACKEND_API_BASE_URL: backendUrl,
    RUNTIME_PUBLIC_BASE_URL: urls.runtime.replace(/\/$/, ''),
    RUNTIME_SERVER_BASE_PATH: new URL(urls.runtime).pathname,
  }
}

/** 在服务存活后验证真实构建执行面；缺少 Worker 或角色就绪失败时直接终止 E2E 准备。 */
export async function assertE2eRuntimeReady(runtimeUrl) {
  const readinessUrl = runtimeProbeUrl(runtimeUrl, RUNTIME_READINESS_PATH)
  const prepareHint = '请检查 E2E_BUILD_WORKER_CREDENTIAL 与 Runtime 构建 Worker 配置后重新执行 pnpm run test:e2e:prepare。'
  let response
  try {
    response = await fetch(readinessUrl, { signal: AbortSignal.timeout(5_000) })
  } catch {
    throw new Error(`无法访问 Runtime 就绪端点 ${readinessUrl}。${prepareHint}`)
  }
  if (!response.ok && response.status !== 503) {
    throw new Error(`Runtime 就绪端点返回 HTTP ${response.status}。${prepareHint}`)
  }
  let readiness
  try {
    readiness = await response.json()
  } catch {
    throw new Error(`Runtime 就绪端点未返回合法 JSON。${prepareHint}`)
  }
  const buildWorker = readiness?.checks?.buildWorker
  if (!response.ok || readiness?.status !== 'ok' || buildWorker?.ready !== true) {
    const reason = buildWorker?.detail || '构建 Worker 就绪检查缺失或执行面尚未就绪。'
    throw new Error(`Runtime 未达到 E2E 构建就绪条件：${reason}${prepareHint}`)
  }
  console.log('[testing] Runtime 构建 Worker 就绪校验通过')
}
