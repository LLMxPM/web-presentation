/**
 * 文件用途：复用 Runtime 诊断基础工作区，并为每个任务提供隔离目录、路径守卫与常驻 Vite worker。
 */

import { createHash, randomUUID } from 'crypto'
import { constants as fsConstants } from 'fs'
import {
  access,
  cp,
  mkdir,
  mkdtemp,
  readdir,
  rm,
  stat,
  symlink,
  writeFile,
} from 'fs/promises'
import os from 'os'
import { isAbsolute, join, relative, resolve, sep } from 'path'

import { normalizeRuntimeModulePath } from '../shared/runtime-preview'
import {
  RuntimeBuildWorkerProcessError,
  RuntimeDiagnosticsWorker,
  normalizeDiagnosticsWorkerTimeoutMs,
  runRuntimeViteBuildInWorker,
} from './runtime-build-worker'

const COPY_TARGETS = [
  'src',
  'index.html',
  'postcss.config.js',
  'tailwind.config.js',
  'tsconfig.json',
  'tsconfig.app.json',
  'tsconfig.node.json',
]
const RESET_DIRECTORIES = ['src/views', 'src/workspace-components']
const RESET_FILES = [
  'src/__build_entry__.ts',
  'src/core/utils/build-release-view-modules.ts',
  'src/core/utils/build-diagnostics-modules.ts',
  'index.html',
]
const ALLOWED_MODULE_PREFIXES = ['src/views/', 'src/workspace-components/']

export interface RuntimeDiagnosticsWorkspacePoolOptions {
  runtimeRoot: string
  size: number
  reuseWorker?: boolean
  workerMaxOldSpaceMb?: number
  workerTimeoutMs?: number
}

interface WorkspaceSlot {
  id: number
  root: string
  generation: string
  busy: boolean
  stale: boolean
  worker: RuntimeDiagnosticsWorker | null
  initializing: Promise<void> | null
}

interface WorkspaceWaiter {
  resolve: () => void
  reject: (error: unknown) => void
}

/**
 * 单次诊断工作区租约。调用方必须在 finally 中 release。
 */
export interface RuntimeDiagnosticsWorkspaceLease {
  tempRoot: string
  taskId: string
  taskRoot: string
  runViteBuild: (base?: string, timeoutMs?: number) => Promise<void>
  release: () => Promise<void>
}

/**
 * 工作区路径或生命周期错误。
 */
export class RuntimeDiagnosticsWorkspaceError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string) {
    super(message)
    this.name = 'RuntimeDiagnosticsWorkspaceError'
    this.statusCode = statusCode
    this.code = code
  }
}

/**
 * 维护固定数量的预热工作区；大体积 Runtime 静态源码只在槽位创建或失效时复制。
 */
export class RuntimeDiagnosticsWorkspacePool {
  private readonly runtimeRoot: string
  private readonly reuseWorker: boolean
  private readonly workerMaxOldSpaceMb?: number
  private readonly workerTimeoutMs: number
  private readonly slots: WorkspaceSlot[]
  private readonly waiters: WorkspaceWaiter[] = []
  private sourceGeneration = ''
  private refreshingGeneration: Promise<void> | null = null
  private closed = false

  constructor(options: RuntimeDiagnosticsWorkspacePoolOptions) {
    this.runtimeRoot = resolve(options.runtimeRoot)
    this.reuseWorker = options.reuseWorker ?? readBooleanEnv(
      process.env.RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED,
      true,
    )
    this.workerMaxOldSpaceMb = options.workerMaxOldSpaceMb
    this.workerTimeoutMs = normalizeDiagnosticsWorkerTimeoutMs(options.workerTimeoutMs)
    const size = normalizePositiveInteger(options.size, 1)
    this.slots = Array.from({ length: size }, (_, id) => ({
      id,
      root: '',
      generation: '',
      busy: false,
      stale: false,
      worker: null,
      initializing: null,
    }))
  }

  /**
   * 顺序预热全部槽位，避免服务启动时并行复制大文件造成瞬时 IO 峰值。
   */
  async warmup(): Promise<void> {
    await this.refreshSourceGeneration()
    for (const slot of this.slots) {
      if (this.closed) {
        return
      }
      try {
        await this.ensureSlot(slot)
      } catch (error) {
        if (this.closed) {
          return
        }
        throw error
      }
    }
  }

