/** 文件功能：将业务响应中的受保护文件地址对齐 Editor API 入口，保留文件版本与下载参数。 */

const FILE_URL_FIELDS = new Set(['screenshot_url', 'first_page_screenshot_url', 'asset_url'])
const PROTECTED_FILE_PATH = /^\/api\/(?:pages\/\d+\/screenshots\/(?:latest|current|[a-f0-9]{64})\/content|workspaces\/\d+\/assets\/(?:\d+\/(?:file|content)|by-hash\/[^/]+))$/

/**
 * 将 Backend 返回的私有文件 URL 改走当前 API 入口，避免公开基址别名导致 host-only Cookie 丢失。
 * 仅接受平台的精确文件路由；预览票据、其它文件路由及非 HTTP 地址保持原样。
 */
export function resolveAuthenticatedFileUrl(value: string, apiBaseUrl: string): string {
  try {
    const url = new URL(value, 'https://editor-file.invalid')
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || !PROTECTED_FILE_PATH.test(url.pathname)) return value
    return `${apiBaseUrl.replace(/\/+$/, '')}${url.pathname.slice('/api'.length)}${url.search}${url.hash}`
  } catch {
    return value
  }
}

/**
 * 在响应进入查询缓存前统一处理页面、项目、字体与资源 DTO 的文件字段。
 * 只遍历普通 JSON 对象；源码字符串、Blob 和 ArrayBuffer 不作解析或修改。
 */
export function normalizeAuthenticatedFileUrls(payload: unknown, apiBaseUrl: string): void {
  if (Array.isArray(payload)) {
    payload.forEach(item => normalizeAuthenticatedFileUrls(item, apiBaseUrl))
    return
  }
  if (!payload || typeof payload !== 'object' || Object.getPrototypeOf(payload) !== Object.prototype) return
  const record = payload as Record<string, unknown>
  const isAsset = typeof record.id === 'number' && (
    (typeof record.workspace_id === 'number' && typeof record.file_hash === 'string')
    || (typeof record.asset_type === 'string' && typeof record.original_name === 'string')
  )
  for (const [key, value] of Object.entries(record)) {
    if (typeof value === 'string' && (FILE_URL_FIELDS.has(key) || (key === 'url' && isAsset))) {
      record[key] = resolveAuthenticatedFileUrl(value, apiBaseUrl)
    } else {
      normalizeAuthenticatedFileUrls(value, apiBaseUrl)
    }
  }
}

/** 为资源下载设置 download=1，保留已有 hash、其它查询参数与锚点。 */
export function buildFileDownloadUrl(value: string): string {
  const url = new URL(value, window.location.origin)
  url.searchParams.set('download', '1')
  return url.toString()
}
