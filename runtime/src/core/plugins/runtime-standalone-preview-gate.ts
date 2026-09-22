/**
 * 文件用途：提供 Runtime dev 独立页面入口访问控制插件，避免直接访问本地 fixture 页面。
 */

import type { ServerResponse } from 'http'
import type { Plugin, ViteDevServer } from 'vite'

import { RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH } from '../shared/runtime-preview'

interface RuntimeStandalonePreviewGateOptions {
  enabled?: boolean
}

export interface StandalonePreviewRequestLike {
  method?: string
  url?: string
  headers?: Record<string, string | string[] | undefined>
}

const DISABLED_CODE = 'STANDALONE_PREVIEW_DISABLED'
const DISABLED_STATUS = 403
const DISABLED_VALUES = new Set(['false', '0', 'off', 'no', 'disabled'])
const RUNTIME_PLATFORM_EXACT_PATHS = new Set([
  '/__preview',
  '/__preview-tailwind.css',
  RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH,
])
const RUNTIME_PLATFORM_PATH_PREFIXES = [
  '/__runtime_internal/',
  '/@',
  '/src/',
  '/node_modules/',
]

/**
 * 将环境变量值解析为独立页面入口是否启用。
 * @param rawValue 环境变量原始值，未配置时默认启用
 * @returns 独立页面入口是否启用
 */
export function resolveStandalonePreviewEnabled(rawValue?: string | boolean | null): boolean {
  if (typeof rawValue === 'boolean') {
    return rawValue
  }
  const normalized = String(rawValue ?? '').trim().toLowerCase()
  if (!normalized) {
    return true
  }
  return !DISABLED_VALUES.has(normalized)
}

/**
 * 判断请求是否应被独立页面入口访问控制拦截。
 * @param req Vite dev server 请求对象
 * @param basePath Runtime 挂载路径前缀
 * @returns 是否应返回禁用响应
 */
export function shouldBlockStandalonePreviewRequest(req: StandalonePreviewRequestLike, basePath = ''): boolean {
  const method = String(req.method || 'GET').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD') {
    return false
  }
  if (isWebSocketUpgradeRequest(req.headers || {})) {
    return false
  }

  const pathname = stripBasePath(getRequestPathname(req.url || '/'), basePath)
  if (isPlatformRuntimePath(pathname)) {
    return false
  }
  if (isStandaloneHtmlEntryPath(pathname)) {
    return true
  }
  if (isStaticAssetPath(pathname)) {
    return false
  }

  return isDocumentNavigationRequest(req.headers || {}) || isSpaFallbackPath(pathname)
}

/**
 * 创建 Runtime 独立页面入口访问控制插件。
 * @param options 插件配置
 * @returns Vite 插件
 */
export default function runtimeStandalonePreviewGate(options: RuntimeStandalonePreviewGateOptions = {}): Plugin {
  const enabled = options.enabled ?? true
  let basePath = ''

  return {
    name: 'runtime-standalone-preview-gate',
    apply: 'serve',
    enforce: 'pre',

    configResolved(config) {
      basePath = normalizeBasePath(config.base)
    },

    configureServer(server: ViteDevServer) {
      if (enabled) {
        return
      }

      server.middlewares.use((req, res, next) => {
        if (!shouldBlockStandalonePreviewRequest(req, basePath)) {
          return next()
        }
        sendStandalonePreviewDisabledResponse(req, res)
      })
    },
  }
}

/**
 * 输出独立页面入口禁用响应。
 * @param req 当前请求
 * @param res Node 响应对象
 */
export function sendStandalonePreviewDisabledResponse(
  req: StandalonePreviewRequestLike,
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
): void {
  const wantsJson = acceptsJson(req.headers || {})
  res.statusCode = DISABLED_STATUS
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('X-Runtime-Error-Code', DISABLED_CODE)

  if (wantsJson) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    if (String(req.method || 'GET').toUpperCase() === 'HEAD') {
      res.end()
      return
    }
    res.end(JSON.stringify({
      success: false,
      code: DISABLED_CODE,
      message: 'Runtime 独立页面入口已关闭，请通过 Backend 预览入口访问。',
    }))
    return
  }

  res.setHeader('Content-Type', 'text/html; charset=utf-8')
  if (String(req.method || 'GET').toUpperCase() === 'HEAD') {
    res.end()
    return
  }
  res.end(`<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Runtime 独立页面入口已关闭</title>
  </head>
  <body style="margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;background:#f8fafc;font-family:Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;color:#0f172a;">
    <main style="max-width:640px;padding:32px;text-align:center;">
      <p style="margin:0 0 12px;font:600 12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#64748b;">${DISABLED_STATUS} ${DISABLED_CODE}</p>
      <h1 style="margin:0 0 12px;font-size:28px;line-height:1.25;">Runtime 独立页面入口已关闭</h1>
      <p style="margin:0;color:#475569;line-height:1.8;">当前 dev 服务仅保留 Backend 平台预览、构建和诊断链路。请通过 Backend 预览入口访问页面。</p>
    </main>
  </body>
</html>`)
}

