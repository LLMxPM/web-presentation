/**
 * 文件用途：提供 Runtime 内部整项目构建入口，并在临时工作区中执行程序化 Vite 构建、子进程归档与回传。
 */

import type { IncomingMessage, ServerResponse } from 'http'
import { mkdir, rm, writeFile, access, readdir, readFile } from 'fs/promises'
import { chmodSync, createReadStream, constants as fsConstants, readFileSync, statSync } from 'fs'
import { Readable } from 'stream'
import { resolve, sep } from 'path'

import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose'
import type { Plugin, ViteDevServer } from 'vite'

import type { RuntimePreloadedConfigBundle, RuntimePreviewArtifactManifest } from '../shared/runtime-preview'
import { normalizeAssetKey, normalizeRuntimeModulePath } from '../shared/runtime-preview'
import { logRuntimeServer } from '../utils/runtime-logger'
import {
  createBuildReleaseViewModulesSource,
  createDiagnosticsBuildModulesSource,
  buildStaticAssetPath,
  hasForbiddenRootAbsoluteAssetPath,
  normalizeBuildBaseUrl,
} from './runtime-build-runner.helpers'
import {
  createBuildEntrySource,
  createBuildIndexHtmlSource,
  createDiagnosticsBuildEntrySource,
} from './runtime-build-entry'
import {
  RuntimeBuildWorkerProcessError,
  RuntimeBuildWorkerViteError,
  normalizeDiagnosticsWorkerTimeoutMs,
  runRuntimeViteBuildInWorker,
  runZipArchiveInWorker,
} from './runtime-build-worker'
import {
  recordRuntimeWorkload,
  registerRuntimeCapacityProvider,
} from './runtime-capacity'
import { registerRuntimeReadinessProbe } from './runtime-health'
import { getRuntimeRole } from './runtime-role'
import {
  RuntimeDiagnosticsWorkspaceError,
  RuntimeDiagnosticsWorkspacePool,
  createDisposableRuntimeWorkspace,
  resolveWritableRuntimeModulePath,
} from './runtime-diagnostics-workspace-pool'
import {
  RuntimeViteTaskScheduler,
  RuntimeViteTaskSchedulerError,
} from './runtime-vite-task-scheduler'
import { startRuntimeBuildQueueWorker } from './runtime-build-queue-worker'
import {
  RuntimeTaskDeadlineError,
  runWithRuntimeTaskDeadline,
  type RuntimeTaskDeadline,
} from './runtime-task-deadline'

interface RuntimeBuildRunnerOptions {
  diagnosticsEndpointPath?: string
  serviceTokenHeaderName?: string
  jwksUrl?: string
  diagnosticsAudience?: string
  backendApiBaseUrl?: string
  /** 是否开放整项目构建能力；build 角色为 true，check 角色为 false。 */
  enableProjectEntry?: boolean
  /** 是否开放编译诊断入口；check 角色为 true，build 角色为 false。 */
  enableDiagnosticsEntry?: boolean
}

interface RuntimeDiagnosticsCommandClaims extends JWTPayload {
  sub: string
  artifact_id: string
  workspace_id: string
  project_id?: string
  jti: string
}

interface RuntimeDiagnosticsRequestBody {
  artifact_id: string
  label?: string
}

interface RuntimeCodeDiagnostic {
  severity: 'error' | 'warning'
  source: string
  code: string
  message: string
  file_path?: string
  line?: number
  column?: number
}

interface RuntimeDiagnosticsSummary {
  success: boolean
  status: 'passed' | 'failed'
  artifactId: string
  summary: string
  diagnostics: RuntimeCodeDiagnostic[]
}

interface UploadedBuildArtifactSummary {
  artifact_storage_key?: string
  artifact_download_url?: string
  artifact_entry_file?: string
  artifact_sha256?: string
  artifact_size_bytes?: number
  message?: string
}

interface BuildArtifactSummary {
  artifactEntryFile: string
  artifactSha256: string
  artifactSizeBytes: number
  message: string
}

interface BuildArtifactUploadParams {
  jobId: string
  buildToken: string
  /** 归档文件路径：上传时按分片从磁盘读取，整包不进入 Runtime 主进程内存。 */
  archivePath: string
  entryFile: string
  sha256: string
  sizeBytes: number
}

interface BuildAssetFetchContext {
  logicalName: string
  fileHash: string
  originalName?: string
}

interface RuntimeBuildLogContext {
  jobId?: string
  artifactId?: string
  baseUrl?: string
  runtimeRoot?: string
  tempRoot?: string
  distRoot?: string
  [key: string]: unknown
}

type RuntimeNodeResponse = Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>

const DEFAULT_DIAGNOSTICS_ENDPOINT = '/__runtime_internal/v1/diagnostics/artifact'
const MODULE_BATCH_SIZE = 128
const DEFAULT_DIAGNOSTICS_AUDIENCE = 'runtime-diagnostics'
const DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER = 'x-runtime-service-token'
const DEFAULT_ARTIFACT_UPLOAD_MAX_ATTEMPTS = 3
const DEFAULT_ARTIFACT_UPLOAD_RETRY_BASE_MS = 750

/**
 * 输出远程构建调试日志，便于定位 Runtime 实际执行路径。
 * @param stage 当前构建阶段
 * @param context 结构化上下文
 */
function logRuntimeBuild(stage: string, context: RuntimeBuildLogContext = {}): void {
  logRuntimeServer('info', `runtime.build.${stage}`, 'Runtime 构建阶段完成。', {
    module: 'runtime.build',
    ...context,
  })
}

/**
 * 输出远程构建异常日志。
 * @param stage 当前构建阶段
 * @param error 异常对象
 * @param context 结构化上下文
 */
function logRuntimeBuildError(stage: string, error: unknown, context: RuntimeBuildLogContext = {}): void {
  logRuntimeServer('error', `runtime.build.${stage}`, 'Runtime 构建阶段失败。', {
    module: 'runtime.build',
    ...context,
    error: error instanceof Error
      ? {
        name: error.name,
        message: error.message,
        stack: error.stack,
      }
      : error,
  })
}
/**
 * Runtime 内部构建与诊断插件：
 * 1. 构建只由 Build Worker 主动向 Backend 领取任务后执行，不暴露 HTTP 同步派发入口；
 * 2. 仅在 Vite serve 下暴露内部编译诊断入口，使用 Backend JWKS 验签诊断令牌；
 * 3. 拉取 build snapshot 后在临时工作区执行程序化构建；
 * 4. 构建阶段只物化当前 snapshot 资源，并将其增量写入 `__build_assets`；
 * 5. 构建完成后将 dist.zip 回传 Backend，并清理临时文件。
 */
