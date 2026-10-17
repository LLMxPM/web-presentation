/**
 * 文件功能：提供 dev-start-test 技能脚本共用的 E2E 依赖探测、IPv4/IPv6 端口检查、停服调用、浏览器安装与状态读取。
 *
 * 依据 SKILL.md 与 scripts/testing/e2e-database-env.mjs：
 * - 依赖按 E2E 实际使用的 E2E_DATABASE_URL/E2E_REDIS_URL 探测；
 * - 端口同时检查 127.0.0.1 与 ::1，避免 Vite 只绑 ::1 时被误判为空闲；
 * - 停服必须由调用方显式请求，共享工具不主动杀进程；
 * - 所有子命令在仓库根执行，避免调用方 cwd 不同导致 compose/pnpm 路径漂移。
 */
import { execFileSync } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { runCommandSync } from '../../../../../scripts/testing/process-utils.mjs'
import {
  DEFAULT_E2E_REDIS_URL,
  resolveE2eDatabaseUrl,
} from '../../../../../scripts/testing/e2e-database-env.mjs'
import { resolveServiceUrls } from '../../../../../scripts/testing/service-env.mjs'

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
export const REPO_ROOT = path.resolve(SCRIPT_DIR, '../../../../..')
export const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]', '0.0.0.0'])
export const SERVICE_DEFS = [
  { key: 'backend', label: 'Backend', urlKey: 'backend', defaultPort: 8000 },
  { key: 'editor', label: 'Editor', urlKey: 'editor', defaultPort: 5173 },
  { key: 'runtime', label: 'Runtime', urlKey: 'runtime', defaultPort: 7373 },
  { key: 'renderer', label: 'Renderer', urlKey: 'renderer', defaultPort: 7400 },
]
const STOP_SCRIPT = path.join(SCRIPT_DIR, '../stop.mjs')
const STATUS_SCRIPT = path.join(SCRIPT_DIR, '../status.mjs')

/**
 * 依赖检查：按 E2E 实际使用的 E2E_DATABASE_URL/E2E_REDIS_URL 探测；
 * 只有本机默认端口才允许 compose 启动，远程或自定义端口直接报错。
 */
export async function ensureE2eDependencies({ startInfra = false, dryRun = false, logPrefix = '[e2e-env]' } = {}) {
  const dependencies = resolveE2eDependencies()
  const unreachable = []

  for (const dependency of dependencies) {
    if (dependency.skipped) {
      console.log(`${logPrefix} ${dependency.label}：${dependency.skipped}`)
      continue
    }
    if (await isTcpReachable(dependency.host, dependency.port)) continue
    unreachable.push(dependency)
  }

  if (unreachable.length === 0) {
    console.log(`${logPrefix} E2E PostgreSQL/Redis 可达`)
    return
  }

  const unsupported = unreachable.filter((dependency) => {
    return (
      !LOOPBACK_HOSTS.has(String(dependency.host || '').toLowerCase()) ||
      Number(dependency.port) !== dependency.expectedPort
    )
  })
  if (unsupported.length > 0) {
    throw new Error(
      `以下 E2E 依赖不可达且不是本机默认端口，compose.infra.yml 无法启动：` +
        unsupported
          .map(({ label, host, port, source }) => `${label}(${host}:${port}，来源 ${source})`)
          .join('、') +
        '；请先恢复对应依赖或修正 E2E_DATABASE_URL/E2E_REDIS_URL。',
    )
  }

  if (!startInfra) {
    throw new Error(
      `E2E 依赖未就绪：${unreachable.map(({ label }) => label).join('、')}。` +
        '加 --start-infra 启动本机 compose，或手动执行 docker compose -f scripts/dev/compose.infra.yml up -d --wait。',
    )
  }

  if (dryRun) {
    console.log(`${logPrefix} dry-run：将启动本机 compose 依赖（${unreachable.map(({ label }) => label).join('、')}）`)
    return
  }

  console.log(`${logPrefix} 启动本机 PostgreSQL/Redis...`)
  const code = runCommandSync('docker', ['compose', '-f', 'scripts/dev/compose.infra.yml', 'up', '-d', '--wait', ...unreachable.map((item) => item.key)], {
    cwd: REPO_ROOT,
  })
  if (code !== 0) throw new Error(`docker compose 启动依赖失败（退出码 ${code}）`)

  const stillDown = []
  for (const dependency of unreachable) {
    if (!(await isTcpReachable(dependency.host, dependency.port))) stillDown.push(dependency)
  }
  if (stillDown.length > 0) {
    throw new Error(`依赖启动后仍不可达：${stillDown.map(({ label }) => label).join('、')}；请检查容器日志。`)
  }
  console.log(`${logPrefix} 基础依赖已就绪`)
}

/** 解析 E2E 实际依赖目标；默认指向本机 _e2e 库与 Redis DB 15。 */
export function resolveE2eDependencies() {
  let databaseUrl
  try {
    databaseUrl = resolveE2eDatabaseUrl()
  } catch (error) {
    throw new Error(`E2E 数据库配置无效：${error instanceof Error ? error.message : String(error)}`)
  }

  return [
    parseDependency('postgres', 'PostgreSQL', databaseUrl, 5432, 'E2E_DATABASE_URL'),
    parseDependency(
      'redis',
      'Redis',
      process.env.E2E_REDIS_URL || DEFAULT_E2E_REDIS_URL,
      6379,
      'E2E_REDIS_URL',
    ),
  ]
}

