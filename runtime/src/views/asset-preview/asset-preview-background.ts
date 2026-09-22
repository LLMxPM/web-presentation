/**
 * 文件用途：归一化资源预览背景参数，并解析 Runtime 渲染器使用的背景颜色。
 */
export type RuntimeAssetPreviewBackground = 'light' | 'dark' | 'checker'

/**
 * 将路由查询参数归一化为受支持的资源预览背景模式。
 * @param value 路由查询参数原始值
 */
export function normalizeAssetPreviewBackground(value: unknown): RuntimeAssetPreviewBackground {
  const normalized = Array.isArray(value) ? value[0] : value
  if (normalized === 'light' || normalized === 'dark' || normalized === 'checker') {
    return normalized
  }
  return 'light'
}

/**
 * 返回 Runtime 资源渲染器应使用的背景颜色；棋盘格由宿主页绘制。
 * @param background 当前背景模式
 */
export function resolveAssetPreviewRendererBackground(background: RuntimeAssetPreviewBackground): string {
  if (background === 'dark') {
    return '#0f172a'
  }
  if (background === 'checker') {
    return 'transparent'
  }
  return '#ffffff'
}