export default function runtimeBuildRunner(options: RuntimeBuildRunnerOptions = {}): Plugin {
  const diagnosticsEndpointPath = options.diagnosticsEndpointPath || DEFAULT_DIAGNOSTICS_ENDPOINT
  const serviceTokenHeaderName = (options.serviceTokenHeaderName || DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER).toLowerCase()
  // 角色裁剪：preview 不注册本插件；build 只跑 Worker 领取循环；check 只开诊断入口。
  const enableProjectEntry = options.enableProjectEntry !== false
  const enableDiagnosticsEntry = options.enableDiagnosticsEntry !== false
  const scheduler = new RuntimeViteTaskScheduler()
  let diagnosticsWorkspacePool: RuntimeDiagnosticsWorkspacePool | null = null
  let runtimeRoot = ''

  let unregisterCapacityProvider: (() => void) | null = null

  return {
    name: 'runtime-build-runner',
    apply: 'serve',

    configResolved(resolvedConfig) {
      runtimeRoot = resolvedConfig.root
      diagnosticsWorkspacePool = new RuntimeDiagnosticsWorkspacePool({
        runtimeRoot,
        size: scheduler.snapshot().concurrency,
      })
      unregisterCapacityProvider?.()
      unregisterCapacityProvider = registerRuntimeCapacityProvider('viteTaskScheduler', () => ({
        ...scheduler.snapshot(),
      }))
    },

    configureServer(server: ViteDevServer) {
      const workspacePool = diagnosticsWorkspacePool
      if (!workspacePool) {
        throw new Error('Runtime 诊断工作区池尚未初始化。')
      }
      // 工作区采用首次诊断时的惰性预热：创建动作位于 diagnostics scheduler 槽位内，
      // 避免服务启动时与正式构建并发复制完整 Runtime 源码。
      let stopBuildQueueWorker: (() => void) | null = null
      const buildWorkerCredential = readRuntimeBuildWorkerCredential()
      const backendApiBaseUrl = options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || ''
      const buildWorkerRunnable = enableProjectEntry
        && Boolean(buildWorkerCredential)
        && Boolean(backendApiBaseUrl)
      if (enableProjectEntry && !buildWorkerRunnable && getRuntimeRole() === 'build') {
        // build 角色只有 Worker 这一条构建执行路径：「启动成功但 Worker 未启动」会让编排层
        // 看到健康副本、Backend 也照常就绪，而所有构建任务永久滞留队列。必须在启动期直接失败。
        throw new Error(
          'RUNTIME_ROLE=build 但构建 Worker 无法启动：'
          + `worker 凭证${buildWorkerCredential ? '已配置' : '缺失或不可读'}，`
          + `Backend API 地址${backendApiBaseUrl ? '已配置' : '缺失'}。`,
        )
      }
      // 就绪探针读的是本次挂载自己的执行面状态：进程存活不等于能构建，
      // Worker 未启动、消费者数量与 project lane 预算不符或调度器已关闭都必须报未就绪。
      // 探针不随 close 注销——排空中的副本应持续报告未就绪，而不是在关闭瞬间变回健康。
      let buildWorkerStopped = true
      let buildWorkerConsumers = 0
      if (enableProjectEntry) {
        registerRuntimeReadinessProbe('buildWorker', () => {
          const snapshot = scheduler.snapshot()
          if (snapshot.closed) {
            return { ready: false, detail: '构建任务调度器已关闭。' }
          }
          if (buildWorkerStopped) {
            return { ready: false, detail: '构建 Worker 领取循环未在运行。' }
          }
          const expectedConsumers = snapshot.kinds.project.concurrency
          if (buildWorkerConsumers !== expectedConsumers) {
            return {
              ready: false,
              detail: `构建 Worker 消费者数量 ${buildWorkerConsumers}，期望 ${expectedConsumers}。`,
            }
          }
          return { ready: true }
        })
      }
      if (buildWorkerRunnable) {
        buildWorkerStopped = false
        stopBuildQueueWorker = startRuntimeBuildQueueWorker({
          backendApiBaseUrl,
          workerCredential: buildWorkerCredential,
          workerId: process.env.RUNTIME_BUILD_WORKER_ID || `runtime-build-${process.pid}`,
          // 消费者数量必须等于 project lane 并发：单循环串行领取会让多出来的执行预算空转。
          concurrency: scheduler.snapshot().kinds.project.concurrency,
          runtimeRoot,
          scheduler,
          runProjectBuild,
          createBuildBackendClient,
          onStarted: info => {
            buildWorkerConsumers = info.consumerCount
          },
        })
      } else if (enableProjectEntry) {
        // 构建没有第二条执行路径：凭证或 Backend 地址缺失时任务只会留在队列里等待人工介入。
        logRuntimeServer('error', 'runtime.build.worker.not_started', '构建 Worker 未能启动，构建任务将保持待执行。', {
          module: 'runtime.build',
          credentialConfigured: Boolean(buildWorkerCredential),
          backendApiConfigured: Boolean(backendApiBaseUrl),
        })
      }
      server.httpServer?.once('close', () => {
        buildWorkerStopped = true
        buildWorkerConsumers = 0
        stopBuildQueueWorker?.()
        stopBuildQueueWorker = null
        unregisterCapacityProvider?.()
        unregisterCapacityProvider = null
        scheduler.close()
        void workspacePool.close()
      })
      server.middlewares.use(async (req, res, next) => {
        const requestPath = (req.url || '').split('?')[0]
        if (!enableDiagnosticsEntry || requestPath !== diagnosticsEndpointPath) {
          return next()
        }
        if (req.method !== 'POST') {
          return sendJson(res, 405, {
            success: false,
            code: 'METHOD_NOT_ALLOWED',
            message: '代码检查入口仅支持 POST。',
          })
        }
        return handleRuntimeDiagnosticsRequest(req, res, {
          runtimeRoot,
          serviceTokenHeaderName,
          jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
          diagnosticsAudience: options.diagnosticsAudience || process.env.RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE || DEFAULT_DIAGNOSTICS_AUDIENCE,
          backendApiBaseUrl: options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || '',
          scheduler,
          workspacePool,
        })
      })
    },
  }
}

/**
 * 验证代码诊断命令令牌。
 * @param token Backend 签发的诊断命令令牌
 * @param options 验签选项
 * @returns 已校验的 claims
 */
async function verifyDiagnosticsToken(
  token: string,
  options: {
    jwksUrl: string
    audience: string
  },
): Promise<RuntimeDiagnosticsCommandClaims> {
  if (!options.jwksUrl) {
    throw new RuntimeBuildError(503, 'JWKS_URL_MISSING', 'Runtime 未配置 JWKS 地址。')
  }
  const jwks = createRemoteJWKSet(new URL(options.jwksUrl))
  const { payload } = await jwtVerify(token, jwks, {
    audience: options.audience,
  })

  const claims = payload as RuntimeDiagnosticsCommandClaims
  if (!claims.artifact_id || !claims.workspace_id) {
    throw new RuntimeBuildError(401, 'DIAGNOSTICS_TOKEN_INVALID', '诊断命令令牌缺少必需声明。')
  }
  return claims
}

/**
 * 处理 Runtime 内部代码诊断请求。
 * @param req Node 请求对象
 * @param res Node 响应对象
 * @param options 诊断入口配置
 */
