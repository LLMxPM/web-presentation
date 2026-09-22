/**
 * 文件用途：管理演讲模式观众窗口的打开与窗口参数。
 */

import {
  buildPresenterRouteUrl,
  normalizePresenterRoutePath,
  PRESENTER_DISPLAY_ROUTE,
} from '@/runtime-shell/presenter/presenter-url'

export interface PresenterDisplayWindowBounds {
  left: number
  top: number
  width: number
  height: number
}

interface PresenterScreenBoundsSource {
  availLeft?: number
  availTop?: number
  availWidth?: number
  availHeight?: number
}

/**
 * 打开观众窗口；保留旧入口名称以兼容原调用方。
 * @param channelId 通信频道 ID
 * @param currentPath 当前演讲页路径
 * @returns 新窗口引用；被浏览器拦截时为空
 */
export function openPendingPresenterDisplayWindow(channelId: string, currentPath: string): Window | null {
  return openPresenterDisplayWindow(channelId, currentPath)
}

/**
 * 打开观众页。
 * 调用方只负责同步打开窗口以避免弹窗拦截；屏幕授权和全屏选择由观众窗口内完成。
 * @param channelId 通信频道 ID
 * @param currentPath 当前演讲页路径
 * @returns 新窗口引用；被浏览器拦截时为空
 */
export function openPresenterDisplayWindow(channelId: string, currentPath: string): Window | null {
  const fallbackBounds = readCurrentScreenBounds()
  const windowRef = window.open(
    buildPresenterDisplayUrl(channelId, currentPath),
    buildPresenterDisplayWindowName(channelId),
    buildPresenterDisplayWindowFeatures(fallbackBounds),
  )
  expandPresenterDisplayWindow(windowRef, fallbackBounds)
  return windowRef
}

/**
 * 构建观众页 URL。
 * @param channelId 通信频道 ID
 * @param currentPath 当前演讲页路径
 * @returns 观众页完整 URL
 */
export function buildPresenterDisplayUrl(channelId: string, currentPath: string): string {
  return buildPresenterRouteUrl(PRESENTER_DISPLAY_ROUTE, channelId, normalizePresenterRoutePath(currentPath))
}

/**
 * 构建观众窗口名称。
 * @param channelId 通信频道 ID
 * @returns window.open 目标窗口名
 */
function buildPresenterDisplayWindowName(channelId: string): string {
  return `web-presentation-presenter-display-${channelId}`
}

/**
 * 构建观众窗口特性，尽量让新窗口占满当前屏幕。
 * @param bounds 目标屏幕可用区域；缺省时使用当前屏幕可用区域
 * @returns window.open 第三个参数
 */
export function buildPresenterDisplayWindowFeatures(bounds: PresenterDisplayWindowBounds = readCurrentScreenBounds()): string {
  return [
    'popup=yes',
    'fullscreen=yes',
    `left=${Math.round(bounds.left)}`,
    `top=${Math.round(bounds.top)}`,
    `width=${Math.max(320, Math.round(bounds.width))}`,
    `height=${Math.max(240, Math.round(bounds.height))}`,
  ].join(',')
}

/**
 * 尝试把观众窗口调整到屏幕尺寸。
 * @param windowRef 观众窗口引用
 * @param bounds 目标屏幕可用区域
 */
function expandPresenterDisplayWindow(windowRef: Window | null, bounds: PresenterDisplayWindowBounds): void {
  if (!windowRef) {
    return
  }
  try {
    windowRef.moveTo?.(bounds.left, bounds.top)
    windowRef.resizeTo?.(bounds.width, bounds.height)
    windowRef.focus?.()
  } catch {
    // 浏览器可能禁止脚本调整窗口尺寸，保留 window.open 特性和页面内全屏按钮兜底。
  }
}

/**
 * 读取当前屏幕可用区域。
 * @returns 当前屏幕窗口参数
 */
function readCurrentScreenBounds(): PresenterDisplayWindowBounds {
  const screenLike = window.screen as Screen & PresenterScreenBoundsSource
  return {
    left: normalizeScreenMetric(screenLike.availLeft, 0),
    top: normalizeScreenMetric(screenLike.availTop, 0),
    width: normalizeScreenMetric(screenLike.availWidth, window.innerWidth || 1280),
    height: normalizeScreenMetric(screenLike.availHeight, window.innerHeight || 720),
  }
}

function normalizeScreenMetric(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}
