/**
 * 文件功能：提供组件预览页面与组件占位选项的默认值、归一化、克隆与差异判断工具。
 */

import type {
  ComponentPreviewAlignment,
  ComponentPreviewOptions,
  ComponentPreviewSizeMode,
} from '@/types/api'

export const DEFAULT_COMPONENT_PREVIEW_OPTIONS: ComponentPreviewOptions = {
  page: {
    width: 1920,
    height: 1080,
    base_font_size: '20px',
    icon_default_stroke_width: 2,
    theme_key: null,
    theme_config_yaml: null,
  },
  placement: {
    width_mode: 'percent',
    width_value: 100,
    height_mode: 'auto',
    height_value: null,
    horizontal_align: 'center',
    vertical_align: 'center',
    padding: 48,
  },
}

/**
 * 创建组件预览默认选项，避免调用方共享同一对象引用。
 * @param defaultThemeKey 工作空间默认主题 key
 * @returns 默认预览选项
 */
export function buildDefaultComponentPreviewOptions(defaultThemeKey: string | null = null): ComponentPreviewOptions {
  const options = cloneComponentPreviewOptions(DEFAULT_COMPONENT_PREVIEW_OPTIONS)
  options.page.theme_key = defaultThemeKey
  return options
}

/**
 * 深拷贝组件预览选项。
 * @param value 原始选项
 * @returns 拷贝后的选项
 */
export function cloneComponentPreviewOptions(value: ComponentPreviewOptions): ComponentPreviewOptions {
  return JSON.parse(JSON.stringify(value)) as ComponentPreviewOptions
}

/**
 * 将任意输入归一化为完整组件预览选项。
 * @param value 原始输入
 * @param defaultThemeKey 工作空间默认主题 key
 * @returns 可直接编辑和提交的预览选项
 */
export function normalizeComponentPreviewOptions(
  value: unknown,
  defaultThemeKey: string | null = null,
): ComponentPreviewOptions {
  const fallback = buildDefaultComponentPreviewOptions(defaultThemeKey)
  const source = isPlainObject(value) ? value as Record<string, any> : {}
  const pageSource = isPlainObject(source.page) ? source.page as Record<string, any> : {}
  const placementSource = isPlainObject(source.placement) ? source.placement as Record<string, any> : {}
  const widthMode = normalizeSizeMode(placementSource.width_mode, fallback.placement.width_mode)
  const heightMode = normalizeSizeMode(placementSource.height_mode, fallback.placement.height_mode)

  return {
    page: {
      width: normalizePositiveDimension(pageSource.width, fallback.page.width),
      height: normalizePositiveDimension(pageSource.height, fallback.page.height),
      base_font_size: normalizeBaseFontSize(pageSource.base_font_size, fallback.page.base_font_size),
      icon_default_stroke_width: normalizeIntegerWithinRange(
        pageSource.icon_default_stroke_width,
        fallback.page.icon_default_stroke_width,
        1,
        64,
      ),
      theme_key: normalizeNullableText(pageSource.theme_key, fallback.page.theme_key),
      theme_config_yaml: normalizeNullableText(pageSource.theme_config_yaml, fallback.page.theme_config_yaml),
    },
    placement: {
      width_mode: widthMode,
      width_value: normalizePlacementSizeValue(widthMode, placementSource.width_value, fallback.placement.width_value),
      height_mode: heightMode,
      height_value: normalizePlacementSizeValue(heightMode, placementSource.height_value, fallback.placement.height_value),
      horizontal_align: normalizeAlignment(placementSource.horizontal_align, fallback.placement.horizontal_align),
      vertical_align: normalizeAlignment(placementSource.vertical_align, fallback.placement.vertical_align),
      padding: normalizePadding(placementSource.padding, fallback.placement.padding),
    },
  }
}

/**
 * 判断两份页面配置是否一致，用于识别是否需要重建预览 artifact。
 * @param left 左侧配置
 * @param right 右侧配置
 * @returns 页面配置是否一致
 */
