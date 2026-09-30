/**
 * 文件用途：隔离 Runtime 构建阶段的 Vite/Rollup 与 ZIP 归档执行，避免构建/压缩 OOM 阻塞或终止 Runtime 主进程。
 */

import { spawn, type ChildProcess, type SpawnOptions } from 'child_process'
import { randomUUID } from 'crypto'
import { chmod, chown, mkdir, readFile, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { resolve } from 'path'

import { RuntimeTaskAbortedError } from './runtime-task-deadline'

const DEFAULT_WORKER_MAX_OLD_SPACE_MB = 1024
const DEFAULT_WORKER_TIMEOUT_MS = 600000
const DEFAULT_ARCHIVE_WORKER_TIMEOUT_MS = 120000
const DEFAULT_ARCHIVE_COMPRESSION_LEVEL = 6
const DEFAULT_DIAGNOSTICS_WORKER_TIMEOUT_MS = 120000
const DEFAULT_DIAGNOSTICS_WORKER_MAX_TASKS = 25
const DEFAULT_DIAGNOSTICS_WORKER_MAX_AGE_MS = 30 * 60 * 1000
const DEFAULT_DIAGNOSTICS_WORKER_RSS_RATIO = 0.75
const MAX_CAPTURED_OUTPUT_LENGTH = 12000
/** SIGTERM 后等待子进程自行退出的宽限；超时升级 SIGKILL，绝不把存活进程视为已回收。 */
const WORKER_STOP_GRACE_MS = 1000

/**
 * 禁止进入构建子进程环境的键：子进程会编译/压缩用户手写代码，
 * 属于「执行不可信输入」的一侧，不得拿到用于领取任务的内部服务身份，
 * 连凭证文件路径也不下发，避免子进程顺着 env 找到 secret。
 */
const BUILD_CHILD_ENV_DENY_LIST = [
  'RUNTIME_BUILD_WORKER_CREDENTIAL',
  'RUNTIME_BUILD_WORKER_CREDENTIAL_FILE',
]

/**
 * 构造构建/归档子进程环境。
 * @param overrides 子进程需要的额外变量
 * @returns 已剔除内部服务凭证变量的环境副本
 */
export function createRuntimeBuildChildEnv(overrides: Record<string, string> = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, FORCE_COLOR: '0', NO_COLOR: '1', ...overrides }
  for (const key of BUILD_CHILD_ENV_DENY_LIST) {
    delete env[key]
  }
  return env
}

/**
 * 构建子进程降权身份（POSIX UID/GID）。
 * 生产形态下编译不可信 SFC 的进程必须与持有全局 Worker 凭证的领取器不同 UID，
 * 否则删环境变量无法阻止子进程读取 `/run/secrets` 下的凭证文件（AR-01/W01）。
 */
export interface RuntimeBuildChildIdentity {
  uid?: number
  gid?: number
}

/**
 * 解析子进程降权身份；未配置时返回空对象（开发/受限形态，仅保留删键）。
 * @param env 环境源，默认 process.env
 * @returns 子进程 uid/gid（若配置）
 */
export function resolveRuntimeBuildChildIdentity(
  env: NodeJS.ProcessEnv = process.env,
): RuntimeBuildChildIdentity {
  const uid = parsePositiveIntEnv(env.RUNTIME_BUILD_CHILD_UID)
  const gid = parsePositiveIntEnv(env.RUNTIME_BUILD_CHILD_GID)
  if (uid == null && gid == null) {
    return {}
  }
  return { uid, gid }
}

/**
 * 解析正整数环境变量；空串、0、负数、非数字均视为未配置。
 */
function parsePositiveIntEnv(raw: string | undefined): number | undefined {
  const text = String(raw ?? '').trim()
  if (!text || !/^\d+$/.test(text)) {
    return undefined
  }
  const value = Number(text)
  return Number.isSafeInteger(value) && value > 0 ? value : undefined
}

/**
 * 把降权身份转换为 spawn 选项。Windows 无 POSIX uid/gid，原样返回空对象。
 * @param identity 子进程身份
 * @returns spawn 可用的 uid/gid 字段
 */
export function toSpawnIdentityOptions(
  identity: RuntimeBuildChildIdentity,
): Pick<SpawnOptions, 'uid' | 'gid'> {
  if (process.platform === 'win32') {
    return {}
  }
  return {
    ...(identity.uid != null ? { uid: identity.uid } : {}),
    ...(identity.gid != null ? { gid: identity.gid } : {}),
  }
}

/**
 * 准备供降权子进程写入的任务目录。
 * 父进程保持目录属主以便继续写入；通过 setgid + 属组可写让 rtchild 能写。
 * @param dir 任务目录
 * @param identity 子进程身份
 */
export async function prepareChildWritableDir(
  dir: string,
  identity: RuntimeBuildChildIdentity,
): Promise<void> {
  await mkdir(dir, { recursive: true })
  if (process.platform === 'win32' || (identity.uid == null && identity.gid == null)) {
    return
  }
  // 属主（领取器）可写；setgid 让子文件继承属组。chmod 不需要 CAP_CHOWN。
  try {
    await chmod(dir, 0o2770)
  } catch {
    try {
      await chmod(dir, 0o2777)
    } catch {
      // 权限不可改时保持 mkdir 默认；M02 验证子进程写失败是否可观测。
    }
  }
  // 尝试把属组对齐子进程（父目录已 setgid 时通常已继承；此处兜底）。
  if (identity.gid != null) {
    try {
      await chown(dir, -1, identity.gid)
    } catch {
      // 无 CAP_CHOWN 时依赖父目录 setgid 继承。
    }
  }
}

/**
 * 解析任务工作区根目录：优先 `RUNTIME_TASK_WORK_ROOT`（生产镜像指向 setgid 目录），
 * 否则回落系统临时目录。
 * @returns 工作区根路径
 */
export function resolveRuntimeTaskWorkRoot(): string {
  const configured = String(process.env.RUNTIME_TASK_WORK_ROOT || '').trim()
  return configured || resolve(tmpdir())
}

export interface RuntimeBuildWorkerRunOptions {
  tempRoot: string
  taskRoot?: string
  base: string
  mode: 'project' | 'diagnostics'
  outDir?: string
  maxOldSpaceMb?: number
  timeoutMs?: number
  workerScriptSource?: string
  /**
   * Runtime Kit 公开导入白名单（`@runtime-kit/...` import_path）。
   * 优先来自 Backend module_resolver.runtime_kit_exports；空数组时 worker 回落到本地 manifest。
   */
  runtimeKitAllowedImports?: string[]
  /**
   * 外部中止信号：租约失守或 deadline 到期时必须真正终止 Vite 子进程。
   * 只中止主进程的 fetch/sleep 会让最耗 CPU 与内存的构建阶段继续跑到自然结束。
   */
  signal?: AbortSignal
}

export interface RuntimeZipArchiveOptions {
  distRoot: string
  outputPath: string
  compressionLevel?: number
  maxOldSpaceMb?: number
  timeoutMs?: number
  workerScriptSource?: string
  /** 外部中止信号：语义同构建 worker，归档阶段同样要能被立即终止。 */
  signal?: AbortSignal
}