async function handleRuntimeDiagnosticsRequest(
  req: IncomingMessage,
  res: RuntimeNodeResponse,
  options: {
    runtimeRoot: string
    serviceTokenHeaderName: string
    jwksUrl: string
    diagnosticsAudience: string
    backendApiBaseUrl: string
    scheduler: RuntimeViteTaskScheduler
    workspacePool: RuntimeDiagnosticsWorkspacePool
  },
): Promise<void> {
  try {
    const diagnosticsToken = readBearerToken(String(req.headers.authorization || ''))
    const verifiedClaims = await verifyDiagnosticsToken(diagnosticsToken, {
      jwksUrl: options.jwksUrl,
      audience: options.diagnosticsAudience,
    })
    const payload = await readJsonBody<RuntimeDiagnosticsRequestBody>(req)
    if (String(payload.artifact_id || '') !== String(verifiedClaims.artifact_id || '')) {
      throw new RuntimeBuildError(403, 'DIAGNOSTICS_ARTIFACT_MISMATCH', '诊断 artifact 与令牌声明不一致。')
    }

    const diagnosticsContext: RuntimeBuildLogContext = {
      artifactId: payload.artifact_id,
      runtimeRoot: options.runtimeRoot,
      requestUrl: req.url,
      label: payload.label,
      request_id: String(req.headers['x-request-id'] || ''),
    }
    logRuntimeBuild('diagnostics.request.received', diagnosticsContext)
    const requestStartedAt = Date.now()
    const serviceToken = String(req.headers[options.serviceTokenHeaderName] || '')
    if (!serviceToken) {
      throw new RuntimeBuildError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Backend 下发的 Runtime 服务令牌。')
    }

    const backendClient = createBuildBackendClient({
      backendApiBaseUrl: options.backendApiBaseUrl,
      serviceToken,
    })
    const queuedAt = Date.now()
    logRuntimeBuild('diagnostics.queue.entered', {
      ...diagnosticsContext,
      taskKind: 'diagnostics',
      ...options.scheduler.snapshot(),
    })
    const diagnosticsSummary = await options.scheduler.schedule('diagnostics', async () => {
      logRuntimeBuild('diagnostics.queue.acquired', {
        ...diagnosticsContext,
        taskKind: 'diagnostics',
        queueWaitMs: Date.now() - queuedAt,
        ...options.scheduler.snapshot(),
      })
      return runWithRuntimeTaskDeadline('diagnostics', normalizeDiagnosticsWorkerTimeoutMs(), async deadline => {
        const manifest = await backendClient.fetchManifest(payload.artifact_id, deadline.signal)
        const configBundle = await backendClient.fetchConfigBundle(payload.artifact_id, deadline.signal)
        deadline.throwIfExpired()
        return runArtifactDiagnostics({
          runtimeRoot: options.runtimeRoot,
          artifactId: payload.artifact_id,
          manifest,
          configBundle,
          backendClient,
          workspacePool: options.workspacePool,
          deadline,
        })
      })
    })

    sendJson(res, 200, {
      success: diagnosticsSummary.success,
      status: diagnosticsSummary.status,
      artifact_id: diagnosticsSummary.artifactId,
      summary: diagnosticsSummary.summary,
      diagnostics: diagnosticsSummary.diagnostics,
    })
    const requestDurationMs = Date.now() - requestStartedAt
    recordRuntimeWorkload('check', requestDurationMs)
    logRuntimeBuild('diagnostics.request.completed', {
      ...diagnosticsContext,
      durationMs: requestDurationMs,
      status: diagnosticsSummary.status,
      diagnosticCount: diagnosticsSummary.diagnostics.length,
    })
  } catch (error) {
    logRuntimeBuildError('diagnostics.request.failed', error, {
      runtimeRoot: options.runtimeRoot,
      method: req.method,
      requestUrl: req.url,
    })
    sendBuildError(res, error)
  }
}

/**
 * 读取请求头中的 Bearer Token。
 * @param authorization 原始 Authorization 头
 * @returns Bearer Token
 */
function readBearerToken(authorization: string): string {
  const trimmed = authorization.trim()
  if (!trimmed.startsWith('Bearer ')) {
    throw new RuntimeBuildError(401, 'BUILD_TOKEN_REQUIRED', '缺少 Bearer 构建令牌。')
  }
  return trimmed.slice('Bearer '.length).trim()
}

/**
 * 读取 JSON 请求体。
 * @param req Node 请求对象
 * @returns 解析后的 JSON
 */
async function readJsonBody<T>(req: NodeJS.ReadableStream): Promise<T> {
  const chunks: Buffer[] = []
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  const rawBody = Buffer.concat(chunks).toString('utf-8')
  try {
    return JSON.parse(rawBody) as T
  } catch {
    throw new RuntimeBuildError(400, 'REQUEST_BODY_INVALID', '请求体不是合法 JSON。')
  }
}

/**
 * 读取 Runtime Build Worker 共享凭证：优先 secret 文件，其次环境变量。
 * @param options 可选注入选项（测试用）
 * @returns 非空凭证；未配置时返回空字符串（Worker 不启动）
 */
export function readRuntimeBuildWorkerCredential(options?: {
  chmodFn?: (path: string, mode: number) => void
}): string {
  const credentialFile = String(process.env.RUNTIME_BUILD_WORKER_CREDENTIAL_FILE || '').trim()
  if (credentialFile) {
    try {
      // 该文件与执行不可信构建代码的进程同容器共存。已配置子进程降权（AR-01/W01）
      // 时，凭证对组/其他用户可读会让降权失效，必须 fail-closed；未配置降权的
      // 开发/受限形态只告警。Windows 不上报：POSIX 权限位在 NTFS 上没有对应语义。
      const stat = statSync(credentialFile)
      const looseMode = process.platform !== 'win32' && (stat.mode & 0o077) !== 0
      if (looseMode) {
        const isolationConfigured =
          Boolean(String(process.env.RUNTIME_BUILD_CHILD_UID || '').trim()) ||
          Boolean(String(process.env.RUNTIME_BUILD_CHILD_GID || '').trim())
        const detail = {
          module: 'runtime.build',
          mode: (stat.mode & 0o777).toString(8),
          isolation_configured: isolationConfigured,
        }
        if (isolationConfigured) {
          // Compose file secrets 常默认挂成 0444。属主是本进程时先收紧再启动，
          // 避免编排层默认权限把 W01 整条链路打成 fail-closed。
          if (tightenCredentialFileMode(credentialFile, options?.chmodFn)) {
            logRuntimeServer(
              'info',
              'runtime.build.worker.credential_loose_mode',
              '构建 Worker 凭证文件权限过宽，已收紧为属主可读后启动。',
              detail,
            )
            return readFileSync(credentialFile, 'utf-8').trim()
          }
          logRuntimeServer(
            'error',
            'runtime.build.worker.credential_loose_mode',
            '构建 Worker 凭证文件对组/其他用户可读，且已配置子进程降权；拒绝启动以维持执行隔离边界。',
            detail,
          )
          throw new RuntimeBuildError(
            503,
            'RUNTIME_BUILD_CREDENTIAL_LOOSE_MODE',
            '构建 Worker 凭证文件权限过宽（非 0400/0600），与子进程降权边界冲突。'
              + '请将 secret 限制为属主可读（chmod 0400），或在 Compose 服务级 secrets 使用 mode/uid/gid，'
              + '或改为环境变量 RUNTIME_BUILD_WORKER_CREDENTIAL（子进程删键 + UID 降权后仍受 W01 保护）。',
          )
        }
        logRuntimeServer('warn', 'runtime.build.worker.credential_loose_mode', '构建 Worker 凭证文件对所有用户可读。', detail)
      }
      return readFileSync(credentialFile, 'utf-8').trim()
    } catch (error) {
      if (error instanceof RuntimeBuildError) {
        throw error
      }
      return ''
    }
  }
  return String(process.env.RUNTIME_BUILD_WORKER_CREDENTIAL || '').trim()
}

/**
 * 尝试把凭证文件收紧为 0400。仅当本进程是属主（或 root）时 chmod 会成功；
 * Compose secrets 默认 0444 且属主对齐本进程时用于自动恢复 W01。
 * @param credentialFile 凭证文件路径
 * @param chmodFn 自定义 chmod 实现（默认使用 fs.chmodSync）
 * @returns 是否已成功收紧到组/其他用户不可读
 */
function tightenCredentialFileMode(
  credentialFile: string,
  chmodFn: (path: string, mode: number) => void = chmodSync,
): boolean {
  try {
    chmodFn(credentialFile, 0o400)
    return (statSync(credentialFile).mode & 0o077) === 0
  } catch {
    return false
  }
}

/**
 * 创建用于读取 Backend build snapshot 的客户端。
 * @param options 客户端配置
 * @returns 只读构建客户端
 */
