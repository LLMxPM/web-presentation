/**
 * 文件用途：提供无状态预览入口、PreviewContextToken 验签、artifact 预加载与远程虚拟模块解析能力。
 */

import { posix } from 'path'
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose'
import type { Plugin, ViteDevServer } from 'vite'

import {
  DEFAULT_PREVIEW_TAILWIND_PATH,
  buildPreviewTailwindCacheSignature,
  buildPreviewTailwindStylesheetHref,
  collectPreviewTailwindSources,
  compilePreviewTailwindUtilities,
  normalizePreviewTailwindEndpointPath,
} from '../tailwind/preview-tailwind'
import {
  buildRemoteModuleId,
  isPreviewEntryModuleRequest,
  isBuiltinLocalViewPath,
  isRuntimeLocalPublicModulePath,
  normalizeRuntimeModulePath,
  parseRemoteModuleId,
  RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH,
  type ComponentPreviewMode,
  type PreviewKind,
  type PreviewScopeType,
  type RuntimePreloadedConfigBundle,
  type RuntimePreviewArtifactManifest,
  type RuntimePreviewContext,
  type RuntimePreviewEntryDescriptor,
} from '../shared/runtime-preview'
import {
  buildSnapdomProxyFetchHeaders,
  inferContentTypeFromUrl,
  isAllowedSnapdomProxyResourceUrl,
  isHttpUrl,
} from './runtime-snapdom-resource-proxy'
import { isRuntimeAccessLogEnabled, logRuntimeServer } from '../utils/runtime-logger'

interface RuntimeSaaSPreviewOptions {
  previewPath?: string
  previewTailwindPath?: string
  previewHeaderName?: string
  previewAssetBaseHeaderName?: string
  serviceTokenHeaderName?: string
  jwksUrl?: string
  previewAudience?: string
  backendApiBaseUrl?: string
  jwksTimeoutMs?: number
  backendRequestTimeoutMs?: number
}

interface PreviewTokenClaims extends JWTPayload {
  sub: string
  tenant_id: string
  artifact_id: string
  preview_kind: PreviewKind
  scope_type: PreviewScopeType
  workspace_id: string
  project_id?: string
  entry_descriptor: RuntimePreviewEntryDescriptor
  asset_base_url: string
  trace_id: string
  component_preview_mode?: ComponentPreviewMode
  component_source?: 'workspace_component' | 'runtime_kit'
  component_code?: string
  component_version_no?: number
  runtime_kit_component_name?: string
  runtime_kit_manifest_version?: string
  asset_id?: string
  jti: string
}

const DEFAULT_PREVIEW_PATH = '/__preview'
const DEFAULT_PREVIEW_HEADER = 'x-runtime-preview-context'
const DEFAULT_PREVIEW_ASSET_BASE_HEADER = 'x-runtime-public-base-url'
const DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER = 'x-runtime-service-token'
const DEFAULT_PREVIEW_AUDIENCE = 'runtime-preview'
const DEFAULT_JWKS_TIMEOUT_MS = 5000
const DEFAULT_BACKEND_REQUEST_TIMEOUT_MS = 10000
const DISALLOWED_REMOTE_IMPORT_PREFIX = '\0runtime-preview-disallowed:'

/**
 * 无状态 SaaS 预览插件：
 * 1. 仅在 Vite serve 下生效；
 * 2. 对 HTML 入口执行 PreviewContextToken 验签与 artifact 预加载；
 * 3. 远程模块加载只依赖 `artifactId + ctx token`；
 * 4. 不再通过 Backend 恢复 preview session。
 */