  /**
   * 获取一个独占诊断槽位，并建立 UUID 任务目录。
   */
  async acquire(): Promise<RuntimeDiagnosticsWorkspaceLease> {
    this.assertOpen()
    await this.refreshSourceGeneration()
    this.assertOpen()
    let slot = this.slots.find(candidate => !candidate.busy)
    while (!slot) {
      await new Promise<void>((resolveWait, rejectWait) => {
        this.waiters.push({ resolve: resolveWait, reject: rejectWait })
      })
      this.assertOpen()
      slot = this.slots.find(candidate => !candidate.busy)
    }

    this.assertOpen()
    slot.busy = true
    try {
      await this.ensureSlot(slot)
      this.assertOpen()
      const taskId = randomUUID()
      const taskRoot = resolve(slot.root, '.runtime-task', taskId)
      await mkdir(taskRoot, { recursive: true })
      await writeFile(
        resolve(taskRoot, 'task.json'),
        JSON.stringify({ taskId, createdAt: new Date().toISOString() }),
        'utf-8',
      )
      let released = false
      return {
        tempRoot: slot.root,
        taskId,
        taskRoot,
        runViteBuild: async (base = './', timeoutMs?: number) => {
          try {
            if (this.reuseWorker) {
              slot.worker ||= new RuntimeDiagnosticsWorker({
                tempRoot: slot.root,
                maxOldSpaceMb: this.workerMaxOldSpaceMb,
                timeoutMs: this.workerTimeoutMs,
              })
              await slot.worker.run(base, timeoutMs)
              return
            }
            await runRuntimeViteBuildInWorker({
              tempRoot: slot.root,
              taskRoot,
              base,
              mode: 'diagnostics',
              maxOldSpaceMb: this.workerMaxOldSpaceMb,
              timeoutMs: resolveTaskTimeoutMs(timeoutMs, this.workerTimeoutMs),
            })
          } catch (error) {
            if (error instanceof RuntimeBuildWorkerProcessError) {
              slot.stale = true
            }
            throw error
          }
        },
        release: async () => {
          if (released) {
            return
          }
          released = true
          await this.releaseSlot(slot as WorkspaceSlot)
        },
      }
    } catch (error) {
      slot.stale = true
      await this.releaseSlot(slot)
      throw error
    }
  }

  /**
   * 关闭常驻 worker、删除临时工作区并拒绝等待者。
   */
  async close(): Promise<void> {
    if (this.closed) {
      return
    }
    this.closed = true
    const closeError = new RuntimeDiagnosticsWorkspaceError(
      503,
      'RUNTIME_DIAGNOSTICS_POOL_CLOSED',
      'Runtime 诊断工作区池已关闭。',
    )
    for (const waiter of this.waiters.splice(0)) {
      waiter.reject(closeError)
    }
    await Promise.all(this.slots.map(async slot => {
      try {
        await slot.initializing
      } catch {
        // 初始化异常由销毁流程统一清理临时目录。
      }
      await this.destroySlot(slot)
    }))
  }

  /**
   * 返回工作区池状态，供日志和测试验证。
   */
  snapshot(): { size: number; ready: number; busy: number; reuseWorker: boolean } {
    return {
      size: this.slots.length,
      ready: this.slots.filter(slot => Boolean(slot.root)).length,
      busy: this.slots.filter(slot => slot.busy).length,
      reuseWorker: this.reuseWorker,
    }
  }

  /**
   * 初始化或重建单个槽位。
   */
  private async ensureSlot(slot: WorkspaceSlot): Promise<void> {
    this.assertOpen()
    if (slot.root && slot.generation === this.sourceGeneration && !slot.stale) {
      return
    }
    if (slot.initializing) {
      await slot.initializing
      return
    }
    slot.initializing = (async () => {
      await this.destroySlot(slot)
      slot.root = await createDisposableRuntimeWorkspace(this.runtimeRoot, 'web-presentation-runtime-diagnostics-')
      slot.generation = this.sourceGeneration
      slot.stale = false
      await mkdir(resolve(slot.root, '.runtime-task'), { recursive: true })
      if (this.closed) {
        await this.destroySlot(slot)
        this.assertOpen()
      }
    })()
    try {
      await slot.initializing
    } finally {
      slot.initializing = null
    }
  }

  /**
   * 任务结束后恢复所有允许被注入的路径；恢复失败时销毁整个槽位。
   */
  private async releaseSlot(slot: WorkspaceSlot): Promise<void> {
    try {
      if (this.closed || slot.stale || slot.generation !== this.sourceGeneration) {
        await this.destroySlot(slot)
      } else {
        await resetDiagnosticsWorkspace(this.runtimeRoot, slot.root)
      }
    } catch {
      await this.destroySlot(slot)
    } finally {
      slot.busy = false
      this.waiters.shift()?.resolve()
    }
  }