export function createBuildBackendClient(options: {
  backendApiBaseUrl: string
  serviceToken: string
}) {
  if (!options.backendApiBaseUrl) {
    throw new RuntimeBuildError(503, 'BACKEND_API_BASE_URL_MISSING', 'Runtime 未配置 Backend API 根地址。')
  }
  if (!options.serviceToken) {
    throw new RuntimeBuildError(503, 'RUNTIME_SERVICE_TOKEN_REQUIRED', 'Runtime 未获取到服务级令牌。')
  }

  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')
  const defaultHeaders: Record<string, string> = {
    Authorization: `Bearer ${options.serviceToken}`,
  }

  return {
    async fetchManifest(artifactId: string, signal?: AbortSignal): Promise<RuntimePreviewArtifactManifest> {
      return requestJson<RuntimePreviewArtifactManifest>(
        `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/manifest`,
        defaultHeaders,
        signal,
      )
    },

    async fetchConfigBundle(artifactId: string, signal?: AbortSignal): Promise<RuntimePreloadedConfigBundle> {
      return requestJson<RuntimePreloadedConfigBundle>(
        `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/config-bundle`,
        defaultHeaders,
        signal,
      )
    },

    async fetchModuleSource(artifactId: string, modulePath: string, signal?: AbortSignal): Promise<string> {
      const url = `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/modules?path=${encodeURIComponent(modulePath)}`
      let response: Response
      try {
        response = await fetch(url, {
          headers: {
            ...defaultHeaders,
            Accept: 'text/plain, application/json;q=0.9',
          },
          signal,
        })
      } catch (error) {
        throw buildBackendRequestNetworkError(url, error)
      }
      if (!response.ok) {
        throw await toBuildError(response, 'MODULE_FETCH_FAILED')
      }
      try {
        return await response.text()
      } catch (error) {
        throw buildBackendRequestNetworkError(url, error)
      }
    },

    async fetchModuleSources(
      artifactId: string,
      modulePaths: string[],
      signal?: AbortSignal,
    ): Promise<Record<string, string>> {
      const url = `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/modules/batch`
      let response: Response
      try {
        response = await fetch(url, {
          method: 'POST',
          headers: {
            ...defaultHeaders,
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ paths: modulePaths }),
          signal,
        })
      } catch (error) {
        throw buildBackendRequestNetworkError(url, error)
      }
      if (response.status === 404 || response.status === 405) {
        const entries = await Promise.all(modulePaths.map(async modulePath => [
          modulePath,
          await this.fetchModuleSource(artifactId, modulePath, signal),
        ] as const))
        return Object.fromEntries(entries)
      }
      if (!response.ok) {
        throw await toBuildError(response, 'MODULE_BATCH_FETCH_FAILED')
      }
      const payload = await response.json() as { modules?: Record<string, unknown> }
      const modules = payload.modules || {}
      if (modulePaths.some(modulePath => typeof modules[modulePath] !== 'string')) {
        throw new RuntimeBuildError(502, 'MODULE_BATCH_RESPONSE_INVALID', 'Backend 批量模块响应缺少请求的源码。')
      }
      return Object.fromEntries(modulePaths.map(modulePath => [modulePath, String(modules[modulePath])]))
    },

    async fetchAssetBinary(assetUrl: string, context?: BuildAssetFetchContext, signal?: AbortSignal): Promise<Buffer> {
      let response: Response
      try {
        response = await fetch(assetUrl, {
          headers: {
            Accept: '*/*',
          },
          signal,
        })
      } catch (error) {
        throw buildAssetFetchNetworkError(assetUrl, error, context)
      }
      if (!response.ok) {
        const buildError = await toBuildError(response, 'ASSET_FETCH_FAILED')
        throw new RuntimeBuildError(
          buildError.statusCode,
          buildError.code,
          appendAssetFetchContext(buildError.message, assetUrl, context),
        )
      }
      try {
        return Buffer.from(await response.arrayBuffer())
      } catch (error) {
        throw buildAssetFetchNetworkError(assetUrl, error, context)
      }
    },

    async uploadBuildArtifact(params: BuildArtifactUploadParams, signal?: AbortSignal): Promise<UploadedBuildArtifactSummary> {
      const uploadUrl = `${apiBaseUrl}/internal/runtime/build-jobs/${encodeURIComponent(params.jobId)}/artifact`
      const response = await uploadBuildArtifactWithRetry(uploadUrl, params, signal)
      if (!response.ok) {
        throw await toBuildError(response, 'BUILD_ARTIFACT_UPLOAD_FAILED')
      }
      try {
        return await response.json() as UploadedBuildArtifactSummary
      } catch (error) {
        throw buildBackendRequestNetworkError(uploadUrl, error)
      }
    },
  }
}

/**
 * 带网络重试地上传构建产物，规避 Backend 热重载或本地连接瞬断。
 * @param uploadUrl Backend 构建产物上传地址
 * @param params 上传参数
 * @param signal 端到端 deadline 的取消信号
 * @returns 上传响应
 */
async function uploadBuildArtifactWithRetry(
  uploadUrl: string,
  params: BuildArtifactUploadParams,
  signal?: AbortSignal,
): Promise<Response> {
  let lastError: unknown = null
  for (let attempt = 1; attempt <= DEFAULT_ARTIFACT_UPLOAD_MAX_ATTEMPTS; attempt += 1) {
    throwIfAborted(signal)
    // 流式 body 一旦发出就无法回退重放，因此每次尝试都重新打开归档文件。
    const archiveStream = createReadStream(params.archivePath)
    try {
      const requestInit: RequestInit & { duplex: 'half' } = {
        method: 'POST',
        headers: buildArtifactUploadHeaders(params),
        body: Readable.toWeb(archiveStream) as unknown as ReadableStream,
        duplex: 'half',
        signal,
      }
      const response = await fetch(uploadUrl, requestInit)
      return response
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }
      lastError = error
      if (attempt >= DEFAULT_ARTIFACT_UPLOAD_MAX_ATTEMPTS) {
        break
      }
      logRuntimeBuild('artifact.upload.retry', {
        jobId: params.jobId,
        uploadUrl,
        attempt,
        maxAttempts: DEFAULT_ARTIFACT_UPLOAD_MAX_ATTEMPTS,
        error: formatUnknownError(error),
        cause: formatUnknownError((error as { cause?: unknown } | null)?.cause),
      })
      await sleep(DEFAULT_ARTIFACT_UPLOAD_RETRY_BASE_MS * attempt, signal)
    } finally {
      archiveStream.destroy()
    }
  }

  throw buildArtifactUploadNetworkError(
    uploadUrl,
    lastError,
    DEFAULT_ARTIFACT_UPLOAD_MAX_ATTEMPTS,
  )
}

/**
 * 构造构建归档上传的请求头：归档元数据随流式正文一起声明，不再走 multipart 字段。
 * @param params 上传参数
 * @returns 认证与归档元数据请求头
 */
function buildArtifactUploadHeaders(params: BuildArtifactUploadParams): Record<string, string> {
  return {
    Authorization: `Bearer ${params.buildToken}`,
    'content-type': 'application/zip',
    'x-runtime-build-archive-entry-file': params.entryFile,
    'x-runtime-build-archive-sha256': params.sha256,
    'x-runtime-build-archive-size-bytes': String(params.sizeBytes),
  }
}

/**
 * 请求 JSON 接口并统一处理错误。
 * @param url 请求地址
 * @param headers 请求头
 * @param signal 端到端 deadline 的取消信号
 * @returns 解析后的 JSON
 */
async function requestJson<T>(url: string, headers: Record<string, string>, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      headers: {
        ...headers,
        Accept: 'application/json',
      },
      signal,
    })
  } catch (error) {
    throw buildBackendRequestNetworkError(url, error)
  }
  if (!response.ok) {
    throw await toBuildError(response, 'BACKEND_REQUEST_FAILED')
  }
  try {
    return await response.json() as T
  } catch (error) {
    throw buildBackendRequestNetworkError(url, error)
  }
}

/**
 * 将读取 preview artifact 时的网络异常保持为可重试的基础设施错误。
 */
function buildBackendRequestNetworkError(url: string, error: unknown): RuntimeBuildError {
  const message = error instanceof Error ? error.message : String(error || '未知网络错误')
  return new RuntimeBuildError(
    502,
    'RUNTIME_BACKEND_REQUEST_FAILED',
    `读取 Backend Runtime artifact 失败：${message}。URL ${url}`,
  )
}

/**
 * 将后端错误响应转换为统一 Runtime 构建错误。
 * @param response HTTP 响应
 * @param fallbackCode 兜底错误码
 * @returns 构建错误
 */
