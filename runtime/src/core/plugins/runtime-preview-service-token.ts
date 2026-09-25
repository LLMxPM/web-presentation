/**
 * 文件功能：预览链路 Runtime 服务令牌的可恢复获取与短期缓存管理。
 *
 * 票据作用域与过期约定：
 * - PreviewContextToken：浏览器持有的最小权限预览票据，绑定单个 artifact / 工作空间 / 入口，
 *   由 Backend 签发并带过期时间；只用于预览鉴权与内部换票，不授予构建、诊断等其它能力。
 * - Runtime 服务令牌：`sub=runtime-service`、`scope=runtime-artifact-read`，绑定 `artifact_id`，
 *   TTL 与 PreviewContextToken 剩余有效期对齐（至少 60 秒），只能读取该 artifact 的内部接口；
 *   仅在 Runtime → Backend 受信内网链路使用，禁止写入预览 HTML 或任何浏览器可见响应。
 * - 进程内缓存只用于加速：缓存缺失、过期或进程重启都不影响正确性，可通过换票接口重新获取。
 *
 * 日志脱敏：任何日志、错误信息都不得携带令牌原文；需要诊断时只记录 artifact_id 与脱敏摘要。
 */

import {
  buildPreviewCacheKey,
  PreviewBoundedCache,
  PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN,
} from './runtime-preview-cache'

export const PREVIEW_SERVICE_TOKEN_EXCHANGE_PATH = '/internal/runtime/preview-service-token'

/** 服务令牌过期前的安全刷新窗口，避免临界过期令牌被缓存继续使用。 */
const SERVICE_TOKEN_REFRESH_MARGIN_MS = 30_000

/** 换票请求默认超时时间。 */
const DEFAULT_EXCHANGE_TIMEOUT_MS = 10_000

/**
 * 进程内服务令牌缓存条目；仅加速，丢失不影响正确性。
 */
export interface ServiceTokenCacheEntry {
  token: string
  expiresAtMs: number
}

/**
 * 服务令牌缓存容器：有界（LRU + TTL），键为稳定 artifact 身份，令牌只作值。
 */
export type ServiceTokenCache = PreviewBoundedCache<ServiceTokenCacheEntry>

/**
 * 解析后的服务令牌及其过期时间。
 */
export interface ResolvedServiceToken {
  token: string
  expiresAtMs: number
}

/**
 * 服务令牌恢复失败时的结构化错误，供调用方映射为预览网关错误。
 */
export class PreviewServiceTokenError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string, cause?: unknown) {
    super(message, { cause })
    this.name = 'PreviewServiceTokenError'
    this.statusCode = statusCode
    this.code = code
  }
}

export interface ResolveRuntimeServiceTokenOptions {
  /** 目标 preview artifact ID */
  artifactId: string
  /** 已验证的 PreviewContextToken，换票凭据 */
  previewToken: string
  /** Backend 内部 API 根地址 */
  backendApiBaseUrl: string
  /** 进程内缓存（仅加速，有界 LRU + TTL） */
  serviceTokenCache: ServiceTokenCache
  /** 本次请求自带的 Backend 下发服务令牌（如 `/__preview` 请求头），优先使用 */
  headerServiceToken?: string
  /** 换票请求超时毫秒数 */
  requestTimeoutMs?: number
}

/**
 * 获取可用于 Backend 内部 artifact 接口的短期服务令牌。
 *
 * 恢复顺序：有效缓存 → 本次请求自带令牌 → 向 Backend 内部换票。缓存只加速，任何缺失都可换票恢复。
 * @param options 恢复选项
 * @returns 服务令牌与其过期时间
 */
