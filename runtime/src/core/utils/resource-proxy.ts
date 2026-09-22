/**
 * 文件用途：提供浏览器侧 Runtime 资源代理 URL 构造与 manifest 资源白名单判断。
 */

import {
  normalizeAssetKey,
  RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH,
} from '@/core/shared/runtime-preview'
import {
  getRuntimePreloadedConfig,
  getRuntimePreviewContext,
  getRuntimePreviewToken,
} from '@/core/utils/path'

/**
 * 解析当前可用的 Runtime 资源代理基址。
 * @param explicitProxyUrl 显式配置的代理 URL
 */
export function resolveRuntimeResourceProxyBaseUrl(explicitProxyUrl?: string): string {
  const configuredProxyUrl = String(explicitProxyUrl || import.meta.env.VITE_SNAPDOM_PROXY_URL || '').trim()
  if (configuredProxyUrl) {
    return configuredProxyUrl
  }

  if (typeof window === 'undefined') {
    return ''
  }

  const previewContext = getRuntimePreviewContext()
  const previewToken = getRuntimePreviewToken()
  if (!previewContext?.artifactId || !previewToken) {
    return ''
  }

  const runtimePublicBaseUrl = resolveRuntimePublicBaseUrl()
  const proxyBaseUrl = runtimePublicBaseUrl || window.location.origin
  const proxyUrl = new URL(
    RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH.replace(/^\/+/, ''),
    `${proxyBaseUrl.replace(/\/+$/, '')}/`,
  )
  proxyUrl.searchParams.set('artifactId', previewContext.artifactId)
  proxyUrl.searchParams.set('token', previewToken)
  proxyUrl.searchParams.set('url', '')

  return proxyUrl.href
}

/**
 * 为当前 artifact 声明的资源构造 Runtime 同源代理 URL。
 * @param rawUrl 原始资源 URL
 * @param proxyBaseUrl 资源代理基址
 */
export function buildRuntimeResourceProxyUrl(rawUrl: string, proxyBaseUrl?: string): string {
  const sourceUrl = normalizeRuntimeHttpResourceUrl(rawUrl)
  if (!sourceUrl || !isRuntimeManifestAssetUrl(sourceUrl)) {
    return ''
  }

  const resolvedProxyBaseUrl = proxyBaseUrl || resolveRuntimeResourceProxyBaseUrl()
  if (!resolvedProxyBaseUrl) {
    return ''
  }

  try {
    const nextUrl = new URL(resolvedProxyBaseUrl, window.location.href)
    nextUrl.searchParams.set('url', sourceUrl)
    return nextUrl.href
  } catch {
    return ''
  }
}

/**
 * 判断 URL 是否属于当前 manifest 声明的工作空间资源。
 * @param sourceUrl 绝对资源 URL
 */
export function isRuntimeManifestAssetUrl(sourceUrl: string): boolean {
  const previewContext = getRuntimePreviewContext()
  const manifest = getRuntimePreloadedConfig()?.manifest
  if (!previewContext || !manifest) {
    return false
  }

  const normalizedSourceUrl = normalizeComparableUrl(sourceUrl)
  if (!normalizedSourceUrl) {
    return false
  }

  const allowedUrls = new Set<string>()
  const assetBaseUrls = [
    previewContext.assetBaseUrl,
    manifest.asset_base_url,
  ]
    .map(value => String(value || '').trim().replace(/\/+$/, ''))
    .filter((value, index, values) => value && values.indexOf(value) === index)

  Object.entries(manifest.assets || {}).forEach(([logicalName, mappedValue]) => {
    const normalizedMappedValue = String(mappedValue || '').trim()
    if (!normalizedMappedValue) {
      return
    }

    addComparableUrl(allowedUrls, normalizedMappedValue)

    const metadata = manifest.asset_metadata?.[logicalName] || manifest.asset_metadata?.[normalizeAssetKey(logicalName)]
    const fileHash = String(metadata?.file_hash || normalizedMappedValue || '').trim()
    if (!fileHash || /^https?:\/\//i.test(fileHash)) {
      return
    }

    assetBaseUrls.forEach(assetBaseUrl => {
      addComparableUrl(allowedUrls, joinAssetUrl(assetBaseUrl, fileHash, false))
      addComparableUrl(allowedUrls, joinAssetUrl(assetBaseUrl, fileHash, true))
    })
  })

  return allowedUrls.has(normalizedSourceUrl)
}

/**
 * 解析为绝对 http(s) URL。
 * @param rawUrl 原始资源 URL
 */
export function normalizeRuntimeHttpResourceUrl(rawUrl: string): string {
  if (typeof window === 'undefined') {
    return ''
  }

  const normalized = String(rawUrl || '').trim()
  if (!normalized || /^(data|blob|about|#):?/i.test(normalized)) {
    return ''
  }

  try {
    const url = new URL(normalized, window.location.href)
    return /^https?:$/i.test(url.protocol) ? url.href : ''
  } catch {
    return ''
  }
}

/**
 * 读取预览 HTML 注入的 Runtime 公开基址。
 */
function resolveRuntimePublicBaseUrl(): string {
  const runtimePublicBaseUrl = String(window.__RUNTIME_PUBLIC_BASE_URL__ || '').trim()
  if (!runtimePublicBaseUrl) {
    return ''
  }

  try {
    return new URL(runtimePublicBaseUrl, window.location.href).href.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

/**
 * 拼接资源基址和资源路径。
 * @param assetBaseUrl 资源基址
 * @param assetPath 资源路径或文件 hash
 * @param encodePath 是否编码路径
 */
function joinAssetUrl(assetBaseUrl: string, assetPath: string, encodePath: boolean): string {
  const normalizedBaseUrl = String(assetBaseUrl || '').trim().replace(/\/+$/, '')
  const normalizedAssetPath = normalizeAssetKey(assetPath)
  if (!normalizedBaseUrl || !normalizedAssetPath) {
    return ''
  }
  return `${normalizedBaseUrl}/${encodePath ? encodeURIComponent(normalizedAssetPath) : normalizedAssetPath}`
}

/**
 * 添加可比较 URL。
 * @param target 目标集合
 * @param rawUrl 原始 URL
 */
function addComparableUrl(target: Set<string>, rawUrl: string): void {
  const normalizedUrl = normalizeComparableUrl(rawUrl)
  if (normalizedUrl && /^https?:\/\//i.test(normalizedUrl)) {
    target.add(normalizedUrl)
  }
}

/**
 * 规范化 URL，便于与 manifest 派生 URL 精确比较。
 * @param rawUrl 原始 URL
 */
function normalizeComparableUrl(rawUrl: string): string {
  if (typeof window === 'undefined') {
    try {
      return new URL(rawUrl).href
    } catch {
      return ''
    }
  }

  try {
    return new URL(rawUrl, window.location.href).href
  } catch {
    return ''
  }
}
