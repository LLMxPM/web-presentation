/**
 * 文件功能：只读探测主仓本地开发服务与基础依赖，供 dev-start-test Skill 判断复用还是启动。
 *
 * 依据 docs/developer/getting-started.md 与 scripts/testing/service-env.mjs：
 * - 开发模式读取根/模块 .env；--e2e 与真实测试入口共享进程环境和隔离默认值；
 * - Backend 以 /api/auth/me 返回 200/401 视为存活，再读取 /api/testing/e2e-readiness 判断 E2E 指纹；
 * - Runtime 探针按服务根拼接，避免 base path 影响；
 * - 只做网络探测，不启动/停止进程，不读写数据库，不输出凭证。
 */
import net from 'node:net'
import { pathToFileURL } from 'node:url'
import { REPO_ROOT, resolveStatusTargets } from './lib/service-targets.mjs'

const PROBE_TIMEOUT_MS = 2500
const jsonMode = process.argv.includes('--json')

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  main().catch((error) => {
    console.error(`[status] 探测失败：${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}

/** 执行一次只读探测并汇总服务、依赖与 E2E 指纹。 */
async function main() {
  const report = await collectStatusReport({ e2e: process.argv.includes('--e2e') })
  if (jsonMode) console.log(JSON.stringify(report, null, 2))
  else printHumanReport(report)
}

/** 根据明确的开发/E2E 模式探测服务，返回不含凭证的状态报告。 */
export async function collectStatusReport(options = {}) {
  const targets = resolveStatusTargets(options)
  const { backend: backendUrl, editor: editorUrl, runtime: runtimeUrl, renderer: rendererUrl } = targets.urls

  const [backend, editorProbe, runtimeHealth, runtimeReadiness, renderer, postgres, redis] = await Promise.all([
    probeBackend(backendUrl),
    probeEditor(editorUrl),
    probeHttp(`${originOf(runtimeUrl)}/__runtime_healthz`),
    probeHttp(`${originOf(runtimeUrl)}/__runtime_readyz`),
    probeHttp(`${rendererUrl}/readyz`),
    probeDependency(parsePostgresTarget(targets.databaseUrl)),
    probeDependency(parseRedisTarget(targets.redisUrl)),
  ])
  const editor = editorProbe.probe

  return {
    repoRoot: REPO_ROOT,
    services: {
      backend: {
        url: backendUrl,
        status: backend.up ? 'up' : 'down',
        httpStatus: backend.httpStatus,
        error: backend.error ?? null,
        e2eReadiness: backend.e2eReadiness,
      },
      editor: {
        url: editorProbe.url,
        status: isHttpUp(editor) ? 'up' : 'down',
        httpStatus: editor.httpStatus,
        error: editor.error ?? null,
      },
      runtime: {
        url: runtimeUrl,
        status: runtimeHealth.httpStatus === 200 ? 'up' : 'down',
        httpStatus: runtimeHealth.httpStatus,
        error: runtimeHealth.error ?? null,
        role: runtimeHealth.body?.role ?? null,
        ready: runtimeReadiness.httpStatus === 200,
        readinessStatus: runtimeReadiness.httpStatus,
      },
      renderer: {
        url: rendererUrl,
        status: renderer.httpStatus === 200 ? 'up' : 'down',
        httpStatus: renderer.httpStatus,
        error: renderer.error ?? null,
      },
    },
    dependencies: {
      postgres,
      redis,
    },
  }
}

/** 探测 Backend 存活；存活时再读取 E2E 就绪指纹。 */
async function probeBackend(backendUrl) {
  const auth = await probeHttp(`${backendUrl.replace(/\/+$/, '')}/api/auth/me`)
  const up = auth.httpStatus === 200 || auth.httpStatus === 401
  if (!up) {
    return { up: false, httpStatus: auth.httpStatus, error: auth.error ?? null, e2eReadiness: null }
  }
  const readiness = await probeHttp(`${backendUrl.replace(/\/+$/, '')}/api/testing/e2e-readiness`)
  return {
    up: true,
    httpStatus: auth.httpStatus,
    error: null,
    e2eReadiness: readiness.httpStatus === 200 ? readiness.body : { httpStatus: readiness.httpStatus },
  }
}

/**
 * 探测 Editor；Vite 默认可能只监听 ::1，127.0.0.1 失败时回退 IPv6 回环。
 * 返回值包含实际可用地址，避免把只绑 IPv6 的 Editor 误报为 down。
 */
async function probeEditor(editorUrl) {
  const primary = await probeHttp(`${editorUrl}/`)
  if (isHttpUp(primary)) return { probe: primary, url: editorUrl }

  let parsed
  try {
    parsed = new URL(editorUrl)
  } catch {
    return { probe: primary, url: editorUrl }
  }
  if (!['127.0.0.1', 'localhost'].includes(parsed.hostname)) {
    return { probe: primary, url: editorUrl }
  }

  const port = parsed.port || '5173'
  const fallback = await probeHttp(`http://[::1]:${port}/`)
  if (isHttpUp(fallback)) {
    return { probe: fallback, url: `http://localhost:${port}` }
  }
  return { probe: primary, url: editorUrl }
}

/** 发送有界 HTTP 探测；只解析 JSON 响应体，不读取其它内容。 */
async function probeHttp(url) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
  try {
    const response = await fetch(url, { signal: controller.signal, redirect: 'manual' })
    let body = null
    if ((response.headers.get('content-type') || '').includes('application/json')) {
      try {
        body = await response.json()
      } catch {
        body = null
      }
    }
    return { httpStatus: response.status, body, error: null }
  } catch (error) {
    return {
      httpStatus: null,
      body: null,
      error: error instanceof Error && error.name === 'AbortError' ? 'timeout' : 'unreachable',
    }
  } finally {
    clearTimeout(timer)
  }
}

/** 解析 DATABASE_URL；SQLite 形态无需探测 PostgreSQL。 */
function parsePostgresTarget(databaseUrl) {
  const raw = String(databaseUrl || '').trim()
  if (!raw) return null
  if (raw.startsWith('sqlite')) return { kind: 'sqlite', status: 'skipped' }
  try {
    const url = new URL(raw)
    return {
      kind: 'postgres',
      host: url.hostname,
      port: Number(url.port || 5432),
      status: 'pending',
    }
  } catch {
    return null
  }
}

/** 解析 REDIS_URL；memory:// 适配器无需探测 Redis。 */
function parseRedisTarget(redisUrl) {
  const raw = String(redisUrl || '').trim()
  if (!raw) return null
  if (raw.startsWith('memory://')) return { kind: 'memory', status: 'skipped' }
  try {
    const url = new URL(raw)
    return {
      kind: 'redis',
      host: url.hostname,
      port: Number(url.port || 6379),
      status: 'pending',
    }
  } catch {
    return null
  }
}

/** TCP 探测依赖端口；状态为 skipped 时直接跳过。 */
async function probeDependency(target) {
  if (!target || target.status === 'skipped') {
    return target
  }
  const reachable = await isTcpReachable(target.host, target.port)
  return { ...target, status: reachable ? 'up' : 'down' }
}

/** 有界 TCP 连接探测；只判断端口是否接受连接。 */
function isTcpReachable(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port })
    const timer = setTimeout(() => {
      socket.destroy()
      resolve(false)
    }, PROBE_TIMEOUT_MS)
    socket.once('connect', () => {
      clearTimeout(timer)
      socket.destroy()
      resolve(true)
    })
    socket.once('error', () => {
      clearTimeout(timer)
      resolve(false)
    })
  })
}