export function isSamePreviewPageOptions(
  left: ComponentPreviewOptions['page'],
  right: ComponentPreviewOptions['page'],
) {
  return (
    left.width === right.width
    && left.height === right.height
    && left.base_font_size === right.base_font_size
    && left.icon_default_stroke_width === right.icon_default_stroke_width
    && left.theme_key === right.theme_key
    && normalizeComparableText(left.theme_config_yaml) === normalizeComparableText(right.theme_config_yaml)
  )
}

/**
 * 将数值归一化到合法的正整数范围。
 * @param rawValue 原始输入
 * @param fallbackValue 回退值
 * @returns 1 到 8192 之间的整数
 */
export function normalizePositiveDimension(rawValue: unknown, fallbackValue: number): number {
  const parsedValue = Number(rawValue)
  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return fallbackValue
  }
  return Math.min(8192, Math.max(1, Math.round(parsedValue)))
}

/**
 * 将基础字号归一化为 px 字符串。
 * @param rawValue 原始字号
 * @param fallbackValue 回退字号
 * @returns 规范化字号
 */
export function normalizeBaseFontSize(rawValue: unknown, fallbackValue: string): string {
  const normalizedValue = String(rawValue || '').trim().toLowerCase()
  const match = normalizedValue.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallbackValue
  }
  const parsedValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(parsedValue) || parsedValue < 1 || parsedValue > 200) {
    return fallbackValue
  }
  return `${parsedValue}px`
}

/**
 * 将整数归一到指定闭区间。
 * @param rawValue 原始数值
 * @param fallbackValue 回退值
 * @param min 最小值
 * @param max 最大值
 * @returns 合法整数
 */
export function normalizeIntegerWithinRange(rawValue: unknown, fallbackValue: number, min: number, max: number): number {
  const parsedValue = Number(rawValue)
  if (!Number.isFinite(parsedValue)) {
    return fallbackValue
  }
  return Math.min(max, Math.max(min, Math.round(parsedValue)))
}

/**
 * 将 padding 归一化到非负整数范围。
 * @param rawValue 原始输入
 * @param fallbackValue 回退值
 * @returns 0 到 512 之间的整数
 */
export function normalizePadding(rawValue: unknown, fallbackValue: number): number {
  const parsedValue = Number(rawValue)
  if (!Number.isFinite(parsedValue) || parsedValue < 0) {
    return fallbackValue
  }
  return Math.min(512, Math.max(0, Math.round(parsedValue)))
}

/**
 * 将可空文本归一化为字符串或 null。
 * @param rawValue 原始输入
 * @param fallbackValue 回退值
 * @returns 归一化后的可空文本
 */
export function normalizeNullableText(rawValue: unknown, fallbackValue: string | null): string | null {
  const normalizedValue = String(rawValue || '').trim()
  return normalizedValue || fallbackValue
}

/**
 * 将颜色文本归一化为非空字符串。
 * @param rawValue 原始输入
 * @param fallbackValue 回退值
 * @returns 可直接写入样式的颜色字符串
 */
export function normalizeColor(rawValue: unknown, fallbackValue: string): string {
  const normalizedValue = String(rawValue || '').trim()
  return normalizedValue || fallbackValue
}

function normalizeSizeMode(value: unknown, fallback: ComponentPreviewSizeMode): ComponentPreviewSizeMode {
  return value === 'auto' || value === 'percent' || value === 'fixed' ? value : fallback
}

function normalizeAlignment(value: unknown, fallback: ComponentPreviewAlignment): ComponentPreviewAlignment {
  return value === 'start' || value === 'center' || value === 'end' ? value : fallback
}

function normalizePlacementSizeValue(
  mode: ComponentPreviewSizeMode,
  rawValue: unknown,
  fallbackValue: number | null,
): number | null {
  if (mode === 'auto') {
    return null
  }
  const parsedValue = Number(rawValue)
  const resolvedValue = Number.isFinite(parsedValue) && parsedValue > 0 ? Math.round(parsedValue) : fallbackValue
  if (resolvedValue === null) {
    return null
  }
  return mode === 'percent'
    ? Math.min(100, Math.max(1, resolvedValue))
    : Math.min(8192, Math.max(1, resolvedValue))
}

function normalizeComparableText(value: string | null | undefined) {
  return String(value || '').trim()
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
