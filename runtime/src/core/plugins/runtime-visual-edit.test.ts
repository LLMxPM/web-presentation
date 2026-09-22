/**
 * 文件用途：验证 Runtime 可视化编辑分析插件的成功响应、协议边界、hash 校验和内部鉴权。
 */

import { createHash } from 'node:crypto'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { PassThrough } from 'node:stream'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ViteDevServer } from 'vite'

import { analyzeVisualEditSfc } from '../visual-edit/source/analyze-sfc'
import runtimeVisualEdit, {
  RUNTIME_VISUAL_EDIT_ANALYZE_PATH,
  RUNTIME_VISUAL_EDIT_APPLY_PATH,
} from './runtime-visual-edit'

const joseMocks = vi.hoisted(() => ({
  createRemoteJWKSet: vi.fn(() => vi.fn()),
  jwtVerify: vi.fn(),
}))

vi.mock('jose', () => joseMocks)
vi.mock('../utils/runtime-logger', () => ({ logRuntimeServer: vi.fn() }))

const SOURCE = `<script setup lang="ts">
const items = [{ id: 'a', title: '标题' }]
</script>
<template><p v-for="item in items" :key="item.id">{{ item.title }}</p></template>`

type MockResponse = ReturnType<typeof createMockResponse>
type VisualEditMiddleware = (
  req: IncomingMessage,
  res: MockResponse,
  next: () => void,
) => Promise<void> | void

describe('runtime visual edit plugin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    joseMocks.jwtVerify.mockResolvedValue({
      payload: {
        sub: 'runtime-service',
        scope: 'runtime-artifact-read',
      },
    })
  })

  it('应鉴权并返回 canonical v1 SFC Manifest', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()

    await middleware(createRequest(buildRequestPayload()), response, vi.fn())

    const payload = JSON.parse(response.body)
    expect(response.statusCode).toBe(200)
    expect(response.headers['cache-control']).toBe('no-store')
    expect(payload).toMatchObject({
      protocolVersion: 1,
      instrumentedSource: expect.any(String),
      manifest: {
        protocolVersion: 1,
        modulePath: 'src/views/PGdemo.vue',
        sourceHash: sourceHash(SOURCE),
      },
    })
    expect(payload.instrumentedSource).toContain('data-page-visual-node-id=')
    expect(payload.instrumentedSource).toContain(':data-page-visual-loop-key="JSON.stringify(item.id)"')
    expect(payload.instrumentedSource).not.toBe(SOURCE)
    expect(payload.manifest.root.children[0].tag).toBe('p')
    expect(joseMocks.jwtVerify).toHaveBeenCalledWith(
      'runtime-service-token',
      expect.any(Function),
      { audience: 'runtime-backend' },
    )
  })

  it('sourceHash 与源码不一致时应拒绝分析', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()

    await middleware(createRequest({ ...buildRequestPayload(), sourceHash: '0'.repeat(64) }), response, vi.fn())

    expect(response.statusCode).toBe(422)
    expect(JSON.parse(response.body)).toMatchObject({
      success: false,
      code: 'PAGE_VISUAL_EDIT_SOURCE_HASH_MISMATCH',
    })
  })

  it('canonical 源码占用 Runtime 保留 marker 时应以稳定业务错误拒绝插桩', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()
    const collisionSource = '<template><div data-page-visual-node-id="forged">内容</div></template>'

    await middleware(createRequest(buildRequestPayload(collisionSource)), response, vi.fn())

    expect(response.statusCode).toBe(422)
    expect(JSON.parse(response.body)).toMatchObject({
      success: false,
      code: 'PAGE_VISUAL_EDIT_RESERVED_ATTRIBUTE_COLLISION',
    })
  })

  it('非 v1 协议应返回明确的不兼容错误', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()

    await middleware(createRequest({ ...buildRequestPayload(), protocolVersion: 2 }), response, vi.fn())

    expect(response.statusCode).toBe(409)
    expect(JSON.parse(response.body)).toMatchObject({
      success: false,
      code: 'PAGE_VISUAL_EDIT_PROTOCOL_MISMATCH',
    })
  })

  it('缺少令牌或令牌声明错误时应拒绝请求', async () => {
    const middleware = registerMiddleware()
    const missingTokenResponse = createMockResponse()

    await middleware(createRequest(buildRequestPayload(), { token: '' }), missingTokenResponse, vi.fn())

    expect(missingTokenResponse.statusCode).toBe(401)
    expect(JSON.parse(missingTokenResponse.body).code).toBe('RUNTIME_SERVICE_TOKEN_REQUIRED')

    joseMocks.jwtVerify.mockResolvedValueOnce({
      payload: { sub: 'runtime-service', scope: 'wrong-scope' },
    })
    const invalidClaimsResponse = createMockResponse()
    await middleware(createRequest(buildRequestPayload()), invalidClaimsResponse, vi.fn())

    expect(invalidClaimsResponse.statusCode).toBe(401)
    expect(JSON.parse(invalidClaimsResponse.body).code).toBe('RUNTIME_SERVICE_TOKEN_INVALID')
  })

  it('非 POST 方法应返回 405，非目标路径应继续传递', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()
    const next = vi.fn()

    await middleware(createRequest(undefined, { method: 'GET' }), response, next)

    expect(response.statusCode).toBe(405)
    expect(JSON.parse(response.body).code).toBe('METHOD_NOT_ALLOWED')
    expect(joseMocks.jwtVerify).not.toHaveBeenCalled()

    const passthroughResponse = createMockResponse()
    await middleware(createRequest(undefined, { path: '/__runtime_healthz' }), passthroughResponse, next)
    expect(next).toHaveBeenCalledTimes(1)
    expect(passthroughResponse.body).toBe('')
  })

  it('apply 端点应按稳定 key 改写源码并返回 Backend camelCase 外壳', async () => {
    const middleware = registerMiddleware()
    const response = createMockResponse()

    await middleware(createRequest(buildApplyRequestPayload(), { path: RUNTIME_VISUAL_EDIT_APPLY_PATH }), response, vi.fn())

    const payload = JSON.parse(response.body)
    expect(response.statusCode).toBe(200)
    expect(payload).toMatchObject({
      protocolVersion: 1,
      baseSourceHash: sourceHash(SOURCE),
      operationsApplied: 1,
      diagnostics: [],
    })
    expect(payload.nextSource).toContain("title: '新标题'")
    expect(payload.nextSourceHash).toBe(sourceHash(payload.nextSource))
    expect(payload.canonicalDiff).toContain('+++ proposed')
  })

  it('apply 端点应拒绝 hash、协议、鉴权和方法错误', async () => {
    const middleware = registerMiddleware()
    const hashResponse = createMockResponse()
    await middleware(createRequest(
      { ...buildApplyRequestPayload(), sourceHash: '0'.repeat(64) },
      { path: RUNTIME_VISUAL_EDIT_APPLY_PATH },
    ), hashResponse, vi.fn())
    expect(JSON.parse(hashResponse.body).code).toBe('PAGE_VISUAL_EDIT_SOURCE_HASH_MISMATCH')

    const protocolResponse = createMockResponse()
    await middleware(createRequest(
      { ...buildApplyRequestPayload(), protocolVersion: 2 },
      { path: RUNTIME_VISUAL_EDIT_APPLY_PATH },
    ), protocolResponse, vi.fn())
    expect(JSON.parse(protocolResponse.body).code).toBe('PAGE_VISUAL_EDIT_PROTOCOL_MISMATCH')

    const authResponse = createMockResponse()
    await middleware(createRequest(buildApplyRequestPayload(), {
      path: RUNTIME_VISUAL_EDIT_APPLY_PATH,
      token: '',
    }), authResponse, vi.fn())
    expect(authResponse.statusCode).toBe(401)
    expect(JSON.parse(authResponse.body).code).toBe('RUNTIME_SERVICE_TOKEN_REQUIRED')

    const methodResponse = createMockResponse()
    await middleware(createRequest(undefined, {
      path: RUNTIME_VISUAL_EDIT_APPLY_PATH,
      method: 'GET',
    }), methodResponse, vi.fn())
    expect(methodResponse.statusCode).toBe(405)
    expect(JSON.parse(methodResponse.body).code).toBe('METHOD_NOT_ALLOWED')
  })
})

