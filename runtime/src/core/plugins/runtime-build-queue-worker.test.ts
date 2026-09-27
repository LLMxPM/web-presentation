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
    lease_expires_at: new Date().toISOString(),
    build_token: 'build-token',
    service_token: 'service-token',
    message: '构建任务领取成功。',
    ...overrides,
  }
}

const scheduler = {
  schedule: async <T>(_kind: 'project', run: () => Promise<T>) => run(),
}

const createBuildBackendClient: CreateBuildBackendClientFn = () => ({
  fetchManifest: async () => ({ modules: {}, assets: {} }) as never,
  fetchConfigBundle: async () => ({}) as never,
})

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
})