export default function runtimeSaaSPreview(options: RuntimeSaaSPreviewOptions = {}): Plugin {
  const previewPath = options.previewPath || DEFAULT_PREVIEW_PATH
  const previewTailwindPath = normalizePreviewTailwindEndpointPath(options.previewTailwindPath || DEFAULT_PREVIEW_TAILWIND_PATH)
  const previewHeaderName = (options.previewHeaderName || DEFAULT_PREVIEW_HEADER).toLowerCase()
  const previewAssetBaseHeaderName = (
    options.previewAssetBaseHeaderName
    || DEFAULT_PREVIEW_ASSET_BASE_HEADER
  ).toLowerCase()
  const serviceTokenHeaderName = (options.serviceTokenHeaderName || DEFAULT_RUNTIME_SERVICE_TOKEN_HEADER).toLowerCase()
  const manifestCache = new Map<string, RuntimePreviewArtifactManifest>()
  const previewTokenCache = new Map<string, string>()
  const serviceTokenCache = new Map<string, string>()
  const tailwindCssCache = new Map<string, string>()
  const jwksTimeoutMs = normalizePositiveInteger(options.jwksTimeoutMs, DEFAULT_JWKS_TIMEOUT_MS)
  const backendRequestTimeoutMs = normalizePositiveInteger(options.backendRequestTimeoutMs, DEFAULT_BACKEND_REQUEST_TIMEOUT_MS)
  let basePath = ''
  let assetBase = ''

  return {
    name: 'runtime-saas-preview',
    apply: 'serve',

    configResolved(resolvedConfig) {
      basePath = normalizeBasePath(resolvedConfig.base)
      assetBase = resolvedConfig.server?.origin ? resolvedConfig.server.origin + basePath : basePath
    },

    configureServer(server: ViteDevServer) {
      server.middlewares.use(async (req, res, next) => {
        const rawUrl = req.url || ''
        const strippedUrl = stripBasePath(rawUrl, basePath)
        if (getPathname(strippedUrl) === RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH) {
          return handleSnapdomResourceProxyRequest(req, res, {
            strippedUrl,
            jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
            previewAudience: options.previewAudience || process.env.RUNTIME_PREVIEW_TOKEN_AUDIENCE || DEFAULT_PREVIEW_AUDIENCE,
            backendApiBaseUrl: options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || '',
            jwksTimeoutMs,
            backendRequestTimeoutMs,
            manifestCache,
            previewTokenCache,
            serviceTokenCache,
          })
        }

        if (getPathname(strippedUrl) === previewTailwindPath) {
          return handlePreviewTailwindCssRequest(req, res, {
            strippedUrl,
            jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
            previewAudience: options.previewAudience || process.env.RUNTIME_PREVIEW_TOKEN_AUDIENCE || DEFAULT_PREVIEW_AUDIENCE,
            backendApiBaseUrl: options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || '',
            jwksTimeoutMs,
            backendRequestTimeoutMs,
            manifestCache,
            previewTokenCache,
            serviceTokenCache,
            tailwindCssCache,
          })
        }

        if (getPathname(strippedUrl) !== previewPath) {
          return next()
        }

        try {
          const previewToken = String(req.headers[previewHeaderName] || '')
          if (!previewToken) {
            throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_REQUIRED', '缺少预览上下文令牌。')
          }

          const verified = await verifyPreviewToken(previewToken, {
            jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
            audience: options.previewAudience || process.env.RUNTIME_PREVIEW_TOKEN_AUDIENCE || DEFAULT_PREVIEW_AUDIENCE,
            timeoutMs: jwksTimeoutMs,
          })
          previewTokenCache.set(verified.publicContext.artifactId, previewToken)
          const serviceToken = String(req.headers[serviceTokenHeaderName] || '')
          if (!serviceToken) {
            throw new PreviewGatewayError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Backend 下发的 Runtime 服务令牌。')
          }
          serviceTokenCache.set(verified.publicContext.artifactId, serviceToken)
          const resolvedAssetBase = resolvePreviewAssetBase(
            String(req.headers[previewAssetBaseHeaderName] || ''),
            assetBase,
          )

          const backendClient = createBackendClient({
            backendApiBaseUrl: options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || '',
            serviceToken,
            previewToken,
            requestTimeoutMs: backendRequestTimeoutMs,
          })

          const [manifest, configBundle] = await Promise.all([
            fetchArtifactManifest(verified.publicContext.artifactId, backendClient, manifestCache),
            backendClient.fetchConfigBundle(verified.publicContext.artifactId),
          ])

          assertManifestMatchesContext(manifest, verified.publicContext)

          sendHtml(res, buildPreviewHtml({
            assetBase: resolvedAssetBase,
            publicContext: verified.publicContext,
            previewToken,
            previewTailwindPath,
            configBundle: {
              ...configBundle,
              manifest,
            },
          }))
          if (isRuntimeAccessLogEnabled()) {
            logRuntimeServer('info', 'runtime.preview.request.completed', 'Runtime 预览入口请求完成。', {
              module: 'runtime.preview',
              request_id: String(req.headers['x-request-id'] || ''),
              trace_id: verified.publicContext.traceId,
              artifact_id: verified.publicContext.artifactId,
              workspace_id: verified.publicContext.workspaceId,
              project_id: verified.publicContext.projectId,
              scope_type: verified.publicContext.scopeType,
              preview_kind: verified.publicContext.previewKind,
              status_code: 200,
            })
          }
        } catch (error) {
          logRuntimeServer('error', 'runtime.preview.request.failed', 'Runtime 预览入口请求失败。', {
            module: 'runtime.preview',
            request_id: String(req.headers['x-request-id'] || ''),
            error,
          })
          sendPreviewError(res, error)
        }
      })
    },

    async resolveId(source, importer) {
      if (source.startsWith(DISALLOWED_REMOTE_IMPORT_PREFIX)) {
        return source
      }
      if (parseRemoteModuleId(source)) {
        return source
      }

      const importerInfo = importer ? parseRemoteModuleId(importer) : null
      if (!importerInfo) {
        return null
      }

      const resolveResult = resolveRemoteModuleImport(source, importerInfo.modulePath)
      if (resolveResult.type === 'ignore') {
        return null
      }
      if (resolveResult.type === 'disallowed') {
        return `${DISALLOWED_REMOTE_IMPORT_PREFIX}${encodeURIComponent(resolveResult.source)}`
      }
      const resolvedModulePath = resolveResult.modulePath
      if (!resolvedModulePath || isBuiltinLocalViewPath(resolvedModulePath) || isRuntimeLocalPublicModulePath(resolvedModulePath)) {
        return null
      }

      return buildRemoteModuleId(importerInfo.artifactId, resolvedModulePath, importerInfo.previewToken)
    },

    async load(id) {
      if (id.startsWith(DISALLOWED_REMOTE_IMPORT_PREFIX)) {
        const rawSource = decodeURIComponent(id.slice(DISALLOWED_REMOTE_IMPORT_PREFIX.length))
        throw new PreviewGatewayError(
          403,
          'RUNTIME_LOCAL_IMPORT_FORBIDDEN',
          `远程模块引用了未开放的 Runtime 本地模块：${rawSource}`,
        )
      }

      const parsed = parseRemoteModuleId(id)
      if (!parsed) {
        return null
      }
      const effectivePreviewToken = parsed.previewToken || previewTokenCache.get(parsed.artifactId) || ''
      if (!effectivePreviewToken) {
        throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_REQUIRED', '远程模块请求缺少预览上下文令牌。')
      }

      const verified = await verifyPreviewToken(effectivePreviewToken, {
        jwksUrl: options.jwksUrl || process.env.RUNTIME_PREVIEW_JWKS_URL || '',
        audience: options.previewAudience || process.env.RUNTIME_PREVIEW_TOKEN_AUDIENCE || DEFAULT_PREVIEW_AUDIENCE,
        timeoutMs: jwksTimeoutMs,
      })
      if (verified.publicContext.artifactId !== parsed.artifactId) {
        throw new PreviewGatewayError(403, 'ARTIFACT_MISMATCH', '预览 artifact 与远程模块请求不一致。')
      }
      previewTokenCache.set(parsed.artifactId, effectivePreviewToken)
      const serviceToken = serviceTokenCache.get(parsed.artifactId) || ''
      if (!serviceToken) {
        throw new PreviewGatewayError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Runtime 服务令牌缓存。')
      }

      const backendClient = createBackendClient({
        backendApiBaseUrl: options.backendApiBaseUrl || process.env.RUNTIME_BACKEND_API_BASE_URL || '',
        serviceToken,
        previewToken: effectivePreviewToken,
        requestTimeoutMs: backendRequestTimeoutMs,
      })

      const manifest = await fetchArtifactManifest(parsed.artifactId, backendClient, manifestCache)
      assertManifestMatchesContext(manifest, verified.publicContext)

      const manifestEntry = manifest.modules[parsed.modulePath]
      if (!manifestEntry && !isPreviewEntryModuleRequest(parsed.modulePath, verified.publicContext.entryDescriptor)) {
        throw new PreviewGatewayError(404, 'MODULE_NOT_ALLOWED', `模块未包含在发布白名单中：${parsed.modulePath}`)
      }

      return backendClient.fetchModuleSource(parsed.artifactId, parsed.modulePath)
    },
  }
}

