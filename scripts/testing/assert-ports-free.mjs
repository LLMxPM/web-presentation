/**
 * 文件功能：校验全量测试自启所需的端口与本地 E2E 依赖，被占用或缺失时给出可执行提示。
 *
 * 依据 docs/developer/testing/strategy.md 的 test:all 编排：
 * - 全量测试由脚本自动启动 Backend/Editor/Runtime，8000/5173/7373 必须空闲；
 * - TESTING_REUSE_BACKEND=true 表示用户显式选择复用现有 Backend，跳过其端口校验；
 * - 服务地址被 E2E_API_BASE_URL/E2E_BASE_URL/E2E_RUNTIME_BASE_URL 覆盖时按对应端口校验；
 * - 默认 E2E 依赖 PostgreSQL/Redis 未监听时给出 docker compose 启动提示。
 */
import net from 'node:net'
import { pathToFileURL } from 'node:url'

import { resolveServiceUrls } from './service-env.mjs'

const DEFAULT_PORTS = { backend: 8000, editor: 5173, runtime: 7373 }
const DEPENDENCY_PORTS = [
  { label: 'PostgreSQL', port: 5432 },
  { label: 'Redis', port: 6379 },
]

function resolvePort(url, fallback) {
  try {
    const port = new URL(url).port
    return port ? Number(port) : fallback
  } catch {
    return fallback
  }
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.once('listening', () => server.close(() => resolve(true)))
    server.listen(port, '127.0.0.1')
  })
}

function isTcpReachable(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host: '127.0.0.1' })
    socket.setTimeout(2000)
    socket.once('connect', () => {
      socket.destroy()
      resolve(true)
    })
    socket.once('error', () => resolve(false))
    socket.once('timeout', () => {
      socket.destroy()
      resolve(false)
    })
  })
}

export async function assertPortsFree() {
  const urls = resolveServiceUrls()
  const appPorts = [
    { label: 'Backend', port: resolvePort(urls.backend, DEFAULT_PORTS.backend) },
    { label: 'Editor', port: resolvePort(urls.editor, DEFAULT_PORTS.editor) },
    { label: 'Runtime', port: resolvePort(urls.runtime, DEFAULT_PORTS.runtime) },
  ]

  const reuseBackend = String(process.env.TESTING_REUSE_BACKEND || '').toLowerCase() === 'true'
  const occupied = []
  for (const { label, port } of appPorts) {
    if (label === 'Backend' && reuseBackend) {
      continue
    }
    if (!(await isPortFree(port))) {
      occupied.push({ label, port })
    }
  }

  if (occupied.length > 0) {
    console.error('[testing] 全量测试需要由脚本自启服务，以下端口已被占用：')
    for (const { label, port } of occupied) {
      console.error(`  - ${label}: 127.0.0.1:${port}`)
    }
    console.error('请先停止占用这些端口的服务（例如正在运行的 dev server），或：')
    console.error("  - 仅 Backend 复用：设置 TESTING_REUSE_BACKEND='true' 并确保其满足 E2E 测试指纹")
    return false
  }

  const missingDependencies = []
  if (!process.env.E2E_DATABASE_URL && !isInheritedE2eDatabase()) {
    for (const { label, port } of DEPENDENCY_PORTS) {
      if (!(await isTcpReachable(port))) {
        missingDependencies.push(`${label}(127.0.0.1:${port})`)
      }
    }
  }

  if (missingDependencies.length > 0) {
    console.error('[testing] 本地 E2E 依赖未监听：' + missingDependencies.join('、'))
    console.error('请先启动依赖容器：docker compose -f docker-compose.dev.yml up -d --wait')
    return false
  }

  console.log('[testing] 端口校验通过：Backend/Editor/Runtime 端口空闲，E2E 依赖已就绪')
  return true
}

function isInheritedE2eDatabase() {
  const databaseUrl = String(process.env.DATABASE_URL || '').trim()
  return databaseUrl.length > 0 && databaseUrl.includes('_e2e')
}

async function main() {
  const ok = await assertPortsFree()
  if (!ok) {
    process.exitCode = 1
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main()
}
