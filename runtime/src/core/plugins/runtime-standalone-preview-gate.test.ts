/**
 * 文件用途：验证 Runtime 独立页面入口访问控制插件的配置解析与请求判定。
 */

import type { ServerResponse } from 'http'
import { describe, expect, it, vi } from 'vitest'
import type { ViteDevServer } from 'vite'

import runtimeStandalonePreviewGate, {
  resolveStandalonePreviewEnabled,
  sendStandalonePreviewDisabledResponse,
  shouldBlockStandalonePreviewRequest,
} from './runtime-standalone-preview-gate'

type MockServerResponse = Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'> & {
  headers: Record<string, string | number | readonly string[]>
  body: string
}

describe('runtime standalone preview gate', () => {
  it('默认启用独立页面入口，仅显式关闭值会禁用', () => {
    expect(resolveStandalonePreviewEnabled(undefined)).toBe(true)
    expect(resolveStandalonePreviewEnabled('')).toBe(true)
    expect(resolveStandalonePreviewEnabled('true')).toBe(true)
    expect(resolveStandalonePreviewEnabled('1')).toBe(true)

    for (const value of ['false', '0', 'off', 'no', 'disabled', ' FALSE ']) {
      expect(resolveStandalonePreviewEnabled(value)).toBe(false)
    }
  })

  it('启用时不注册拦截中间件', () => {
    const plugin = runtimeStandalonePreviewGate({ enabled: true })
    const use = vi.fn()
    const server = {
      middlewares: { use },
    } as unknown as ViteDevServer

    const configureServer = plugin.configureServer
    if (typeof configureServer === 'function') {
      configureServer.call({} as never, server)
    } else {
      configureServer?.handler.call({} as never, server)
    }

    expect(use).not.toHaveBeenCalled()
  })

  it('关闭时拦截 Runtime 独立页面入口请求', () => {
    expect(shouldBlockStandalonePreviewRequest({
      method: 'GET',
      url: '/',
      headers: { accept: 'text/html' },
    })).toBe(true)

    expect(shouldBlockStandalonePreviewRequest({
      method: 'GET',
      url: '/feature-showcase',
      headers: { 'sec-fetch-mode': 'navigate' },
    })).toBe(true)

    expect(shouldBlockStandalonePreviewRequest({
      method: 'HEAD',
      url: '/index.html',
      headers: { accept: 'text/html' },
    })).toBe(true)

    expect(shouldBlockStandalonePreviewRequest({
      method: 'GET',
      url: '/',
      headers: { upgrade: 'websocket', 'sec-websocket-key': 'hmr' },
    })).toBe(false)
  })

  it('关闭时放行平台预览、构建、诊断与 Vite 资源路径', () => {
    const allowedUrls = [
      '/__preview',
      '/__preview-tailwind.css',
      '/__runtime-snapdom-resource-proxy?artifactId=artifact-1&token=token&url=https%3A%2F%2Fexample.com%2Fasset.png',
      '/__runtime_internal/v1/builds/project',
      '/__runtime_internal/v1/diagnostics/artifact',
      '/@vite/client',
      '/@runtime-preview/artifact-1/src/views/Cover.vue?ctx=token',
      '/src/main.ts',
      '/node_modules/vue/dist/vue.runtime.esm-bundler.js',
      '/config/routes.config.yaml',
      '/img/logo/runtime_icon.svg',
      '/fonts/Monaco.woff2',
    ]

    for (const url of allowedUrls) {
      expect(shouldBlockStandalonePreviewRequest({
        method: 'GET',
        url,
        headers: { accept: 'text/html,*/*' },
      })).toBe(false)
    }
  })

  it('关闭时应放行带 Runtime 挂载前缀的平台资源路径', () => {
    const allowedUrls = [
      '/runtime/__preview',
      '/runtime/__preview-tailwind.css',
      '/runtime/__runtime-snapdom-resource-proxy?artifactId=artifact-1&token=token&url=https%3A%2F%2Fexample.com%2Fasset.png',
      '/runtime/__runtime_internal/v1/builds/project',
      '/runtime/@vite/client',
      '/runtime/@runtime-preview/artifact-1/src/views/Cover.vue?ctx=token',
      '/runtime/src/main.ts',
      '/runtime/node_modules/.vite/deps/vue.js',
    ]

    for (const url of allowedUrls) {
      expect(shouldBlockStandalonePreviewRequest({
        method: 'GET',
        url,
        headers: { accept: 'text/html,*/*' },
      }, '/runtime')).toBe(false)
    }

    expect(shouldBlockStandalonePreviewRequest({
      method: 'GET',
      url: '/runtime/',
      headers: { accept: 'text/html' },
    }, '/runtime')).toBe(true)
  })

  it('禁用响应返回明确的 403 错误码', () => {
    const response = createMockResponse()

    sendStandalonePreviewDisabledResponse({
      method: 'GET',
      url: '/',
      headers: { accept: 'text/html' },
    }, response)

    expect(response.statusCode).toBe(403)
    expect(response.headers['x-runtime-error-code']).toBe('STANDALONE_PREVIEW_DISABLED')
    expect(response.body).toContain('STANDALONE_PREVIEW_DISABLED')
  })

  it('JSON 请求返回结构化禁用响应', () => {
    const response = createMockResponse()

    sendStandalonePreviewDisabledResponse({
      method: 'GET',
      url: '/',
      headers: { accept: 'application/json' },
    }, response)

    expect(response.statusCode).toBe(403)
    expect(response.headers['content-type']).toBe('application/json; charset=utf-8')
    expect(JSON.parse(response.body)).toMatchObject({
      success: false,
      code: 'STANDALONE_PREVIEW_DISABLED',
    })
  })
})

/**
 * 创建用于断言响应内容的最小 ServerResponse 替身。
 * @returns 可记录状态、响应头和响应体的对象
 */
function createMockResponse(): MockServerResponse {
  return {
    statusCode: 200,
    headers: {},
    body: '',
    setHeader(name: string, value: string | number | readonly string[]) {
      this.headers[name.toLowerCase()] = value
      return this
    },
    end(
      chunkOrCallback?: string | Uint8Array | (() => void),
      encodingOrCallback?: BufferEncoding | (() => void),
      callback?: () => void,
    ) {
      if (typeof chunkOrCallback === 'function') {
        chunkOrCallback()
        this.body = ''
        return this
      }

      if (typeof encodingOrCallback === 'function') {
        encodingOrCallback()
      } else {
        callback?.()
      }

      this.body = chunkOrCallback ? String(chunkOrCallback) : ''
      return this
    },
  }
}