export interface RuntimeZipArchiveResult {
  archivePath: string
  sha256: string
  sizeBytes: number
  fileCount: number
  durationMs: number
  rssBytes: number
  compressionLevel: number
}

interface RuntimeBuildWorkerInput {
  tempRoot: string
  base: string
  mode: 'project' | 'diagnostics'
  outDir?: string
  /** Runtime Kit 公开导入白名单；省略时 worker 读取本地 manifest。 */
  runtimeKitAllowedImports?: string[]
}

interface SerializedWorkerError {
  name?: string
  message?: string
  stack?: string
  id?: string
  plugin?: string
  code?: string
  loc?: {
    file?: string
    line?: number
    column?: number
  }
}

interface RuntimeBuildWorkerOutput {
  success: boolean
  error?: SerializedWorkerError
}

interface RuntimeDiagnosticsWorkerMessage extends RuntimeBuildWorkerOutput {
  taskId: string
  rssBytes?: number
}

interface RuntimeDiagnosticsPendingTask {
  child: ChildProcess
  taskId: string
  resolve: () => void
  reject: (error: unknown) => void
  timeoutHandle: ReturnType<typeof setTimeout>
}

export interface RuntimeDiagnosticsWorkerOptions {
  tempRoot: string
  maxOldSpaceMb?: number
  timeoutMs?: number
  maxTasks?: number
  maxAgeMs?: number
  rssRecycleRatio?: number
  workerScriptSource?: string
}

interface RuntimeBuildWorkerExit {
  code: number | null
  signal: NodeJS.Signals | null
  stdout: string
  stderr: string
  timedOut: boolean
}

/**
 * Runtime 构建 worker 进程错误。
 */
export class RuntimeBuildWorkerProcessError extends Error {
  statusCode: number
  code: string
  stdout?: string
  stderr?: string

  constructor(statusCode: number, code: string, message: string, output?: { stdout?: string; stderr?: string }) {
    super(message)
    this.name = 'RuntimeBuildWorkerProcessError'
    this.statusCode = statusCode
    this.code = code
    this.stdout = output?.stdout
    this.stderr = output?.stderr
  }
}

/**
 * Runtime 构建 worker 中捕获到的 Vite 构建错误。
 */
export class RuntimeBuildWorkerViteError extends Error {
  code: string
  id?: string
  plugin?: string
  loc?: {
    file?: string
    line?: number
    column?: number
  }

  constructor(payload: SerializedWorkerError) {
    super(String(payload.message || 'Runtime Vite 构建失败。'))
    this.name = String(payload.name || 'RuntimeBuildWorkerViteError')
    this.stack = payload.stack
    this.code = String(payload.code || 'RUNTIME_VITE_COMPILE_FAILED')
    this.id = payload.id
    this.plugin = payload.plugin
    this.loc = payload.loc
  }
}

/**
 * 长期驻留的诊断 worker。每个实例只允许一个任务在途，调用方必须按工作区槽位串行使用。
 */
export class RuntimeDiagnosticsWorker {
  private readonly tempRoot: string
  private readonly maxOldSpaceMb: number
  private readonly timeoutMs: number
  private readonly maxTasks: number
  private readonly maxAgeMs: number
  private readonly rssRecycleRatio: number
  private readonly workerScriptSource?: string
  private child: ChildProcess | null = null
  private childStartedAt = 0
  private completedTasks = 0
  private stdout = ''
  private stderr = ''
  private pending: RuntimeDiagnosticsPendingTask | null = null
  private recycling: Promise<void> | null = null
  private pendingRecycleError: { pending: RuntimeDiagnosticsPendingTask; error: unknown } | null = null
  private closed = false

  constructor(options: RuntimeDiagnosticsWorkerOptions) {
    this.tempRoot = resolve(options.tempRoot)
    this.maxOldSpaceMb = normalizeWorkerMaxOldSpaceMb(options.maxOldSpaceMb)
    this.timeoutMs = normalizeDiagnosticsWorkerTimeoutMs(options.timeoutMs)
    this.maxTasks = normalizePositiveInteger(
      options.maxTasks,
      process.env.RUNTIME_DIAGNOSTICS_WORKER_MAX_TASKS,
      DEFAULT_DIAGNOSTICS_WORKER_MAX_TASKS,
    )
    this.maxAgeMs = normalizePositiveInteger(
      options.maxAgeMs,
      process.env.RUNTIME_DIAGNOSTICS_WORKER_MAX_AGE_MS,
      DEFAULT_DIAGNOSTICS_WORKER_MAX_AGE_MS,
    )
    this.rssRecycleRatio = normalizePositiveRatio(
      options.rssRecycleRatio,
      process.env.RUNTIME_DIAGNOSTICS_WORKER_RSS_RECYCLE_RATIO,
      DEFAULT_DIAGNOSTICS_WORKER_RSS_RATIO,
    )
    this.workerScriptSource = options.workerScriptSource
  }

  /**
   * 在常驻进程中执行一次只读 Vite 诊断构建。
   * @param base Vite base 配置
   * @param timeoutMs 本次端到端任务剩余时长，会收敛到 worker 配置上限
   */
  async run(base = './', timeoutMs?: number): Promise<void> {
    this.assertOpen()
    if (this.pending) {
      throw new RuntimeBuildWorkerProcessError(
        500,
        'RUNTIME_DIAGNOSTICS_WORKER_BUSY',
        'Runtime 诊断 worker 同时收到多个任务。',
      )
    }
    await this.waitForRecycle()
    await this.ensureChild()
    this.assertOpen()
    const child = this.child
    if (!child?.connected) {
      await this.recycle()
      throw new RuntimeBuildWorkerProcessError(
        500,
        'RUNTIME_DIAGNOSTICS_WORKER_FAILED',
        'Runtime 诊断 worker IPC 未连接。',
      )
    }

    const taskId = randomUUID()
    const taskTimeoutMs = resolveTaskTimeoutMs(timeoutMs, this.timeoutMs)
    await new Promise<void>((resolveTask, rejectTask) => {
      const timeoutHandle = setTimeout(() => {
        const error = new RuntimeBuildWorkerProcessError(
          504,
          'RUNTIME_BUILD_WORKER_TIMEOUT',
          'Runtime 诊断 worker 执行超时。',
          { stdout: this.stdout, stderr: this.stderr },
        )
        void this.failPendingAfterRecycle(child, taskId, error)
      }, taskTimeoutMs)
      this.pending = {
        child,
        taskId,
        resolve: resolveTask,
        reject: rejectTask,
        timeoutHandle,
      }
      child.send({ taskId, tempRoot: this.tempRoot, base, mode: 'diagnostics' }, error => {
        if (!error) {
          return
        }
        void this.failPendingAfterRecycle(
          child,
          taskId,
          new RuntimeBuildWorkerProcessError(
            500,
            'RUNTIME_DIAGNOSTICS_WORKER_FAILED',
            `Runtime 诊断 worker 发送任务失败：${error.message}`,
          ),
        )
      })
    })
  }

  /**
   * 主动终止 worker，并拒绝仍在执行的任务。
   */
  async close(): Promise<void> {
    if (this.closed) {
      await this.recycle()
      return
    }
    this.closed = true
    const pending = this.pending
    const error = new RuntimeBuildWorkerProcessError(
      503,
      'RUNTIME_DIAGNOSTICS_WORKER_CLOSED',
      'Runtime 诊断 worker 已关闭。',
    )
    this.rememberPendingRecycleError(pending, error)
    await this.recycle()
    this.rejectPendingIfCurrent(pending, error)
  }