async function toBuildError(response: Response, fallbackCode: string): Promise<RuntimeBuildError> {
  let message = response.statusText || 'Backend 请求失败。'
  let code = fallbackCode
  try {
    const payload = await response.json()
    code = String(payload?.code || code)
    message = String(payload?.message || message)
  } catch {
    // 忽略非 JSON 错误体
  }
  return new RuntimeBuildError(response.status, code, message)
}

/**
 * 将资源下载网络异常转换为可定位的构建错误。
 * @param assetUrl 资源下载 URL
 * @param error 底层 fetch 异常
 * @param context 资源逻辑上下文
 * @returns Runtime 构建错误
 */
function buildAssetFetchNetworkError(
  assetUrl: string,
  error: unknown,
  context?: BuildAssetFetchContext,
): RuntimeBuildError {
  const message = error instanceof Error ? error.message : String(error || '未知网络错误')
  const cause = (error as { cause?: unknown } | null)?.cause
  const causeMessage = cause ? `；底层原因：${formatUnknownError(cause)}` : ''
  return new RuntimeBuildError(
    502,
    'BUILD_ASSET_FETCH_FAILED',
    appendAssetFetchContext(`构建静态资源下载失败：${message}${causeMessage}。`, assetUrl, context),
  )
}

/**
 * 将构建产物上传网络异常转换为可定位的构建错误。
 * @param uploadUrl 产物上传 URL
 * @param error 底层 fetch 异常
 * @param attempts 已尝试次数
 * @returns Runtime 构建错误
 */
function buildArtifactUploadNetworkError(uploadUrl: string, error: unknown, attempts: number): RuntimeBuildError {
  const message = error instanceof Error ? error.message : String(error || '未知网络错误')
  const cause = (error as { cause?: unknown } | null)?.cause
  const causeMessage = cause ? `；底层原因：${formatUnknownError(cause)}` : ''
  return new RuntimeBuildError(
    502,
    'BUILD_ARTIFACT_UPLOAD_NETWORK_FAILED',
    `构建产物上传失败：${message}${causeMessage}。已重试 ${attempts} 次，URL ${uploadUrl}`,
  )
}

/**
 * 给资源下载错误追加逻辑资源名、hash 与原始 URL。
 * @param message 原始错误信息
 * @param assetUrl 资源下载 URL
 * @param context 资源逻辑上下文
 * @returns 带定位信息的错误消息
 */
function appendAssetFetchContext(message: string, assetUrl: string, context?: BuildAssetFetchContext): string {
  const details = [
    context?.logicalName ? `资源名 ${context.logicalName}` : '',
    context?.fileHash ? `hash ${context.fileHash}` : '',
    context?.originalName ? `原始文件 ${context.originalName}` : '',
    assetUrl ? `URL ${assetUrl}` : '',
  ].filter(Boolean)
  return details.length > 0 ? `${message}（${details.join('，')}）` : message
}

/**
 * 格式化未知异常，避免日志只输出 `[object Object]`。
 * @param error 未知错误对象
 * @returns 可读错误文本
 */
function formatUnknownError(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  if (typeof error === 'object' && error !== null) {
    try {
      return JSON.stringify(error)
    } catch {
      return String(error)
    }
  }
  return String(error || '未知错误')
}

/**
 * 等待指定时间后继续执行。
 * @param ms 等待毫秒数
 */
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal)
  return new Promise((resolveSleep, rejectSleep) => {
    const onAbort = () => {
      clearTimeout(timeoutHandle)
      rejectSleep(signal?.reason || new Error('Runtime 任务已取消。'))
    }
    const timeoutHandle = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolveSleep()
    }, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * 在重试循环等同步边界主动感知 deadline 已取消，避免继续发起后续网络请求。
 */
function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw signal.reason || new Error('Runtime 任务已取消。')
  }
}

/**
 * 执行整项目构建、归档与上传。
 * @param params 构建参数
 * @returns 构建摘要
 */
export async function runProjectBuild(params: {
  runtimeRoot: string
  jobId: string
  artifactId: string
  buildToken: string
  baseUrl: string
  manifest: RuntimePreviewArtifactManifest
  configBundle: RuntimePreloadedConfigBundle
  backendClient: ReturnType<typeof createBuildBackendClient>
  deadline: RuntimeTaskDeadline
}): Promise<BuildArtifactSummary> {
  params.deadline.throwIfExpired()
  // Backend 只按用户输入原样存库，base_url 的规范化与非法值拒绝统一在这里做。
  const baseUrl = normalizeBuildBaseUrl(params.baseUrl)
  const workspaceStartedAt = Date.now()
  const tempRoot = await createDisposableRuntimeWorkspace(params.runtimeRoot)
  const distRoot = resolve(tempRoot, 'dist')
  const buildContext: RuntimeBuildLogContext = {
    jobId: params.jobId,
    artifactId: params.artifactId,
    baseUrl,
    runtimeRoot: params.runtimeRoot,
    tempRoot,
    distRoot,
  }

  try {
    params.deadline.throwIfExpired()
    // workspace 阶段必须计墙钟：全量 src 拷贝 + node_modules 软链是真实成本。
    logRuntimeBuild('workspace.created', {
      ...buildContext,
      durationMs: Date.now() - workspaceStartedAt,
    })

    const injectStartedAt = Date.now()
    logRuntimeBuild('modules.inject.start', buildContext)
    await injectSnapshotModules(tempRoot, params.artifactId, params.manifest, params.backendClient, params.deadline)
    params.deadline.throwIfExpired()
    logRuntimeBuild('modules.inject.done', {
      ...buildContext,
      durationMs: Date.now() - injectStartedAt,
      moduleCount: Object.keys(params.manifest.modules || {}).length,
    })

    const validateStartedAt = Date.now()
    logRuntimeBuild('workspace.validate.start', buildContext)
    await validateBuildWorkspaceSources(tempRoot)
    params.deadline.throwIfExpired()
    validateConfigAssetReferences(params.manifest, params.configBundle)
    logRuntimeBuild('workspace.validate.done', {
      ...buildContext,
      durationMs: Date.now() - validateStartedAt,
    })

    const materializeStartedAt = Date.now()
    logRuntimeBuild('assets.materialize.start', buildContext)
    const staticAssetMapping = await materializeSnapshotAssets(
      tempRoot,
      params.manifest,
      params.backendClient,
      params.deadline,
    )
    params.deadline.throwIfExpired()
    logRuntimeBuild('assets.materialize.done', {
      ...buildContext,
      durationMs: Date.now() - materializeStartedAt,
      materializedAssetCount: Object.keys(staticAssetMapping).length,
    })

    const entryStartedAt = Date.now()
    logRuntimeBuild('entry.write.start', buildContext)
    await writeBuildEntryFiles(tempRoot, {
      ...params.configBundle,
      manifest: {
        ...params.manifest,
        artifact_kind: 'build_release',
        asset_base_url: undefined,
        assets: staticAssetMapping,
      },
    })
    params.deadline.throwIfExpired()
    logRuntimeBuild('entry.write.done', {
      ...buildContext,
      durationMs: Date.now() - entryStartedAt,
    })

    const viteStartedAt = Date.now()
    logRuntimeBuild('vite.build.start', buildContext)
    await runRuntimeViteBuildInWorker({
      tempRoot,
      base: baseUrl,
      mode: 'project',
      outDir: distRoot,
      timeoutMs: params.deadline.remainingMs(),
      // 消费 Backend 下发的 runtime_kit_exports 快照作为构建端白名单；
      // 空数组时 worker 侧回落本地 manifest 门禁。
      runtimeKitAllowedImports: (params.configBundle.module_resolver?.runtime_kit_exports || []).map(
        item => String(item.import_path || ''),
      ).filter(Boolean),
      // 必须传 signal：租约失守时只有它能让 Vite 子进程真正退出，
      // 否则最耗 CPU/内存的阶段会一直跑到自然结束或 worker 超时。
      signal: params.deadline.signal,
    })
    params.deadline.throwIfExpired()
    logRuntimeBuild('vite.build.done', {
      ...buildContext,
      durationMs: Date.now() - viteStartedAt,
    })

    // ZIP 归档在独立子进程执行，避免同步压缩阻塞承载预览的主事件循环。
    logRuntimeBuild('artifact.archive.start', buildContext)
    const archiveStartedAt = Date.now()
    const parentRssBefore = process.memoryUsage().rss
    let parentRssPeak = parentRssBefore
    const rssSampler = setInterval(() => {
      parentRssPeak = Math.max(parentRssPeak, process.memoryUsage().rss)
    }, 50)
    rssSampler.unref?.()
    let archiveResult: Awaited<ReturnType<typeof runZipArchiveInWorker>>
    try {
      archiveResult = await runZipArchiveInWorker({
        distRoot,
        outputPath: resolve(tempRoot, 'artifact.zip'),
        timeoutMs: params.deadline.remainingMs(),
        signal: params.deadline.signal,
      })
    } finally {
      clearInterval(rssSampler)
      parentRssPeak = Math.max(parentRssPeak, process.memoryUsage().rss)
    }
    params.deadline.throwIfExpired()
    const artifactSha256 = archiveResult.sha256
    const artifactSizeBytes = archiveResult.sizeBytes
    // archive 墙钟与其它阶段口径一致（含 spawn/写脚本/父进程侧等待），child 自报时长仅作附注。
    logRuntimeBuild('artifact.archive.done', {
      ...buildContext,
      durationMs: Date.now() - archiveStartedAt,
      childDurationMs: archiveResult.durationMs,
      artifactSha256,
      artifactSizeBytes,
      archiveFileCount: archiveResult.fileCount,
      archiveRssBytes: archiveResult.rssBytes,
      archiveParentRssBeforeBytes: parentRssBefore,
      archiveParentRssPeakBytes: parentRssPeak,
      archiveCompressionLevel: archiveResult.compressionLevel,
    })

    const uploadStartedAt = Date.now()
    logRuntimeBuild('artifact.upload.start', {
      ...buildContext,
      artifactSha256,
      artifactSizeBytes,
    })
    const uploadSummary = await params.backendClient.uploadBuildArtifact({
      jobId: params.jobId,
      buildToken: params.buildToken,
      archivePath: archiveResult.archivePath,
      entryFile: 'index.html',
      sha256: artifactSha256,
      sizeBytes: artifactSizeBytes,
    }, params.deadline.signal)
    params.deadline.throwIfExpired()
    logRuntimeBuild('artifact.upload.done', {
      ...buildContext,
      durationMs: Date.now() - uploadStartedAt,
      artifactStorageKey: uploadSummary.artifact_storage_key,
      artifactDownloadUrl: uploadSummary.artifact_download_url,
      artifactEntryFile: uploadSummary.artifact_entry_file || 'index.html',
      artifactSha256: uploadSummary.artifact_sha256 || artifactSha256,
      artifactSizeBytes: uploadSummary.artifact_size_bytes || artifactSizeBytes,
    })

    return {
      artifactEntryFile: String(uploadSummary.artifact_entry_file || 'index.html'),
      artifactSha256: String(uploadSummary.artifact_sha256 || artifactSha256),
      artifactSizeBytes: Number(uploadSummary.artifact_size_bytes || artifactSizeBytes),
      message: String(uploadSummary.message || '构建完成。'),
    }
  } catch (error) {
    logRuntimeBuildError('run.failed', error, buildContext)
    throw error
  } finally {
    logRuntimeBuild('workspace.cleanup.start', buildContext)
    await rm(tempRoot, { recursive: true, force: true })
    logRuntimeBuild('workspace.cleanup.done', buildContext)
  }
}

