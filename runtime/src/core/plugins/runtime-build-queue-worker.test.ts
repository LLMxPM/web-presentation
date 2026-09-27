/**
 * 文件用途：验证 Runtime Build Worker 领取循环、租约中止与 complete 终态语义。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  startRuntimeBuildQueueWorker,
  type CreateBuildBackendClientFn,
  type RunProjectBuildFn,
} from './runtime-build-queue-worker'
import { RuntimeTaskAbortedError } from './runtime-task-deadline'

function emptyClaim() {
  return {
    job_id: null,
    project_id: null,
    snapshot_release_id: null,
    base_url: null,
    workspace_id: null,
    attempt_id: null,
    lease_owner: null,
    lease_expires_at: null,
    deadline_at: null,
    build_token: null,
    service_token: null,
    message: '当前没有可领取的构建任务。',
  }
}

type FetchCall = [url: string, init?: RequestInit]

function completeBodyOf(call: FetchCall): unknown {
  return JSON.parse(String(call[1]?.body))
}

function filledClaim(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    job_id: 1,
    project_id: 1,
    snapshot_release_id: '10',
    base_url: './',
    workspace_id: 1,
    attempt_id: 'attempt-1',
    lease_owner: 'runtime-build-test',
    // 默认给一份仍在有效期内的租约：本地看门狗按到期时间判定，过期夹具会让所有
    // 用例都在第一秒被判定失守，掩盖真正要测的分支。
    lease_expires_at: isoFromNow(960_000),
    deadline_at: null,
    build_token: 'build-token',
    service_token: 'service-token',
    message: '构建任务领取成功。',
    ...overrides,
  }
}

const scheduler = {
  schedule: async <T>(_kind: 'project', run: () => Promise<T>) => run(),
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 相对当前时刻偏移若干毫秒的 ISO 字符串，用于构造 Backend 返回的租约/期限。 */
function isoFromNow(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString()
}

const createBuildBackendClient: CreateBuildBackendClientFn = () => ({
  fetchManifest: async () => ({ modules: {}, assets: {} }) as never,
  fetchConfigBundle: async () => ({}) as never,
})

/** 构造直接返回成功产物的构建替身：用于只关心 complete 语义的用例。 */
function succeededBuildFn(): RunProjectBuildFn {
  return vi.fn(async () => ({
    artifactEntryFile: 'index.html',
    artifactSha256: 'abc',
    artifactSizeBytes: 12,
    message: 'ok',
  })) as unknown as RunProjectBuildFn
}

