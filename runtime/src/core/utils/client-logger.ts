/**
 * 文件用途：统一 Runtime 浏览器端错误捕获，并向平台 Backend 上报 runtime-browser 错误。
 */
import type { App } from 'vue'

interface RuntimeClientErrorPayload {
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
const IGNORED_BROWSER_ERROR_MESSAGES = new Set([
  'ResizeObserver loop completed with undelivered notifications.',
  'ResizeObserver loop limit exceeded',
])
const recentErrors = new Map<string, number>()
let installed = false

/**
 * 安装 Runtime 浏览器错误捕获。
 * @param app Vue 应用实例
 */
export function installRuntimeClientLogger(app: App): void {
  if (installed || typeof window === 'undefined') {
    return
  }
  installed = true

  app.config.errorHandler = (error, _instance, info) => {
    reportRuntimeClientError(error, {
      component: 'vue',
      context: { info },
    })
  }

  window.addEventListener('error', (event) => {
    reportRuntimeClientError(event.error || event.message, {
      component: 'window.error',
      context: { filename: event.filename, lineno: event.lineno, colno: event.colno },
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    reportRuntimeClientError(event.reason, {
      component: 'window.unhandledrejection',
    })
  })
}

/**
 * 记录 Runtime 浏览器错误；开发控制台保留输出，平台预览场景会上报 Backend。
 * @param error 错误对象或文本
 * @param options 附加上下文
 */
export function reportRuntimeClientError(error: unknown, options: Partial<RuntimeClientErrorPayload> = {}): void {
  const payload = buildRuntimeClientErrorPayload(error, options)
  if (shouldIgnoreRuntimeClientError(payload)) {
    return
  }
  if (import.meta.env.DEV) {
    console.error(payload.message, sanitizeUnknown(error))
  }
  if (!shouldReportRuntimeClientError() || shouldDropDuplicate(payload)) {
    return
  }
  void sendRuntimeClientError(payload)
}

/**
 * 构造 Runtime 错误上报载荷，补齐 preview context 中的 trace 与 artifact。
 * @param error 错误对象或文本
 * @param options 附加上下文
 * @returns 可上报载荷
 */
export function buildRuntimeClientErrorPayload(
  error: unknown,
  options: Partial<RuntimeClientErrorPayload> = {},
): RuntimeClientErrorPayload {
  const normalized = normalizeError(error)
  const previewContext = typeof window === 'undefined' ? undefined : window.__RUNTIME_PREVIEW_CONTEXT__
  return {
    message: sanitizeText(options.message || normalized.message || 'Runtime 浏览器端错误。'),
    error_name: sanitizeText(options.error_name || normalized.name || 'Error'),
    stack: sanitizeText(options.stack || normalized.stack || ''),
    route: sanitizeText(options.route || currentRouteText()),
    url: sanitizeText(options.url || currentUrlText()),
    component: sanitizeText(options.component || ''),
    trace_id: sanitizeText(options.trace_id || previewContext?.traceId || ''),
    artifact_id: sanitizeText(options.artifact_id || previewContext?.artifactId || ''),
    context: sanitizeUnknown({
      scopeType: previewContext?.scopeType,
      previewKind: previewContext?.previewKind,
      workspaceId: previewContext?.workspaceId,
      projectId: previewContext?.projectId,
      ...(options.context || {}),
    }) as Record<string, unknown>,
  }
}

async function sendRuntimeClientError(payload: RuntimeClientErrorPayload): Promise<void> {
  try {
    await fetch('/api/client-logs/errors', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'runtime-browser', ...payload }),
      keepalive: true,
    })
  } catch {
    // 错误上报失败不能影响预览渲染
  }
}

function shouldReportRuntimeClientError(): boolean {
  return typeof window !== 'undefined' && Boolean(window.__RUNTIME_PREVIEW_CONTEXT__)
}

function shouldDropDuplicate(payload: RuntimeClientErrorPayload): boolean {
  const signature = `${payload.error_name || ''}:${payload.message}:${payload.trace_id || ''}:${payload.route || ''}`
  const now = Date.now()
  const lastSeenAt = recentErrors.get(signature) || 0
  if (now - lastSeenAt < ERROR_DEDUPE_WINDOW_MS) {
    return true
  }
  recentErrors.set(signature, now)
  return false
}

/**
 * 过滤浏览器派发到 window.error 的已知良性噪声，避免污染控制台和后端错误统计。
 * @param payload 标准化后的错误载荷
 * @returns 是否应忽略
 */
function shouldIgnoreRuntimeClientError(payload: RuntimeClientErrorPayload): boolean {
  return IGNORED_BROWSER_ERROR_MESSAGES.has((payload.message || '').trim())
}

function normalizeError(error: unknown): { name: string; message: string; stack: string } {
  if (error instanceof Error) {
    return { name: error.name, message: error.message, stack: error.stack || '' }
  }
  return {
    name: 'Error',
    message: typeof error === 'string' ? error : JSON.stringify(sanitizeUnknown(error)),
    stack: '',
  }
}

function sanitizeUnknown(value: unknown): unknown {
  if (value === null || value === undefined || typeof value === 'number' || typeof value === 'boolean') {
    return value ?? null
  }
  if (typeof value === 'string') {
    return sanitizeText(value)
  }
  if (Array.isArray(value)) {
    return value.slice(0, 20).map(item => sanitizeUnknown(item))
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