/** 取服务根地址，供健康探针绕开可能的 base path。 */
function originOf(url) {
  try {
    return new URL(url).origin
  } catch {
    return url
  }
}

/** 编辑器等普通 HTTP 服务以 2xx/3xx 视为可用。 */
function isHttpUp(probe) {
  return probe.httpStatus !== null && probe.httpStatus < 400
}

/** 输出人类可读状态与启动提示；不包含凭证。 */
function printHumanReport(report) {
  const { services, dependencies } = report
  console.log('本地开发状态（只读探测，不启动/停止服务）')
  console.log('')

  printRow('Backend', services.backend, describeBackend(services.backend))
  printRow('Editor', services.editor, httpDetail(services.editor))
  printRow('Runtime', services.runtime, describeRuntime(services.runtime))
  printRow('Renderer', services.renderer, httpDetail(services.renderer))
  printRow('PostgreSQL', dependencies.postgres, describeDependency(dependencies.postgres))
  printRow('Redis', dependencies.redis, describeDependency(dependencies.redis))

  if (services.backend.e2eReadiness) {
    console.log('')
    console.log(`E2E 指纹: ${describeE2e(services.backend.e2eReadiness)}`)
  }

  const hints = []
  if (services.backend.status === 'down') {
    hints.push('Backend: uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend')
  }
  if (services.editor.status === 'down') {
    hints.push('Editor: pnpm --filter editor dev')
  }
  if (services.runtime.status === 'down') {
    hints.push('Runtime: pnpm --filter web-runtime-vue dev')
  }
  if (services.renderer.status === 'down') {
    hints.push('Renderer: uv run --project renderer uvicorn wp_renderer.main:app --host 127.0.0.1 --port 7400')
  }
  if (dependencies.postgres?.status === 'down' || dependencies.redis?.status === 'down') {
    hints.push('基础依赖: docker compose -f scripts/dev/compose.infra.yml up -d --wait')
  }

  if (hints.length) {
    console.log('')
    console.log('启动提示（已 up 的服务直接复用，不要重复启动）：')
    for (const hint of hints) console.log(`  - ${hint}`)
    console.log('  若对应端口已被占用但状态为 down，先排查占用进程，不要重复启动。')
  }
}