  /**
   * 创建 IPC worker，并绑定协议与崩溃处理。
   */
  private async ensureChild(): Promise<void> {
    this.assertOpen()
    await this.waitForRecycle()
    this.assertOpen()
    if (this.child?.connected) {
      return
    }
    const workerRoot = resolve(this.tempRoot, '.runtime-worker')
    const workerScriptPath = resolve(workerRoot, 'runtime-diagnostics-worker.mjs')
    const childIdentity = resolveRuntimeBuildChildIdentity()
    await prepareChildWritableDir(workerRoot, childIdentity)
    this.assertOpen()
    await writeFile(
      workerScriptPath,
      this.workerScriptSource || createRuntimeDiagnosticsWorkerScript(),
      'utf-8',
    )
    this.assertOpen()
    const child = spawn(process.execPath, [
      `--max-old-space-size=${this.maxOldSpaceMb}`,
      workerScriptPath,
    ], {
      cwd: this.tempRoot,
      env: createRuntimeBuildChildEnv(),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
      ...toSpawnIdentityOptions(childIdentity),
    })
    this.child = child
    this.childStartedAt = Date.now()
    this.completedTasks = 0
    this.stdout = ''
    this.stderr = ''
    child.stdout?.on('data', chunk => {
      this.stdout = appendCapturedOutput(this.stdout, chunk)
    })
    child.stderr?.on('data', chunk => {
      this.stderr = appendCapturedOutput(this.stderr, chunk)
    })
    child.on('message', message => this.handleMessage(child, message))
    child.on('error', error => {
      const classified = toSpawnFailureError(error, childIdentity)
      const workerError = classified instanceof RuntimeBuildWorkerProcessError
        ? classified
        : new RuntimeBuildWorkerProcessError(
          500,
          'RUNTIME_DIAGNOSTICS_WORKER_FAILED',
          `Runtime 诊断 worker 启动失败：${error.message}。`,
          { stdout: this.stdout, stderr: this.stderr },
        )
      const pending = this.pending
      if (pending?.child === child) {
        void this.failPendingAfterRecycle(child, pending.taskId, workerError)
        return
      }
      void this.recycleChild(child)
    })
    child.on('exit', (code, signal) => {
      if (this.child !== child) {
        return
      }
      this.child = null
      const pending = this.pending
      if (pending?.child === child && this.pendingRecycleError?.pending === pending) {
        return
      }
      const oom = isRuntimeBuildWorkerOomFailure(this.stderr, code)
      this.rejectPendingForChild(
        child,
        new RuntimeBuildWorkerProcessError(
          500,
          oom ? 'RUNTIME_BUILD_WORKER_OOM' : 'RUNTIME_DIAGNOSTICS_WORKER_FAILED',
          oom
            ? 'Runtime 诊断 worker 内存不足或被 V8 终止。'
            : `Runtime 诊断 worker 异常退出：exitCode=${code ?? 'null'} signal=${signal ?? 'null'}。`,
          { stdout: this.stdout, stderr: this.stderr },
        ),
      )
    })
    if (this.closed) {
      await this.recycleChild(child)
      this.assertOpen()
    }
  }

  /**
   * 处理 worker 结构化结果，并按任务数、寿命和 RSS 判断是否轮换。
   */
  private handleMessage(child: ChildProcess, rawMessage: unknown): void {
    if (this.child !== child) {
      return
    }
    const message = rawMessage as RuntimeDiagnosticsWorkerMessage
    const pending = this.pending
    if (!pending || pending.child !== child) {
      return
    }
    if (this.pendingRecycleError?.pending === pending) {
      return
    }
    if (!message || message.taskId !== pending.taskId || typeof message.success !== 'boolean') {
      void this.failPendingAfterRecycle(
        child,
        pending.taskId,
        new RuntimeBuildWorkerProcessError(
          500,
          'RUNTIME_DIAGNOSTICS_WORKER_PROTOCOL_ERROR',
          'Runtime 诊断 worker 返回了无法匹配的协议消息。',
          { stdout: this.stdout, stderr: this.stderr },
        ),
      )
      return
    }

    void this.completePendingFromMessage(child, pending, message)
  }

  /**
   * 在收到匹配 IPC 结果后收敛任务；需要轮换时先等待旧进程完全退出。
   */
  private async completePendingFromMessage(
    child: ChildProcess,
    pending: RuntimeDiagnosticsPendingTask,
    message: RuntimeDiagnosticsWorkerMessage,
  ): Promise<void> {
    if (this.pending !== pending || this.child !== child) {
      return
    }
    this.pending = null
    clearTimeout(pending.timeoutHandle)
    this.completedTasks += 1
    const shouldRecycle = this.shouldRecycle(message.rssBytes)
    if (shouldRecycle) {
      await this.recycleChild(child)
    }
    if (message.success) {
      pending.resolve()
    } else if (message.error) {
      pending.reject(new RuntimeBuildWorkerViteError(message.error))
    } else {
      pending.reject(new RuntimeBuildWorkerProcessError(
        500,
        'RUNTIME_DIAGNOSTICS_WORKER_PROTOCOL_ERROR',
        'Runtime 诊断 worker 未返回错误详情。',
      ))
    }
  }

  /**
   * 判断常驻 worker 是否已达到轮换阈值。
   */
  private shouldRecycle(rssBytes?: number): boolean {
    const rssLimitBytes = this.maxOldSpaceMb * 1024 * 1024 * this.rssRecycleRatio
    return this.completedTasks >= this.maxTasks
      || Date.now() - this.childStartedAt >= this.maxAgeMs
      || (Number(rssBytes) > 0 && Number(rssBytes) >= rssLimitBytes)
  }

  /**
   * 失败后先停止对应 child，再拒绝任务，防止调用方提前释放工作区槽位。
   */
  private async failPendingAfterRecycle(child: ChildProcess, taskId: string, error: unknown): Promise<void> {
    const pending = this.pending
    if (!pending || pending.child !== child || pending.taskId !== taskId) {
      return
    }
    this.rememberPendingRecycleError(pending, error)
    await this.recycleChild(child)
    const pendingRecycleError = this.pendingRecycleError
    const rememberedError = pendingRecycleError?.pending === pending
      ? pendingRecycleError.error
      : error
    this.rejectPendingIfCurrent(pending, rememberedError)
  }

  /**
   * 仅拒绝当前仍归属指定 child 的任务，旧 child 事件不得影响新任务。
   */
  private rejectPendingForChild(child: ChildProcess, error: unknown): void {
    const pending = this.pending
    if (!pending || pending.child !== child) {
      return
    }
    this.rejectPendingIfCurrent(pending, error)
  }

  /**
   * 在对象仍是当前 pending 时清理计时器并完成拒绝。
   */
  private rejectPendingIfCurrent(pending: RuntimeDiagnosticsPendingTask | null, error: unknown): void {
    if (!pending || this.pending !== pending) {
      return
    }
    this.pending = null
    if (this.pendingRecycleError?.pending === pending) {
      this.pendingRecycleError = null
    }
    clearTimeout(pending.timeoutHandle)
    pending.reject(error)
  }

