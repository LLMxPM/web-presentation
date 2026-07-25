/**
 * 文件功能：定义资源预览背景模式，供选择器、侧边栏和详情预览共享。
 */
export type AssetPreviewBackground = 'light' | 'dark' | 'checker'

export const ASSET_PREVIEW_BACKGROUND_OPTIONS = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
  { label: '网格', value: 'checker' },
]
