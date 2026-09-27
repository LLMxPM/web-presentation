/**
 * 文件用途：Runtime Build Worker 领取循环——从 Backend claim API 拉取持久构建任务，
 * 执行整包构建并 complete，替代 Backend 长同步 HTTP 派发。
 * 依赖通过参数注入，避免与 runtime-build-runner 形成循环 import。
 */

import { logRuntimeServer } from '../utils/runtime-logger'
import { RuntimeTaskAbortedError, runWithRuntimeTaskDeadline } from './runtime-task-deadline'
import type { RuntimePreloadedConfigBundle, RuntimePreviewArtifactManifest } from '../shared/runtime-preview'

/** claim API 返回的任务载荷。 */
export interface BuildJobClaimPayload {
  job_id: number | null
  project_id: number | null
  snapshot_release_id: string | null
  base_url: string | null
  workspace_id: number | null
  attempt_id: string | null
  lease_owner: string | null
  lease_expires_at: string | null
  /** 任务绝对 wall-clock 期限；本地执行预算据此裁剪。 */
  deadline_at: string | null
  build_token: string | null
  service_token: string | null
  message: string
}

/** 构建客户端工厂：由 runtime-build-runner 注入，保持单一事实源。 */
export type CreateBuildBackendClientFn = (options: {
  backendApiBaseUrl: string
  serviceToken: string
}) => {
  fetchManifest: (artifactId: string, signal?: AbortSignal) => Promise<RuntimePreviewArtifactManifest>
  fetchConfigBundle: (artifactId: string, signal?: AbortSignal) => Promise<RuntimePreloadedConfigBundle>
}

/** 整项目构建执行函数：由 runtime-build-runner 注入。 */
export type RunProjectBuildFn = (params: {
  runtimeRoot: string
  jobId: string
  artifactId: string
  buildToken: string
  baseUrl: string
  manifest: RuntimePreviewArtifactManifest
  configBundle: RuntimePreloadedConfigBundle
  backendClient: ReturnType<CreateBuildBackendClientFn>
  deadline: { signal: AbortSignal; remainingMs: () => number; throwIfExpired: () => void }
}) => Promise<{
  artifactEntryFile: string
  artifactSha256: string
  artifactSizeBytes: number
  message: string
}>

export interface RuntimeBuildQueueWorkerOptions {
  backendApiBaseUrl: string
  workerCredential: string
  workerId?: string
  pollIntervalMs?: number
  requestTimeoutMs?: number
  /**
   * 单实例并发消费者数量，应与 project lane 执行预算保持一致：每个消费者串行领取一个任务，
   * 消费者数量少于并发预算时，多出来的槽位永远不会被用满。
   */
  concurrency?: number
  /** 续租间隔；同时决定本地租约看门狗的 tick 与安全提前量。 */
  renewIntervalMs?: number
  runtimeRoot: string
  scheduler: {
    schedule: <T>(kind: 'project', run: () => Promise<T>) => Promise<T>
  }
  runProjectBuild: RunProjectBuildFn
  createBuildBackendClient: CreateBuildBackendClientFn
}

const DEFAULT_POLL_INTERVAL_MS = 2000
const DEFAULT_RENEW_INTERVAL_MS = 30_000
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000
const DEFAULT_BUILD_WORKER_TIMEOUT_MS = 600_000
/** 单进程并发消费者硬上限，避免误配一次性压垮容器。 */
const MAX_CONSUMER_COUNT = 16
/** 无法从响应解析出服务端时刻时，保守按该时长维持本地租约。 */
const FALLBACK_LEASE_MS = 960_000
/** 剩余总期限低于该值时不再启动构建：注定超期的任务交给恢复循环收敛。 */
const MIN_BUILD_BUDGET_MS = 5_000

/**
 * 按并发预算启动等量的 Runtime Build Worker 领取循环，返回统一停止函数。
 * @param options Worker 配置
 * @returns 停止全部消费者的函数
 */
