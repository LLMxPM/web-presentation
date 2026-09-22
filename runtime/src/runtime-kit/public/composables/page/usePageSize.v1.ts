/**
 * 文件用途：暴露 Runtime 页面尺寸读取与标准页面画布样式构造能力。
 */

import { computed, type CSSProperties } from 'vue'

import { appPageConfig, DEFAULT_PAGE_CONFIG, type RuntimePageConfig } from '@/core/utils/config'

export interface RuntimeKitPageSize {
  width: number
  height: number
  aspectRatio: number
  pageStyle: CSSProperties
}

/**
 * 构造标准页面内容画布样式。
 * @param pageSize 页面宽高；缺省时使用 Runtime 默认页面尺寸
 * @returns 可绑定到页面根容器的样式对象
 */
export function buildPageCanvasStyle(pageSize: Partial<RuntimePageConfig> = {}): CSSProperties {
  const width = normalizePageDimension(pageSize.width, DEFAULT_PAGE_CONFIG.width)
  const height = normalizePageDimension(pageSize.height, DEFAULT_PAGE_CONFIG.height)
  return {
    width: `${width}px`,
    height: `${height}px`,
    position: 'relative',
    overflow: 'hidden',
  }
}

/**
 * 读取当前 Runtime 生效的页面尺寸，并返回页面画布样式。
 * @returns 页面宽高、宽高比和标准画布样式
 */
export function usePageSize() {
  const width = computed(() => normalizePageDimension(appPageConfig.value.width, DEFAULT_PAGE_CONFIG.width))
  const height = computed(() => normalizePageDimension(appPageConfig.value.height, DEFAULT_PAGE_CONFIG.height))
  const aspectRatio = computed(() => width.value / height.value)
  const pageStyle = computed(() => buildPageCanvasStyle({ width: width.value, height: height.value }))

  return {
    width,
    height,
    aspectRatio,
    pageStyle,
  }
}

/**
 * 将页面尺寸归一为正整数。
 * @param value 原始尺寸
 * @param fallback 回退尺寸
 * @returns 合法页面尺寸
 */
function normalizePageDimension(value: unknown, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return Math.round(parsed)
}