  /**
   * 删除工作区并停止与其绑定的常驻进程。
   */
  private async destroySlot(slot: WorkspaceSlot): Promise<void> {
    const worker = slot.worker
    const root = slot.root
    slot.worker = null
    slot.root = ''
    slot.generation = ''
    slot.stale = false
    if (worker) {
      await worker.close()
    }
    if (root) {
      await rm(root, { recursive: true, force: true })
    }
  }

  /**
   * 检测 Runtime 源码代次变化，并使旧槽位在安全时机失效。
   */
  private async refreshSourceGeneration(): Promise<void> {
    if (this.refreshingGeneration) {
      await this.refreshingGeneration
      return
    }
    this.refreshingGeneration = (async () => {
      const nextGeneration = await computeRuntimeSourceGeneration(this.runtimeRoot)
      if (!this.sourceGeneration) {
        this.sourceGeneration = nextGeneration
        return
      }
      if (nextGeneration === this.sourceGeneration) {
        return
      }
      this.sourceGeneration = nextGeneration
      for (const slot of this.slots) {
        if (slot.busy) {
          slot.stale = true
        } else {
          await this.destroySlot(slot)
        }
      }
    })()
    try {
      await this.refreshingGeneration
    } finally {
      this.refreshingGeneration = null
    }
  }

  /**
   * 在异步边界后复查关闭态，避免 close 与 acquire 并发时重新创建工作区。
   */
  private assertOpen(): void {
    if (this.closed) {
      throw new RuntimeDiagnosticsWorkspaceError(503, 'RUNTIME_DIAGNOSTICS_POOL_CLOSED', 'Runtime 诊断工作区池已关闭。')
    }
  }
}

/**
 * 创建一次性 Runtime 工作区，正式构建继续使用该入口。
 */
export async function createDisposableRuntimeWorkspace(
  runtimeRoot: string,
  prefix = 'web-presentation-runtime-build-',
): Promise<string> {
  const normalizedRuntimeRoot = resolve(runtimeRoot)
  const tempRoot = await mkdtemp(join(os.tmpdir(), prefix))
  try {
    for (const relativePath of COPY_TARGETS) {
      await restoreRuntimePath(normalizedRuntimeRoot, tempRoot, relativePath)
    }

    const sourceNodeModules = resolve(normalizedRuntimeRoot, 'node_modules')
    if (await pathExists(sourceNodeModules)) {
      await symlink(
        sourceNodeModules,
        resolve(tempRoot, 'node_modules'),
        process.platform === 'win32' ? 'junction' : 'dir',
      )
    }
    await mkdir(resolve(tempRoot, 'public'), { recursive: true })
    return tempRoot
  } catch (error) {
    try {
      await rm(tempRoot, { recursive: true, force: true })
    } catch {
      // 保留原始初始化错误，残留目录由外层启动诊断或系统临时目录清理处理。
    }
    throw error
  }
}

/**
 * 校验并解析可由远程 artifact 写入的模块路径。
 * 只开放页面和工作空间组件目录，防止绝对路径与 `..` 逃逸。
 */
export function resolveWritableRuntimeModulePath(tempRoot: string, rawPath: string): {
  logicalPath: string
  targetPath: string
} {
  const rawNormalized = String(rawPath || '').trim().replace(/\\/g, '/')
  if (!rawNormalized || rawNormalized.includes('\0') || isAbsolute(rawNormalized) || /^[a-zA-Z]:\//.test(rawNormalized)) {
    throw forbiddenModulePath(rawPath)
  }
  const logicalPath = normalizeRuntimeModulePath(rawNormalized)
  const segments = logicalPath.split('/')
  if (segments.some(segment => !segment || segment === '.' || segment === '..')) {
    throw forbiddenModulePath(rawPath)
  }
  if (!ALLOWED_MODULE_PREFIXES.some(prefix => logicalPath.startsWith(prefix))) {
    throw forbiddenModulePath(rawPath)
  }
  const normalizedRoot = resolve(tempRoot)
  const targetPath = resolve(normalizedRoot, logicalPath.split('/').join(sep))
  const relativeTarget = relative(normalizedRoot, targetPath)
  if (!relativeTarget || relativeTarget.startsWith('..') || isAbsolute(relativeTarget)) {
    throw forbiddenModulePath(rawPath)
  }
  return { logicalPath, targetPath }
}

/**
 * 恢复诊断任务允许改写的目录与构建入口文件。
 */
