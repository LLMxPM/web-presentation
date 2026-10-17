/** 文件功能：纯函数生成停服计划，约束仓库路径边界、服务包装器和未知进程的强制停止范围。 */
import path from 'node:path'

const TERMINAL_NAMES = new Set([
  'pwsh.exe', 'pwsh', 'powershell.exe', 'powershell', 'bash.exe', 'bash',
  'sh.exe', 'sh', 'zsh', 'fish', 'cmd.exe', 'wt.exe', 'windowsterminal.exe',
  'explorer.exe', 'conhost.exe', 'openconsole.exe',
])

/** 仓库路径必须是独立参数或参数中的目录，不能匹配同名前缀目录与仓库外路径。 */
export function isRepoOwned(proc, repoRoot) {
  if (!repoRoot) return false
  const windows = /^(?:[a-z]:[\\/]|\\\\)/i.test(repoRoot)
  const paths = windows ? path.win32 : path.posix
  const root = paths.normalize(repoRoot)
  return commandTokens(proc.commandLine, false).some((token) => {
    const value = token.slice(token.indexOf('=') + 1)
    if (!paths.isAbsolute(value)) return false
    const relative = paths.relative(root, paths.normalize(value))
    return relative === '' || (!relative.startsWith(`..${paths.sep}`) && relative !== '..' && !paths.isAbsolute(relative))
  })
}

/** 将命令行按引号分组；这里只识别服务启动器，不用解析结果重新执行命令。 */
function commandTokens(command, lowercase = true) {
  return [...String(command || '').matchAll(/"([^"]*)"|'([^']*)'|([^\s"']+)/g)]
    .map((match) => {
      const value = (match[1] ?? match[2] ?? match[3]).replace(/\\/g, '/')
      return lowercase ? value.toLowerCase() : value
    })
}

/** 提取可执行文件名，兼容 Windows 与 POSIX 路径。 */
function executableName(token = '') {
  return token.split('/').at(-1)
}

/** 只接受实际的 pnpm、uv、uvicorn/reloader 与 cross-env 服务启动器，拒绝通用编排父进程。 */
export function isServiceWrapper(proc) {
  const tokens = commandTokens(proc.commandLine)
  const name = String(proc.name || executableName(tokens[0])).toLowerCase()
  if (TERMINAL_NAMES.has(name)) return false
  let runner = executableName(tokens[0])
  let args = tokens.slice(1)
  if (/^node(?:\.exe)?$/.test(runner)) {
    runner = executableName(args[0])
    args = args.slice(1)
  } else if (/^python(?:\d+(?:\.\d+)*)?(?:\.exe)?$/.test(runner)) {
    if (args[0] === '-m') args = args.slice(1)
    runner = executableName(args[0])
    args = args.slice(1)
  }
  if (/^cross-env(?:\.(?:js|mjs|cjs))?$/.test(runner)) {
    const start = args.findIndex((arg) => !arg.includes('='))
    return start >= 0 && isServiceWrapper({ commandLine: args.slice(start).join(' ') })
  }
  const app = args.includes('app.main:app') || args.includes('wp_renderer.main:app')
  if (/^uv(?:\.exe)?$/.test(runner)) return args.includes('run') && args.includes('uvicorn') && app
  if (/^uvicorn(?:\.exe)?$/.test(runner)) return app
  if (!/^pnpm(?:\.(?:cjs|mjs|js|exe|cmd))?$/.test(runner) || !args.includes('dev')) return false
  return args.some((arg, index) => (
    (arg === '--dir' && ['editor', 'runtime'].includes(args[index + 1])) ||
    (arg === '--filter' && ['editor', 'web-runtime-vue'].includes(args[index + 1]))
  ))
}

/** 仅沿已知服务启动链追溯；遇到终端、通用父进程、调用者或环立即停止。 */
export function findRoot(proc, processes, protectedPids = [process.pid, process.ppid]) {
  let root = proc
  const seen = new Set([proc.pid, ...protectedPids])
  for (;;) {
    const parent = processes.get(root.ppid)
    if (!parent || seen.has(parent.pid) || !isServiceWrapper(parent)) return root
    seen.add(parent.pid)
    root = parent
  }
}

/** 为一个服务生成停服计划；未知进程默认拒绝，强制模式只选择监听 PID 自身作为树根。 */
export function planService(target, snapshot, { repoRoot, force = false } = {}) {
  if (!target.local) {
    return { target, entries: [], skippedReason: `配置地址不是本机回环（${target.host}），已跳过` }
  }
  const entries = []
  const seen = new Set()
  for (const listener of snapshot.listeners.filter((item) => item.port === target.port)) {
    if (seen.has(listener.pid)) continue
    seen.add(listener.pid)
    const proc = snapshot.processes.get(listener.pid)
    if (proc && isRepoOwned(proc, repoRoot)) {
      const root = findRoot(proc, snapshot.processes)
      entries.push({ pid: proc.pid, action: 'kill', rootPid: root.pid, command: proc.commandLine, rootCommand: root.commandLine })
    } else if (force) {
      entries.push({ pid: listener.pid, action: 'kill', rootPid: listener.pid, forced: true, command: proc?.commandLine })
    } else {
      entries.push({
        pid: listener.pid, action: 'skip', status: 'unknown', command: proc?.commandLine,
        reason: proc ? '命令行不包含具有完整路径边界的本仓目录，无法确认归属' : '无法读取进程信息',
      })
    }
  }
  return { target, entries }
}

/** 按树根去重执行目标；显式强制的未知 PID 同样进入执行集合。 */
export function collectRoots(plans) {
  const roots = new Map()
  for (const plan of plans) {
    for (const entry of plan.entries) {
      if (entry.action !== 'kill') continue
      if (!roots.has(entry.rootPid)) roots.set(entry.rootPid, { pid: entry.rootPid, services: [] })
      roots.get(entry.rootPid).services.push(plan.target.label)
    }
  }
  return [...roots.values()]
}

/** 任一未知监听被拒绝时阻止整次停止，避免已知服务被部分停止后才报错。 */
export function hasBlockedEntry(plan) {
  return plan.entries.some((entry) => entry.action === 'skip' && entry.status === 'unknown')
}