  /**
   * 记录导致回收的首个错误，避免 exit 事件把超时等精确错误覆盖为通用崩溃。
   */
  private rememberPendingRecycleError(pending: RuntimeDiagnosticsPendingTask | null, error: unknown): void {
    if (!pending || this.pending !== pending || this.pendingRecycleError?.pending === pending) {
      return
    }
    this.pendingRecycleError = { pending, error }
  }

  /**
   * 等待上一轮回收完成，避免同一槽位出现新旧两个 Node 进程。
   */
  private async waitForRecycle(): Promise<void> {
    if (this.recycling) {
      await this.recycling
    }
  }

  /**
   * 已关闭的 worker 不得重新拉起 child，避免工作区销毁后遗留孤儿进程。
   */
  private assertOpen(): void {
    if (this.closed) {
      throw new RuntimeBuildWorkerProcessError(
        503,
        'RUNTIME_DIAGNOSTICS_WORKER_CLOSED',
        'Runtime 诊断 worker 已关闭。',
      )
    }
  }

  /**
   * 回收当前 child，并在真正收到 exit 前保持工作区占用。
   */
  private async recycle(): Promise<void> {
    const child = this.child
    if (child) {
      await this.recycleChild(child)
    } else {
      await this.waitForRecycle()
    }
  }

  /**
   * 终止指定 child；先温和终止，超时后强制终止，并始终等待 exit。
   */
  private recycleChild(child: ChildProcess): Promise<void> {
    if (this.child !== child || child.exitCode !== null || child.signalCode !== null) {
      if (this.child === child) {
        this.child = null
      }
      return Promise.resolve()
    }
    if (this.recycling) {
      return this.recycling
    }

    const recycling = waitForChildExitAfterTermination(child)
      .finally(() => {
        if (this.child === child) {
          this.child = null
        }
        if (this.recycling === recycling) {
          this.recycling = null
        }
      })
    this.recycling = recycling
    return recycling
  }
}

/**
 * 请求 child 退出并等待真实 exit；超出宽限时间后使用 SIGKILL，避免只释放信号量而进程仍运行。
 */
async function waitForChildExitAfterTermination(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) {
    return
  }
  await new Promise<void>(resolveExit => {
    let forceTimer: ReturnType<typeof setTimeout> | null = null
    const finish = () => {
      if (forceTimer) {
        clearTimeout(forceTimer)
      }
      resolveExit()
    }
    child.once('exit', finish)
    try {
      child.kill('SIGTERM')
    } catch {
      // 终止调用失败时仍等待 exit；下一轮强制终止会再次尝试。
    }
    forceTimer = setTimeout(() => {
      if (child.exitCode !== null || child.signalCode !== null) {
        finish()
        return
      }
      try {
        child.kill('SIGKILL')
      } catch {
        // 保持 exit 监听，绝不把仍存活的进程视为已回收。
      }
    }, WORKER_STOP_GRACE_MS)
  })
}

/**
 * 在子进程中执行 Runtime Vite 构建。
 * @param options worker 执行参数
 */
export async function runRuntimeViteBuildInWorker(options: RuntimeBuildWorkerRunOptions): Promise<void> {
  // 正式构建必须可被中止：租约失守后继续编译是最贵的僵尸计算，
  // 缺信号属于接线错误，必须在这里响亮失败，而不是退化成只能等超时。
  if (options.mode === 'project') {
    requireAbortSignal(options.signal, 'Runtime 正式构建')
  }
  throwIfSignalAborted(options.signal)
  const tempRoot = resolve(options.tempRoot)
  const taskRoot = options.taskRoot
    ? resolve(options.taskRoot)
    : resolve(tempRoot, '.runtime-task', randomUUID())
  const childIdentity = resolveRuntimeBuildChildIdentity()
  await prepareChildWritableDir(taskRoot, childIdentity)
  const inputPath = resolve(taskRoot, 'runtime-build-worker-input.json')
  const outputPath = resolve(taskRoot, 'runtime-build-worker-output.json')
  const workerScriptPath = resolve(taskRoot, 'runtime-build-worker.mjs')
  const workerInput: RuntimeBuildWorkerInput = {
    tempRoot,
    base: options.base,
    mode: options.mode,
    outDir: options.outDir ? resolve(options.outDir) : undefined,
    runtimeKitAllowedImports: options.runtimeKitAllowedImports,
  }

  await writeFile(inputPath, JSON.stringify(workerInput), 'utf-8')
  await writeFile(workerScriptPath, options.workerScriptSource || createRuntimeBuildWorkerScript(), 'utf-8')

  let exit: RuntimeBuildWorkerExit
  try {
    exit = await spawnRuntimeBuildWorker({
      workerScriptPath,
      inputPath,
      outputPath,
      cwd: tempRoot,
      maxOldSpaceMb: normalizeWorkerMaxOldSpaceMb(options.maxOldSpaceMb),
      timeoutMs: normalizeWorkerTimeoutMs(options.timeoutMs),
      signal: options.signal,
      identity: childIdentity,
    })
  } catch (error) {
    throwIfSignalAborted(options.signal)
    // 降权 EPERM 等已分类错误不得被通用「启动失败」覆盖，否则排障只剩 exitCode。
    if (error instanceof RuntimeBuildWorkerProcessError) {
      throw error
    }
    throw new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_BUILD_WORKER_FAILED',
      error instanceof Error ? error.message : 'Runtime 构建 worker 启动失败。',
    )
  }
  // 子进程被中止信号终止时不得读取残留输出：必须保持租约失守语义，
  // 否则一次外部中止会被误报成构建失败。
  throwIfSignalAborted(options.signal)
  const output = await readWorkerOutput(outputPath)

  if (output?.success) {
    return
  }
  if (output?.error) {
    throw new RuntimeBuildWorkerViteError(output.error)
  }
  throw buildWorkerProcessError(exit)
}

/**
 * 在独立子进程中把 dist 目录打成 ZIP，避免同步压缩阻塞 Runtime 主进程（预览事件循环）。
 * @param options 归档参数
 * @returns 归档产物摘要与阶段耗时
 */