/**
 * 预览网关错误类型，便于统一映射状态码与错误码。
 */
class PreviewGatewayError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string) {
    super(message)
    this.statusCode = statusCode
    this.code = code
  }
}

/**
 * 将 token 验签和 JWKS 拉取异常转换为预览网关错误。
 * @param error 原始异常
 * @returns 结构化预览错误
 */
function toPreviewTokenError(error: unknown): PreviewGatewayError {
  const name = error instanceof Error ? error.name : ''
  const message = error instanceof Error ? error.message : String(error || '')
  const lowerMessage = message.toLowerCase()
  if (name === 'JWKSTimeout' || lowerMessage.includes('timed out') || lowerMessage.includes('timeout')) {
    return new PreviewGatewayError(504, 'PREVIEW_JWKS_TIMEOUT', '预览 JWKS 获取超时。')
  }
  if (error instanceof TypeError && lowerMessage.includes('invalid url')) {
    return new PreviewGatewayError(503, 'JWKS_URL_INVALID', 'Runtime 预览 JWKS 地址无效。')
  }
  if (error instanceof TypeError || lowerMessage.includes('fetch failed')) {
    return new PreviewGatewayError(502, 'PREVIEW_JWKS_UNAVAILABLE', '预览 JWKS 获取失败。')
  }
  return new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '预览上下文令牌非法或已过期。')
}

/**
 * 根据 `@/views`、`/src/views` 或相对路径计算远程视图导入目标。
 * @param source import 源
 * @param importerPath 导入方逻辑路径
 * @returns 目标逻辑路径；非远程视图导入时返回 null
 */
function resolveRemoteModuleImport(
  source: string,
  importerPath: string,
): { type: 'remote'; modulePath: string } | { type: 'ignore' } | { type: 'disallowed'; source: string } {
  const normalizedSource = String(source || '').trim().replace(/\\/g, '/')
  if (!normalizedSource) {
    return { type: 'ignore' }
  }

  if (normalizedSource.startsWith('@workspace-components/')) {
    return { type: 'remote', modulePath: normalizeRuntimeModulePath(normalizedSource) }
  }

  if (normalizedSource.startsWith('@runtime-kit/')) {
    return { type: 'ignore' }
  }

  if (
    normalizedSource.startsWith('@/views/')
    || normalizedSource.startsWith('/src/views/')
    || normalizedSource.startsWith('src/views/')
    || normalizedSource.startsWith('views/')
  ) {
    return { type: 'remote', modulePath: normalizeRuntimeModulePath(normalizedSource) }
  }

  if (normalizedSource.startsWith('@/')) {
    const normalizedModulePath = normalizeRuntimeModulePath(normalizedSource)
    if (isBuiltinLocalViewPath(normalizedModulePath)) {
      return { type: 'ignore' }
    }
    return { type: 'disallowed', source: normalizedSource }
  }

  if (normalizedSource.startsWith('./') || normalizedSource.startsWith('../')) {
    const importerDir = posix.dirname(importerPath)
    const normalizedModulePath = normalizeRuntimeModulePath(posix.normalize(posix.join(importerDir, normalizedSource)))
    if (!normalizedModulePath) {
      return { type: 'ignore' }
    }
    if (normalizedModulePath.startsWith('src/runtime-kit/')) {
      return { type: 'disallowed', source: normalizedSource }
    }
    if (isBuiltinLocalViewPath(normalizedModulePath)) {
      return { type: 'ignore' }
    }
    if (normalizedModulePath.startsWith('src/views/') || normalizedModulePath.startsWith('src/workspace-components/')) {
      return { type: 'remote', modulePath: normalizedModulePath }
    }
    return { type: 'ignore' }
  }

  return { type: 'ignore' }
}

/**
 * 规范化 Vite base，根路径返回空串。
 * @param rawBase 原始 base 配置
 * @returns 规范化前缀
 */