/**
 * 对 preview artifact 执行只读代码诊断，不写出 dist，也不上传产物。
 * @param params 诊断参数
 * @returns 结构化诊断摘要
 */
async function runArtifactDiagnostics(params: {
  runtimeRoot: string
  artifactId: string
  manifest: RuntimePreviewArtifactManifest
  configBundle: RuntimePreloadedConfigBundle
  backendClient: ReturnType<typeof createBuildBackendClient>
  workspacePool: RuntimeDiagnosticsWorkspacePool
  deadline: RuntimeTaskDeadline
}): Promise<RuntimeDiagnosticsSummary> {
  params.deadline.throwIfExpired()
  const workspaceLease = await params.workspacePool.acquire()
  const tempRoot = workspaceLease.tempRoot
  const diagnosticsContext: RuntimeBuildLogContext = {
    artifactId: params.artifactId,
    runtimeRoot: params.runtimeRoot,
    tempRoot,
  }

  try {
    params.deadline.throwIfExpired()
    logRuntimeBuild('diagnostics.workspace.created', diagnosticsContext)
    const modulesStartedAt = Date.now()
    await injectSnapshotModules(tempRoot, params.artifactId, params.manifest, params.backendClient, params.deadline)
    await injectEntryModuleIfNeeded(tempRoot, params.artifactId, params.manifest, params.backendClient, params.deadline)
    logRuntimeBuild('diagnostics.modules.ready', {
      ...diagnosticsContext,
      durationMs: Date.now() - modulesStartedAt,
    })
    const validationStartedAt = Date.now()
    await validateBuildWorkspaceSources(tempRoot)
    params.deadline.throwIfExpired()
    validateConfigAssetReferences(params.manifest, params.configBundle)
    await writeBuildEntryFiles(tempRoot, {
      ...params.configBundle,
      manifest: {
        ...params.manifest,
        artifact_kind: 'build_release',
      },
    }, { mode: 'diagnostics' })
    logRuntimeBuild('diagnostics.workspace.validated', {
      ...diagnosticsContext,
      durationMs: Date.now() - validationStartedAt,
    })
    params.deadline.throwIfExpired()

    const viteStartedAt = Date.now()
    await workspaceLease.runViteBuild('./', params.deadline.remainingMs())
    logRuntimeBuild('diagnostics.vite.finished', {
      ...diagnosticsContext,
      durationMs: Date.now() - viteStartedAt,
    })
    params.deadline.throwIfExpired()
    return {
      success: true,
      status: 'passed',
      artifactId: params.artifactId,
      summary: '代码检查通过。',
      diagnostics: [],
    }
  } catch (error) {
    logRuntimeBuildError('diagnostics.run.failed', error, diagnosticsContext)
    if (isRuntimeDiagnosticsInfrastructureError(error)) {
      throw error
    }
    return buildFailedDiagnostics(params.artifactId, error)
  } finally {
    logRuntimeBuild('diagnostics.workspace.reset.start', diagnosticsContext)
    await workspaceLease.release()
    logRuntimeBuild('diagnostics.workspace.reset.done', diagnosticsContext)
  }
}

/**
 * 将 Runtime 诊断异常转为结构化失败结果。
 * @param artifactId artifact ID
 * @param error 原始异常
 * @returns 诊断失败摘要
 */
function buildFailedDiagnostics(artifactId: string, error: unknown): RuntimeDiagnosticsSummary {
  const diagnostic = buildDiagnosticFromError(error)
  return {
    success: false,
    status: 'failed',
    artifactId,
    summary: `发现 ${diagnostic.severity === 'error' ? 1 : 0} 个错误。`,
    diagnostics: [diagnostic],
  }
}

/**
 * 判断诊断异常是否属于可重试的 Runtime 基础设施故障。
 * 源码 Vite 错误必须继续作为 HTTP 200 的结构化诊断返回，不能被误判为服务故障。
 */