export async function runZipArchiveInWorker(options: RuntimeZipArchiveOptions): Promise<RuntimeZipArchiveResult> {
  // 归档只服务于正式构建链路，同样必须能被租约失守立即终止。
  requireAbortSignal(options.signal, 'Runtime 归档')
  throwIfSignalAborted(options.signal)
  const distRoot = resolve(options.distRoot)
  const outputPath = resolve(options.outputPath)
  const compressionLevel = normalizeArchiveCompressionLevel(options.compressionLevel)
  const taskRoot = resolve(outputPath, '..', '.runtime-archive')
  const childIdentity = resolveRuntimeBuildChildIdentity()
  await prepareChildWritableDir(taskRoot, childIdentity)
  const inputPath = resolve(taskRoot, 'runtime-archive-worker-input.json')
  const workerOutputPath = resolve(taskRoot, 'runtime-archive-worker-output.json')
  const workerScriptPath = resolve(taskRoot, 'runtime-archive-worker.mjs')
  const workerInput = {
    distRoot,
    outputPath,
    compressionLevel,
  }

  await writeFile(inputPath, JSON.stringify(workerInput), 'utf-8')
  await writeFile(
    workerScriptPath,
    options.workerScriptSource || createRuntimeArchiveWorkerScript(),
    'utf-8',
  )

  let exit: RuntimeBuildWorkerExit
  try {
    exit = await spawnRuntimeBuildWorker({
      workerScriptPath,
      inputPath,
      outputPath: workerOutputPath,
      cwd: taskRoot,
      maxOldSpaceMb: normalizeWorkerMaxOldSpaceMb(options.maxOldSpaceMb),
      timeoutMs: normalizeArchiveWorkerTimeoutMs(options.timeoutMs),
      signal: options.signal,
      identity: childIdentity,
    })
  } catch (error) {
    throwIfSignalAborted(options.signal)
    if (error instanceof RuntimeBuildWorkerProcessError) {
      throw error
    }
    throw new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_ARCHIVE_WORKER_FAILED',
      error instanceof Error ? error.message : 'Runtime 归档 worker 启动失败。',
    )
  }

  throwIfSignalAborted(options.signal)
  const output = await readArchiveWorkerOutput(workerOutputPath)
  if (output?.success && output.archive) {
    return {
      archivePath: String(output.archive.path),
      sha256: String(output.archive.sha256),
      sizeBytes: Number(output.archive.sizeBytes),
      fileCount: Number(output.archive.fileCount || 0),
      durationMs: Number(output.archive.durationMs || 0),
      rssBytes: Number(output.archive.rssBytes || 0),
      compressionLevel,
    }
  }
  if (output?.error) {
    throw new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_ARCHIVE_WORKER_FAILED',
      String(output.error.message || 'Runtime ZIP 归档失败。'),
      { stdout: exit.stdout, stderr: exit.stderr },
    )
  }
  throw buildWorkerProcessError(exit)
}

/**
 * 解析归档压缩级别；默认 6，避免无差别使用最高压缩拖慢构建。
 * 显式 0 表示不压缩，空环境变量不得被当成 0。
 */
export function normalizeArchiveCompressionLevel(explicitValue?: number): number {
  if (Number.isInteger(explicitValue) && Number(explicitValue) >= 0 && Number(explicitValue) <= 9) {
    return Number(explicitValue)
  }
  const rawEnv = String(process.env.RUNTIME_ARCHIVE_COMPRESSION_LEVEL || '').trim()
  if (rawEnv !== '') {
    const fromEnv = Number(rawEnv)
    if (Number.isInteger(fromEnv) && fromEnv >= 0 && fromEnv <= 9) {
      return fromEnv
    }
  }
  return DEFAULT_ARCHIVE_COMPRESSION_LEVEL
}

/**
 * 解析归档 worker 超时时间。
 */
export function normalizeArchiveWorkerTimeoutMs(explicitValue?: number): number {
  return normalizePositiveInteger(
    explicitValue,
    process.env.RUNTIME_ARCHIVE_WORKER_TIMEOUT_MS,
    DEFAULT_ARCHIVE_WORKER_TIMEOUT_MS,
  )
}

interface RuntimeArchiveWorkerOutput {
  success: boolean
  error?: { message?: string }
  archive?: {
    path: string
    sha256: string
    sizeBytes: number
    fileCount: number
    durationMs: number
    rssBytes: number
  }
}

/**
 * 读取归档 worker 结构化结果。
 */
async function readArchiveWorkerOutput(outputPath: string): Promise<RuntimeArchiveWorkerOutput | null> {
  try {
    return JSON.parse(await readFile(outputPath, 'utf-8')) as RuntimeArchiveWorkerOutput
  } catch {
    return null
  }
}

/**
 * 生成可被 Node 直接执行的 ZIP 归档 worker 脚本。
 * @returns ESM worker 脚本文本
 */
export function createRuntimeArchiveWorkerScript(): string {
  return [
    '/**',
    ' * 文件用途：Runtime 临时归档 worker，在独立 Node 进程内将 dist 打包为 ZIP 并计算摘要。',
    ' */',
    "import { createHash } from 'node:crypto'",
    "import { readdir, readFile, writeFile } from 'node:fs/promises'",
    "import { resolve, sep } from 'node:path'",
    "import { zipSync } from 'fflate'",
    '',
    'async function collectEntries(rootDir, currentDir, archiveEntries) {',
    '  const entries = await readdir(currentDir, { withFileTypes: true })',
    '  for (const entry of entries) {',
    '    const entryPath = resolve(currentDir, entry.name)',
    '    if (entry.isDirectory()) {',
    '      await collectEntries(rootDir, entryPath, archiveEntries)',
    '      continue',
    '    }',
    '    const entryBytes = await readFile(entryPath)',
    '    const relativePath = entryPath',
    '      .replace(rootDir, "")',
    '      .replace(/^[\\\\/]+/, "")',
    '      .split(sep)',
    '      .join("/")',
    '    archiveEntries[relativePath] = new Uint8Array(entryBytes)',
    '  }',
    '}',
    '',
    'async function main() {',
    '  const inputPath = process.argv[2]',
    '  const outputPath = process.argv[3]',
    '  const input = JSON.parse(await readFile(inputPath, "utf-8"))',
    '  const startedAt = Date.now()',
    '  try {',
    '    const archiveEntries = {}',
    '    await collectEntries(input.distRoot, input.distRoot, archiveEntries)',
    '    const zipped = zipSync(archiveEntries, { level: input.compressionLevel })',
    '    await writeFile(input.outputPath, zipped)',
    '    const sha256 = createHash("sha256").update(zipped).digest("hex")',
    '    await writeFile(outputPath, JSON.stringify({',
    '      success: true,',
    '      archive: {',
    '        path: input.outputPath,',
    '        sha256,',
    '        sizeBytes: zipped.length,',
    '        fileCount: Object.keys(archiveEntries).length,',
    '        durationMs: Date.now() - startedAt,',
    '        rssBytes: process.memoryUsage().rss,',
    '      },',
    '    }), "utf-8")',
    '  } catch (error) {',
    '    await writeFile(outputPath, JSON.stringify({',
    '      success: false,',
    '      error: { message: String(error?.message || error || "Runtime ZIP 归档失败。") },',
    '    }), "utf-8")',
    '    process.exitCode = 1',
    '  }',
    '}',
    '',
    'await main()',
    '',
  ].join('\n')
}

/**
 * 解析 worker 进程堆内存上限。
 * @param explicitValue 显式传入值
 * @returns MB 数
 */
export function normalizeWorkerMaxOldSpaceMb(explicitValue?: number): number {
  return normalizePositiveInteger(
    explicitValue,
    process.env.RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB,
    DEFAULT_WORKER_MAX_OLD_SPACE_MB,
  )
}

/**
 * 解析 worker 进程超时时间。
 * @param explicitValue 显式传入值
 * @returns 毫秒数
 */
export function normalizeWorkerTimeoutMs(explicitValue?: number): number {
  return normalizePositiveInteger(
    explicitValue,
    process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS,
    DEFAULT_WORKER_TIMEOUT_MS,
  )
}

/**
 * 解析诊断 worker 的单任务超时，和正式构建的 600 秒上限分开管理。
 */