async function resetDiagnosticsWorkspace(runtimeRoot: string, tempRoot: string): Promise<void> {
  await rm(resolve(tempRoot, '.runtime-task'), { recursive: true, force: true })
  await mkdir(resolve(tempRoot, '.runtime-task'), { recursive: true })
  for (const relativePath of RESET_DIRECTORIES) {
    await rm(resolve(tempRoot, relativePath), { recursive: true, force: true })
    await restoreRuntimePath(runtimeRoot, tempRoot, relativePath)
  }
  for (const relativePath of RESET_FILES) {
    await rm(resolve(tempRoot, relativePath), { force: true })
    await restoreRuntimePath(runtimeRoot, tempRoot, relativePath)
  }
}

/**
 * 复制单个 Runtime 基准路径；源路径不存在时保持目标不存在。
 */
async function restoreRuntimePath(runtimeRoot: string, tempRoot: string, relativePath: string): Promise<void> {
  const sourcePath = resolve(runtimeRoot, relativePath)
  if (!await pathExists(sourcePath)) {
    return
  }
  const targetPath = resolve(tempRoot, relativePath)
  await mkdir(resolve(targetPath, '..'), { recursive: true })
  await cp(sourcePath, targetPath, {
    recursive: true,
    filter: source => shouldCopyRuntimePath(source),
  })
}

/**
 * 生成足以识别运行中源码变更的轻量指纹，不读取大体积文件内容。
 */
async function computeRuntimeSourceGeneration(runtimeRoot: string): Promise<string> {
  const hash = createHash('sha256')
  for (const relativePath of COPY_TARGETS) {
    await appendPathGeneration(resolve(runtimeRoot, relativePath), runtimeRoot, hash)
  }
  return hash.digest('hex')
}

/**
 * 递归写入路径、大小和 mtime，测试文件与构建目录沿用复制过滤规则。
 */
async function appendPathGeneration(
  currentPath: string,
  runtimeRoot: string,
  hash: ReturnType<typeof createHash>,
): Promise<void> {
  if (!await pathExists(currentPath) || !shouldCopyRuntimePath(currentPath)) {
    return
  }
  const metadata = await stat(currentPath)
  hash.update(`${relative(runtimeRoot, currentPath)}:${metadata.size}:${metadata.mtimeMs}\n`)
  if (!metadata.isDirectory()) {
    return
  }
  const entries = await readdir(currentPath, { withFileTypes: true })
  entries.sort((left, right) => left.name.localeCompare(right.name))
  for (const entry of entries) {
    await appendPathGeneration(resolve(currentPath, entry.name), runtimeRoot, hash)
  }
}

/**
 * 判断 Runtime 模板路径是否允许进入临时工作区。
 */
function shouldCopyRuntimePath(source: string): boolean {
  const normalized = source.replace(/\\/g, '/')
  return !normalized.includes('/node_modules/')
    && !normalized.includes('/dist/')
    && !normalized.includes('/.git/')
    && !normalized.includes('/__tests__/')
    && !/\.(test|spec)\.[^/]+$/i.test(normalized)
}

/**
 * 检查文件或目录是否存在。
 */
async function pathExists(path: string): Promise<boolean> {
  try {
    await access(path, fsConstants.F_OK)
    return true
  } catch {
    return false
  }
}

/**
 * 构造统一的模块路径拒绝错误。
 */
function forbiddenModulePath(rawPath: string): RuntimeDiagnosticsWorkspaceError {
  return new RuntimeDiagnosticsWorkspaceError(
    409,
    'RUNTIME_DIAGNOSTICS_MODULE_PATH_FORBIDDEN',
    `诊断模块路径不在允许目录内：${String(rawPath || '')}`,
  )
}

/**
 * 解析布尔环境变量，无法识别时使用默认值。
 */
function readBooleanEnv(rawValue: string | undefined, fallback: boolean): boolean {
  const normalized = String(rawValue || '').trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false
  }
  return fallback
}

/**
 * 解析正整数并提供安全默认值。
 */
function normalizePositiveInteger(value: number | undefined, fallback: number): number {
  return Number.isInteger(value) && Number(value) > 0 ? Number(value) : fallback
}

/**
 * 将本次任务剩余时长限制在诊断 worker 的配置上限内。
 */
function resolveTaskTimeoutMs(requestedTimeoutMs: number | undefined, configuredTimeoutMs: number): number {
  const requested = Math.floor(Number(requestedTimeoutMs))
  if (!Number.isFinite(requested) || requested <= 0) {
    return configuredTimeoutMs
  }
  return Math.min(configuredTimeoutMs, requested)
}