/**
 * 注册插件并取回唯一 Connect 中间件。
 */
function registerMiddleware(): VisualEditMiddleware {
  const handlers: VisualEditMiddleware[] = []
  const plugin = runtimeVisualEdit({
    jwksUrl: 'https://backend.example.com/.well-known/jwks.json',
    serviceAudience: 'runtime-backend',
  })
  const server = {
    middlewares: {
      use(handler: VisualEditMiddleware) {
        handlers.push(handler)
      },
    },
  } as unknown as ViteDevServer
  const configureServer = plugin.configureServer
  if (typeof configureServer === 'function') {
    configureServer.call({} as never, server)
  } else {
    configureServer?.handler.call({} as never, server)
  }
  if (!handlers[0]) {
    throw new Error('runtime visual edit 插件必须注册中间件。')
  }
  return handlers[0]
}

/**
 * 构造可读流形式的最小 IncomingMessage 替身。
 */
function createRequest(
  payload?: unknown,
  options: { method?: string; path?: string; token?: string } = {},
): IncomingMessage {
  const stream = new PassThrough()
  const body = payload === undefined ? '' : JSON.stringify(payload)
  Object.assign(stream, {
    method: options.method || 'POST',
    url: options.path || RUNTIME_VISUAL_EDIT_ANALYZE_PATH,
    headers: {
      'content-type': 'application/json',
      'content-length': String(Buffer.byteLength(body)),
      'x-runtime-service-token': options.token === undefined ? 'runtime-service-token' : options.token,
    },
  })
  stream.end(body)
  return stream as unknown as IncomingMessage
}

/**
 * 构造合法 analyze 请求。
 */
function buildRequestPayload(source = SOURCE): Record<string, unknown> {
  return {
    protocolVersion: 1,
    modulePath: 'src/views/PGdemo.vue',
    sourceHash: sourceHash(source),
    source,
  }
}

/**
 * 根据真实 analyze 结果构造合法 apply 请求，避免测试复制 node/binding ID 算法。
 */
function buildApplyRequestPayload(): Record<string, unknown> {
  const request = buildRequestPayload()
  const manifest = analyzeVisualEditSfc(SOURCE, { modulePath: request.modulePath as string })
  const node = manifest.root.children[0]
  const binding = node?.bindings.find(candidate => candidate.expression === 'item.title')
  if (!node || !binding) {
    throw new Error('apply 插件测试缺少目标 binding。')
  }
  return {
    ...request,
    operations: [{
      type: 'set_value',
      nodeId: node.nodeId,
      bindingId: binding.bindingId,
      instancePath: [{ loopNodeId: node.nodeId, key: 'a', index: 0 }],
      value: '新标题',
    }],
  }
}

/**
 * 按 Runtime/Backend 共同约定计算 UTF-8 SHA-256。
 */
function sourceHash(source: string): string {
  return createHash('sha256').update(source).digest('hex')
}

/**
 * 创建可记录状态、响应头和响应体的 ServerResponse 替身。
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
