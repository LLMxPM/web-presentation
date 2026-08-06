/**
 * 文件功能：定义主题内置字体预设，统一编辑器中的选项、展示文案和 CSS 回退语义。
 */

export type ThemeFontPreset = 'platform-sans' | 'platform-mono' | 'system-ui' | 'monospace'

const PRESET_LABELS: Record<ThemeFontPreset, string> = {
  'platform-sans': '平台默认（跨端一致）',
  'platform-mono': '平台等宽（跨端一致）',
  'system-ui': '跟随系统（可能不一致）',
  monospace: '系统等宽（可能不一致）',
}

/** 判断接口返回的字体 label 是否为已知内置预设。 */
export function isThemeFontPreset(value: string | null | undefined): value is ThemeFontPreset {
  return Boolean(value && value in PRESET_LABELS)
}

/** 把持久化 token 转换为面向用户的字体名称。 */
export function formatThemeFontLabel(value: string | null | undefined): string {
  if (isThemeFontPreset(value)) {
    return PRESET_LABELS[value]
  }
  return String(value || '')
}

/** 为 Editor 卡片提供内置预设的近似 CSS 回退；真实页面由 Runtime 加载固定字体文件。 */
export function resolveThemeFontPreviewFallback(value: string): string {
  if (value === 'platform-sans') return 'sans-serif'
  if (value === 'platform-mono') return 'monospace'
  return value
}
