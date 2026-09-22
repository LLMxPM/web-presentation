/**
 * 文件用途：提供组件预览占位配置归一化和样式构造辅助函数。
 */

import type { CSSProperties } from 'vue'

import type {
  RuntimeComponentPreviewAlignment,
  RuntimeComponentPreviewPlacementOptions,
  RuntimeComponentPreviewSizeMode,
} from '@/core/shared/runtime-preview'

export const DEFAULT_PREVIEW_PLACEMENT: Required<RuntimeComponentPreviewPlacementOptions> = {
  width_mode: 'percent',
  width_value: 100,
  height_mode: 'auto',
  height_value: null,
  horizontal_align: 'center',
  vertical_align: 'center',
  padding: 48,
}

/**
 * 归一化组件预览占位配置，确保宿主页可以直接消费。
 * @param rawPlacement 后端或父窗口传入的占位配置
 * @returns 完整占位配置
 */
export function normalizeComponentPreviewPlacement(
  rawPlacement?: RuntimeComponentPreviewPlacementOptions | null,
): Required<RuntimeComponentPreviewPlacementOptions> {
  const widthMode = normalizeSizeMode(rawPlacement?.width_mode, DEFAULT_PREVIEW_PLACEMENT.width_mode)
  const heightMode = normalizeSizeMode(rawPlacement?.height_mode, DEFAULT_PREVIEW_PLACEMENT.height_mode)
  return {
    width_mode: widthMode,
    width_value: normalizeSizeValue(widthMode, rawPlacement?.width_value, DEFAULT_PREVIEW_PLACEMENT.width_value),
    height_mode: heightMode,
    height_value: normalizeSizeValue(heightMode, rawPlacement?.height_value, DEFAULT_PREVIEW_PLACEMENT.height_value),
    horizontal_align: normalizeAlignment(rawPlacement?.horizontal_align, DEFAULT_PREVIEW_PLACEMENT.horizontal_align),
    vertical_align: normalizeAlignment(rawPlacement?.vertical_align, DEFAULT_PREVIEW_PLACEMENT.vertical_align),
    padding: normalizePadding(rawPlacement?.padding, DEFAULT_PREVIEW_PLACEMENT.padding),
  }
}

/**
 * 构建页面内层对齐容器样式。
 * @param placement 完整占位配置
 * @returns 可绑定到页面内层容器的样式
 */
export function buildPlacementContainerStyle(
  placement: Required<RuntimeComponentPreviewPlacementOptions>,
): CSSProperties {
  return {
    padding: `${placement.padding}px`,
    justifyContent: resolveFlexAlignment(placement.horizontal_align),
    alignItems: resolveFlexAlignment(placement.vertical_align),
  }
}

/**
 * 构建目标组件包装层样式。
 * @param placement 完整占位配置
 * @returns 可绑定到组件包装层的样式
 */
export function buildPlacementFrameStyle(
  placement: Required<RuntimeComponentPreviewPlacementOptions>,
): CSSProperties {
  return {
    width: resolveCssSize(placement.width_mode, placement.width_value),
    height: resolveCssSize(placement.height_mode, placement.height_value),
  }
}

function normalizeSizeMode(value: unknown, fallback: RuntimeComponentPreviewSizeMode): RuntimeComponentPreviewSizeMode {
  return value === 'auto' || value === 'percent' || value === 'fixed' ? value : fallback
}

function normalizeAlignment(value: unknown, fallback: RuntimeComponentPreviewAlignment): RuntimeComponentPreviewAlignment {
  return value === 'start' || value === 'center' || value === 'end' ? value : fallback
}

function normalizeSizeValue(
  mode: RuntimeComponentPreviewSizeMode,
  value: unknown,
  fallback: number | null,
): number | null {
  if (mode === 'auto') {
    return null
  }
  const parsedValue = Number(value)
  const resolvedValue = Number.isFinite(parsedValue) && parsedValue > 0 ? Math.round(parsedValue) : fallback
  if (resolvedValue === null) {
    return null
  }
  return mode === 'percent'
    ? Math.min(100, Math.max(1, resolvedValue))
    : Math.min(8192, Math.max(1, resolvedValue))
}

function normalizePadding(value: unknown, fallback: number): number {
  const parsedValue = Number(value)
  return Number.isFinite(parsedValue) && parsedValue >= 0
    ? Math.min(512, Math.round(parsedValue))
    : fallback
}

function resolveCssSize(mode: RuntimeComponentPreviewSizeMode, value: number | null): string {
  if (mode === 'auto' || value === null) {
    return 'auto'
  }
  return mode === 'percent' ? `${value}%` : `${value}px`
}

function resolveFlexAlignment(alignment: RuntimeComponentPreviewAlignment): string {
  if (alignment === 'start') {
    return 'flex-start'
  }
  if (alignment === 'end') {
    return 'flex-end'
  }
  return 'center'
}
