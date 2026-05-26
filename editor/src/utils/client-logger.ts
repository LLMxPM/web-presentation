/**
 * 文件功能：统一 Editor 浏览器端日志、错误捕获和后端错误上报。
 */
import type { App } from 'vue'
import type { Router } from 'vue-router'

import { resolveApiBaseUrl } from '@/api/http'

interface ClientErrorPayload {
  message: string
  error_name?: string | null
  stack?: string | null
  route?: string | null
  url?: string | null
  component?: string | null
  trace_id?: string | null
  artifact_id?: string | null
  context?: Record<string, unknown>
}

const ERROR_DEDUPE_WINDOW_MS = 30_000
const MAX_TEXT_LENGTH = 4096
const recentErrors = new Map<string, number>()
let installed = false

/**
 * 安装全局错误捕获；Vue、window error 和 Promise rejection 均通过同一出口上报。
 * @param app Vue 应用实例
 * @param router 当前路由实例，用于补充 route 字段
 */
export function installEditorClientLogger(app: App, router: Router): void {
  if (installed || typeof window === 'undefined') {
    return
  }
  installed = true

  app.config.errorHandler = (error, _instance, info) => {
    reportClientError(error, {
      component: 'vue',
      context: { info },
      route: router.currentRoute.value.fullPath,
    })
  }

  window.addEventListener('error', (event) => {
    reportClientError(event.error || event.message, {
      component: 'window.error',
      route: router.currentRoute.value.fullPath,
      context: { filename: event.filename, lineno: event.lineno, colno: event.colno },
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    reportClientError(event.reason, {
      component: 'window.unhandledrejection',
      route: router.currentRoute.value.fullPath,
    })
  })
}

/**
 * 记录开发调试信息；生产环境不输出也不上报。
 * @param stage 调试阶段
 * @param payload 调试上下文
 */
export function logClientDebug(stage: string, payload?: unknown): void {
  if (import.meta.env.DEV) {
    console.debug(stage, sanitizeUnknown(payload))
  }
}

/**
 * 记录可恢复告警；仅开发环境输出控制台，不上报后端。
 * @param message 告警说明
 * @param error 可选异常对象
 */
export function logClientWarning(message: string, error?: unknown): void {
  if (import.meta.env.DEV) {
    console.warn(message, sanitizeUnknown(error))
  }
}

/**
 * 记录浏览器端错误；开发环境输出控制台，生产或显式开启时上报 Backend。
 * @param error 错误对象或错误消息
 * @param options 附加上下文
 */
export function reportClientError(error: unknown, options: Partial<ClientErrorPayload> = {}): void {
  const payload = buildClientErrorPayload(error, options)
  if (import.meta.env.DEV) {
    console.error(payload.message, sanitizeUnknown(error))
  }
  if (!shouldReportClientError() || shouldDropDuplicate(payload)) {
    return
  }
  void sendClientError(payload)
}

/**
 * 构造后端上报载荷；测试也复用该函数验证脱敏和限长。
 * @param error 错误对象或错误消息
 * @param options 附加上下文
 * @returns 可上报的错误载荷
 */
export function buildClientErrorPayload(error: unknown, options: Partial<ClientErrorPayload> = {}): ClientErrorPayload {
  const normalized = normalizeError(error)
  return {
    message: sanitizeText(options.message || normalized.message || 'Editor 浏览器端错误。'),
    error_name: sanitizeText(options.error_name || normalized.name || 'Error'),
    stack: sanitizeText(options.stack || normalized.stack || ''),
    route: sanitizeText(options.route || currentRouteText()),
    url: sanitizeText(options.url || currentUrlText()),
    component: sanitizeText(options.component || ''),
    trace_id: sanitizeText(options.trace_id || ''),
    artifact_id: sanitizeText(options.artifact_id || ''),
    context: sanitizeUnknown(options.context || {}) as Record<string, unknown>,
  }
}

function shouldReportClientError(): boolean {
  const configured = String(import.meta.env.VITE_CLIENT_ERROR_REPORTING ?? '').trim().toLowerCase()
  if (configured === 'false') {
    return false
  }
  return !import.meta.env.DEV || configured === 'true'
}

async function sendClientError(payload: ClientErrorPayload): Promise<void> {
  try {
    await fetch(`${resolveApiBaseUrl()}/client-logs/errors`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'editor', ...payload }),
      keepalive: true,
    })
  } catch {
    // 日志上报不能影响主流程
  }
}

function shouldDropDuplicate(payload: ClientErrorPayload): boolean {
  const signature = `${payload.error_name || ''}:${payload.message}:${payload.route || ''}`
  const now = Date.now()
  const lastSeenAt = recentErrors.get(signature) || 0
  if (now - lastSeenAt < ERROR_DEDUPE_WINDOW_MS) {
    return true
  }
  recentErrors.set(signature, now)
  return false
}

function normalizeError(error: unknown): { name: string; message: string; stack: string } {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack || '',
    }
  }
  return {
    name: 'Error',
    message: typeof error === 'string' ? error : JSON.stringify(sanitizeUnknown(error)),
    stack: '',
  }
}

function sanitizeUnknown(value: unknown): Record<string, unknown> | string | number | boolean | null {
  if (value === null || value === undefined || typeof value === 'number' || typeof value === 'boolean') {
    return value ?? null
  }
  if (typeof value === 'string') {
    return sanitizeText(value)
  }
  if (Array.isArray(value)) {
    return { items: value.slice(0, 20).map(item => sanitizeUnknown(item)) }
  }
  if (typeof value === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>).slice(0, 50)) {
      const normalizedKey = key.toLowerCase()
      if (/token|ctx|authorization|cookie|password|secret|api_?key/.test(normalizedKey)) {
        result[key] = '[redacted]'
      } else if (/content|source|prompt|result|body/.test(normalizedKey)) {
        result[key] = '[omitted]'
      } else {
        result[key] = sanitizeUnknown(item)
      }
    }
    return result
  }
  return sanitizeText(String(value))
}

function sanitizeText(value: string): string {
  const redacted = String(value || '')
    .replace(/([?&](?:token|ctx|authorization|api_key|apikey|secret|password)=)[^&\s]+/gi, '$1[redacted]')
    .replace(/\bBearer\s+[A-Za-z0-9_.=-]{16,}/gi, 'Bearer [redacted]')
    .replace(/\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b/g, '[redacted-token]')
  return redacted.length > MAX_TEXT_LENGTH ? `${redacted.slice(0, MAX_TEXT_LENGTH - 15)}...[truncated]` : redacted
}

function currentRouteText(): string {
  return typeof window === 'undefined' ? '' : `${window.location.pathname}${window.location.hash || ''}`
}

function currentUrlText(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return `${window.location.origin}${window.location.pathname}${window.location.hash || ''}`
}