export async function resolveRuntimeServiceToken(
  options: ResolveRuntimeServiceTokenOptions,
): Promise<ResolvedServiceToken> {
  const { artifactId, previewToken, backendApiBaseUrl, serviceTokenCache } = options
  if (!artifactId) {
    throw new PreviewServiceTokenError(401, 'PREVIEW_CONTEXT_INVALID', '缺少 artifact 标识，无法恢复服务令牌。')
  }
  if (!previewToken) {
    throw new PreviewServiceTokenError(401, 'PREVIEW_CONTEXT_REQUIRED', '缺少预览上下文令牌，无法换发服务令牌。')
  }

  const cached = readFreshCacheEntry(serviceTokenCache, artifactId)
  if (cached) {
    return cached
  }

  if (options.headerServiceToken) {
    const resolved = resolveTokenWithExpiry(options.headerServiceToken, Date.now())
    writeCacheEntry(serviceTokenCache, artifactId, resolved)
    return resolved
  }

  return exchangeServiceToken({
    artifactId,
    previewToken,
    backendApiBaseUrl,
    serviceTokenCache,
    requestTimeoutMs: options.requestTimeoutMs,
  })
}

/**
 * 向 Backend 内部换票端点换取 artifact 作用域的短期服务令牌，并写入缓存。
 * @param options 换票选项
 * @returns 换票结果
 */
async function exchangeServiceToken(options: {
  artifactId: string
  previewToken: string
  backendApiBaseUrl: string
  serviceTokenCache: ServiceTokenCache
  requestTimeoutMs?: number
}): Promise<ResolvedServiceToken> {
  const apiBaseUrl = String(options.backendApiBaseUrl || '').trim().replace(/\/+$/, '')
  if (!apiBaseUrl) {
    throw new PreviewServiceTokenError(503, 'BACKEND_API_BASE_URL_MISSING', 'Runtime 未配置 Backend API 根地址。')
  }

  const url = `${apiBaseUrl}${PREVIEW_SERVICE_TOKEN_EXCHANGE_PATH}`
  const timeoutMs = normalizePositiveInteger(options.requestTimeoutMs, DEFAULT_EXCHANGE_TIMEOUT_MS)
  const response = await fetchWithTimeout(
    url,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ preview_token: options.previewToken }),
    },
    timeoutMs,
  )

  if (!response.ok) {
    throw await toExchangeError(response)
  }

  let payload: { service_token?: string; expires_in?: number; artifact_id?: string }
  try {
    payload = await response.json() as { service_token?: string; expires_in?: number; artifact_id?: string }
  } catch {
    throw new PreviewServiceTokenError(502, 'SERVICE_TOKEN_EXCHANGE_INVALID', '服务令牌换票响应格式非法。')
  }

  const serviceToken = String(payload.service_token || '')
  if (!serviceToken) {
    throw new PreviewServiceTokenError(502, 'SERVICE_TOKEN_EXCHANGE_INVALID', '服务令牌换票响应缺少令牌。')
  }
  if (payload.artifact_id && String(payload.artifact_id) !== options.artifactId) {
    throw new PreviewServiceTokenError(403, 'ARTIFACT_MISMATCH', '换票响应与目标 artifact 不一致。')
  }

  const expiresAtMs = Date.now() + normalizePositiveInteger(payload.expires_in, 60) * 1000
  const resolved = { token: serviceToken, expiresAtMs }
  writeCacheEntry(options.serviceTokenCache, options.artifactId, resolved)
  return resolved
}

/**
 * 读取未过期的缓存条目；临近过期视为缺失。
 * @param cache 服务令牌缓存（有界 LRU + TTL）
 * @param artifactId artifact 标识
 * @returns 有效缓存条目；缺失或过期返回 null
 */
export function readFreshCacheEntry(
  cache: ServiceTokenCache,
  artifactId: string,
): ServiceTokenCacheEntry | null {
  const entry = cache.get(buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN))
  if (!entry?.token) {
    return null
  }
  if (entry.expiresAtMs - Date.now() <= SERVICE_TOKEN_REFRESH_MARGIN_MS) {
    cache.delete(buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN))
    return null
  }
  return entry
}

/**
 * 写入服务令牌缓存；过期时间不可读的令牌不做缓存。
 * 缓存 TTL 与令牌剩余有效期对齐，避免过期条目滞留。
 * @param cache 服务令牌缓存（有界 LRU + TTL）
 * @param artifactId artifact 标识
 * @param resolved 解析结果
 */
