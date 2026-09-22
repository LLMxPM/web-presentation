/**
 * 文件用途：提供 Runtime Kit 渲染组件共享的渲染区域样式参数与构建函数。
 */

import { computed, type ComputedRef, type CSSProperties } from 'vue'

export type ViewerSizeValue = string | number

export interface ViewerSurfaceProps {
  /** 渲染区域宽度 */
  width?: ViewerSizeValue
  /** 渲染区域高度 */
  height?: ViewerSizeValue
  /** 渲染区域最小高度 */
  minHeight?: ViewerSizeValue
  /** 渲染区域背景颜色 */
  backgroundColor?: string
  /** 是否显示渲染区域边框 */
  showBorder?: boolean
  /** 渲染区域边框颜色 */
  borderColor?: string
  /** 渲染区域边框宽度 */
  borderWidth?: ViewerSizeValue
  /** 渲染区域边框样式 */
  borderStyle?: CSSProperties['borderStyle']
  /** 渲染区域圆角 */
  borderRadius?: ViewerSizeValue
  /** 渲染区域内边距 */
  padding?: ViewerSizeValue
}

/**
 * 将数字尺寸规范化为 px，字符串尺寸保持原样。
 *
 * @param value 尺寸输入值
 * @returns 可用于 CSSProperties 的尺寸值
 */
export function normalizeViewerSize(value?: ViewerSizeValue): string | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  return typeof value === 'number' ? `${value}px` : value
}

/**
 * 根据统一渲染区域参数构建根容器样式。
 *
 * @param props 渲染组件传入的统一区域参数
 * @returns Vue 内联样式对象
 */
export function buildViewerSurfaceStyle(props: ViewerSurfaceProps): CSSProperties {
  const width = normalizeViewerSize(props.width)
  const height = normalizeViewerSize(props.height)
  const minHeight = normalizeViewerSize(props.minHeight)
  const borderRadius = normalizeViewerSize(props.borderRadius)
  const padding = normalizeViewerSize(props.padding)
  const borderWidth = normalizeViewerSize(props.borderWidth)

  const style: CSSProperties = {
    ...(width ? { width } : {}),
    ...(height ? { height } : {}),
    ...(minHeight ? { minHeight } : {}),
    ...(props.backgroundColor ? { backgroundColor: props.backgroundColor } : {}),
    ...(borderRadius ? { borderRadius } : {}),
    ...(padding ? { padding } : {}),
  }
  if (props.showBorder === true) {
    style.border = `${borderWidth || '1px'} ${props.borderStyle || 'solid'} ${props.borderColor || '#e5e7eb'}`
  }

  return style
}

/**
 * 响应式构建渲染区域样式，供 Vue SFC 直接绑定。
 *
 * @param props 渲染组件 props
 * @returns 响应式渲染区域样式
 */
export function useViewerSurfaceStyle(props: ViewerSurfaceProps): ComputedRef<CSSProperties> {
  return computed(() => buildViewerSurfaceStyle(props))
}
