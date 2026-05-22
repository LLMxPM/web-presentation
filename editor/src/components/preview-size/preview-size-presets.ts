/**
 * 文件功能：提供用户级预设尺寸的前端默认值、归一化和选项匹配工具。
 */
import type { PreviewSizePreset } from '@/types/api'

export const DEFAULT_PREVIEW_SIZE_PRESETS: PreviewSizePreset[] = [
  { name: '桌面 16:9', width: 1920, height: 1080, base_font_size: '20px', icon_default_stroke_width: 2 },
  { name: '桌面 16:9 小屏', width: 1600, height: 900, base_font_size: '20px', icon_default_stroke_width: 2 },
  { name: '笔记本', width: 1366, height: 768, base_font_size: '20px', icon_default_stroke_width: 2 },
  { name: '手机竖屏', width: 1080, height: 1920, base_font_size: '28px', icon_default_stroke_width: 3 },
  { name: '手机竖屏小屏', width: 750, height: 1334, base_font_size: '24px', icon_default_stroke_width: 3 },
]

/**
 * 将尺寸归一化为安全整数。
 * @param value 原始尺寸
 * @param fallback 非法时的回退值
 */
export function normalizePreviewSizeDimension(value: unknown, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return Math.min(8192, Math.max(1, Math.round(parsed)))
}

/**
 * 归一化预设里的基础字号。
 * @param value 原始字号
 * @param fallback 非法时的回退字号
 */
export function normalizePreviewBaseFontSize(value: unknown, fallback: string): string {
  const normalizedValue = String(value || '').trim().toLowerCase()
  const match = normalizedValue.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const parsedValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(parsedValue) || parsedValue < 1 || parsedValue > 200) {
    return fallback
  }
  return `${parsedValue}px`
}

/**
 * 将预设里的整数规格限制在指定范围。
 * @param value 原始值
 * @param fallback 非法时的回退值
 * @param min 最小值
 * @param max 最大值
 */
export function normalizePreviewIntegerSpec(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return fallback
  }
  return Math.min(max, Math.max(min, Math.round(parsed)))
}

/**
 * 归一化用户预设尺寸，过滤掉无效项。
 * @param value 原始预设列表
 */
export function normalizePreviewSizePresets(value: unknown): PreviewSizePreset[] {
  if (!Array.isArray(value)) {
    return DEFAULT_PREVIEW_SIZE_PRESETS.map(item => ({ ...item }))
  }

  return value
    .map((item): PreviewSizePreset | null => {
      if (!item || typeof item !== 'object') {
        return null
      }
      const source = item as Partial<PreviewSizePreset>
      const name = String(source.name || '').trim()
      if (!name) {
        return null
      }
      return {
        name,
        width: normalizePreviewSizeDimension(source.width, 1920),
        height: normalizePreviewSizeDimension(source.height, 1080),
        base_font_size: normalizePreviewBaseFontSize(source.base_font_size, '20px'),
        icon_default_stroke_width: normalizePreviewIntegerSpec(source.icon_default_stroke_width, 2, 1, 64),
      }
    })
    .filter((item): item is PreviewSizePreset => Boolean(item))
}

/**
 * 为预设生成仅用于前端渲染和选择的稳定 key。
 * @param preset 预设尺寸
 * @param index 当前列表索引
 */
export function buildPreviewSizePresetKey(preset: PreviewSizePreset, index: number): string {
  return [
    index,
    preset.name,
    `${preset.width}x${preset.height}`,
    preset.base_font_size || '20px',
    preset.icon_default_stroke_width ?? 2,
  ].join(':')
}

/**
 * 查找与当前宽高完全一致的预设索引。
 */
export function findMatchedPreviewSizePresetIndex(
  presets: PreviewSizePreset[],
  width: number,
  height: number,
  baseFontSize?: string,
  iconDefaultStrokeWidth?: number,
): number {
  return presets.findIndex((item) => {
    if (item.width !== width || item.height !== height) {
      return false
    }
    if (baseFontSize === undefined && iconDefaultStrokeWidth === undefined) {
      return true
    }
    return normalizePreviewBaseFontSize(item.base_font_size, '20px') === normalizePreviewBaseFontSize(baseFontSize, '20px')
      && normalizePreviewIntegerSpec(item.icon_default_stroke_width, 2, 1, 64) === normalizePreviewIntegerSpec(iconDefaultStrokeWidth, 2, 1, 64)
  })
}
