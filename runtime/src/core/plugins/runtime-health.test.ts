/**
 * 文件用途：验证 Runtime 健康检查插件的中间件注册、容量快照响应与就绪探针语义。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ServerResponse } from 'http'
import type { ViteDevServer } from 'vite'

import runtimeHealth, {
  RUNTIME_READINESS_PATH,
  buildRuntimeHealthPayload,
  buildRuntimeReadinessPayload,
  buildRuntimeVersionFingerprint,
  collectRuntimeReadiness,
  registerRuntimeReadinessProbe,
  sendRuntimeHealthResponse,
  sendRuntimeReadinessResponse,
} from './runtime-health'
import {
  recordRuntimeWorkload,
  registerRuntimeCapacityProvider,
  resetRuntimeWorkloadCounters,
} from './runtime-capacity'

type MockResponse = ReturnType<typeof createMockResponse>
type RuntimeHealthMiddleware = (
  req: { url?: string },
  res: MockResponse,
  next: () => void,
) => void

/** 每个用例都会注册就绪探针，必须逐个注销，避免污染其它用例的就绪汇总。 */
const unregisterReadinessProbes: Array<() => void> = []

afterEach(() => {
  while (unregisterReadinessProbes.length > 0) {
    unregisterReadinessProbes.pop()?.()
  }
})

describe('runtime health plugin', () => {
  it('应只处理健康检查路径，其它请求继续交给后续中间件', () => {
    const plugin = runtimeHealth()
    const handlers: RuntimeHealthMiddleware[] = []
    const configureServer = plugin.configureServer as unknown

    if (typeof configureServer !== 'function') {
      throw new Error('runtime health 插件必须注册 configureServer。')
    }

    const runConfigureServer = configureServer as (server: ViteDevServer) => void
    runConfigureServer({
      middlewares: {
        use(handler: RuntimeHealthMiddleware) {
          handlers.push(handler)
        },
      },
    } as unknown as ViteDevServer)

    const response = createMockResponse()
    const next = vi.fn()
    handlers[0]({ url: '/__runtime_healthz?probe=1' }, response, next)

    expect(response.statusCode).toBe(200)
    expect(response.headers['content-type']).toBe('application/json; charset=utf-8')
    const payload = JSON.parse(response.body)
    expect(payload.status).toBe('ok')
    expect(payload.role).toBe('all')
    expect(payload.memory).toMatchObject({
      rssBytes: expect.any(Number),
      heapUsedBytes: expect.any(Number),
    })
    expect(payload.eventLoop).toMatchObject({ enabled: expect.any(Boolean) })
    expect(payload.workloads).toMatchObject({
      preview: expect.objectContaining({ calls: expect.any(Number) }),
      check: expect.objectContaining({ calls: expect.any(Number) }),
      build: expect.objectContaining({ calls: expect.any(Number) }),
    })
    expect(next).not.toHaveBeenCalled()

    const passthroughResponse = createMockResponse()
    handlers[0]({ url: '/__preview' }, passthroughResponse, next)

    expect(next).toHaveBeenCalledTimes(1)
    expect(passthroughResponse.body).toBe('')
  })

  it('应输出 no-store JSON 响应并包含容量字段', () => {
    const response = createMockResponse()

    sendRuntimeHealthResponse(response)

    expect(response.statusCode).toBe(200)
    expect(response.headers['cache-control']).toBe('no-store')
    const payload = JSON.parse(response.body)
    expect(payload.status).toBe('ok')
    expect(payload.uptimeMs).toEqual(expect.any(Number))
    expect(payload.runtime_kit_version).toEqual(expect.any(String))
    expect(payload.runtime_kit_version.length).toBeGreaterThan(0)
    expect(payload.build_id).toEqual(expect.any(String))
  })

  it('版本指纹应包含 runtime_kit_version 与 RUNTIME_BUILD_ID', () => {
    const originalBuildId = process.env.RUNTIME_BUILD_ID
    try {
      delete process.env.RUNTIME_BUILD_ID
      expect(buildRuntimeVersionFingerprint()).toEqual({
        runtime_kit_version: expect.stringMatching(/^\d+\.\d+\.\d+/),
        build_id: '',
      })

      process.env.RUNTIME_BUILD_ID = 'preview-b1'
      expect(buildRuntimeVersionFingerprint()).toEqual({
        runtime_kit_version: expect.stringMatching(/^\d+\.\d+\.\d+/),
        build_id: 'preview-b1',
      })

      const payload = buildRuntimeHealthPayload()
      expect(payload).toMatchObject({
        runtime_kit_version: expect.stringMatching(/^\d+\.\d+\.\d+/),
        build_id: 'preview-b1',
      })
    } finally {
      if (originalBuildId === undefined) {
        delete process.env.RUNTIME_BUILD_ID
      } else {
        process.env.RUNTIME_BUILD_ID = originalBuildId
      }
    }
  })

  it('应汇总负载计数与注册的容量提供者', () => {
    resetRuntimeWorkloadCounters()
    recordRuntimeWorkload('build', 120)
    recordRuntimeWorkload('check', 30)
    recordRuntimeWorkload('preview', 12)
    recordRuntimeWorkload('light_tool', 5)

    const unregister = registerRuntimeCapacityProvider('viteTaskScheduler', () => ({
      active: 1,
      queuedDiagnostics: 0,
      queuedProject: 2,
    }))

    const payload = buildRuntimeHealthPayload()
    expect(payload.workloads).toMatchObject({
      build: { calls: 1, totalDurationMs: 120, lastDurationMs: 120 },
      check: { calls: 1, totalDurationMs: 30 },
      preview: { calls: 1, totalDurationMs: 12 },
      light_tool: { calls: 1, totalDurationMs: 5 },
    })
    expect(payload.viteTaskScheduler).toEqual({
      active: 1,
      queuedDiagnostics: 0,
      queuedProject: 2,
    })

    unregister()
    resetRuntimeWorkloadCounters()
    expect(buildRuntimeHealthPayload().viteTaskScheduler).toBeUndefined()
  })
})

