/**
 * 文件用途：为 Runtime Node 插件日志提供 JSON Lines 输出和脱敏工具。
 */

type RuntimeLogLevel = 'debug' | 'info' | 'warn' | 'error'

const LEVEL_ORDER: Record<RuntimeLogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
}
const MAX_TEXT_LENGTH = 4096
const ANSI_ESCAPE_PATTERN = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g')

/**
 * 输出 Runtime 服务端日志；容器模式下默认使用单行 JSON。
 * @param level 日志等级
 * @param event 事件名
 * @param message 可读说明
 * @param context 结构化上下文
 */
export function logRuntimeServer(
  level: RuntimeLogLevel,
  event: string,
  message: string,
  context: Record<string, unknown> = {},
): void {
  if (!shouldEmit(level)) {
    return
  }

  const payload = sanitizeValue({
    ts: new Date().toISOString(),
    level: level.toUpperCase(),
    service: 'runtime',
    module: context.module || 'runtime.server',
    event,
    message,
    request_id: context.request_id || '',
    ...context,
  }) as Record<string, unknown>

  const line = runtimeLogFormat() === 'json'
    ? JSON.stringify(payload)
    : `${payload.ts} ${payload.level} [${payload.module}] ${payload.message}`

  if (level === 'error') {
    console.error(line)
  } else if (level === 'warn') {
    console.warn(line)
  } else {
    console.info(line)
  }
}

/**
 * 脱敏任意日志上下文，避免 token、源码正文和长文本进入日志。
 * @param value 原始值
 * @returns 已脱敏值
 */
export function sanitizeValue(value: unknown): unknown {
  if (value === null || value === undefined || typeof value === 'number' || typeof value === 'boolean') {
    return value ?? null
  }
  if (typeof value === 'string') {
    return sanitizeText(value)
  }
  if (Array.isArray(value)) {
    return value.slice(0, 50).map(item => sanitizeValue(item))
  }
  if (value instanceof Error) {
    return {
      name: value.name,
      message: sanitizeText(value.message),
      stack: sanitizeText(value.stack || ''),
    }
  }
  if (typeof value === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
      const normalizedKey = key.toLowerCase()
      if (/token|ctx|authorization|cookie|password|secret|api_?key|access_key/.test(normalizedKey)) {
        result[key] = '[redacted]'
      } else if (/content|source|prompt|result|body/.test(normalizedKey)) {
        result[key] = '[omitted]'
      } else {
        result[key] = sanitizeValue(item)
      }
    }
    return result
  }
  return sanitizeText(String(value))
}

/**
 * 判断 Runtime 访问类日志是否启用。
 * @returns true 表示输出预览、构建、诊断请求生命周期日志
 */
export function isRuntimeAccessLogEnabled(): boolean {
  return readProcessEnv('RUNTIME_ACCESS_LOG_ENABLED').toLowerCase() !== 'false'
}

function shouldEmit(level: RuntimeLogLevel): boolean {
  return LEVEL_ORDER[level] >= LEVEL_ORDER[runtimeLogLevel()]
}

function runtimeLogLevel(): RuntimeLogLevel {
  const rawLevel = readProcessEnv('RUNTIME_LOG_LEVEL').toLowerCase()
  return rawLevel in LEVEL_ORDER ? rawLevel as RuntimeLogLevel : 'info'
}

function runtimeLogFormat(): 'json' | 'text' {
  return readProcessEnv('RUNTIME_LOG_FORMAT').toLowerCase() === 'text' ? 'text' : 'json'
}

function readProcessEnv(key: string): string {
  if (typeof process === 'undefined') {
    return ''
  }
  return String(process.env?.[key] || '')
}

function sanitizeText(value: string): string {
  const redacted = String(value || '')
    .replace(ANSI_ESCAPE_PATTERN, '')
    .replace(/([?&](?:token|ctx|authorization|api_key|apikey|secret|password)=)[^&\s]+/gi, '$1[redacted]')
    .replace(/\bBearer\s+[A-Za-z0-9_.=-]{16,}/gi, 'Bearer [redacted]')
    .replace(/\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b/g, '[redacted-token]')
  return redacted.length > MAX_TEXT_LENGTH ? `${redacted.slice(0, MAX_TEXT_LENGTH - 15)}...[truncated]` : redacted
}