/** 解析依赖 URL；SQLite/memory 适配器跳过探测，解析失败时不输出凭证。 */
function parseDependency(key, label, rawUrl, defaultPort, source) {
  const raw = String(rawUrl || '').trim()
  if (!raw) return { key, label, skipped: '未配置' }
  if (raw.startsWith('sqlite')) return { key, label, skipped: 'SQLite 适配器' }
  if (raw.startsWith('memory://')) return { key, label, skipped: 'memory 适配器' }

  let parsed
  try {
    parsed = new URL(raw)
  } catch {
    throw new Error(`${source} 无法解析（不输出连接串）`)
  }
  if (!parsed.hostname) {
    throw new Error(`${source} 未包含主机名，无法探测`)
  }

  return {
    key,
    label,
    host: parsed.hostname,
    port: Number(parsed.port || defaultPort),
    expectedPort: defaultPort,
    source,
  }
}

/** 有界 TCP 可达性探测。 */
export function isTcpReachable(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port })
    const timer = setTimeout(() => {
      socket.destroy()
      resolve(false)
    }, 2500)
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

/** 检查 E2E 服务端口；非本机地址跳过并提示。 */
export async function findOccupiedServices({ logPrefix = '[e2e-env]' } = {}) {
  const urls = resolveServiceUrls()
  const occupied = []

  for (const def of SERVICE_DEFS) {
    const url = urls[def.urlKey]
    let parsed
    try {
      parsed = new URL(url)
    } catch {
      console.warn(`${logPrefix} ${def.label} 地址无法解析，跳过端口检查：${url}`)
      continue
    }
    if (!LOOPBACK_HOSTS.has(parsed.hostname.toLowerCase())) {
      console.warn(`${logPrefix} ${def.label} 指向非本机地址，跳过本地端口检查：${url}`)
      continue
    }
    const port = Number(parsed.port || def.defaultPort)
    if (!(await isPortFree(port))) {
      occupied.push({ ...def, port })
    }
  }
  return occupied
}

/** 同时检查 IPv4 与 IPv6 回环，任一不可绑定即视为占用。 */
export async function isPortFree(port) {
  const ipv4Free = await canBind(port, '127.0.0.1')
  if (!ipv4Free) return false
  return canBind(port, '::1')
}

/** 尝试绑定端口；地址族不支持时视为空闲，其余错误视为占用。 */
function canBind(port, host) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', (error) => {
      resolve(error.code === 'EADDRNOTAVAIL' || error.code === 'EAFNOSUPPORT')
    })
    server.once('listening', () => server.close(() => resolve(true)))
    server.listen({ host, port, exclusive: true })
  })
}

/** 调用 stop.mjs 停止占用端口的本仓服务；dry-run 时只预演。 */
export function stopOccupiedServices(occupied, { dryRun = false, logPrefix = '[e2e-env]' } = {}) {
  if (occupied.length === 0) return

  const urls = resolveServiceUrls()
  const stopArgs = [STOP_SCRIPT, '--services', occupied.map((item) => item.key).join(',')]
  if (dryRun) stopArgs.push('--dry-run')
  const stopEnv = {
    ...process.env,
    BACKEND_BASE_URL: urls.backend,
    EDITOR_BASE_URL: urls.editor,
    RUNTIME_BASE_URL: urls.runtime,
    RENDERER_BASE_URL: urls.renderer,
  }

  console.log(`${logPrefix} ${dryRun ? '预演停止' : '停止'}占用端口的服务：${occupied.map((item) => item.key).join(', ')}`)
  const code = runCommandSync(process.execPath, stopArgs, { env: stopEnv, cwd: REPO_ROOT })
  if (code !== 0) throw new Error(`stop.mjs 退出码 ${code}，请先处理未知端口占用。`)
}

/** 安装 Node 与 Renderer 两套 Playwright Chromium。 */
export function installBrowsers({ dryRun = false, logPrefix = '[e2e-env]' } = {}) {
  if (dryRun) {
    console.log(`${logPrefix} dry-run：将安装 Node 与 Renderer 的 Playwright Chromium`)
    return
  }

  console.log(`${logPrefix} 安装 Node Playwright Chromium...`)
  const nodeCode = runCommandSync('pnpm', ['exec', 'playwright', 'install', 'chromium'], { cwd: REPO_ROOT })
  if (nodeCode !== 0) throw new Error(`pnpm exec playwright install chromium 退出码 ${nodeCode}`)

  console.log(`${logPrefix} 安装 Renderer Playwright Chromium...`)
  const rendererCode = runCommandSync(
    'uv',
    ['run', '--project', 'renderer', 'playwright', 'install', 'chromium'],
    { cwd: REPO_ROOT },
  )
  if (rendererCode !== 0) throw new Error(`Renderer Playwright Chromium 安装退出码 ${rendererCode}`)
}

/** 调用只读状态脚本并解析 JSON。 */
export function readStatus() {
  try {
    const output = execFileSync(process.execPath, [STATUS_SCRIPT, '--json', '--e2e'], {
      encoding: 'utf8',
      maxBuffer: 8 * 1024 * 1024,
    })
    return JSON.parse(output)
  } catch (error) {
    throw new Error(`无法读取服务状态：${error instanceof Error ? error.message : String(error)}`)
  }
}
