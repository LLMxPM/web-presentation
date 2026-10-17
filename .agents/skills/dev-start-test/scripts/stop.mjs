/**
 * 文件功能：安全停止主仓本地开发服务进程树，供 dev-start-test Skill 在重启或 E2E 准备前释放端口。
 *
 * 安全边界：
 * - 只处理开发服务端口上的监听进程，仓库路径匹配必须有完整目录边界；
 * - 只向上追溯 pnpm/uv/uvicorn/cross-env 服务启动器，遇到终端或通用编排进程停止；
 * - 未知占用默认只报告不停止，仅 --force 才强制停止；
 * - 不停止 PostgreSQL/Redis 容器，不修改数据与配置。
 */
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { collectRoots, hasBlockedEntry, planService } from './lib/stop-plan.mjs'
import { readSnapshot, sleep, stopProcessTree } from './lib/system-processes.mjs'
import { resolveServiceUrls } from '../../../../scripts/testing/service-env.mjs'

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(SCRIPT_DIR, '../../../..')
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]', '0.0.0.0'])
const SERVICE_DEFS = [
  {
    key: 'backend',
    label: 'Backend',
    env: 'backend',
    defaultPort: 8000,
    urlKeys: ['BACKEND_BASE_URL'],
    portKeys: ['APP_PORT'],
  },
  {
    key: 'editor',
    label: 'Editor',
    env: 'editor',
    defaultPort: 5173,
    urlKeys: ['EDITOR_BASE_URL'],
    portKeys: [],
  },
  {
    key: 'runtime',
    label: 'Runtime',
    env: 'runtime',
    defaultPort: 7373,
    urlKeys: ['RUNTIME_BASE_URL'],
    portKeys: ['RUNTIME_SERVER_PORT'],
  },
  {
    key: 'renderer',
    label: 'Renderer',
    env: 'renderer',
    defaultPort: 7400,
    urlKeys: ['RENDERER_BASE_URL'],
    portKeys: ['RENDER_PORT'],
  },
]

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  main().catch((error) => {
    console.error(`[stop] 失败：${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}

/** 解析参数、识别目标服务并停止可验证归属的进程树。 */
export async function main(argv = process.argv.slice(2), { read = readSnapshot, stop = stopProcessTree } = {}) {
  const options = parseArgs(argv)
  if (options.help) {
    printHelp()
    return
  }

  const targets = await resolveTargets(options.services, options.e2e)
  const snapshot = read(targets.map((target) => target.port))
  const plans = targets.map((target) => planService(target, snapshot, { ...options, repoRoot: REPO_ROOT }))

  printPlan(plans, options)
  if (options.dryRun || plans.some(hasBlockedEntry)) {
    if (plans.some(hasBlockedEntry)) process.exitCode = 1
    return
  }

  const roots = collectRoots(plans)
  for (const root of roots) {
    try {
      await stop(root.pid, snapshot.processes)
    } catch (error) {
      root.error = error instanceof Error ? error.message : String(error)
    }
  }

  const remaining = await waitForPortsReleased(plans, read)
  printResult(roots, remaining)
  if (roots.some((root) => root.error) || remaining.length > 0 || plans.some(hasBlockedEntry)) {
    process.exitCode = 1
  }
}

/** 解析命令行；服务名仅允许已知四类服务。 */
function parseArgs(argv) {
  const options = { services: null, dryRun: false, force: false, e2e: false, help: false }
  const requested = new Set()

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--dry-run') {
      options.dryRun = true
    } else if (arg === '--force') {
      options.force = true
    } else if (arg === '--e2e') {
      options.e2e = true
    } else if (arg === '--help' || arg === '-h') {
      options.help = true
    } else if (arg === '--services' || arg === '--service') {
      const value = argv[index + 1]
      if (!value) throw new Error(`${arg} 需要服务名，例如 backend,editor,runtime,renderer`)
      index += 1
      addServiceKeys(value, requested)
    } else if (arg.startsWith('--services=')) {
      addServiceKeys(arg.slice('--services='.length), requested)
    } else {
      throw new Error(`未知参数：${arg}（使用 --help 查看用法）`)
    }
  }

  if (requested.size > 0) options.services = requested
  return options
}

/** 将逗号分隔的服务名加入集合，拒绝未知服务。 */
function addServiceKeys(value, requested) {
  if (!value.split(',').some((key) => key.trim())) throw new Error('服务列表不能为空')
  const known = new Set(SERVICE_DEFS.map((def) => def.key))
  for (const raw of value.split(',')) {
    const key = raw.trim().toLowerCase()
    if (!key) continue
    if (!known.has(key)) throw new Error(`未知服务：${key}（可选 backend,editor,runtime,renderer）`)
    requested.add(key)
  }
}

/** 按服务配置解析本地端口；非回环地址不参与本机停止。 */
async function resolveTargets(selectedKeys, e2e) {
  const { resolveServiceEnvironments } = await import(
    pathToFileURL(path.join(REPO_ROOT, 'scripts/dev/env-files.mjs')).href
  )
  const envs = resolveServiceEnvironments(REPO_ROOT)
  const e2eUrls = e2e ? resolveServiceUrls() : null
  const defs = selectedKeys ? SERVICE_DEFS.filter((def) => selectedKeys.has(def.key)) : SERVICE_DEFS

  return defs.map((def) => {
    const env = envs[def.env] || {}
    const configuredUrl = e2eUrls ? e2eUrls[def.key] : pickUrl(env, def.urlKeys)
    let port = def.defaultPort
    let host = '127.0.0.1'
    let portResolved = false

    if (configuredUrl) {
      try {
        const parsed = new URL(configuredUrl)
        host = parsed.hostname
        if (parsed.port) {
          port = Number(parsed.port)
          portResolved = true
        }
      } catch {
        // 配置无法解析时退回端口环境变量与默认端口。
      }
    }
    if (!portResolved) {
      for (const key of def.portKeys) {
        const value = Number(env[key])
        if (Number.isInteger(value) && value > 0) {
          port = value
          break
        }
      }
    }

    return {
      ...def,
      url: configuredUrl,
      host,
      port,
      local: LOOPBACK_HOSTS.has(String(host).toLowerCase()),
    }
  })
}

/** 读取服务 URL 配置；未配置时返回空串。 */
function pickUrl(env, keys) {
  for (const key of keys) {
    const value = String(env[key] || '').trim()
    if (value) return value
  }
  return ''
}

/** 等待已停止服务的端口释放；超时返回仍占用的监听项。 */
async function waitForPortsReleased(plans, read, timeoutMs = 8000) {
  const ports = [
    ...new Set(
      plans
        .filter((plan) => plan.entries.some((entry) => entry.action === 'kill'))
        .map((plan) => plan.target.port),
    ),
  ]
  if (ports.length === 0) return []

  const deadline = Date.now() + timeoutMs
  for (;;) {
    const listeners = read(ports).listeners.filter((listener) => ports.includes(listener.port))
    if (listeners.length === 0) return []
    if (Date.now() >= deadline) return listeners
    await sleep(700)
  }
}

/** 输出停服计划；未知占用给出明确提示。 */
function printPlan(plans, options) {
  console.log(`[stop] 目标服务：${plans.map((plan) => plan.target.label).join(', ')}${options.dryRun ? '（dry-run）' : ''}`)
  for (const plan of plans) {
    const { target, entries } = plan
    if (plan.skippedReason) {
      console.log(`[stop] ${target.label} ${target.port} 跳过：${plan.skippedReason}`)
      continue
    }
    if (entries.length === 0) {
      console.log(`[stop] ${target.label} ${target.host}:${target.port} 未监听`)
      continue
    }
    for (const entry of entries) {
      if (entry.action === 'skip') {
        console.log(
          `[stop] ${target.label} ${target.host}:${target.port} pid=${entry.pid} 跳过：${entry.reason}` +
            `${entry.command ? `（${formatCommand(entry.command)}）` : ''}`,
        )
        console.log(`       确认可停止后使用 --force，或手动处理该进程。`)
        continue
      }
      const prefix = options.dryRun ? '将停止' : '停止'
      console.log(
        `[stop] ${target.label} ${target.host}:${target.port} pid=${entry.pid} ${prefix}进程树 root=${entry.rootPid}` +
          `${entry.forced ? '（--force）' : ''}（${formatCommand(entry.rootCommand || entry.command)}）`,
      )
    }
  }
}

/** 输出停止结果与未释放端口。 */
function printResult(roots, remaining) {
  for (const root of roots) {
    if (root.error) {
      console.log(`[stop] root=${root.pid} 停止失败：${root.error}`)
    } else {
      console.log(`[stop] root=${root.pid} 已停止（${root.services.join(', ')}）`)
    }
  }
  if (remaining.length > 0) {
    console.log('[stop] 以下端口仍被占用，请检查是否有自动重启或未知进程：')
    for (const listener of remaining) {
      console.log(`  - 127.0.0.1:${listener.port} pid=${listener.pid}`)
    }
  } else if (roots.length > 0) {
    console.log('[stop] 端口已释放；PostgreSQL/Redis 未受影响。')
  }
}

/** 截断命令行，避免输出过长或包含换行。 */
function formatCommand(command) {
  const text = String(command || '').replace(/\s+/g, ' ').trim()
  return text.length > 160 ? `${text.slice(0, 157)}...` : text
}

/** 打印用法与安全边界。 */
function printHelp() {
  console.log(`用法：node stop.mjs [选项]

按开发服务端口停止本仓进程树；默认只停止命令行可验证属于本仓的服务。

选项：
  --services <列表>  只处理指定服务：backend,editor,runtime,renderer（逗号分隔）
  --dry-run          只输出计划，不停止任何进程
  --e2e              按测试入口的 E2E 地址覆盖解析端口
  --force            允许停止无法确认归属的端口占用（需用户明确同意）
  -h, --help         显示帮助

说明：
  - 只停止 Backend/Editor/Runtime/Renderer，不动 PostgreSQL/Redis。
  - 遇到终端或未知父进程立即停止向上追溯，避免误杀用户 shell。
  - 停止后若端口仍被占用，脚本退出码为 1 并列出占用进程。`)
}
