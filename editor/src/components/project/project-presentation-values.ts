/** 文件功能：集中维护项目展示规格的默认值与输入归一化规则。 */

export const DEFAULT_PROJECT_PAGE_WIDTH = 1920
export const DEFAULT_PROJECT_PAGE_HEIGHT = 1080
export const DEFAULT_PROJECT_BASE_FONT_SIZE = '20px'

/**
 * 归一化项目页面尺寸。
 * @param value 原始输入
 * @param fallback 非法输入的回退值
 */
export function normalizeProjectDimension(value: string | number, fallback: number): number {
  const parsedValue = Number(value)
  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return fallback
  }
  return Math.min(8192, Math.max(1, Math.round(parsedValue)))
}

/**
 * 归一化项目基础字号并维持 px 字符串契约。
 * @param value 原始字号
 * @param fallback 非法输入的回退值
 */
export function normalizeProjectBaseFontSize(value: string, fallback: string): string {
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
 * 将项目展示规格限制为指定范围内的整数。
 * @param value 原始输入
 * @param fallback 非法输入的回退值
 * @param min 最小值
 * @param max 最大值
 */
export function normalizeProjectInteger(
  value: string | number,
  fallback: number,
  min: number,
  max: number,
): number {
  const parsedValue = Number(value)
  if (!Number.isFinite(parsedValue)) {
    return fallback
  }
  return Math.min(max, Math.max(min, Math.round(parsedValue)))
}