export function startRuntimeBuildQueueWorker(options: RuntimeBuildQueueWorkerOptions): () => void {
  const baseWorkerId = options.workerId || `runtime-build-${process.pid}`
  const pollIntervalMs = Math.max(500, options.pollIntervalMs || DEFAULT_POLL_INTERVAL_MS)
  const renewIntervalMs = Math.max(1_000, options.renewIntervalMs || DEFAULT_RENEW_INTERVAL_MS)
  const concurrency = clampConcurrency(options.concurrency)
  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')
  let stopped = false
  const activeLeases = new Set<LeaseRenewalHandle>()

  logRuntimeServer('info', 'runtime.build.worker.started', 'Runtime Build Worker 领取循环已启动。', {
    module: 'runtime.build.worker',
    workerId: baseWorkerId,
    apiBaseUrl,
    pollIntervalMs,
    renewIntervalMs,
    concurrency,
  })

  for (let index = 0; index < concurrency; index += 1) {
    // 每个消费者使用独立 lease_owner 标识：租约归属和排障日志能落到具体槽位。
    const consumerId = concurrency === 1 ? baseWorkerId : `${baseWorkerId}-${index + 1}`
    void runConsumerLoop({
      apiBaseUrl,
      consumerId,
      options,
      pollIntervalMs,
      renewIntervalMs,
      activeLeases,
      isStopped: () => stopped,
    })
  }

  return () => {
    stopped = true
    for (const lease of activeLeases) {
      lease.stop()
    }
    activeLeases.clear()
    logRuntimeServer('info', 'runtime.build.worker.stopped', 'Runtime Build Worker 领取循环已停止。', {
      module: 'runtime.build.worker',
      workerId: baseWorkerId,
      concurrency,
    })
  }
}

interface ConsumerLoopParams {
  apiBaseUrl: string
  consumerId: string
  options: RuntimeBuildQueueWorkerOptions
  pollIntervalMs: number
  renewIntervalMs: number
  activeLeases: Set<LeaseRenewalHandle>
  isStopped: () => boolean
}

/**
 * 单个消费者的领取循环：串行执行「claim → 构建 → complete」。
 * 并发度来自并行的消费者数量，而不是单次循环内派发多任务。
 */
async function runConsumerLoop(params: ConsumerLoopParams): Promise<void> {
  const { apiBaseUrl, consumerId, options, pollIntervalMs } = params
  while (!params.isStopped()) {
    try {
      const claim = await claimBuildJob(apiBaseUrl, options.workerCredential, consumerId, options.requestTimeoutMs)
      if (claim.job_id && claim.build_token && claim.service_token) {
        const lease = startLeaseRenewal({
          apiBaseUrl,
          buildToken: claim.build_token,
          jobId: claim.job_id,
          workerId: consumerId,
          requestTimeoutMs: options.requestTimeoutMs,
          renewIntervalMs: params.renewIntervalMs,
          leaseExpiresAtMs: resolveLocalLeaseDeadline(claim.lease_expires_at),
        })
        params.activeLeases.add(lease)
        try {
          await executeClaimedBuildJob(claim, options, consumerId, lease.abortController)
        } finally {
          lease.stop()
          params.activeLeases.delete(lease)
        }
        continue
      }
      if (claim.job_id) {
        // 领取成功但缺少令牌：Backend 已把任务标为失败，记录后继续轮询。
        logRuntimeServer('warn', 'runtime.build.worker.claim_unusable', '领取结果缺少令牌，跳过本次任务。', {
          module: 'runtime.build.worker',
          workerId: consumerId,
          jobId: claim.job_id,
          message: claim.message,
        })
      }
    } catch (error) {
      logRuntimeServer('warn', 'runtime.build.worker.poll_failed', 'Runtime Build Worker 领取循环单次失败。', {
        module: 'runtime.build.worker',
        workerId: consumerId,
        error: error instanceof Error ? error.message : String(error),
      })
    }
    await sleep(pollIntervalMs)
  }
}

/**
 * 向 Backend claim 一个构建任务；空闲时返回空 job_id。
 */
async function claimBuildJob(
  apiBaseUrl: string,
  workerCredential: string,
  workerId: string,
  requestTimeoutMs?: number,
): Promise<BuildJobClaimPayload> {
  const response = await fetchWithTimeout(
    `${apiBaseUrl}/internal/runtime/build-jobs/claim`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${workerCredential}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ worker_id: workerId }),
    },
    requestTimeoutMs,
  )
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`claim 失败：HTTP ${response.status} ${body.slice(0, 200)}`)
  }
  return await response.json() as BuildJobClaimPayload
}

interface LeaseRenewalHandle {
  stop: () => void
  abortController: AbortController
}

interface LeaseRenewalParams {
  apiBaseUrl: string
  buildToken: string
  jobId: number
  workerId: string
  requestTimeoutMs?: number
  renewIntervalMs: number
  leaseExpiresAtMs: number
}

/**
 * 周期续租并维护本地租约视图。
 *
 * 失守判定有两条缺一不可的路径：
 * 1. Backend 明确拒绝（401/409）——立即中止在跑构建；
 * 2. Backend 不可达或响应异常——没有任何信号告知「租约已没」，
 *    只能由本地看门狗在扣除安全提前量后自行停手。
 * 只依赖第 1 条会让断网场景下的僵尸 Worker 继续烧 CPU 直到构建自然结束。
 */