function normalizeBasePath(rawBase: string): string {
  const normalized = String(rawBase || '/').trim()
  if (!normalized || normalized === '/' || normalized === '.' || normalized === './') {
    return ''
  }

  const stripped = normalized
    .replace(/^\.\//, '')
    .replace(/^\/+|\/+$/g, '')

  return stripped ? `/${stripped}` : ''
}

/**
 * 去掉 URL 中的 base 前缀。
 * @param rawUrl 原始 URL
 * @param basePath 规范化前缀
 * @returns 去前缀后的 URL
 */
function stripBasePath(rawUrl: string, basePath: string): string {
  if (!basePath || rawUrl === basePath) {
    return rawUrl
  }
  if (rawUrl.startsWith(`${basePath}/`)) {
    return rawUrl.slice(basePath.length)
  }
  return rawUrl
}

/**
 * 提取 URL pathname。
 * @param rawUrl 原始 URL
 * @returns pathname
 */
function getPathname(rawUrl: string): string {
  return String(rawUrl || '').split('?')[0] || '/'
}

/**
 * 规范化正整数超时配置。
 * @param value 原始配置值
 * @param fallback 默认值
 * @returns 可用于请求的毫秒数
 */
function normalizePositiveInteger(value: unknown, fallback: number): number {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return fallback
  }
  return Math.round(normalized)
}

/**
 * 校验 PreviewContextToken，并构造可公开注入浏览器的上下文。
 * @param token JWS 令牌
 * @param options 校验选项
 * @returns 校验后的结果
 */
async function verifyPreviewToken(token: string, options: { jwksUrl: string; audience: string; timeoutMs?: number }): Promise<{
  publicContext: RuntimePreviewContext
}> {
  if (!options.jwksUrl) {
    throw new PreviewGatewayError(503, 'JWKS_URL_MISSING', 'Runtime 未配置预览 JWKS 地址。')
  }

  let payload: JWTPayload
  try {
    const jwks = createRemoteJWKSet(new URL(options.jwksUrl), {
      timeoutDuration: normalizePositiveInteger(options.timeoutMs, DEFAULT_JWKS_TIMEOUT_MS),
    })
    const verified = await jwtVerify(token, jwks, {
      audience: options.audience,
    })
    payload = verified.payload
  } catch (error) {
    throw toPreviewTokenError(error)
  }

  const claims = payload as PreviewTokenClaims
  if (
    !claims.jti
    || !claims.tenant_id
    || !claims.artifact_id
    || !claims.preview_kind
    || !claims.scope_type
    || !claims.workspace_id
    || !claims.entry_descriptor
    || !claims.asset_base_url
    || !claims.trace_id
  ) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '预览上下文缺少必填声明。')
  }

  const entryDescriptor = normalizeEntryDescriptor(claims.entry_descriptor)
  if (claims.scope_type === 'project' && !claims.project_id) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '项目级预览缺少 project_id。')
  }
  if (
    claims.scope_type === 'workspace_component'
    && (!claims.component_code || claims.component_version_no === undefined || claims.component_source === 'runtime_kit')
  ) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '工作空间组件预览上下文缺少组件版本声明。')
  }
  if (
    claims.scope_type === 'runtime_kit_component'
    && (
      claims.component_source !== 'runtime_kit'
      || !claims.runtime_kit_component_name
      || !claims.runtime_kit_manifest_version
    )
  ) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', 'Runtime Kit 组件预览上下文缺少内建能力声明。')
  }
  if (claims.scope_type === 'workspace_asset' && !claims.asset_id) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '资源预览上下文缺少 asset_id。')
  }

  return {
    publicContext: {
      artifactId: String(claims.artifact_id),
      tenantId: String(claims.tenant_id),
      previewKind: claims.preview_kind,
      scopeType: claims.scope_type,
      workspaceId: String(claims.workspace_id),
      projectId: claims.project_id ? String(claims.project_id) : undefined,
      entryDescriptor,
      assetBaseUrl: String(claims.asset_base_url),
      traceId: String(claims.trace_id),
      componentPreviewMode: claims.component_preview_mode,
      componentSource: claims.component_source,
      componentCode: claims.component_code ? String(claims.component_code) : undefined,
      componentVersionNo: claims.component_version_no !== undefined ? Number(claims.component_version_no) : undefined,
      runtimeKitComponentName: claims.runtime_kit_component_name ? String(claims.runtime_kit_component_name) : undefined,
      runtimeKitManifestVersion: claims.runtime_kit_manifest_version ? String(claims.runtime_kit_manifest_version) : undefined,
      assetId: claims.asset_id ? String(claims.asset_id) : undefined,
    },
  }
}

/**
 * 规范化入口描述，避免非法 token 结构直接进入运行时。
 * @param value token 中的入口描述
 * @returns 规范化后的入口描述
 */
function normalizeEntryDescriptor(value: unknown): RuntimePreviewEntryDescriptor {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '预览入口描述格式非法。')
  }

  const source = value as Record<string, unknown>
  const entryType = String(source.entry_type || '')
  if (entryType === 'route') {
    const route = String(source.route || '').trim()
    if (!route) {
      throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', 'route 预览缺少 route。')
    }
    return { entry_type: 'route', route }
  }
  if (entryType === 'module') {
    const modulePath = normalizeRuntimeModulePath(String(source.module_path || ''))
    if (!modulePath) {
      throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', 'module 预览缺少 module_path。')
    }
    return { entry_type: 'module', module_path: modulePath }
  }
  if (entryType === 'component_host') {
    return { entry_type: 'component_host' }
  }
  if (entryType === 'asset_host') {
    return { entry_type: 'asset_host' }
  }
  throw new PreviewGatewayError(401, 'PREVIEW_CONTEXT_INVALID', '未知的预览入口类型。')
}

/**
 * 构造 Backend 内部 API 客户端。
 * @param options 客户端参数
 * @returns 内部 API 客户端
 */