describe('runtime-build-queue-worker', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('无任务时应空转且不执行构建', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(emptyClaim()), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn()
    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()
    expect(runProjectBuild).not.toHaveBeenCalled()
  })

  it('领取成功后应执行构建并上报 success complete', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return new Response(JSON.stringify(emptyClaim()), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        claimed = true
        return new Response(JSON.stringify(filledClaim()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (String(url).includes('/complete')) {
        return new Response(JSON.stringify({ message: 'ok' }), { status: 200 })
      }
      if (String(url).includes('/renew')) {
        return new Response(JSON.stringify({ message: 'ok' }), { status: 200 })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn(async () => ({
      artifactEntryFile: 'index.html',
      artifactSha256: 'abc',
      artifactSizeBytes: 12,
      message: 'ok',
    }))
    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()

    expect(runProjectBuild).toHaveBeenCalledTimes(1)
    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls.length).toBe(1)
    expect(completeBodyOf(completeCalls[0])).toEqual({ success: true })
  })

  it('构建失败应上报 failed complete，不得写成功', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return new Response(JSON.stringify(emptyClaim()), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        claimed = true
        return new Response(JSON.stringify(filledClaim()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (String(url).includes('/complete')) {
        return new Response(JSON.stringify({ message: 'ok' }), { status: 200 })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn(async () => {
      throw new Error('vite build failed')
    })
    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()

    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls.length).toBe(1)
    const body = completeBodyOf(completeCalls[0]) as { success: boolean; error_message: string }
    expect(body.success).toBe(false)
    expect(body.error_message).toContain('vite build failed')
  })

  it('上传成功后 complete 失败不得再写 failed', async () => {
    let claimed = false
    let completeCount = 0
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return new Response(JSON.stringify(emptyClaim()), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        claimed = true
        return new Response(JSON.stringify(filledClaim()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (String(url).includes('/complete')) {
        completeCount += 1
        return new Response(JSON.stringify({ message: 'rejected' }), { status: 409 })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn(async () => ({
      artifactEntryFile: 'index.html',
      artifactSha256: 'abc',
      artifactSizeBytes: 12,
      message: 'ok',
    }))
    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()

    // 只有一次 success complete 尝试；失败后交由租约恢复，不得追加 failed。
    expect(completeCount).toBe(1)
  })

  it('complete 响应丢失时应重试，而不是退化成等待租约过期', async () => {
    let claimed = false
    let completeCount = 0
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return jsonResponse(emptyClaim())
        }
        claimed = true
        return jsonResponse(filledClaim())
      }
      if (String(url).includes('/complete')) {
        completeCount += 1
        if (completeCount === 1) {
          // Backend 可能已提交终态但响应丢失：只能靠幂等 complete 的重试收敛。
          throw new TypeError('connection reset')
        }
        return jsonResponse({ message: 'ok' })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: succeededBuildFn(),
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(1_500)
    stop()

    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls).toHaveLength(2)
    // 两次都必须是 success：产物已提升，任何一次改写 failed 都会清掉最终产物。
    expect(completeCalls.map(call => (completeBodyOf(call) as { success: boolean }).success)).toEqual([true, true])
  })

  it('complete 传输持续失败时应重试到上限后放弃，交给租约恢复收敛', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return jsonResponse(emptyClaim())
        }
        claimed = true
        return jsonResponse(filledClaim())
      }
      if (String(url).includes('/complete')) {
        throw new TypeError('connection refused')
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: succeededBuildFn(),
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(3_000)
    stop()

    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls).toHaveLength(3)
  })

  it('renew 收到 409 时应 abort 在跑构建', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return new Response(JSON.stringify(emptyClaim()), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        claimed = true
        return new Response(JSON.stringify(filledClaim()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (String(url).includes('/renew')) {
        return new Response(JSON.stringify({ message: 'lease lost' }), { status: 409 })
      }
      if (String(url).includes('/complete')) {
        return new Response(JSON.stringify({ message: 'ok' }), { status: 200 })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    let observedAbort: unknown = null
    const runProjectBuild = vi.fn(async (params: { deadline: { signal: AbortSignal } }) => {
      // 挂起直到 renew 触发 abort
      await new Promise((_resolve, reject) => {
        if (params.deadline.signal.aborted) {
          reject(params.deadline.signal.reason)
          return
        }
        params.deadline.signal.addEventListener('abort', () => {
          observedAbort = params.deadline.signal.reason
          reject(params.deadline.signal.reason)
        })
      })
    })

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    // 触发一次轮询 + renew 定时器（30s）
    await vi.advanceTimersByTimeAsync(30_050)
    stop()

    expect(runProjectBuild).toHaveBeenCalled()
    expect(observedAbort).toBeInstanceOf(Error)
  })

  it('concurrency=2 时应并行领取并执行两个任务', async () => {
    const claimWorkerIds: string[] = []
    let runningJobs = 0
    let maxRunningJobs = 0
    let claimCount = 0
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/claim')) {
        claimCount += 1
        claimWorkerIds.push(String(JSON.parse(String(init?.body)).worker_id))
        if (claimCount <= 2) {
          return jsonResponse(filledClaim({ job_id: claimCount }))
        }
        return jsonResponse(emptyClaim())
      }
      if (String(url).includes('/complete')) {
        return jsonResponse({ message: 'ok' })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    // 两个构建都进入执行后才放行：只有这样断言到的并发才是真实并发，而不是先后完成。
    let releaseBoth: () => void = () => {}
    const bothStarted = new Promise<void>(resolve => {
      releaseBoth = resolve
    })
    const runProjectBuild = vi.fn(async () => {
      runningJobs += 1
      maxRunningJobs = Math.max(maxRunningJobs, runningJobs)
      if (runningJobs >= 2) {
        releaseBoth()
      }
      await bothStarted
      runningJobs -= 1
      return {
        artifactEntryFile: 'index.html',
        artifactSha256: 'abc',
        artifactSizeBytes: 12,
        message: 'ok',
      }
    })

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      concurrency: 2,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()

    expect(runProjectBuild).toHaveBeenCalledTimes(2)
    expect(maxRunningJobs).toBe(2)
    expect(new Set(claimWorkerIds)).toEqual(new Set(['w1-1', 'w1-2']))
    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete'))
    expect(completeCalls.length).toBe(2)
  })

  it('renew 持续失败时应在本地租约到期时中止构建', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return jsonResponse(emptyClaim())
        }
        claimed = true
        return jsonResponse(filledClaim({ lease_expires_at: isoFromNow(20_000) }))
      }
      if (String(url).includes('/renew')) {
        // Backend 不可达：没有任何响应告诉 Worker 租约已失守，只能靠本地判定。
        throw new Error('network unreachable')
      }
      if (String(url).includes('/complete')) {
        return jsonResponse({ message: 'ok' })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    let observedAbort: unknown = null
    const runProjectBuild = vi.fn(async (params: { deadline: { signal: AbortSignal } }) => {
      await new Promise((_resolve, reject) => {
        const signal = params.deadline.signal
        if (signal.aborted) {
          reject(signal.reason)
          return
        }
        signal.addEventListener('abort', () => {
          observedAbort = signal.reason
          reject(signal.reason)
        })
      })
    })

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      renewIntervalMs: 3_000,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    // 租约 20s、安全提前量 1.5s：到点前不应中止，到点后必须自行停手。
    await vi.advanceTimersByTimeAsync(18_000)
    expect(observedAbort).toBe(null)
    await vi.advanceTimersByTimeAsync(3_000)
    stop()

    expect(observedAbort).toBeInstanceOf(Error)
    expect((observedAbort as Error).name).toBe('RuntimeTaskAbortedError')
    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls.length).toBe(1)
    const body = completeBodyOf(completeCalls[0]) as { success: boolean; error_message: string }
    expect(body.success).toBe(false)
    expect(body.error_message).toContain('本地判定已到期')
  })

  it('执行预算应以任务剩余总期限封顶，而不是跑满 Worker 超时', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return jsonResponse(emptyClaim())
        }
        claimed = true
        return jsonResponse(filledClaim({ deadline_at: isoFromNow(10_000) }))
      }
      if (String(url).includes('/complete')) {
        return jsonResponse({ message: 'ok' })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn(async (params: { deadline: { signal: AbortSignal } }) => {
      await new Promise((_resolve, reject) => {
        params.deadline.signal.addEventListener('abort', () => reject(params.deadline.signal.reason))
      })
    })

    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    // Worker 默认超时 600s：任务只剩 10s 时必须在 10s 处收手。
    await vi.advanceTimersByTimeAsync(11_000)
    stop()

    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls.length).toBe(1)
    const body = completeBodyOf(completeCalls[0]) as { success: boolean; error_message: string }
    expect(body.success).toBe(false)
    expect(body.error_message).toContain('执行时限')
  })

  it('剩余总期限不足时应放弃执行并直接上报失败', async () => {
    let claimed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/claim')) {
        if (claimed) {
          return jsonResponse(emptyClaim())
        }
        claimed = true
        return jsonResponse(filledClaim({ deadline_at: isoFromNow(1_000) }))
      }
      if (String(url).includes('/complete')) {
        return jsonResponse({ message: 'ok' })
      }
      return new Response('', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const runProjectBuild = vi.fn()
    const stop = startRuntimeBuildQueueWorker({
      backendApiBaseUrl: 'http://backend',
      workerCredential: 'cred',
      workerId: 'w1',
      pollIntervalMs: 500,
      runtimeRoot: '/tmp/runtime',
      scheduler,
      runProjectBuild: runProjectBuild as unknown as RunProjectBuildFn,
      createBuildBackendClient,
    })

    await vi.advanceTimersByTimeAsync(50)
    stop()

    expect(runProjectBuild).not.toHaveBeenCalled()
    const completeCalls = fetchMock.mock.calls.filter(call => String(call[0]).includes('/complete')) as FetchCall[]
    expect(completeCalls.length).toBe(1)
    const body = completeBodyOf(completeCalls[0]) as { success: boolean; error_message: string }
    expect(body.success).toBe(false)
    expect(body.error_message).toContain('剩余总期限')
  })
})
