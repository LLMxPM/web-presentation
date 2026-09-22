/**
 * 文件用途：验证 Runtime 健康检查插件的中间件注册与响应内容。
 */

import { describe, expect, it, vi } from 'vitest'
import type { ServerResponse } from 'http'
import type { ViteDevServer } from 'vite'

import runtimeHealth, { sendRuntimeHealthResponse } from './runtime-health'

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
    expect(JSON.parse(response.body)).toEqual({ status: 'ok' })
    expect(next).not.toHaveBeenCalled()

    const passthroughResponse = createMockResponse()
    handlers[0]({ url: '/__preview' }, passthroughResponse, next)

    expect(next).toHaveBeenCalledTimes(1)
    expect(passthroughResponse.body).toBe('')
  })

  it('应输出 no-store JSON 响应', () => {
    const response = createMockResponse()

    sendRuntimeHealthResponse(response)

    expect(response.statusCode).toBe(200)
    expect(response.headers['cache-control']).toBe('no-store')
    expect(response.body).toBe('{"status":"ok"}')
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