/**
 * 解析请求路径，避免 query 影响路径判断。
 * @param rawUrl 原始请求 URL
 * @returns pathname
 */
function getRequestPathname(rawUrl: string): string {
  try {
    return new URL(rawUrl, 'http://runtime.local').pathname || '/'
  } catch {
    return '/'
  }
}

/**
 * 规范化 Vite base，根路径返回空串，便于请求路径判断。
 * @param rawBase 原始 base 配置
 * @returns 规范化后的路径前缀
 */
function normalizeBasePath(rawBase: string): string {
  const normalized = String(rawBase || '').trim()
  if (!normalized || normalized === '/' || normalized === '.' || normalized === './') {
    return ''
  }

  const stripped = normalized
    .replace(/^\.\//, '')
    .replace(/^\/+|\/+$/g, '')

  return stripped ? `/${stripped}` : ''
}

/**
 * 去掉 Runtime 挂载路径前缀，避免同域 /runtime 部署下误拦截 Vite 资源。
 * @param pathname 请求路径
 * @param basePath Runtime 挂载路径前缀
 * @returns 去掉前缀后的路径
 */
function stripBasePath(pathname: string, basePath: string): string {
  if (!basePath) {
    return pathname
  }
  if (pathname === basePath) {
    return '/'
  }
  if (pathname.startsWith(`${basePath}/`)) {
    return pathname.slice(basePath.length) || '/'
  }
  return pathname
}

/**
 * 判断是否为平台预览、构建或 Vite 运行所需路径。
 * @param pathname 请求路径
 * @returns 是否应直接放行
 */
function isPlatformRuntimePath(pathname: string): boolean {
  return RUNTIME_PLATFORM_EXACT_PATHS.has(pathname)
    || RUNTIME_PLATFORM_PATH_PREFIXES.some(prefix => (
      pathname === prefix.replace(/\/$/, '') || pathname.startsWith(prefix)
    ))
}

/**
 * 判断是否为带扩展名的静态资源路径。
 * @param pathname 请求路径
 * @returns 是否看起来是静态资源
 */
function isStaticAssetPath(pathname: string): boolean {
  const lastSegment = pathname.split('/').pop() || ''
  return /\.[a-z0-9][a-z0-9-]*$/i.test(lastSegment)
}

/**
 * 判断是否为 Runtime 独立应用 HTML 入口。
 * @param pathname 请求路径
 * @returns 是否为独立页面入口
 */
function isStandaloneHtmlEntryPath(pathname: string): boolean {
  return pathname === '/' || pathname === '/index.html'
}

/**
 * 判断是否为浏览器页面导航请求。
 * @param headers 请求头
 * @returns 是否为 document 导航
 */
function isDocumentNavigationRequest(headers: Record<string, string | string[] | undefined>): boolean {
  const secFetchDest = getHeaderValue(headers, 'sec-fetch-dest').toLowerCase()
  if (secFetchDest === 'document') {
    return true
  }

  const secFetchMode = getHeaderValue(headers, 'sec-fetch-mode').toLowerCase()
  if (secFetchMode === 'navigate') {
    return true
  }

  const accept = getHeaderValue(headers, 'accept').toLowerCase()
  return accept.includes('text/html')
}

/**
 * 判断是否为 Vite HMR 等 WebSocket upgrade 请求。
 * @param headers 请求头
 * @returns 是否为 WebSocket 请求
 */
function isWebSocketUpgradeRequest(headers: Record<string, string | string[] | undefined>): boolean {
  return getHeaderValue(headers, 'upgrade').toLowerCase() === 'websocket'
    || Boolean(getHeaderValue(headers, 'sec-websocket-key'))
}

/**
 * 判断路径是否会落到 Vite SPA fallback。
 * @param pathname 请求路径
 * @returns 是否为页面入口类路径
 */
function isSpaFallbackPath(pathname: string): boolean {
  return pathname === '/' || pathname === '/index.html' || !isStaticAssetPath(pathname)
}

/**
 * 判断请求是否更偏向 JSON 响应。
 * @param headers 请求头
 * @returns 是否返回 JSON
 */
function acceptsJson(headers: Record<string, string | string[] | undefined>): boolean {
  const accept = getHeaderValue(headers, 'accept').toLowerCase()
  return accept.includes('application/json') && !accept.includes('text/html')
}

/**
 * 读取请求头字符串值。
 * @param headers 请求头集合
 * @param name 请求头名称
 * @returns 请求头文本值
 */
function getHeaderValue(headers: Record<string, string | string[] | undefined>, name: string): string {
  const directValue = headers[name] ?? headers[name.toLowerCase()]
  if (Array.isArray(directValue)) {
    return directValue.join(',')
  }
  return String(directValue || '')
}