export function normalizeDiagnosticsWorkerTimeoutMs(explicitValue?: number): number {
  return normalizePositiveInteger(
    explicitValue,
    process.env.RUNTIME_DIAGNOSTICS_WORKER_TIMEOUT_MS,
    DEFAULT_DIAGNOSTICS_WORKER_TIMEOUT_MS,
  )
}

/**
 * 判断 worker 退出信息是否符合 Node/V8 OOM 特征。
 * @param stderr 标准错误输出
 * @param exitCode 进程退出码
 * @returns 是否为 OOM 失败
 */
export function isRuntimeBuildWorkerOomFailure(stderr: string, exitCode?: number | null): boolean {
  const normalizedStderr = String(stderr || '').toLowerCase()
  return exitCode === 134
    || normalizedStderr.includes('javascript heap out of memory')
    || normalizedStderr.includes('ineffective mark-compacts near heap limit')
    || normalizedStderr.includes('allocation failed')
}

/**
 * 生成可被 Node 直接执行的构建 worker 脚本。
 * @returns ESM worker 脚本文本
 */
export function createRuntimeBuildWorkerScript(): string {
  return [
    '/**',
    ' * 文件用途：Runtime 临时构建 worker，在独立 Node 进程内执行 Vite/Rollup 构建。',
    ' */',
    "import { readFile, writeFile } from 'node:fs/promises'",
    "import { resolve } from 'node:path'",
    "import { build as viteBuild } from 'vite'",
    "import vue from '@vitejs/plugin-vue'",
    "import tailwindcss from 'tailwindcss'",
    "import autoprefixer from 'autoprefixer'",
    '',
    'function buildRuntimeBuildCssConfig(tempRoot) {',
    '  return {',
    '    modules: { localsConvention: "camelCase" },',
    '    postcss: {',
    '      plugins: [',
    '        tailwindcss(resolve(tempRoot, "tailwind.config.js")),',
    '        autoprefixer(),',
    '      ],',
    '    },',
    '  }',
    '}',
    '',
    'function serializeError(error) {',
    '  return {',
    '    name: error?.name,',
    '    message: String(error?.message || error || "Runtime Vite 构建失败。"),',
    '    stack: error?.stack,',
    '    id: error?.id,',
    '    plugin: error?.plugin,',
    '    code: error?.code,',
    '    loc: error?.loc ? {',
    '      file: error.loc.file,',
    '      line: error.loc.line,',
    '      column: error.loc.column,',
    '    } : undefined,',
    '  }',
    '}',
    '',
    createRuntimeKitImportGatePluginSource(),
    'function createBuildOptions(input) {',
    '  const tempRoot = input.tempRoot',
    '  const buildOptions = {',
    '    emptyOutDir: false,',
    '    sourcemap: false,',
    '    rollupOptions: {',
    '      output: {',
    '        manualChunks(id) {',
    '          if (id.includes("/node_modules/vue/") || id.includes("/node_modules/vue-router/")) {',
    '            return "vendor"',
    '          }',
    '          return undefined',
    '        },',
    '      },',
    '    },',
    '  }',
    '  if (input.mode === "diagnostics") {',
    '    buildOptions.write = false',
    '  } else {',
    '    buildOptions.outDir = input.outDir',
    '  }',
    '  return {',
    '    configFile: false,',
    '    root: tempRoot,',
    '    base: input.base,',
    '    define: { __RUNTIME_BACKEND_BUILD__: "true" },',
    '    plugins: [vue(), createRuntimeKitImportGatePlugin(input.runtimeKitAllowedImports, tempRoot)],',
    '    assetsInclude: ["**/*.drawio"],',
    '    resolve: {',
    '      alias: {',
    '        "@": resolve(tempRoot, "src"),',
    '        "@runtime-kit": resolve(tempRoot, "src/runtime-kit"),',
    '        "@components": resolve(tempRoot, "src/components"),',
    '        "@views": resolve(tempRoot, "src/views"),',
    '        "@workspace-components": resolve(tempRoot, "src/workspace-components"),',
    '        "@utils": resolve(tempRoot, "src/utils"),',
    '        "@types": resolve(tempRoot, "src/types"),',
    '        "@styles": resolve(tempRoot, "src/styles"),',
    '      },',
    '      extensions: [".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json", ".vue"],',
    '    },',
    '    css: buildRuntimeBuildCssConfig(tempRoot),',
    '    build: buildOptions,',
    '  }',
    '}',
    '',
    'async function main() {',
    '  const inputPath = process.argv[2]',
    '  const outputPath = process.argv[3]',
    '  const input = JSON.parse(await readFile(inputPath, "utf-8"))',
    '  try {',
    '    await viteBuild(createBuildOptions(input))',
    '    await writeFile(outputPath, JSON.stringify({ success: true }), "utf-8")',
    '  } catch (error) {',
    '    await writeFile(outputPath, JSON.stringify({ success: false, error: serializeError(error) }), "utf-8")',
    '    process.exitCode = 1',
    '  }',
    '}',
    '',
    'await main()',
    '',
  ].join('\n')
}

/**
 * 生成构建 worker 内嵌的 Runtime Kit 导入门禁 Vite 插件源码。
 * 第二道闸：拒绝 internal/、未版本化与不在白名单中的 @runtime-kit 导入。
 * 白名单优先取 Backend 下发的 runtime_kit_exports；否则读取本地 manifest。
 */
function createRuntimeKitImportGatePluginSource(): string {
  return [
    'async function loadLocalRuntimeKitAllowedImports(tempRoot) {',
    '  try {',
    '    const { readFile } = await import("node:fs/promises")',
    '    const { resolve } = await import("node:path")',
    '    const manifestPath = resolve(tempRoot, "src/runtime-kit/manifest/runtime-kit.manifest.json")',
    '    const raw = await readFile(manifestPath, "utf-8")',
    '    const manifest = JSON.parse(raw)',
    '    return (manifest.exports || [])',
    '      .map((item) => String(item?.import_path || "").trim())',
    '      .filter((path) => path.startsWith("@runtime-kit/"))',
    '  } catch {',
    '    return []',
    '  }',
    '}',
    '',
    'function createRuntimeKitImportGatePlugin(allowedImports, tempRoot) {',
    '  let allowed = new Set(Array.isArray(allowedImports) ? allowedImports : [])',
    '  let ready = allowed.size > 0',
    '  const VERSIONED = /\\.v\\d+(?:\\.[A-Za-z0-9]+)?$/',
    '  const FORBIDDEN = ["/internal/", "/runtime-shell/", "/component-preview", "/PDF"]',
    '  async function ensureAllowed() {',
    '    if (ready) return',
    '    const local = await loadLocalRuntimeKitAllowedImports(tempRoot)',
    '    allowed = new Set(local)',
    '    ready = true',
    '  }',
    '  function decide(source) {',
    '    const normalized = String(source || "").trim().replace(/\\\\/g, "/")',
    '    if (!normalized.startsWith("@runtime-kit/")) return null',
    '    for (const fragment of FORBIDDEN) {',
    '      if (normalized.includes(fragment)) {',
    '        return `Runtime Kit 不允许导入内部路径：${normalized}`',
    '      }',
    '    }',
    '    if (!VERSIONED.test(normalized)) {',
    '      return `Runtime Kit 导入必须带 .vN 版本后缀：${normalized}`',
    '    }',
    '    if (ready && allowed.size > 0 && !allowed.has(normalized)) {',
    '      return `Runtime Kit 导入不在公开白名单中：${normalized}`',
    '    }',
    '    return null',
    '  }',
    '  return {',
    '    name: "runtime-kit-import-gate",',
    '    enforce: "pre",',
    '    async buildStart() {',
    '      await ensureAllowed()',
    '    },',
    '    async resolveId(source) {',
    '      await ensureAllowed()',
    '      const reason = decide(source)',
    '      if (reason) {',
    '        const error = new Error(reason)',
    '        error.code = "RUNTIME_LOCAL_IMPORT_FORBIDDEN"',
    '        throw error',
    '      }',
    '      return null',
    '    },',
    '  }',
    '}',
    '',
  ].join('\n')
}