export function isRuntimeDiagnosticsInfrastructureError(error: unknown): boolean {
  if (error instanceof RuntimeBuildWorkerViteError) {
    return false
  }
  if (
    error instanceof RuntimeBuildWorkerProcessError
    || error instanceof RuntimeViteTaskSchedulerError
    || error instanceof RuntimeTaskDeadlineError
  ) {
    return true
  }
  if (error instanceof RuntimeDiagnosticsWorkspaceError || error instanceof RuntimeBuildError) {
    return error.statusCode >= 500
  }
  const code = String((error as { code?: unknown } | null)?.code || '')
  return [
    'EACCES',
    'EAI_AGAIN',
    'ECONNABORTED',
    'ECONNREFUSED',
    'ECONNRESET',
    'EIO',
    'EMFILE',
    'ENFILE',
    'ENOSPC',
    'ENOTFOUND',
    'EPIPE',
    'ETIMEDOUT',
  ].includes(code)
}

/**
 * 从 Vite、Rollup 或 Runtime 校验异常中提取可读诊断。
 * @param error 原始异常
 * @returns 单条结构化诊断
 */
function buildDiagnosticFromError(error: unknown): RuntimeCodeDiagnostic {
  if (error instanceof RuntimeBuildError || error instanceof RuntimeBuildWorkerProcessError) {
    return {
      severity: 'error',
      source: 'runtime',
      code: error.code,
      message: error.message,
    }
  }

  const source = error as {
    message?: string
    id?: string
    plugin?: string
    code?: string
    loc?: { file?: string; line?: number; column?: number }
  }
  const message = String(source?.message || 'Runtime 代码检查失败。')
  return {
    severity: 'error',
    source: source?.plugin ? `vite:${source.plugin}` : 'vite',
    code: String(source?.code || 'RUNTIME_VITE_COMPILE_FAILED'),
    message,
    file_path: normalizeDiagnosticFilePath(source?.loc?.file || source?.id || ''),
    line: normalizeDiagnosticNumber(source?.loc?.line),
    column: normalizeDiagnosticNumber(source?.loc?.column),
  }
}

/**
 * 规范化诊断文件路径，避免返回 Vite 查询参数。
 * @param rawPath 原始路径
 * @returns 规范化路径或 undefined
 */
function normalizeDiagnosticFilePath(rawPath: string): string | undefined {
  const normalized = String(rawPath || '').trim().replace(/\\/g, '/').split('?', 1)[0]
  return normalized || undefined
}

/**
 * 规范化诊断行列号。
 * @param value 原始数值
 * @returns 正整数或 undefined
 */
function normalizeDiagnosticNumber(value: unknown): number | undefined {
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized > 0 ? normalized : undefined
}

/**
 * 将 build snapshot 的远程模块写入临时工作区。
 * @param tempRoot 临时工作区
 * @param artifactId build snapshot artifact ID
 * @param manifest 预览清单
 * @param backendClient 后端客户端
 */
async function injectSnapshotModules(
  tempRoot: string,
  artifactId: string,
  manifest: RuntimePreviewArtifactManifest,
  backendClient: ReturnType<typeof createBuildBackendClient>,
  deadline: RuntimeTaskDeadline,
): Promise<void> {
  const injectedPaths = new Set<string>()
  const logicalPaths = Object.keys(manifest.modules || {})
  const fetchStartedAt = Date.now()
  for (let offset = 0; offset < logicalPaths.length; offset += MODULE_BATCH_SIZE) {
    const batchPaths = logicalPaths.slice(offset, offset + MODULE_BATCH_SIZE)
    deadline.throwIfExpired()
    const modules = await backendClient.fetchModuleSources(artifactId, batchPaths, deadline.signal)
    await Promise.all(batchPaths.map(async logicalPath => {
      const resolvedModule = resolveWritableRuntimeModulePath(tempRoot, logicalPath)
      if (injectedPaths.has(resolvedModule.logicalPath)) {
        throw new RuntimeDiagnosticsWorkspaceError(
          409,
          'RUNTIME_DIAGNOSTICS_MODULE_PATH_DUPLICATED',
          `多个诊断模块映射到同一路径：${resolvedModule.logicalPath}`,
        )
      }
      injectedPaths.add(resolvedModule.logicalPath)
      const targetPath = resolvedModule.targetPath
      await mkdir(resolve(targetPath, '..'), { recursive: true })
      await writeFile(targetPath, modules[logicalPath], 'utf-8')
    }))
    deadline.throwIfExpired()
  }
  logRuntimeBuild('diagnostics.modules.injected', {
    artifactId,
    moduleCount: logicalPaths.length,
    durationMs: Date.now() - fetchStartedAt,
  })
}

/**
 * 单页预览入口可能不在 manifest 白名单中，诊断仍需把入口源码注入临时工作区。
 * @param tempRoot 临时工作区
 * @param artifactId artifact ID
 * @param manifest 预览清单
 * @param backendClient 后端客户端
 */
async function injectEntryModuleIfNeeded(
  tempRoot: string,
  artifactId: string,
  manifest: RuntimePreviewArtifactManifest,
  backendClient: ReturnType<typeof createBuildBackendClient>,
  deadline: RuntimeTaskDeadline,
): Promise<void> {
  if (manifest.entry_descriptor?.entry_type !== 'module') {
    return
  }
  const entryModulePath = normalizeRuntimeModulePath(manifest.entry_descriptor.module_path || '')
  if (!entryModulePath || manifest.modules?.[entryModulePath]) {
    return
  }
  deadline.throwIfExpired()
  const content = await backendClient.fetchModuleSource(artifactId, entryModulePath, deadline.signal)
  const targetPath = resolveWritableRuntimeModulePath(tempRoot, entryModulePath).targetPath
  await mkdir(resolve(targetPath, '..'), { recursive: true })
  await writeFile(targetPath, content, 'utf-8')
  deadline.throwIfExpired()
}

/**
 * 校验工作区源码中不存在根绝对静态资源引用。
 * @param tempRoot 临时工作区根目录
 */
async function validateBuildWorkspaceSources(tempRoot: string): Promise<void> {
  const sourceRoot = resolve(tempRoot, 'src')
  const violations: string[] = []
  await collectTextFileViolations(sourceRoot, violations)
  if (violations.length > 0) {
    throw new RuntimeBuildError(
      409,
      'BUILD_SOURCE_ABSOLUTE_ASSET_PATH_FORBIDDEN',
      `构建源码中存在根绝对静态资源引用：${violations.join('；')}`,
    )
  }
}

/**
 * 递归扫描源码文本中的非法根绝对静态资源引用。
 * @param rootDir 扫描目录
 * @param violations 违规列表
 */
async function collectTextFileViolations(rootDir: string, violations: string[]): Promise<void> {
  if (!await pathExists(rootDir)) {
    return
  }
  const entries = await readdir(rootDir, { withFileTypes: true })
  for (const entry of entries) {
    const entryPath = resolve(rootDir, entry.name)
    if (entry.isDirectory()) {
      await collectTextFileViolations(entryPath, violations)
      continue
    }
    if (/\.(test|spec)\.[^/]+$/i.test(entry.name)) {
      continue
    }
    if (!/\.(vue|ts|tsx|js|jsx|css)$/.test(entry.name)) {
      continue
    }
    const content = await readFile(entryPath, 'utf-8')
    if (hasForbiddenRootAbsoluteAssetPath(content)) {
      violations.push(entryPath.replace(/\\/g, '/'))
    }
  }
}

/**
 * 校验 themes/icons/fonts 中声明的逻辑资源必须命中 manifest。
 * @param manifest build snapshot manifest
 * @param configBundle build snapshot config bundle
 */