/** 按固定列宽输出单行状态。 */
function printRow(label, service, detail) {
  const status = service?.status === 'skipped' ? 'skip' : (service?.status || 'down')
  console.log(`${label.padEnd(11)} ${status.padEnd(5)} ${detail}`)
}

/** 汇总 Backend 地址与 HTTP 存活信号。 */
function describeBackend(service) {
  const http = service.httpStatus ? `HTTP ${service.httpStatus}` : service.error
  return `${service.url}${http ? `（${http}）` : ''}`
}

/** 在 Runtime 存活时展示角色与构建就绪状态。 */
function describeRuntime(service) {
  if (service.status !== 'up') return httpDetail(service)
  const role = service.role ? `role=${service.role}` : 'role=?'
  return `${service.url}（${role}, ready=${service.ready}）`
}

/** 展示依赖适配器或主机端口，不输出连接凭据。 */
function describeDependency(dependency) {
  if (!dependency) return '未配置'
  if (dependency.status === 'skipped') {
    return dependency.kind === 'sqlite' ? '未使用（SQLite）' : '未使用（memory 适配器）'
  }
  return `${dependency.host}:${dependency.port}`
}

/** 将就绪指纹或不可读原因转换为诊断摘要。 */
function describeE2e(readiness) {
  if (readiness.httpStatus === 404) return '未启用（AI_TEST_MODE 不是 mock）'
  if (readiness.httpStatus) return `不可读（HTTP ${readiness.httpStatus}）`
  const fields = [
    `test_mode=${readiness.test_mode ?? '?'}`,
    `database_profile=${readiness.database_profile ?? '?'}`,
    `redis_profile=${readiness.redis_profile ?? '?'}`,
    `seed_version=${readiness.seed_version ?? '?'}`,
    `smoke_data_ready=${readiness.smoke_data_ready ?? '?'}`,
  ]
  return fields.join(', ')
}

/** 展示普通 HTTP 服务的地址、状态码或失败原因。 */
function httpDetail(service) {
  const http = service.httpStatus ? `HTTP ${service.httpStatus}` : service.error
  return `${service.url}${http ? `（${http}）` : ''}`
}
