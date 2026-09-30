/** 文件功能：解析 Runtime 固定挂载路径与版本化资源路径，供受保护入口及访问门禁共用。 */
import { RUNTIME_VERSION_PATH } from './runtime-version-identity'

/**
 * 同时接收 /runtime/__preview 管理入口与带版本的资源路径，保留原查询参数。
 * 仅规范化路径；版本检查和票据鉴权必须由调用方的前置门禁完成。
 */
export function stripRuntimeRequestBase(url: string, basePath: string): string {
  const versionBase = basePath.replace(/\/+$/, '')
  const mountBase = versionBase.split(RUNTIME_VERSION_PATH)[0] || ''
  for (const candidate of new Set([versionBase, mountBase])) {
    if (!candidate) continue
    if (url === candidate) return '/'
    if (url.startsWith(`${candidate}/`)) return url.slice(candidate.length)
    if (url.startsWith(`${candidate}?`)) return `/${url.slice(candidate.length)}`
  }
  return url
}
