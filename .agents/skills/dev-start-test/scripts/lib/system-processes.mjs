/** 文件功能：读取系统监听/进程快照并执行已批准的进程树停止；不负责仓库归属决策。 */
import { execFileSync } from 'node:child_process'
import process from 'node:process'

const IS_WINDOWS = process.platform === 'win32'

/** 执行停止：Windows 使用 taskkill 进程树，POSIX 先 TERM 后 KILL。 */
export async function stopProcessTree(pid, processes) {
  if (IS_WINDOWS) {
    try {
      execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      })
    } catch (error) {
      if (!isProcessAlive(pid)) return
      throw error
    }
    return
  }

  const targets = [pid, ...collectDescendants(pid, processes)]
  for (const target of targets) safeSignal(target, 'SIGTERM')
  await sleep(1500)
  for (const target of targets) {
    if (isProcessAlive(target)) safeSignal(target, 'SIGKILL')
  }
}

/** 收集指定进程的全部后代 PID。 */
function collectDescendants(rootPid, processes) {
  const children = new Map()
  for (const proc of processes.values()) {
    if (!children.has(proc.ppid)) children.set(proc.ppid, [])
    children.get(proc.ppid).push(proc.pid)
  }

  const descendants = []
  const stack = [...(children.get(rootPid) || [])]
  while (stack.length > 0) {
    const pid = stack.pop()
    descendants.push(pid)
    stack.push(...(children.get(pid) || []))
  }
  return descendants
}

/** 发送信号；进程已退出或无权限时忽略。 */
function safeSignal(pid, signal) {
  try {
    process.kill(pid, signal)
  } catch {
    // 已退出或不可访问，由后续端口校验兜底。
  }
}

/** 判断进程是否仍存在。 */
function isProcessAlive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

/** 解析监听地址末尾端口。 */
function parsePortFromAddress(address) {
  const match = String(address || '').trim().match(/:(\d+)\]?$/)
  return match ? Number(match[1]) : null
}

/** 读取系统监听与进程快照。 */
export function readSnapshot(ports) {
  const uniquePorts = [...new Set(ports.filter((port) => Number.isInteger(port) && port > 0))]
  return IS_WINDOWS ? readWindowsSnapshot(uniquePorts) : readPosixSnapshot(uniquePorts)
}

/** Windows 优先用 Get-NetTCPConnection，失败时退回 netstat。 */
function readWindowsSnapshot(ports) {
  try {
    return parseWindowsSnapshot(readWindowsSnapshotJson(ports))
  } catch {
    return readWindowsSnapshotFallback(ports)
  }
}

/** 一次 PowerShell 调用同时读取监听与进程表。 */
function readWindowsSnapshotJson(ports) {
  const portList = ports.map(Number).join(',')
  const script = [
    "$ErrorActionPreference='Stop'",
    '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8',
    `$ports=@(${portList})`,
    '$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $ports -contains $_.LocalPort } | Select-Object LocalPort,OwningProcess)',
    '$processes=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine)',
    '@{ listeners=$listeners; processes=$processes } | ConvertTo-Json -Depth 4 -Compress',
  ].join('\n')

  return execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
    encoding: 'utf8',
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 64 * 1024 * 1024,
  })
}

/** netstat 回退：进程查询不可用时保留监听 PID，由规划层默认拒绝或显式强制。 */
function readWindowsSnapshotFallback(ports) {
  const netstat = execFileSync('netstat', ['-ano'], { encoding: 'utf8' })
  let processes = new Map()
  try {
    processes = readWindowsProcesses()
  } catch {
    // 不把权限错误伪装成端口空闲；未知 PID 仍由停服规划层处理。
  }
  return { listeners: parseNetstatListeners(netstat, ports), processes }
}

/** 只解析 TCP LISTENING 行，忽略活动连接、TIME_WAIT、UDP 与无效 PID。 */
export function parseNetstatListeners(netstat, ports) {
  const wanted = new Set(ports)
  const listeners = []

  for (const line of netstat.split(/\r?\n/)) {
    const fields = line.trim().split(/\s+/)
    if (fields.length < 5 || fields[0].toUpperCase() !== 'TCP' || fields[3].toUpperCase() !== 'LISTENING') continue
    const pid = Number(fields[fields.length - 1])
    if (!Number.isInteger(pid) || pid <= 0) continue
    const port = parsePortFromAddress(fields[1])
    if (port !== null && wanted.has(port)) listeners.push({ port, pid })
  }

  return dedupeListeners(listeners)
}