/**
 * 生成长期诊断 worker 脚本；每个 IPC 消息都创建全新的 Vite 配置和插件实例。
 */
export function createRuntimeDiagnosticsWorkerScript(): string {
  return [
    '/**',
    ' * 文件用途：长期驻留的 Runtime 诊断 worker，通过 IPC 串行执行独立 Vite 构建。',
    ' */',
    "import { resolve } from 'node:path'",
    "import { readFile } from 'node:fs/promises'",
    "import { build as viteBuild } from 'vite'",
    "import vue from '@vitejs/plugin-vue'",
    "import tailwindcss from 'tailwindcss'",
    "import autoprefixer from 'autoprefixer'",
    '',
    'function serializeError(error) {',
    '  return {',
    '    name: error?.name,',
    '    message: String(error?.message || error || "Runtime Vite 构建失败。"),',
    '    stack: error?.stack,',
    '    id: error?.id,',
    '    plugin: error?.plugin,',
    '    code: error?.code,',
    '    loc: error?.loc ? {',
    '      file: error.loc.file,',
    '      line: error.loc.line,',
    '      column: error.loc.column,',
    '    } : undefined,',
    '  }',
    '}',
    '',
    createRuntimeKitImportGatePluginSource(),
    'function createOptions(input) {',
    '  const tempRoot = input.tempRoot',
    '  return {',
    '    configFile: false,',
    '    root: tempRoot,',
    '    base: input.base,',
    '    define: { __RUNTIME_BACKEND_BUILD__: "true" },',
    '    plugins: [vue(), createRuntimeKitImportGatePlugin(input.runtimeKitAllowedImports, tempRoot)],',
    '    assetsInclude: ["**/*.drawio"],',
    '    resolve: {',
    '      alias: {',
    '        "@": resolve(tempRoot, "src"),',
    '        "@runtime-kit": resolve(tempRoot, "src/runtime-kit"),',
    '        "@components": resolve(tempRoot, "src/components"),',
    '        "@views": resolve(tempRoot, "src/views"),',
    '        "@workspace-components": resolve(tempRoot, "src/workspace-components"),',
    '        "@utils": resolve(tempRoot, "src/utils"),',
    '        "@types": resolve(tempRoot, "src/types"),',
    '        "@styles": resolve(tempRoot, "src/styles"),',
    '      },',
    '      extensions: [".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json", ".vue"],',
    '    },',
    '    css: {',
    '      modules: { localsConvention: "camelCase" },',
    '      postcss: { plugins: [tailwindcss(resolve(tempRoot, "tailwind.config.js")), autoprefixer()] },',
    '    },',
    '    build: {',
    '      emptyOutDir: false,',
    '      sourcemap: false,',
    '      write: false,',
    '      rollupOptions: {',
    '        output: {',
    '          manualChunks(id) {',
    '            if (id.includes("/node_modules/vue/") || id.includes("/node_modules/vue-router/")) return "vendor"',
    '            return undefined',
    '          },',
    '        },',
    '      },',
    '    },',
    '  }',
    '}',
    '',
    'let running = false',
    'process.on("message", async input => {',
    '  if (running || !input?.taskId) {',
    '    process.send?.({ taskId: input?.taskId || "", success: false, error: { code: "RUNTIME_DIAGNOSTICS_WORKER_BUSY", message: "诊断 worker 当前不可用。" } })',
    '    return',
    '  }',
    '  running = true',
    '  try {',
    '    await viteBuild(createOptions(input))',
    '    process.send?.({ taskId: input.taskId, success: true, rssBytes: process.memoryUsage().rss })',
    '  } catch (error) {',
    '    process.send?.({ taskId: input.taskId, success: false, error: serializeError(error), rssBytes: process.memoryUsage().rss })',
    '  } finally {',
    '    running = false',
    '  }',
    '})',
    '',
  ].join('\n')
}

interface SpawnRuntimeBuildWorkerOptions {
  workerScriptPath: string
  inputPath: string
  outputPath: string
  cwd: string
  maxOldSpaceMb: number
  timeoutMs: number
  /** 外部中止信号：触发后立即终止子进程，不等待其自然结束。 */
  signal?: AbortSignal
  /** 子进程降权身份；省略时从环境解析。 */
  identity?: RuntimeBuildChildIdentity
}

/**
 * 启动 Node worker 进程并等待退出。
 *
 * 超时与外部中止走同一条终止路径：先 SIGTERM，宽限期内未退出再 SIGKILL，
 * 并始终等到 close 才落定 promise。只中止主进程的 await 而不杀子进程，
 * 会让租约失守后的 Vite/ZIP 阶段继续占用 CPU、内存与调度槽位。
 * @param options 进程参数
 * @returns 退出摘要
 */
function spawnRuntimeBuildWorker(options: SpawnRuntimeBuildWorkerOptions): Promise<RuntimeBuildWorkerExit> {
  const abortSignal = options.signal
  if (abortSignal?.aborted) {
    return Promise.reject(toAbortError(abortSignal.reason))
  }
  return new Promise((resolve, reject) => {
    const identity = options.identity ?? resolveRuntimeBuildChildIdentity()
    const child = spawn(process.execPath, [
      `--max-old-space-size=${options.maxOldSpaceMb}`,
      options.workerScriptPath,
      options.inputPath,
      options.outputPath,
    ], {
      cwd: options.cwd,
      env: createRuntimeBuildChildEnv(),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      ...toSpawnIdentityOptions(identity),
    })
    let stdout = ''
    let stderr = ''
    let timedOut = false
    let forceKillTimer: ReturnType<typeof setTimeout> | null = null
    const clearTimers = () => {
      if (forceKillTimer) {
        clearTimeout(forceKillTimer)
        forceKillTimer = null
      }
      clearTimeout(timeoutHandle)
      abortSignal?.removeEventListener('abort', onAbort)
    }
    /**
     * 请求子进程退出，并在宽限期后强制终止。
     * 子进程若忽略 SIGTERM，必须升级 SIGKILL；否则 promise 永不落定，
     * 调度器槽位与临时工作区都会泄漏（M5）。
     */
    const terminate = () => {
      if (child.exitCode !== null || child.signalCode !== null) {
        return
      }
      try {
        child.kill('SIGTERM')
      } catch {
        // 终止调用失败时仍等待 exit / 强制终止。
      }
      if (forceKillTimer) {
        return
      }
      forceKillTimer = setTimeout(() => {
        forceKillTimer = null
        if (child.exitCode !== null || child.signalCode !== null) {
          return
        }
        try {
          child.kill('SIGKILL')
        } catch {
          // 保持 close 监听，绝不把仍存活的进程视为已回收。
        }
      }, WORKER_STOP_GRACE_MS)
    }
    const onAbort = () => terminate()
    const timeoutHandle = setTimeout(() => {
      timedOut = true
      terminate()
    }, options.timeoutMs)
    abortSignal?.addEventListener('abort', onAbort, { once: true })

    child.stdout.on('data', chunk => {
      stdout = appendCapturedOutput(stdout, chunk)
    })
    child.stderr.on('data', chunk => {
      stderr = appendCapturedOutput(stderr, chunk)
    })
    child.on('error', error => {
      clearTimers()
      reject(toSpawnFailureError(error, identity))
    })
    child.on('close', (code, signal) => {
      clearTimers()
      resolve({ code, signal, stdout, stderr, timedOut })
    })
  })
}

