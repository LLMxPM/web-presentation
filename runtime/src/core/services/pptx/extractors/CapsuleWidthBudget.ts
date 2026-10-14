/** 文件用途：用统一的 PPT 英寸几何计算胶囊文字区内缩和总扩宽上限，避免重复应用预览缩放。 */
import type { ElementBox } from '../PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '../PPTXDomConverterLayout'

/** 将 CSS 圆角只换算一次，再按 PPT 原生 roundRect 文字区公式计算左右内缩总和。 */
export function resolveCapsuleNativeInsetGuard(
  layout: PPTXDomConverterLayout,
  element: HTMLElement,
  style: CSSStyleDeclaration,
  box: ElementBox,
): number {
  const radiusPx = layout.resolveElementCornerRadiusPx(element, style)
  const maxRadiusIn = Math.min(box.w, box.h) / 2
  const radiusIn = radiusPx > 0 ? layout.measuredPxToInch(layout.cssPxToMeasuredPx(radiusPx)) : maxRadiusIn
  return layout.roundInch(2 * 0.29289 * Math.min(radiusIn, maxRadiusIn))
}

/** 给胶囊所有补偿需求统一封顶；内容复杂度、标点和字距均不能突破自身宽度的 12%。 */
export function resolveCapsuleWidthGuardLimit(box: ElementBox, nativeInset: number): number {
  return Math.max(
    Math.min(nativeInset, box.w * 0.11),
    Math.min(box.w * 0.12, Math.max(box.h * 0.38, 0.04)),
  )
}
