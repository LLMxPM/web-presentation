/**
 * 文件用途：构建 Runtime 演讲模式内部窗口 URL 与窗口通信频道标识。
 */

export const PRESENTER_CONSOLE_ROUTE = '/__presenter'
export const PRESENTER_DISPLAY_ROUTE = '/__presenter-display'

export interface PresenterWindowUrls {
  consoleUrl: string
  displayUrl: string
  channelId: string
}

/**
 * 创建演讲模式频道标识。
 * @returns 可用于 BroadcastChannel 的短生命周期频道 ID
 */
export function createPresenterChannelId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `presenter-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * 基于当前页面地址构建演讲者控制台和观众窗口 URL。
 * @param currentPath 当前 Runtime 路由路径
 * @returns 两个内部窗口地址和通信频道 ID
 */
export function buildPresenterWindowUrls(currentPath: string): PresenterWindowUrls {
  const channelId = createPresenterChannelId()
  return {
    channelId,
    consoleUrl: buildPresenterRouteUrl(PRESENTER_CONSOLE_ROUTE, channelId, currentPath),
    displayUrl: buildPresenterRouteUrl(PRESENTER_DISPLAY_ROUTE, channelId, currentPath),
  }
}

/**
 * 构建指定演讲模式内部路由的完整 URL，保留当前 preview token 与其他 search 参数。
 * @param routePath 内部路由路径
 * @param channelId 通信频道 ID
 * @param currentPath 初始页面路径
 * @returns 可由 window.open 打开的完整 URL
 */
export function buildPresenterRouteUrl(routePath: string, channelId: string, currentPath: string): string {
  const url = new URL(window.location.href)
  const params = new URLSearchParams({
    channel: channelId,
    runtimeMode: routePath === PRESENTER_DISPLAY_ROUTE ? 'display' : 'presenter',
  })
  url.hash = `${normalizePresenterRoutePath(currentPath)}?${params.toString()}`
  return url.toString()
}

/**
 * 归一化演讲模式初始页路径。
 * @param path 原始路径
 * @returns 以 / 开头的 Runtime 路由路径
 */
export function normalizePresenterRoutePath(path: string): string {
  const normalized = String(path || '').trim()
  if (!normalized || normalized === '/') {
    return '/'
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`
}
