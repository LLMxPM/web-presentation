/**
 * 文件用途：提供 snapDOM 截图资源代理的 URL 白名单、鉴权头转发与响应类型辅助逻辑。
 */

import {
  normalizeAssetKey,
  type RuntimePreviewArtifactManifest,
  type RuntimePreviewContext,
} from '../shared/runtime-preview'

/**
 * 构建截图资源代理的上游请求头。
 * @param sourceUrl 原始远端资源 URL
 * @param serviceToken Runtime 服务令牌
 * @param previewToken 预览上下文令牌
 * @param manifest 当前预览 artifact 清单
 * @param previewContext 已校验的公开上下文
 */
export function buildSnapdomProxyFetchHeaders(
  sourceUrl: string,
  serviceToken: string,
  previewToken: string,
  manifest: RuntimePreviewArtifactManifest,
  previewContext: RuntimePreviewContext,
): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: '*/*',
  }

  if (shouldForwardPreviewAuthHeaders(sourceUrl, manifest, previewContext)) {
    headers.Authorization = `Bearer ${serviceToken}`
    headers['x-runtime-preview-context'] = previewToken
  }

  return headers
}

/**
 * 判断 snapDOM 资源代理是否允许访问目标 URL。
 * @param sourceUrl 原始远端资源 URL
 * @param manifest 当前预览 artifact 清单
 * @param previewContext 已校验的公开上下文
 */
export function isAllowedSnapdomProxyResourceUrl(
  sourceUrl: string,
  manifest: RuntimePreviewArtifactManifest,
  previewContext: RuntimePreviewContext,
): boolean {
  const normalizedSourceUrl = normalizeComparableUrl(sourceUrl)
  if (!normalizedSourceUrl || !isHttpUrl(normalizedSourceUrl)) {
    return false
  }

  return buildAllowedSnapdomProxyResourceUrls(manifest, previewContext).has(normalizedSourceUrl)
}

/**
 * 判断是否是 http/https URL。
 * @param value 待判断文本
 */
export function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(String(value || '').trim())
}

/**
 * 根据 URL 后缀推断常见资源类型。
 * @param sourceUrl 资源 URL
 */
export function inferContentTypeFromUrl(sourceUrl: string): string {
  const pathname = (() => {
    try {
      return new URL(sourceUrl).pathname.toLowerCase()
    } catch {
      return ''
    }
  })()

  if (pathname.endsWith('.svg')) return 'image/svg+xml'
  if (pathname.endsWith('.png')) return 'image/png'
  if (pathname.endsWith('.jpg') || pathname.endsWith('.jpeg')) return 'image/jpeg'
  if (pathname.endsWith('.webp')) return 'image/webp'
  if (pathname.endsWith('.gif')) return 'image/gif'
  if (pathname.endsWith('.avif')) return 'image/avif'
  return 'application/octet-stream'
}

/**
 * 判断上游资源是否属于当前 Backend 资源基址，只有这类请求才透传内部鉴权头。
 * @param sourceUrl 原始远端资源 URL
 * @param manifest 当前预览 artifact 清单
 * @param previewContext 已校验的公开上下文
 */
function shouldForwardPreviewAuthHeaders(
  sourceUrl: string,
  manifest: RuntimePreviewArtifactManifest,
  previewContext: RuntimePreviewContext,
): boolean {
  const normalizedSourceUrl = normalizeComparableUrl(sourceUrl)
  if (!normalizedSourceUrl) {
    return false
  }

  return [
    previewContext.assetBaseUrl,
    manifest.asset_base_url,
  ]
    .map(normalizeAssetBaseUrl)
    .map(value => normalizeComparableUrl(value).replace(/\/+$/, ''))
    .some(assetBaseUrl => {
      return assetBaseUrl &&
        (normalizedSourceUrl === assetBaseUrl || normalizedSourceUrl.startsWith(`${assetBaseUrl}/`))
    })
}

/**
 * 构建当前 artifact 允许被截图代理读取的资源 URL 集合。
 * @param manifest 当前预览 artifact 清单
 * @param previewContext 已校验的公开上下文
 */
function buildAllowedSnapdomProxyResourceUrls(
  manifest: RuntimePreviewArtifactManifest,
  previewContext: RuntimePreviewContext,
): Set<string> {
  const allowedUrls = new Set<string>()
  const assetBaseUrls = [
    previewContext.assetBaseUrl,
    manifest.asset_base_url,
  ]
    .map(normalizeAssetBaseUrl)
    .filter((value, index, array) => value && array.indexOf(value) === index)

  Object.entries(manifest.assets || {}).forEach(([logicalName, mappedValue]) => {
    const normalizedMappedValue = String(mappedValue || '').trim()
    if (!normalizedMappedValue) {
      return
    }

    addComparableUrl(allowedUrls, normalizedMappedValue)

    const metadata = manifest.asset_metadata?.[logicalName] || manifest.asset_metadata?.[normalizeAssetKey(logicalName)]
    const fileHash = String(metadata?.file_hash || normalizedMappedValue || '').trim()
    if (!fileHash || isHttpUrl(fileHash)) {
      return
    }

    assetBaseUrls.forEach(assetBaseUrl => {
      addComparableUrl(allowedUrls, joinAssetUrl(assetBaseUrl, fileHash, false))
      addComparableUrl(allowedUrls, joinAssetUrl(assetBaseUrl, fileHash, true))
    })
  })

  return allowedUrls
}

/**
 * 拼接资源基址和资源路径。
 * @param assetBaseUrl 资源基址
 * @param assetPath 资源路径或文件 hash
 * @param encodePath 是否按完整文件名编码
 */
function joinAssetUrl(assetBaseUrl: string, assetPath: string, encodePath: boolean): string {
  const normalizedBaseUrl = normalizeAssetBaseUrl(assetBaseUrl)
  const normalizedAssetPath = normalizeAssetKey(assetPath)
  if (!normalizedBaseUrl || !normalizedAssetPath) {
    return ''
  }

  return `${normalizedBaseUrl}/${encodePath ? encodeURIComponent(normalizedAssetPath) : normalizedAssetPath}`
}

/**
 * 标准化资源基址。
 * @param rawValue 原始地址
 */
function normalizeAssetBaseUrl(rawValue: unknown): string {
  return String(rawValue || '').trim().replace(/\/+$/, '')
}

/**
 * 将 URL 规范化为可比较格式。
 * @param rawUrl 原始 URL
 */
function normalizeComparableUrl(rawUrl: string): string {
  try {
    return new URL(rawUrl).href
  } catch {
    return ''
  }
}

/**
 * 添加一个可比较 URL。
 * @param target 目标集合
 * @param rawUrl 原始 URL
 */
function addComparableUrl(target: Set<string>, rawUrl: string): void {
  const normalizedUrl = normalizeComparableUrl(rawUrl)
  if (normalizedUrl && isHttpUrl(normalizedUrl)) {
    target.add(normalizedUrl)
  }
}