function startLeaseRenewal(params: LeaseRenewalParams): LeaseRenewalHandle {
  const abortController = new AbortController()
  // 安全提前量：留出一次续租往返的余量，避免在到期边界上误杀仍可续期的任务。
  const safetyMarginMs = Math.max(1_000, Math.floor(params.renewIntervalMs / 2))
  let leaseExpiresAtMs = params.leaseExpiresAtMs
  let stopping = false

  const abortLeaseLost = (reason: string) => {
    if (!abortController.signal.aborted) {
      abortController.abort(new RuntimeTaskAbortedError(reason))
    }
  }

  const renewOnce = async (): Promise<void> => {
    try {
      const response = await fetchWithTimeout(
        `${params.apiBaseUrl}/internal/runtime/build-jobs/${params.jobId}/renew`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${params.buildToken}`,
            Accept: 'application/json',
          },
        },
        params.requestTimeoutMs,
      )
      if (response.ok) {
        const payload = await response.json().catch(() => null) as { lease_expires_at?: string } | null
        const remainingMs = remainingFromServerClock(payload?.lease_expires_at ?? null)
        // Backend 时钟与本地不保证严格同步，因此只采用「距现在的剩余时长」而非绝对时刻。
        leaseExpiresAtMs = Date.now() + (remainingMs ?? FALLBACK_LEASE_MS)
        return
      }
      const text = await response.text().catch(() => '')
      logRuntimeServer('warn', 'runtime.build.worker.renew_rejected', '构建租约续期被拒绝。', {
        module: 'runtime.build.worker',
        jobId: params.jobId,
        workerId: params.workerId,
        status: response.status,
        body: text.slice(0, 200),
      })
      if (response.status === 401 || response.status === 409) {
        abortLeaseLost(`构建租约失守：HTTP ${response.status}`)
      }
      // 其它状态码不即时中止：Backend 仍是权威判定方，本地由看门狗兜底。
    } catch (error) {
      logRuntimeServer('warn', 'runtime.build.worker.renew_failed', '构建租约续期请求失败，租约进入本地倒计时。', {
        module: 'runtime.build.worker',
        jobId: params.jobId,
        workerId: params.workerId,
        leaseRemainingMs: Math.max(0, Math.round(leaseExpiresAtMs - safetyMarginMs - Date.now())),
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  const renewTimer = setInterval(() => {
    if (!stopping) {
      void renewOnce()
    }
  }, params.renewIntervalMs)
  const watchdogTimer = setInterval(() => {
    if (stopping) {
      return
    }
    if (Date.now() >= leaseExpiresAtMs - safetyMarginMs) {
      abortLeaseLost('构建租约本地判定已到期，停止继续投入计算。')
    }
  }, Math.max(1_000, Math.floor(params.renewIntervalMs / 3)))
  renewTimer.unref?.()
  watchdogTimer.unref?.()

  return {
    abortController,
    stop: () => {
      stopping = true
      clearInterval(renewTimer)
      clearInterval(watchdogTimer)
    },
  }
}

async function executeClaimedBuildJob(
  claim: BuildJobClaimPayload,
  options: RuntimeBuildQueueWorkerOptions,
  workerId: string,
  leaseAbort: AbortController,
): Promise<void> {
  const jobId = Number(claim.job_id)
  const buildToken = String(claim.build_token || '')
  const serviceToken = String(claim.service_token || '')
  const artifactId = String(claim.snapshot_release_id || '')
  const baseUrl = String(claim.base_url || './')
  const workerTimeoutMs = Number(process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS) || DEFAULT_BUILD_WORKER_TIMEOUT_MS
  // Backend 已把租约与令牌裁剪到绝对 deadline，执行侧同样不得超过剩余预算，
  // 否则「排队到最后一秒」的任务仍能再跑一个完整 timeout。
  const deadlineRemainingMs = remainingFromServerClock(claim.deadline_at)
  const executionBudgetMs = deadlineRemainingMs === null
    ? workerTimeoutMs
    : Math.min(workerTimeoutMs, deadlineRemainingMs)
  const logContext = {
    module: 'runtime.build.worker',
    jobId,
    workerId,
    artifactId,
    baseUrl,
    executionBudgetMs: Math.round(executionBudgetMs),
  }

  logRuntimeServer('info', 'runtime.build.worker.job_acquired', 'Runtime Build Worker 已领取构建任务。', logContext)
  const startedAt = Date.now()
  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')

  let summary: Awaited<ReturnType<RunProjectBuildFn>>
  try {
    if (executionBudgetMs < MIN_BUILD_BUDGET_MS) {
      throw new Error(`构建任务剩余总期限不足 ${Math.max(0, Math.round(executionBudgetMs))}ms，放弃执行。`)
    }
    const backendClient = options.createBuildBackendClient({
      backendApiBaseUrl: options.backendApiBaseUrl,
      serviceToken,
    })
    summary = await options.scheduler.schedule('project', async () => {
      return runWithRuntimeTaskDeadline(
        'project',
        executionBudgetMs,
        async deadline => {
          const manifest = await backendClient.fetchManifest(artifactId, deadline.signal)
          const configBundle = await backendClient.fetchConfigBundle(artifactId, deadline.signal)
          deadline.throwIfExpired()
          return options.runProjectBuild({
            runtimeRoot: options.runtimeRoot,
            jobId: String(jobId),
            artifactId,
            buildToken,
            baseUrl,
            manifest,
            configBundle,
            backendClient,
            deadline,
          })
        },
        leaseAbort.signal,
      )
    })
  } catch (error) {
    // 仅确定性构建失败才上报 failed；成功上传后的 complete 抖动不得走此路径。
    const errorMessage = error instanceof Error ? error.message : String(error || '未知构建错误')
    logRuntimeServer('error', 'runtime.build.worker.job_failed', 'Runtime Build Worker 构建任务失败。', {
      ...logContext,
      durationMs: Date.now() - startedAt,
      error: errorMessage,
    })
    try {
      await completeBuildJob(apiBaseUrl, buildToken, jobId, {
        success: false,
        error_message: errorMessage.slice(0, 2000),
      }, options.requestTimeoutMs)
    } catch (completeError) {
      logRuntimeServer('error', 'runtime.build.worker.complete_failed', 'Runtime Build Worker 上报失败终态被拒绝。', {
        ...logContext,
        error: completeError instanceof Error ? completeError.message : String(completeError),
      })
    }
    return
  }

  // 构建与产物上传已成功：complete 上报失败时禁止再写 failed，
  // 否则会清空已提升产物。留给租约过期恢复按 succeeded 收敛。
  try {
    await completeBuildJob(apiBaseUrl, buildToken, jobId, { success: true }, options.requestTimeoutMs)
    logRuntimeServer('info', 'runtime.build.worker.job_succeeded', 'Runtime Build Worker 构建任务完成。', {
      ...logContext,
      durationMs: Date.now() - startedAt,
      artifactEntryFile: summary.artifactEntryFile,
      artifactSha256: summary.artifactSha256,
      artifactSizeBytes: summary.artifactSizeBytes,
    })
  } catch (completeError) {
    logRuntimeServer('error', 'runtime.build.worker.complete_success_lost', '构建成功但终态上报失败，交由租约恢复收敛。', {
      ...logContext,
      durationMs: Date.now() - startedAt,
      artifactEntryFile: summary.artifactEntryFile,
      artifactSha256: summary.artifactSha256,
      error: completeError instanceof Error ? completeError.message : String(completeError),
    })
  }
}

async function completeBuildJob(
  apiBaseUrl: string,
  buildToken: string,
  jobId: number,
  body: { success: boolean; error_message?: string },
  requestTimeoutMs?: number,
): Promise<void> {
  const response = await fetchWithTimeout(
    `${apiBaseUrl}/internal/runtime/build-jobs/${jobId}/complete`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${buildToken}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    },
    requestTimeoutMs,
  )
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`complete 失败：HTTP ${response.status} ${text.slice(0, 200)}`)
  }
}

/**
 * 带超时的 fetch：避免 Backend 挂起时 Worker 循环永久卡住。
 */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs?: number,
): Promise<Response> {
  const normalized = Math.max(1000, timeoutMs || DEFAULT_REQUEST_TIMEOUT_MS)
  return await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(normalized),
  })
}

/**
 * 把 Backend 返回的 ISO 时刻换算成「距本地现在的剩余毫秒」。
 * @returns 缺失或非法时返回 null，由调用方决定兜底口径；已过期时返回 0
 */
function remainingFromServerClock(rawIso: string | null | undefined): number | null {
  const text = String(rawIso || '').trim()
  if (!text) {
    return null
  }
  const timestamp = Date.parse(text)
  if (Number.isNaN(timestamp)) {
    return null
  }
  return Math.max(0, timestamp - Date.now())
}

/**
 * 领取响应里的租约时刻换算为本地到期时间戳；缺失时保守按默认租约时长起算。
 */
function resolveLocalLeaseDeadline(rawIso: string | null | undefined): number {
  return Date.now() + (remainingFromServerClock(rawIso) ?? FALLBACK_LEASE_MS)
}

/**
 * 归一化并发消费者数量：至少 1，且不超过单进程硬上限。
 */
function clampConcurrency(raw: number | undefined): number {
  const normalized = Number.isFinite(raw) ? Math.floor(Number(raw)) : 1
  return Math.min(MAX_CONSUMER_COUNT, Math.max(1, normalized))
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    const timer = setTimeout(resolve, ms)
    timer.unref?.()
  })
}