/** 回退路径单独读取进程表。 */
function readWindowsProcesses() {
  const script = [
    "$ErrorActionPreference='Stop'",
    '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8',
    '@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine) | ConvertTo-Json -Depth 4 -Compress',
  ].join('\n')
  const output = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
    encoding: 'utf8',
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 64 * 1024 * 1024,
  })
  return parseWindowsProcesses(output)
}

/** 解析 PowerShell 快照 JSON；兼容单对象返回值。 */
function parseWindowsSnapshot(output) {
  const data = JSON.parse(String(output || '').trim() || '{}') || {}
  const listeners = asArray(data.listeners).map((listener) => ({
    port: Number(listener.LocalPort),
    pid: Number(listener.OwningProcess),
  }))
  return {
    listeners: dedupeListeners(listeners),
    processes: parseWindowsProcessesFromValue(data.processes),
  }
}

/** 解析 PowerShell 进程数组。 */
function parseWindowsProcesses(output) {
  return parseWindowsProcessesFromValue(JSON.parse(String(output || '').trim() || '[]'))
}

/** 将进程数组转为 PID 映射。 */
function parseWindowsProcessesFromValue(value) {
  const processes = new Map()
  for (const proc of asArray(value)) {
    const pid = Number(proc.ProcessId)
    if (!Number.isInteger(pid)) continue
    processes.set(pid, {
      pid,
      ppid: Number(proc.ParentProcessId) || 0,
      name: proc.Name || '',
      commandLine: proc.CommandLine || '',
    })
  }
  return processes
}

/** POSIX 使用 lsof/ss 读取监听，ps 读取进程表。 */
function readPosixSnapshot(ports) {
  const listeners = readPosixListeners(ports)
  const processes = new Map()
  const output = execFileSync('ps', ['-axo', 'pid=,ppid=,command='], { encoding: 'utf8' })

  for (const line of output.split(/\r?\n/)) {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(.*)$/)
    if (!match) continue
    const pid = Number(match[1])
    processes.set(pid, { pid, ppid: Number(match[2]), name: '', commandLine: match[3] })
  }

  return { listeners, processes }
}

/** 读取 POSIX TCP 监听；lsof 缺失时退回 ss。 */
function readPosixListeners(ports) {
  const wanted = new Set(ports)
  const listeners = []

  try {
    const output = execFileSync('lsof', ['-nP', '-iTCP', '-sTCP:LISTEN', '-F', 'pcn'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    let currentPid = null
    for (const line of output.split(/\r?\n/)) {
      if (line.startsWith('p')) {
        currentPid = Number(line.slice(1))
      } else if (line.startsWith('n') && currentPid) {
        const port = parsePortFromAddress(line.slice(1))
        if (port !== null && wanted.has(port)) listeners.push({ port, pid: currentPid })
      }
    }
    return dedupeListeners(listeners)
  } catch {
    try {
      const output = execFileSync('ss', ['-ltnp'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
      for (const line of output.split(/\r?\n/)) {
        const portMatch = line.match(/^\S+\s+\d+\s+\d+\s+\S*:(\d+)\s/)
        const pidMatch = line.match(/pid=(\d+)/)
        if (!portMatch || !pidMatch) continue
        const port = Number(portMatch[1])
        if (wanted.has(port)) listeners.push({ port, pid: Number(pidMatch[1]) })
      }
      return dedupeListeners(listeners)
    } catch {
      throw new Error('无法读取 TCP 监听信息：lsof 与 ss 均不可用，请检查工具或进程查询权限。')
    }
  }
}

/** 去重监听项，避免 IPv4/IPv6 双监听重复处理。 */
function dedupeListeners(listeners) {
  const seen = new Set()
  const result = []
  for (const listener of listeners) {
    if (!Number.isInteger(listener.port) || !Number.isInteger(listener.pid) || listener.pid <= 0) continue
    const key = `${listener.port}:${listener.pid}`
    if (seen.has(key)) continue
    seen.add(key)
    result.push(listener)
  }
  return result
}

/** 将单对象或数组统一为数组。 */
function asArray(value) {
  if (Array.isArray(value)) return value
  return value == null ? [] : [value]
}

/** 有界等待，供进程退出和端口释放轮询使用。 */
export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
