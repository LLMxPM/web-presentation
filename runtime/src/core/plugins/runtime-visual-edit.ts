/**
 * 文件用途：为 Backend 提供受鉴权的页面可视化编辑 SFC 分析与原子改写内部端点。
 */

import type { IncomingMessage, ServerResponse } from 'node:http'

import type { Plugin } from 'vite'

import {
  analyzeVisualEditRequest,
  PAGE_VISUAL_EDIT_MAX_REQUEST_BYTES,
  VisualEditAnalyzeError,
} from '../visual-edit/server/analyze-request'
import { VisualEditInstrumentationError } from '../visual-edit/instrumentation/instrument-sfc'
import { applyVisualEditRequest } from '../visual-edit/server/apply-request'
import { VisualEditApplyError } from '../visual-edit/apply/errors'
import { logRuntimeServer } from '../utils/runtime-logger'
import {
  RuntimeServiceAuthError,
  verifyRuntimeServiceToken,
} from './runtime-service-auth'

export const RUNTIME_VISUAL_EDIT_ANALYZE_PATH = '/__runtime_internal/v1/visual-edit/analyze'
export const RUNTIME_VISUAL_EDIT_APPLY_PATH = '/__runtime_internal/v1/visual-edit/apply'

const DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER = 'x-runtime-service-token'
const DEFAULT_SERVICE_AUDIENCE = 'runtime-backend'

export interface RuntimeVisualEditOptions {
  analyzeEndpointPath?: string
  applyEndpointPath?: string
  serviceTokenHeaderName?: string
  jwksUrl?: string
  serviceAudience?: string
}

type RuntimeNodeResponse = Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>

/**
 * 注册可视化编辑内部 analyze/apply 端点；apply 只返回候选源码，不直接持久化。
 * @param options 内部路径与服务令牌校验配置
 * @returns Vite serve 插件
 */
export default function runtimeVisualEdit(options: RuntimeVisualEditOptions = {}): Plugin {
  const endpointPath = options.analyzeEndpointPath || RUNTIME_VISUAL_EDIT_ANALYZE_PATH
  const applyEndpointPath = options.applyEndpointPath || RUNTIME_VISUAL_EDIT_APPLY_PATH
  const serviceTokenHeaderName = (options.serviceTokenHeaderName || DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER).toLowerCase()

  return {
    name: 'runtime-visual-edit',
    apply: 'serve',

    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const requestPath = (req.url || '').split('?')[0]
        if (requestPath !== endpointPath && requestPath !== applyEndpointPath) {
          return next()
        }
        if (req.method !== 'POST') {
          return sendJson(res, 405, {
            success: false,
            code: 'METHOD_NOT_ALLOWED',
            message: '页面可视化编辑内部入口仅支持 POST。',
          })
        }

        try {
          await verifyRuntimeServiceToken(String(req.headers[serviceTokenHeaderName] || ''), {
            jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
            audience: options.serviceAudience || process.env.RUNTIME_SERVICE_TOKEN_AUDIENCE || DEFAULT_SERVICE_AUDIENCE,
            requiredScope: 'runtime-artifact-read',
          })
          const payload = await readJsonBody(req, PAGE_VISUAL_EDIT_MAX_REQUEST_BYTES)
          const result = requestPath === endpointPath
            ? analyzeVisualEditRequest(payload)
            : applyVisualEditRequest(payload)
          sendJson(res, 200, result)
        } catch (error) {
          const action = requestPath === applyEndpointPath ? 'apply' : 'analyze'
          logRuntimeServer('error', `runtime.visual_edit.${action}.failed`, `Runtime 页面可视化编辑 ${action} 失败。`, {
            module: 'runtime.visual_edit',
            request_id: String(req.headers['x-request-id'] || ''),
            requestUrl: req.url,
            error,
          })
          sendVisualEditError(res, error, action)
        }
      })
    },
  }
}

/**
 * 读取带字节上限的 JSON 请求体，避免超大内部请求耗尽 Runtime 内存。
 */
async function readJsonBody(req: IncomingMessage, maxBytes: number): Promise<unknown> {
  const declaredLength = Number(req.headers['content-length'] || 0)
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new VisualEditAnalyzeError(413, 'PAGE_VISUAL_EDIT_REQUEST_TOO_LARGE', '分析请求体超过大小上限。')
  }

  const chunks: Buffer[] = []
  let receivedBytes = 0
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    receivedBytes += buffer.byteLength
    if (receivedBytes > maxBytes) {
      throw new VisualEditAnalyzeError(413, 'PAGE_VISUAL_EDIT_REQUEST_TOO_LARGE', '分析请求体超过大小上限。')
    }
    chunks.push(buffer)
  }

  try {
    const rawBody = Buffer.concat(chunks).toString('utf-8').trim()
    return rawBody ? JSON.parse(rawBody) : {}
  } catch (error) {
    throw new VisualEditAnalyzeError(400, 'REQUEST_BODY_INVALID', '请求体不是合法 JSON。', error)
  }
}

/**
 * 输出 no-store JSON，避免含页面源码分析结果的内部响应被中间缓存。
 */
function sendJson(res: RuntimeNodeResponse, statusCode: number, payload: unknown): void {
  res.statusCode = statusCode
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(payload))
}

/**
 * 将鉴权、协议校验及未知错误映射为稳定 JSON 响应。
 */
function sendVisualEditError(res: RuntimeNodeResponse, error: unknown, action: 'analyze' | 'apply'): void {
  if (
    error instanceof RuntimeServiceAuthError
    || error instanceof VisualEditAnalyzeError
    || error instanceof VisualEditApplyError
    || error instanceof VisualEditInstrumentationError
  ) {
    sendJson(res, error.statusCode, {
      success: false,
      code: error.code,
      message: error.message,
    })
    return
  }
  sendJson(res, 500, {
    success: false,
    code: action === 'apply' ? 'RUNTIME_VISUAL_EDIT_APPLY_FAILED' : 'RUNTIME_VISUAL_EDIT_ANALYZE_FAILED',
    message: error instanceof Error ? error.message : `Runtime 页面可视化编辑 ${action} 失败。`,
  })
}