function createBackendClient(options: {
  backendApiBaseUrl: string
  serviceToken: string
  previewToken?: string
  requestTimeoutMs?: number
}) {
  if (!options.backendApiBaseUrl) {
    throw new PreviewGatewayError(503, 'BACKEND_API_BASE_URL_MISSING', 'Runtime 未配置 Backend API 根地址。')
  }
  if (!options.serviceToken) {
    throw new PreviewGatewayError(503, 'RUNTIME_SERVICE_TOKEN_REQUIRED', 'Runtime 未获取到服务级令牌。')
  }

  const apiBaseUrl = options.backendApiBaseUrl.replace(/\/+$/, '')
  const requestTimeoutMs = normalizePositiveInteger(options.requestTimeoutMs, DEFAULT_BACKEND_REQUEST_TIMEOUT_MS)
  const defaultHeaders: Record<string, string> = {
    Authorization: `Bearer ${options.serviceToken}`,
  }
  if (options.previewToken) {
    defaultHeaders['x-runtime-preview-context'] = options.previewToken
  }

  return {
    async fetchManifest(artifactId: string): Promise<RuntimePreviewArtifactManifest> {
      return requestJson<RuntimePreviewArtifactManifest>(
        `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/manifest`,
        defaultHeaders,
        requestTimeoutMs,
      )
    },

    async fetchConfigBundle(artifactId: string): Promise<RuntimePreloadedConfigBundle> {
      return requestJson<RuntimePreloadedConfigBundle>(
        `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/config-bundle`,
        defaultHeaders,
        requestTimeoutMs,
      )
    },

    async fetchModuleSource(artifactId: string, modulePath: string): Promise<string> {
      const url = `${apiBaseUrl}/internal/runtime/preview-artifacts/${encodeURIComponent(artifactId)}/modules?path=${encodeURIComponent(modulePath)}`
      const response = await fetchWithTimeout(
        url,
        {
          headers: {
            ...defaultHeaders,
            Accept: 'text/plain, application/json;q=0.9',
          },
        },
        requestTimeoutMs,
        'BACKEND_MODULE_REQUEST_TIMEOUT',
      )
      if (!response.ok) {
        throw await toPreviewError(response, 'MODULE_FETCH_FAILED')
      }
      return response.text()
    },
  }
}

/**
 * 请求 JSON 接口并统一处理错误。
 * @param url 请求地址
 * @param headers 请求头
 * @returns 解析后的 JSON
 */
async function requestJson<T>(url: string, headers: Record<string, string>, timeoutMs: number): Promise<T> {
  const response = await fetchWithTimeout(
    url,
    {
      headers: {
        ...headers,
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'BACKEND_REQUEST_TIMEOUT',
  )
  if (!response.ok) {
    throw await toPreviewError(response, 'BACKEND_REQUEST_FAILED')
  }
  return response.json() as Promise<T>
}

/**
 * 带超时地请求 Backend 内部接口。
 * @param url 请求 URL
 * @param init fetch 参数
 * @param timeoutMs 超时时间
 * @param timeoutCode 超时错误码
 * @returns 原始响应
 */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  timeoutCode: string,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw new PreviewGatewayError(504, timeoutCode, 'Backend 内部接口请求超时。')
    }
    throw new PreviewGatewayError(
      502,
      'BACKEND_REQUEST_FAILED',
      error instanceof Error ? error.message : 'Backend 内部接口请求失败。',
    )
  } finally {
    clearTimeout(timeoutHandle)
  }
}

/**
 * 判断 fetch 异常是否由 AbortController 触发。
 * @param error 原始异常
 * @returns 是否为取消请求
 */
function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

/**
 * 将 Backend 响应转换为预览网关错误。
 * @param response 原始响应
 * @param fallbackCode 兜底错误码
 * @returns 统一错误对象
 */
async function toPreviewError(response: Response, fallbackCode: string): Promise<PreviewGatewayError> {
  let message = response.statusText || 'Backend 请求失败。'
  let code = fallbackCode
  try {
    const payload = await response.json()
    code = String(payload?.code || code)
    message = String(payload?.message || payload?.detail || message)
  } catch {
    // 忽略 JSON 解析异常，保留默认错误信息
  }
  return new PreviewGatewayError(response.status, code, message)
}

/**
 * 校验 manifest 与预览上下文声明是否一致。
 * @param manifest preview artifact manifest
 * @param previewContext 已校验的公开上下文
 */
export function assertManifestMatchesContext(
  manifest: RuntimePreviewArtifactManifest,
  previewContext: RuntimePreviewContext,
): void {
  if (
    manifest.artifact_id !== previewContext.artifactId
    || manifest.tenant_id !== previewContext.tenantId
    || manifest.preview_kind !== previewContext.previewKind
    || manifest.owner_scope?.scope_type !== previewContext.scopeType
    || String(manifest.owner_scope?.workspace_id || '') !== previewContext.workspaceId
  ) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', '预览清单与预览上下文不一致。')
  }

  if (previewContext.scopeType === 'project' && String(manifest.owner_scope?.project_id || '') !== String(previewContext.projectId || '')) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', '项目级预览 project_id 不一致。')
  }

  if (
    previewContext.scopeType === 'workspace_component'
    && (
      String(manifest.owner_scope?.component_code || '') !== String(previewContext.componentCode || '')
      || String(manifest.owner_scope?.component_version_no ?? '') !== String(previewContext.componentVersionNo ?? '')
    )
  ) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', '工作空间组件预览版本声明不一致。')
  }

  if (
    previewContext.scopeType === 'runtime_kit_component'
    && (
      String(manifest.owner_scope?.runtime_kit_component_name || '') !== String(previewContext.runtimeKitComponentName || '')
      || String(manifest.owner_scope?.runtime_kit_manifest_version || '') !== String(previewContext.runtimeKitManifestVersion || '')
    )
  ) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', 'Runtime Kit 组件能力声明不一致。')
  }

  if (
    previewContext.scopeType === 'workspace_asset'
    && String(manifest.owner_scope?.asset_id || '') !== String(previewContext.assetId || '')
  ) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', '资源预览 asset_id 不一致。')
  }

  if (!isEntryDescriptorEqual(manifest.entry_descriptor, previewContext.entryDescriptor)) {
    throw new PreviewGatewayError(403, 'MANIFEST_CONTEXT_MISMATCH', '预览入口描述与 artifact 清单不一致。')
  }
}

