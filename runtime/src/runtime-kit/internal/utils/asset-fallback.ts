/**
 * 文件用途：统一 Runtime Kit 资源组件的兜底 URL 与兜底文案解析规则。
 */

export const DEFAULT_ASSET_FALLBACK_MESSAGE = '资源无法渲染，请检查资源名称或资源内容。'

/**
 * 判断 fallback 是否是浏览器可直接加载的资源 URL。
 *
 * @param value fallback 输入
 * @returns 是 URL 或明确相对路径时返回 true
 */
export function isAssetFallbackUrl(value: string): boolean {
  return /^(https?:\/\/|data:|blob:|\/|\.\/|\.\.\/)/i.test(value.trim())
}

/**
 * 从 fallback 输入中提取 URL；普通文案会被视为非 URL。
 *
 * @param value fallback 输入
 * @returns 可作为资源地址使用的字符串
 */
export function resolveAssetFallbackUrl(value?: string): string {
  const normalizedValue = String(value || '').trim()
  return normalizedValue && isAssetFallbackUrl(normalizedValue) ? normalizedValue : ''
}

/**
 * 从 fallback 输入中提取展示文案；URL fallback 不作为文案展示。
 *
 * @param value fallback 输入
 * @param defaultMessage 默认兜底文案
 * @returns 可展示给用户的兜底文案
 */
export function resolveAssetFallbackMessage(
  value?: string,
  defaultMessage: string = DEFAULT_ASSET_FALLBACK_MESSAGE,
): string {
  const normalizedValue = String(value || '').trim()
  if (!normalizedValue || isAssetFallbackUrl(normalizedValue)) {
    return defaultMessage
  }
  return normalizedValue
}