/**
 * 把 spawn 失败转换为可操作的错误；降权 EPERM 必须指向 CAP_SETUID/根因，
 * 否则会退化成三次 attempt 全灭后才暴露的通用「启动失败」。
 * @param error 原始 spawn 错误
 * @param identity 请求的子进程降权身份
 * @returns 结构化错误
 */
export function toSpawnFailureError(error: unknown, identity: RuntimeBuildChildIdentity): Error {
  const errno = error as NodeJS.ErrnoException
  const dropPrivilegeRequested = identity.uid != null || identity.gid != null
  if (dropPrivilegeRequested && (errno?.code === 'EPERM' || errno?.code === 'EACCES')) {
    return new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_BUILD_CHILD_IDENTITY_EPERM',
      `构建子进程降权失败（${errno.code}）：当前进程无权 setuid/setgid 到 `
        + `uid=${identity.uid ?? 'unchanged'} gid=${identity.gid ?? 'unchanged'}。`
        + '主进程必须以 root 运行才能降权（compose cap_add 对非 root 无效）。'
        + '或清空 RUNTIME_BUILD_CHILD_UID/GID 退回仅删环境变量的受限形态（不能关闭 W01）。',
      { stdout: String(errno.message || error || '') },
    )
  }
  return error instanceof Error ? error : new Error(String(error))
}

/**
 * 把外部中止信号转换成可直接抛出的错误；signal.reason 已是任务级错误时原样复用。
 * @param reason AbortSignal.reason
 * @returns 中止错误
 */
function toAbortError(reason: unknown): Error {
  if (reason instanceof Error) {
    return reason
  }
  return new RuntimeTaskAbortedError(String(reason || 'Runtime 任务已中止。'))
}

/**
 * 在中止信号已触发时立即抛出，避免继续启动子进程或读取其残留输出。
 * @param signal 外部中止信号
 */
function throwIfSignalAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw toAbortError(signal.reason)
  }
}

/**
 * 要求调用方为不可回退的重计算阶段接上中止信号。
 *
 * 子进程一旦启动就无法被「只中止 await」收回，缺少信号会让租约失守后的
 * Vite/ZIP 阶段继续烧 CPU 与内存直到自身超时，属于必须暴露的接线错误。
 * @param signal 外部中止信号
 * @param stage 阶段名称，用于错误消息定位
 */
function requireAbortSignal(signal: AbortSignal | undefined, stage: string): void {
  if (!signal) {
    throw new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_BUILD_WORKER_SIGNAL_REQUIRED',
      `${stage}必须传入中止信号，否则租约失守后无法终止子进程。`,
    )
  }
}

/**
 * 读取 worker 写出的结构化结果。
 * @param outputPath 输出文件路径
 * @returns worker 输出；文件不存在时返回 null
 */
async function readWorkerOutput(outputPath: string): Promise<RuntimeBuildWorkerOutput | null> {
  try {
    return JSON.parse(await readFile(outputPath, 'utf-8')) as RuntimeBuildWorkerOutput
  } catch {
    return null
  }
}

/**
 * 根据 worker 退出信息构建主进程可处理的错误。
 * @param exit worker 退出摘要
 * @returns 结构化错误
 */
function buildWorkerProcessError(exit: RuntimeBuildWorkerExit): RuntimeBuildWorkerProcessError {
  const output = { stdout: exit.stdout, stderr: exit.stderr }
  if (exit.timedOut) {
    return new RuntimeBuildWorkerProcessError(
      504,
      'RUNTIME_BUILD_WORKER_TIMEOUT',
      'Runtime 构建 worker 执行超时。',
      output,
    )
  }
  if (isRuntimeBuildWorkerOomFailure(exit.stderr, exit.code)) {
    return new RuntimeBuildWorkerProcessError(
      500,
      'RUNTIME_BUILD_WORKER_OOM',
      'Runtime 构建 worker 内存不足或被 V8 终止。',
      output,
    )
  }
  return new RuntimeBuildWorkerProcessError(
    500,
    'RUNTIME_BUILD_WORKER_FAILED',
    `Runtime 构建 worker 异常退出：exitCode=${exit.code ?? 'null'} signal=${exit.signal ?? 'null'}。`,
    output,
  )
}

/**
 * 追加并裁剪子进程输出，避免异常日志占用过多主进程内存。
 * @param current 当前已捕获输出
 * @param chunk 新输出
 * @returns 裁剪后的输出
 */
function appendCapturedOutput(current: string, chunk: unknown): string {
  const next = current + String(chunk || '')
  if (next.length <= MAX_CAPTURED_OUTPUT_LENGTH) {
    return next
  }
  return next.slice(next.length - MAX_CAPTURED_OUTPUT_LENGTH)
}

/**
 * 解析正整数配置。
 * @param explicitValue 显式值
 * @param rawEnv 环境变量值
 * @param fallback 默认值
 * @returns 正整数
 */
function normalizePositiveInteger(explicitValue: number | undefined, rawEnv: string | undefined, fallback: number): number {
  const explicit = Number(explicitValue)
  if (Number.isInteger(explicit) && explicit > 0) {
    return explicit
  }

  const fromEnv = Number(String(rawEnv || '').trim())
  if (Number.isInteger(fromEnv) && fromEnv > 0) {
    return fromEnv
  }

  return fallback
}

/**
 * 解析 0 到 1 之间的比例配置。
 */
function normalizePositiveRatio(explicitValue: number | undefined, rawEnv: string | undefined, fallback: number): number {
  const values = [Number(explicitValue), Number(String(rawEnv || '').trim())]
  for (const value of values) {
    if (Number.isFinite(value) && value > 0 && value <= 1) {
      return value
    }
  }
  return fallback
}

/**
 * 将本次剩余 deadline 限制在 worker 配置上限内，避免 Vite 子进程越过端到端执行预算。
 */
function resolveTaskTimeoutMs(requestedTimeoutMs: number | undefined, configuredTimeoutMs: number): number {
  const requested = Math.floor(Number(requestedTimeoutMs))
  if (!Number.isFinite(requested) || requested <= 0) {
    return configuredTimeoutMs
  }
  return Math.min(configuredTimeoutMs, requested)
}