/**
 * 比较两个入口描述是否语义一致。
 * @param left 左侧入口描述
 * @param right 右侧入口描述
 * @returns 是否一致
 */
function isEntryDescriptorEqual(left: RuntimePreviewEntryDescriptor, right: RuntimePreviewEntryDescriptor): boolean {
  return (
    left.entry_type === right.entry_type
    && String(left.route || '') === String(right.route || '')
    && String(left.module_path || '') === String(right.module_path || '')
  )
}

/**
 * 按 artifact 读取清单，允许缓存不可变 manifest 以减少重复请求。
 * @param artifactId preview artifact ID
 * @param backendClient Backend 客户端
 * @param manifestCache manifest 缓存
 * @returns 预览清单
 */
async function fetchArtifactManifest(
  artifactId: string,
  backendClient: ReturnType<typeof createBackendClient>,
  manifestCache: Map<string, RuntimePreviewArtifactManifest>,
): Promise<RuntimePreviewArtifactManifest> {
  const cachedManifest = manifestCache.get(artifactId)
  if (cachedManifest) {
    return cachedManifest
  }

  const manifest = await backendClient.fetchManifest(artifactId)
  manifestCache.set(artifactId, manifest)
  return manifest
}

interface SnapdomResourceProxyRequestOptions {
  strippedUrl: string
  jwksUrl: string
  previewAudience: string
  backendApiBaseUrl: string
  jwksTimeoutMs: number
  backendRequestTimeoutMs: number
  manifestCache: Map<string, RuntimePreviewArtifactManifest>
  previewTokenCache: Map<string, string>
  serviceTokenCache: Map<string, string>
}

interface RuntimeNodeRequest {
  method?: string
}

interface RuntimeNodeResponse {
  statusCode: number
  setHeader: (name: string, value: string) => void
  end: (chunk?: string | Buffer) => void
}

/**
 * 处理 snapDOM 截图阶段的远端资源代理请求。
 * @param req Node 请求对象
 * @param res Node 响应对象
 * @param options 请求上下文
 */
async function handleSnapdomResourceProxyRequest(
  req: RuntimeNodeRequest,
  res: RuntimeNodeResponse,
  options: SnapdomResourceProxyRequestOptions,
): Promise<void> {
  try {
    if (req.method && req.method !== 'GET' && req.method !== 'HEAD') {
      throw new PreviewGatewayError(405, 'METHOD_NOT_ALLOWED', '截图资源代理仅支持 GET。')
    }

    const requestUrl = new URL(options.strippedUrl || '/', 'http://runtime.local')
    const artifactId = String(requestUrl.searchParams.get('artifactId') || '')
    const previewToken = String(requestUrl.searchParams.get('token') || '')
    const sourceUrl = String(requestUrl.searchParams.get('url') || '')
    if (!artifactId || !previewToken || !sourceUrl) {
      throw new PreviewGatewayError(400, 'SNAPDOM_PROXY_QUERY_INVALID', '缺少 artifactId、token 或 url。')
    }
    if (!isHttpUrl(sourceUrl)) {
      throw new PreviewGatewayError(400, 'SNAPDOM_PROXY_URL_INVALID', '截图资源代理只允许 http/https 资源。')
    }

    const verified = await verifyPreviewToken(previewToken, {
      jwksUrl: options.jwksUrl,
      audience: options.previewAudience,
      timeoutMs: options.jwksTimeoutMs,
    })
    if (verified.publicContext.artifactId !== artifactId) {
      throw new PreviewGatewayError(403, 'ARTIFACT_MISMATCH', '预览 artifact 与截图资源代理请求不一致。')
    }
    options.previewTokenCache.set(artifactId, previewToken)

    const serviceToken = options.serviceTokenCache.get(artifactId) || ''
    if (!serviceToken) {
      throw new PreviewGatewayError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Runtime 服务令牌缓存。')
    }

    const backendClient = createBackendClient({
      backendApiBaseUrl: options.backendApiBaseUrl,
      serviceToken,
      previewToken,
      requestTimeoutMs: options.backendRequestTimeoutMs,
    })
    const manifest = await fetchArtifactManifest(artifactId, backendClient, options.manifestCache)
    assertManifestMatchesContext(manifest, verified.publicContext)

    if (!isAllowedSnapdomProxyResourceUrl(sourceUrl, manifest, verified.publicContext)) {
      throw new PreviewGatewayError(403, 'SNAPDOM_PROXY_RESOURCE_FORBIDDEN', '截图资源代理只允许访问当前 artifact 声明的静态资源。')
    }

    const response = await fetchWithTimeout(
      sourceUrl,
      {
        headers: buildSnapdomProxyFetchHeaders(sourceUrl, serviceToken, previewToken, manifest, verified.publicContext),
      },
      options.backendRequestTimeoutMs,
      'SNAPDOM_PROXY_REQUEST_TIMEOUT',
    )
    if (!response.ok) {
      throw await toPreviewError(response, 'SNAPDOM_PROXY_FETCH_FAILED')
    }

    const body = Buffer.from(await response.arrayBuffer())
    sendBinary(res, body, {
      contentType: response.headers.get('content-type') || inferContentTypeFromUrl(sourceUrl),
      isHead: req.method === 'HEAD',
    })
  } catch (error) {
    logRuntimeServer('error', 'runtime.preview.snapdom.failed', '截图资源代理请求失败。', {
      module: 'runtime.preview',
      error,
    })
    sendSnapdomResourceProxyError(res, error)
  }
}

/**
 * 写入可供 snapDOM 读取的代理响应。
 * @param res Node 响应对象
 * @param body 二进制内容
 * @param options 响应选项
 */
