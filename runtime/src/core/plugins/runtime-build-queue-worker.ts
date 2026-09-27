/**
 * 文件用途：Runtime Build Worker 领取循环——从 Backend claim API 拉取持久构建任务，
 * 执行整包构建并 complete，替代 Backend 长同步 HTTP 派发。
 * 依赖通过参数注入，避免与 runtime-build-runner 形成循环 import。
 */

import { logRuntimeServer } from '../utils/runtime-logger'
import { runWithRuntimeTaskDeadline } from './runtime-task-deadline'
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

/**
 * 启动 Runtime Build Worker 领取循环；返回停止函数。
 * @param options Worker 配置
 * @returns 停止循环的函数
 */
export function startRuntimeBuildQueueWorker(options: RuntimeBuildQueueWorkerOptions): () => void {
  const workerId = options.workerId || `runtime-build-${process.pid}`
  const pollIntervalMs = Math.max(500, options.pollIntervalMs || DEFAULT_POLL_INTERVAL_MS)
  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')
  let stopped = false
  let activeRenew: LeaseRenewalHandle | null = null

  logRuntimeServer('info', 'runtime.build.worker.started', 'Runtime Build Worker 领取循环已启动。', {
    module: 'runtime.build.worker',
    workerId,
    apiBaseUrl,
    pollIntervalMs,
  })

  const loop = async (): Promise<void> => {
    while (!stopped) {
      try {
        const claim = await claimBuildJob(apiBaseUrl, options.workerCredential, workerId, options.requestTimeoutMs)
        if (claim.job_id && claim.build_token && claim.service_token) {
          activeRenew = startLeaseRenewal({
            apiBaseUrl,
            buildToken: claim.build_token,
            jobId: claim.job_id,
            workerId,
            requestTimeoutMs: options.requestTimeoutMs,
          })
          try {
            await executeClaimedBuildJob(claim, options, workerId, activeRenew.abortController)
          } finally {
            activeRenew.stop()
            activeRenew = null
          }
          continue
        }
        if (claim.job_id) {
          // 领取成功但缺少令牌：Backend 已把任务标为失败，记录后继续轮询。
          logRuntimeServer('warn', 'runtime.build.worker.claim_unusable', '领取结果缺少令牌，跳过本次任务。', {
            module: 'runtime.build.worker',
            workerId,
            jobId: claim.job_id,
            message: claim.message,
          })
        }
      } catch (error) {
        logRuntimeServer('warn', 'runtime.build.worker.poll_failed', 'Runtime Build Worker 领取循环单次失败。', {
          module: 'runtime.build.worker',
          workerId,
          error: error instanceof Error ? error.message : String(error),
        })
      }
      await sleep(pollIntervalMs)
    }
  }

  void loop()
  return () => {
    stopped = true
    activeRenew?.stop()
    activeRenew = null
    logRuntimeServer('info', 'runtime.build.worker.stopped', 'Runtime Build Worker 领取循环已停止。', {
      module: 'runtime.build.worker',
      workerId,
    })
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

/**
 * 周期续租；401/409 视为租约失守，立即 abort 在跑构建，避免继续烧 CPU。
 */
function startLeaseRenewal(params: {
  apiBaseUrl: string
  buildToken: string
  jobId: number
  workerId: string
  requestTimeoutMs?: number
}): LeaseRenewalHandle {
  const abortController = new AbortController()
  const timer = setInterval(() => {
    void fetchWithTimeout(
      `${params.apiBaseUrl}/internal/runtime/build-jobs/${params.jobId}/renew`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${params.buildToken}`,
          Accept: 'application/json',
        },
      },
      params.requestTimeoutMs,
    ).then(async (response) => {
      if (response.ok) {
        return
      }
      const text = await response.text().catch(() => '')
      logRuntimeServer('warn', 'runtime.build.worker.renew_rejected', '构建租约续期被拒绝，中止在跑构建。', {
        module: 'runtime.build.worker',
        jobId: params.jobId,
        workerId: params.workerId,
        status: response.status,
        body: text.slice(0, 200),
      })
      if (response.status === 401 || response.status === 409) {
        abortController.abort(new Error(`构建租约失守：HTTP ${response.status}`))
      }
    }).catch((error: unknown) => {
      logRuntimeServer('warn', 'runtime.build.worker.renew_failed', '构建租约续期失败。', {
        module: 'runtime.build.worker',
        jobId: params.jobId,
        workerId: params.workerId,
        error: error instanceof Error ? error.message : String(error),
      })
    })
  }, DEFAULT_RENEW_INTERVAL_MS)
  timer.unref?.()
  return {
    stop: () => clearInterval(timer),
    abortController,
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
  const logContext = {
    module: 'runtime.build.worker',
    jobId,
    workerId,
    artifactId,
    baseUrl,
  }

  logRuntimeServer('info', 'runtime.build.worker.job_acquired', 'Runtime Build Worker 已领取构建任务。', logContext)
  const startedAt = Date.now()
  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')

  let summary: Awaited<ReturnType<RunProjectBuildFn>>
  try {
    const backendClient = options.createBuildBackendClient({
      backendApiBaseUrl: options.backendApiBaseUrl,
      serviceToken,
    })
    summary = await options.scheduler.schedule('project', async () => {
      return runWithRuntimeTaskDeadline(
        'project',
        Number(process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS) || 600_000,
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

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    const timer = setTimeout(resolve, ms)
    timer.unref?.()
  })
}