function validateConfigAssetReferences(
  manifest: RuntimePreviewArtifactManifest,
  configBundle: RuntimePreloadedConfigBundle,
): void {
  const assetKeys = new Set(Object.keys(manifest.assets || {}).map(item => normalizeAssetKey(item)))
  const missingAssetKeys = collectConfigAssetKeys(configBundle).filter(assetKey => !assetKeys.has(assetKey))
  if (missingAssetKeys.length > 0) {
    throw new RuntimeBuildError(
      409,
      'BUILD_CONFIG_ASSET_MISSING',
      `构建配置引用了未进入 snapshot 的静态资源：${missingAssetKeys.join(', ')}`,
    )
  }
}

/**
 * 从 build snapshot 配置包中收集必须进入 manifest 的逻辑资源名。
 * @param configBundle build snapshot 配置包
 * @returns 去重后的逻辑资源名
 */
function collectConfigAssetKeys(configBundle: RuntimePreloadedConfigBundle): string[] {
  const assetKeys = new Set<string>()

  const themeEntries = Object.values(((configBundle.themes as Record<string, unknown>)?.themes as Record<string, Record<string, unknown>>) || {})
  for (const themeEntry of themeEntries) {
    appendAssetKey(assetKeys, themeEntry?.logo)
    appendAssetKey(assetKeys, themeEntry?.invertLogo)
  }

  const iconEntries = ((configBundle.icons as Record<string, unknown>)?.static_icons as Array<Record<string, unknown>>) || []
  for (const iconEntry of iconEntries) {
    appendAssetKey(assetKeys, iconEntry?.src)
  }

  const fontEntries = Object.values(((configBundle.fonts as unknown as Record<string, unknown>)?.items as Record<string, Record<string, unknown>>) || {})
  for (const fontEntry of fontEntries) {
    appendAssetKey(assetKeys, fontEntry?.asset_name)
  }

  return Array.from(assetKeys)
}

/**
 * 将单个逻辑资源名加入校验集合。
 * @param target 目标集合
 * @param rawValue 原始资源名
 */
function appendAssetKey(target: Set<string>, rawValue: unknown): void {
  const normalizedValue = normalizeAssetKey(String(rawValue || ''))
  if (!normalizedValue || /^https?:\/\//i.test(normalizedValue)) {
    return
  }
  target.add(normalizedValue)
}

/**
 * 下载并落盘 build snapshot 中声明的静态资源。
 * @param tempRoot 临时工作区
 * @param manifest 预览清单
 * @param backendClient 后端客户端
 * @returns 供静态构建使用的资源映射
 */
async function materializeSnapshotAssets(
  tempRoot: string,
  manifest: RuntimePreviewArtifactManifest,
  backendClient: ReturnType<typeof createBuildBackendClient>,
  deadline: RuntimeTaskDeadline,
): Promise<Record<string, string>> {
  const staticAssetMapping: Record<string, string> = {}
  const assetBaseUrl = String(manifest.asset_base_url || '').replace(/\/+$/, '')
  if (!assetBaseUrl) {
    throw new RuntimeBuildError(409, 'BUILD_ASSET_BASE_URL_MISSING', '构建快照缺少 asset_base_url。')
  }

  for (const [logicalName, mappedValue] of Object.entries(manifest.assets || {})) {
    deadline.throwIfExpired()
    const metadata = manifest.asset_metadata?.[logicalName]
    const fileHash = String(metadata?.file_hash || mappedValue || '').trim()
    if (!fileHash) {
      continue
    }

    const staticPath = buildStaticAssetPath(fileHash, metadata?.original_name, logicalName)
    const assetUrl = `${assetBaseUrl}/${encodeURIComponent(fileHash)}`
    const content = await backendClient.fetchAssetBinary(assetUrl, {
      logicalName,
      fileHash,
      originalName: metadata?.original_name,
    }, deadline.signal)

    await writePublicBinary(tempRoot, staticPath, content)
    deadline.throwIfExpired()
    staticAssetMapping[logicalName] = staticPath
  }

  return staticAssetMapping
}

/**
 * 向 public 目录写入二进制资源。
 * @param tempRoot 临时工作区
 * @param relativePath public 相对路径
 * @param content 文件内容
 */
async function writePublicBinary(tempRoot: string, relativePath: string, content: Buffer): Promise<void> {
  const normalizedPath = String(relativePath || '').trim().replace(/^\.?\/*/, '').replace(/\\/g, '/')
  if (!normalizedPath) {
    return
  }
  const targetPath = resolve(tempRoot, 'public', normalizedPath.split('/').join(sep))
  await mkdir(resolve(targetPath, '..'), { recursive: true })
  await writeFile(targetPath, content)
}

/**
 * 写入构建专用入口脚本与 index.html。
 * @param tempRoot 临时工作区
 * @param preloadedConfig 预加载配置包
 * @param options 入口生成模式
 */
async function writeBuildEntryFiles(
  tempRoot: string,
  preloadedConfig: RuntimePreloadedConfigBundle,
  options: { mode?: 'project' | 'diagnostics' } = {},
): Promise<void> {
  const entryFilePath = resolve(tempRoot, 'src/__build_entry__.ts')
  const indexHtmlPath = resolve(tempRoot, 'index.html')
  const buildReleaseViewModulesPath = resolve(tempRoot, 'src/core/utils/build-release-view-modules.ts')
  const diagnosticsBuildModulesPath = resolve(tempRoot, 'src/core/utils/build-diagnostics-modules.ts')
  const manifestModulePaths = [
    ...Object.keys(preloadedConfig.manifest?.modules || {}),
    String(preloadedConfig.manifest?.entry_descriptor?.module_path || ''),
  ]
  const entrySource = options.mode === 'diagnostics'
    ? createDiagnosticsBuildEntrySource(preloadedConfig)
    : createBuildEntrySource(preloadedConfig)

  await writeFile(
    entryFilePath,
    entrySource,
    'utf-8',
  )

  await writeFile(
    buildReleaseViewModulesPath,
    createBuildReleaseViewModulesSource(manifestModulePaths),
    'utf-8',
  )

  await writeFile(
    diagnosticsBuildModulesPath,
    createDiagnosticsBuildModulesSource(manifestModulePaths),
    'utf-8',
  )

  await writeFile(
    indexHtmlPath,
    createBuildIndexHtmlSource(),
    'utf-8',
  )
}

/**
 * 判断路径是否存在。
 * @param targetPath 目标路径
 * @returns 是否存在
 */
async function pathExists(targetPath: string): Promise<boolean> {
  try {
    await access(targetPath, fsConstants.F_OK)
    return true
  } catch {
    return false
  }
}

/**
 * 输出 JSON 响应。
 * @param res Node 响应对象
 * @param statusCode HTTP 状态码
 * @param payload 返回体
 */
function sendJson(res: RuntimeNodeResponse, statusCode: number, payload: Record<string, unknown>): void {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(payload))
}

/**
 * 输出统一的构建错误响应。
 * @param res Node 响应对象
 * @param error 原始错误
 */
function sendBuildError(res: RuntimeNodeResponse, error: unknown): void {
  if (
    error instanceof RuntimeBuildError
    || error instanceof RuntimeViteTaskSchedulerError
    || error instanceof RuntimeDiagnosticsWorkspaceError
    || error instanceof RuntimeTaskDeadlineError
  ) {
    return sendJson(res, error.statusCode, {
      success: false,
      code: error.code,
      message: error.message,
    })
  }

  if (error instanceof RuntimeBuildWorkerProcessError) {
    return sendJson(res, error.statusCode, {
      success: false,
      code: error.code,
      message: error.message,
    })
  }

  if (error instanceof RuntimeBuildWorkerViteError) {
    return sendJson(res, 500, {
      success: false,
      code: error.code,
      message: error.message,
    })
  }

  return sendJson(res, 500, {
    success: false,
    code: 'RUNTIME_BUILD_FAILED',
    message: error instanceof Error ? error.message : 'Runtime 构建失败。',
  })
}

/**
 * Runtime 内部整项目构建错误。
 */
export class RuntimeBuildError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string) {
    super(message)
    this.statusCode = statusCode
    this.code = code
  }
}