function sendBinary(
  res: RuntimeNodeResponse,
  body: Buffer,
  options: { contentType: string; isHead: boolean },
): void {
  res.statusCode = 200
  res.setHeader('Content-Type', options.contentType || 'application/octet-stream')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Content-Length', String(body.length))
  res.end(options.isHead ? undefined : body)
}

/**
 * 输出 snapDOM 资源代理错误。
 * @param res Node 响应对象
 * @param error 错误对象
 */
function sendSnapdomResourceProxyError(res: RuntimeNodeResponse, error: unknown): void {
  const previewError = error instanceof PreviewGatewayError
    ? error
    : new PreviewGatewayError(500, 'SNAPDOM_PROXY_ERROR', error instanceof Error ? error.message : '截图资源代理异常。')

  res.statusCode = previewError.statusCode
  res.setHeader('Content-Type', 'text/plain; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(`${previewError.code}: ${previewError.message}`)
}

interface PreviewTailwindCssRequestOptions {
  strippedUrl: string
  jwksUrl: string
  previewAudience: string
  backendApiBaseUrl: string
  jwksTimeoutMs: number
  backendRequestTimeoutMs: number
  manifestCache: Map<string, RuntimePreviewArtifactManifest>
  previewTokenCache: Map<string, string>
  serviceTokenCache: Map<string, string>
  tailwindCssCache: Map<string, string>
}

/**
 * 处理预览 artifact 的 Tailwind utilities CSS 请求。
 * @param req Node 请求对象
 * @param res Node 响应对象
 * @param options 请求上下文
 */
async function handlePreviewTailwindCssRequest(
  req: RuntimeNodeRequest,
  res: RuntimeNodeResponse,
  options: PreviewTailwindCssRequestOptions,
): Promise<void> {
  try {
    if (req.method && req.method !== 'GET' && req.method !== 'HEAD') {
      throw new PreviewGatewayError(405, 'METHOD_NOT_ALLOWED', '预览 Tailwind CSS 入口仅支持 GET。')
    }

    const requestUrl = new URL(options.strippedUrl || '/', 'http://runtime.local')
    const artifactId = String(requestUrl.searchParams.get('artifactId') || '')
    const previewToken = String(requestUrl.searchParams.get('token') || '')
    if (!artifactId || !previewToken) {
      throw new PreviewGatewayError(400, 'PREVIEW_TAILWIND_QUERY_INVALID', '缺少 artifactId 或 token。')
    }

    const verified = await verifyPreviewToken(previewToken, {
      jwksUrl: options.jwksUrl,
      audience: options.previewAudience,
      timeoutMs: options.jwksTimeoutMs,
    })
    if (verified.publicContext.artifactId !== artifactId) {
      throw new PreviewGatewayError(403, 'ARTIFACT_MISMATCH', '预览 artifact 与 Tailwind CSS 请求不一致。')
    }
    options.previewTokenCache.set(artifactId, previewToken)

    const serviceToken = options.serviceTokenCache.get(artifactId) || ''
    if (!serviceToken) {
      throw new PreviewGatewayError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Runtime 服务令牌缓存。')
    }

    const backendClient = createBackendClient({
      backendApiBaseUrl: options.backendApiBaseUrl,
      serviceToken,
      previewToken,
      requestTimeoutMs: options.backendRequestTimeoutMs,
    })
    const manifest = await fetchArtifactManifest(artifactId, backendClient, options.manifestCache)
    assertManifestMatchesContext(manifest, verified.publicContext)

    const sources = await collectPreviewTailwindSources({
      artifactId,
      manifest,
      entryDescriptor: verified.publicContext.entryDescriptor,
      backendClient,
    })
    const cacheKey = `${artifactId}:${buildPreviewTailwindCacheSignature(sources)}`
    const cachedCss = options.tailwindCssCache.get(cacheKey)
    if (cachedCss) {
      return sendCss(res, cachedCss)
    }

    let css: string
    try {
      css = await compilePreviewTailwindUtilities(sources)
    } catch (error) {
      logRuntimeServer('error', 'runtime.preview.tailwind.compile.failed', '预览 Tailwind CSS 编译失败。', {
        module: 'runtime.preview',
        artifact_id: artifactId,
        moduleCount: sources.length,
        error: error instanceof Error
          ? { name: error.name, message: error.message, stack: error.stack }
          : error,
      })
      css = `/* preview tailwind compile failed: ${escapeCssComment(error instanceof Error ? error.message : String(error))} */\n`
    }

    options.tailwindCssCache.set(cacheKey, css)
    sendCss(res, css)
  } catch (error) {
    logRuntimeServer('error', 'runtime.preview.tailwind.request.failed', '预览 Tailwind CSS 请求失败。', {
      module: 'runtime.preview',
      error,
    })
    sendPreviewTailwindErrorCss(res, error)
  }
}

/**
 * 生成预览页 HTML，并注入公开上下文、预加载配置与 PreviewContextToken。
 * @param params HTML 参数
 * @returns HTML 文本
 */
export function buildPreviewHtml(params: {
  assetBase: string
  publicContext: RuntimePreviewContext
  previewToken: string
  previewTailwindPath?: string
  configBundle: RuntimePreloadedConfigBundle
}): string {
  const viteClientPath = `${params.assetBase || ''}/@vite/client`
  const mainEntryPath = `${params.assetBase || ''}/src/main.ts`
  const previewTailwindHref = buildPreviewTailwindStylesheetHref({
    assetBase: params.assetBase,
    artifactId: params.publicContext.artifactId,
    previewToken: params.previewToken,
    previewTailwindPath: params.previewTailwindPath,
  })
  const serializedContext = serializeForInlineScript(params.publicContext)
  const serializedToken = serializeForInlineScript(params.previewToken)
  const serializedConfig = serializeForInlineScript(params.configBundle)
  const serializedRuntimePublicBaseUrl = serializeForInlineScript(params.assetBase)

  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Runtime Preview</title>
    <style>
      html, body, #app { margin: 0; width: 100%; height: 100%; background: #f8fafc; }
      body { overflow: hidden; font-family: "Segoe UI", "PingFang SC", sans-serif; }
    </style>
    <script>
      window.__RUNTIME_PREVIEW_CONTEXT__ = ${serializedContext};
      window.__RUNTIME_PREVIEW_TOKEN__ = ${serializedToken};
      window.__RUNTIME_PRELOADED_CONFIG__ = ${serializedConfig};
      window.__RUNTIME_PUBLIC_BASE_URL__ = ${serializedRuntimePublicBaseUrl};
    </script>
    <script type="module" src="${viteClientPath}"></script>
    <link rel="stylesheet" href="${previewTailwindHref}" />
    <script type="module" src="${mainEntryPath}"></script>
  </head>
  <body>
    <div id="app"></div>
  </body>
</html>`
}

/**
 * 解析当前预览 HTML 应使用的前端资源根地址。
 * @param requestAssetBase Backend 透传的浏览器可访问 Runtime 地址
 * @param fallbackAssetBase Runtime 当前服务推导出的兜底地址
 * @returns 最终资源根地址
 */
export function resolvePreviewAssetBase(requestAssetBase: string, fallbackAssetBase: string): string {
  const normalizedRequestAssetBase = normalizePreviewAssetBase(requestAssetBase)
  if (normalizedRequestAssetBase) {
    return normalizedRequestAssetBase
  }
  return normalizePreviewAssetBase(fallbackAssetBase)
}

/**
 * 将 JSON 安全序列化为可直接写入内联 script 的文本。
 * @param value 任意可 JSON 序列化值
 * @returns 已转义的 JSON 文本
 */
export function serializeForInlineScript(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003C')
    .replace(/>/g, '\\u003E')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029')
}

/**
 * 规范化预览前端资源根地址，移除尾部斜杠。
 * @param rawValue 原始地址
 * @returns 规范化后的地址
 */
function normalizePreviewAssetBase(rawValue: string): string {
  return String(rawValue || '').trim().replace(/\/+$/, '')
}

/**
 * 输出 HTML 响应。
 * @param res Node 响应对象
 * @param html HTML 内容
 */
function sendHtml(res: RuntimeNodeResponse, html: string): void {
  res.statusCode = 200
  res.setHeader('Content-Type', 'text/html; charset=utf-8')
  res.end(html)
}

/**
 * 输出 CSS 响应。
 * @param res Node 响应对象
 * @param css CSS 内容
 */
function sendCss(res: RuntimeNodeResponse, css: string): void {
  res.statusCode = 200
  res.setHeader('Content-Type', 'text/css; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(css)
}

/**
 * 输出预览 Tailwind CSS 错误响应，避免样式编译问题阻断页面脚本执行。
 * @param res Node 响应对象
 * @param error 错误对象
 */
function sendPreviewTailwindErrorCss(res: RuntimeNodeResponse, error: unknown): void {
  const previewError = error instanceof PreviewGatewayError
    ? error
    : new PreviewGatewayError(500, 'PREVIEW_TAILWIND_ERROR', error instanceof Error ? error.message : '预览 Tailwind CSS 生成失败。')

  res.statusCode = previewError.statusCode
  res.setHeader('Content-Type', 'text/css; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(`/* ${escapeCssComment(previewError.code)}: ${escapeCssComment(previewError.message)} */\n`)
}

/**
 * 输出统一预览错误响应。
 * @param res Node 响应对象
 * @param error 错误对象
 */
function sendPreviewError(res: RuntimeNodeResponse, error: unknown): void {
  const previewError = error instanceof PreviewGatewayError
    ? error
    : new PreviewGatewayError(500, 'PREVIEW_GATEWAY_ERROR', error instanceof Error ? error.message : '预览网关异常。')

  res.statusCode = previewError.statusCode
  res.setHeader('Content-Type', 'text/html; charset=utf-8')
  res.end(`<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Runtime Preview Error</title>
    <style>
      html, body { margin: 0; width: 100%; height: 100%; background: #f8fafc; font-family: "Segoe UI", "PingFang SC", sans-serif; }
      body { display: flex; align-items: center; justify-content: center; padding: 24px; box-sizing: border-box; }
      .card { max-width: 760px; width: 100%; background: #fff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 32px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08); }
      .title { margin: 0 0 12px; font-size: 28px; color: #0f172a; }
      .desc { margin: 0 0 20px; color: #475569; line-height: 1.7; }
      .meta { display: grid; gap: 10px; padding: 16px; background: #f8fafc; border-radius: 12px; color: #334155; }
      .code { color: #b91c1c; font-weight: 700; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1 class="title">预览启动失败</h1>
      <p class="desc">请检查 PreviewContextToken、preview artifact 清单以及 Runtime 到 Backend 的内部接口连通性。</p>
      <div class="meta">
        <div><span class="code">HTTP ${previewError.statusCode}</span></div>
        <div>错误码：${escapeHtml(previewError.code)}</div>
        <div>错误信息：${escapeHtml(previewError.message)}</div>
      </div>
    </div>
  </body>
</html>`)
}

/**
 * 转义 HTML 文本，避免错误详情破坏页面结构。
 * @param value 原始文本
 * @returns 转义后的文本
 */
function escapeHtml(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 转义 CSS 注释内容，避免错误信息破坏 stylesheet。
 * @param value 原始文本
 * @returns 可安全写入 CSS 注释的文本
 */
function escapeCssComment(value: string): string {
  return String(value)
    .replace(/\*\//g, '* /')
    .replace(/[\r\n]+/g, ' ')
}
