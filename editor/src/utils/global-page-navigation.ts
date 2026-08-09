/**
 * 文件功能：构建全局管理页面的来源导航，并校验可安全返回的 Editor 站内路径。
 */
import type { RouteLocationRaw } from 'vue-router'

const globalPagePaths = new Set(['/account/ai-settings', '/admin/users'])

/**
 * 校验全局页面携带的返回路径，仅允许 Editor 内部绝对路径并阻止全局页面之间循环返回。
 * @param value 路由查询参数中的候选返回路径
 */
export function resolveGlobalReturnPath(value: unknown): string | null {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string' || !candidate.startsWith('/') || candidate.startsWith('//')) {
    return null
  }

  const pathname = candidate.split(/[?#]/, 1)[0]
  if (globalPagePaths.has(pathname)) {
    return null
  }
  return candidate
}

/**
 * 从工作空间内路径提取空间 ID，供全局页面展示来源空间名称。
 * @param path 已校验的 Editor 站内路径
 */
export function parseWorkspaceIdFromPath(path: string | null): number | null {
  const matched = path?.match(/^\/workspaces\/(\d+)(?:\/|$)/)
  if (!matched) return null
  const workspaceId = Number(matched[1])
  return Number.isSafeInteger(workspaceId) && workspaceId > 0 ? workspaceId : null
}

/**
 * 构建携带当前来源的全局页面路由位置。
 * @param name 全局页面路由名称
 * @param currentFullPath 当前 Editor 路径
 */
export function buildGlobalPageLocation(name: 'accountAiSettings' | 'users', currentFullPath: string): RouteLocationRaw {
  const returnTo = resolveGlobalReturnPath(currentFullPath)
  return returnTo ? { name, query: { returnTo } } : { name }
}