describe('runtime readiness probe', () => {
  it('没有角色探针时应就绪，并由中间件按路径分流', () => {
    const plugin = runtimeHealth()
    const handlers: RuntimeHealthMiddleware[] = []
    const runConfigureServer = plugin.configureServer as unknown as (server: ViteDevServer) => void
    runConfigureServer({
      middlewares: {
        use(handler: RuntimeHealthMiddleware) {
          handlers.push(handler)
        },
      },
    } as unknown as ViteDevServer)

    const readinessResponse = createMockResponse()
    const next = vi.fn()
    handlers[0]({ url: `${RUNTIME_READINESS_PATH}?probe=1` }, readinessResponse, next)

    expect(next).not.toHaveBeenCalled()
    expect(readinessResponse.statusCode).toBe(200)
    expect(readinessResponse.headers['cache-control']).toBe('no-store')
    expect(JSON.parse(readinessResponse.body)).toMatchObject({
      status: 'ok',
      role: 'all',
      checks: {},
    })
  })

  it('任一角色探针未就绪时应返回 503，但存活探针仍返回 200', () => {
    unregisterReadinessProbes.push(registerRuntimeReadinessProbe('buildWorker', () => ({
      ready: false,
      detail: '构建 Worker 未启动：缺少可用凭证或 Backend API 地址。',
    })))

    const readinessResponse = createMockResponse()
    sendRuntimeReadinessResponse(readinessResponse)
    expect(readinessResponse.statusCode).toBe(503)
    const readinessPayload = JSON.parse(readinessResponse.body)
    expect(readinessPayload.status).toBe('unavailable')
    expect(readinessPayload.checks.buildWorker).toEqual({
      ready: false,
      detail: '构建 Worker 未启动：缺少可用凭证或 Backend API 地址。',
    })

    // 进程仍然存活：存活探针不得因为角色能力缺失而失败，否则会被编排层反复重启。
    const healthResponse = createMockResponse()
    sendRuntimeHealthResponse(healthResponse)
    expect(healthResponse.statusCode).toBe(200)
    expect(JSON.parse(healthResponse.body).status).toBe('ok')
  })

  it('布尔探针与抛错探针都应被归一化，抛错按未就绪处理', () => {
    unregisterReadinessProbes.push(registerRuntimeReadinessProbe('booleanProbe', () => true))
    unregisterReadinessProbes.push(
      registerRuntimeReadinessProbe('throwingProbe', () => {
        throw new Error('探针自身故障')
      }),
    )

    const readiness = collectRuntimeReadiness()
    expect(readiness.ready).toBe(false)
    expect(readiness.checks.booleanProbe).toEqual({ ready: true })
    expect(readiness.checks.throwingProbe).toEqual({ ready: false, detail: '探针自身故障' })
    expect(buildRuntimeReadinessPayload(readiness).status).toBe('unavailable')
  })

  it('注销探针后不得继续影响就绪汇总', () => {
    const unregister = registerRuntimeReadinessProbe('transient', () => false)
    expect(collectRuntimeReadiness().ready).toBe(false)

    unregister()
    const readiness = collectRuntimeReadiness()
    expect(readiness.ready).toBe(true)
    expect(readiness.checks.transient).toBeUndefined()
  })

  it('同名探针重复注册时只保留最后一个实现，注销后不残留', () => {
    unregisterReadinessProbes.push(registerRuntimeReadinessProbe('buildWorker', () => false))
    const unregisterSecond = registerRuntimeReadinessProbe('buildWorker', () => true)

    expect(collectRuntimeReadiness().checks.buildWorker).toEqual({ ready: true })

    unregisterSecond()
    const readiness = collectRuntimeReadiness()
    expect(readiness.ready).toBe(true)
    expect(readiness.checks.buildWorker).toBeUndefined()
  })
})

/**
 * 创建用于断言健康检查响应的最小 ServerResponse 替身。
 * @returns 可记录状态、响应头和响应体的对象
 */
function createMockResponse() {
  return {
    statusCode: 0,
    headers: {} as Record<string, string | number | readonly string[]>,
    body: '',
    setHeader(name: string, value: string | number | readonly string[]): ServerResponse {
      this.headers[name.toLowerCase()] = value
      return this as unknown as ServerResponse
    },
    end(chunk?: unknown): ServerResponse {
      this.body = typeof chunk === 'string' ? chunk : ''
      return this as unknown as ServerResponse
    },
  }
}
