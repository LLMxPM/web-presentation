/**
 * 文件用途：验证 Runtime 健康检查插件的中间件注册与容量快照响应内容。
 */

import { describe, expect, it, vi } from 'vitest'
import type { ServerResponse } from 'http'
import type { ViteDevServer } from 'vite'

import runtimeHealth, {
  buildRuntimeHealthPayload,
  buildRuntimeVersionFingerprint,
  sendRuntimeHealthResponse,
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