function writeCacheEntry(
  cache: ServiceTokenCache,
  artifactId: string,
  resolved: ResolvedServiceToken,
): void {
  const cacheKey = buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN)
  const remainingTtlMs = resolved.expiresAtMs - Date.now()
  if (remainingTtlMs <= 0) {
    cache.delete(cacheKey)
    return
  }
  cache.set(cacheKey, resolved, { artifactId, ttlMs: remainingTtlMs })
}

/**
 * 解析服务令牌并推导其缓存过期时间；无法读取 exp 时视为立即过期。
 * @param token 服务令牌原文
 * @param nowMs 当前时间毫秒
 * @returns 令牌与过期时间
 */
function resolveTokenWithExpiry(token: string, nowMs: number): ResolvedServiceToken {
  const expiresAtMs = readJwtExpiresAtMs(token)
  return {
    token,
    expiresAtMs: expiresAtMs ?? nowMs,
  }
}

/**
 * 读取 JWT 的 `exp` 声明（仅用于缓存过期管理，不替代签名校验）。
 * @param token JWT 原文
 * @returns 过期时间毫秒；无法解析返回 null
 */
export function readJwtExpiresAtMs(token: string): number | null {
  const parts = String(token || '').split('.')
  if (parts.length !== 3 || !parts[1]) {
    return null
  }
  try {
    const json = Buffer.from(parts[1], 'base64url').toString('utf8')
    const payload = JSON.parse(json) as { exp?: unknown }
    const exp = Number(payload.exp)
    if (!Number.isFinite(exp) || exp <= 0) {
      return null
    }
    return exp * 1000
  } catch {
    return null
  }
}

/**
 * 将 JWT 形态的文本脱敏为可安全写入日志的摘要。
 * @param value 可能包含令牌的文本
 * @returns 脱敏后的摘要
 */
export function redactJwtForLog(value: string): string {
  const trimmed = String(value || '')
  if (!trimmed) {
    return ''
  }
  if (trimmed.split('.').length === 3) {
    const expiresAtMs = readJwtExpiresAtMs(trimmed)
    return `jwt(len=${trimmed.length}, exp=${expiresAtMs ? new Date(expiresAtMs).toISOString() : 'unknown'})`
  }
  return trimmed.length > 16 ? `${trimmed.slice(0, 8)}…(len=${trimmed.length})` : trimmed
}

/**
 * 带超时地发起换票请求。
 * @param url 换票地址
 * @param init fetch 参数
 * @param timeoutMs 超时毫秒
 * @returns 原始响应
 */
async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new PreviewServiceTokenError(504, 'SERVICE_TOKEN_EXCHANGE_TIMEOUT', '服务令牌换票请求超时。')
    }
    throw new PreviewServiceTokenError(
      502,
      'SERVICE_TOKEN_EXCHANGE_FAILED',
      '服务令牌换票请求失败。',
    )
  } finally {
    clearTimeout(timeoutHandle)
  }
}

/**
 * 将换票失败的 Backend 响应转换为结构化错误；响应体不写入日志。
 * @param response 原始响应
 * @returns 结构化错误
 */
async function toExchangeError(response: Response): Promise<PreviewServiceTokenError> {
  let code = 'SERVICE_TOKEN_EXCHANGE_FAILED'
  let message = '服务令牌换票被拒绝。'
  try {
    const payload = await response.json() as { code?: unknown; message?: unknown; detail?: unknown }
    if (payload?.code) {
      code = String(payload.code)
    }
    const detail = String(payload?.message || payload?.detail || '')
    if (detail) {
      message = detail
    }
  } catch {
    // 忽略响应体解析异常，保留默认错误信息
  }
  return new PreviewServiceTokenError(response.status, code, message)
}

/**
 * 规范化正整数配置。
 * @param value 原始值
 * @param fallback 兜底值
 * @returns 规范化后的整数
 */
function normalizePositiveInteger(value: unknown, fallback: number): number {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return fallback
  }
  return Math.round(normalized)
}
