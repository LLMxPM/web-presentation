/**
 * 文件用途：计算 Connector 组件（svg.connector-svg）的紧边界导出视口与 PPTX 定位盒模型，避免整块画布容器带入 PPT 造成偏移。
 */

import type { PPTXSvgSerializer } from '@/core/services/pptx/PPTXSvgSerializer'
import type { ElementBox } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'

export interface ResolvedSvgExportPayload {
  data: string
  boxElement: Element
  boxOverride?: ElementBox
}

interface SvgViewBoxRect {
  x: number
  y: number
  width: number
  height: number
}

/**
 * 为 Connector 组件构造紧边界 SVG 导出载荷；非 Connector 或不满足条件时返回 null。
 * @param svg 目标 SVG 根节点
 * @param layout 布局测量与坐标转换器
 * @param svgSerializer SVG 序列化器
 * @returns 紧边界 SVG Data URL 与定位盒信息
 */
export function buildConnectorSvgExportPayload(
  svg: SVGSVGElement,
  layout: PPTXDomConverterLayout,
  svgSerializer: PPTXSvgSerializer,
): ResolvedSvgExportPayload | null {
  if (!svg.classList.contains('connector-svg')) {
    return null
  }

  const path = findConnectorRenderablePath(svg)
  if (!path) {
    return null
  }

  const viewBox = resolveConnectorViewBox(svg, path)
  if (!viewBox) {
    return null
  }
  const viewportElement = svg.parentElement instanceof HTMLElement ? svg.parentElement : svg
  const boxOverride = resolveSvgViewBoxPptxBox(svg, viewBox, viewportElement, layout)
  if (!boxOverride) {
    return null
  }

  return {
    data: svgSerializer.svgToDataUrl(svg, {
      measured: {
        width: viewBox.width,
        height: viewBox.height,
      },
      viewBox,
      removeResponsiveSizing: true,
    }),
    boxElement: viewportElement,
    boxOverride,
  }
}

/**
 * 查找 Connector 中真正可见的连线路径，跳过 defs 里的箭头 marker 图形。
 * @param svg Connector 根 SVG
 * @returns 实际渲染在线条上的 path；未找到时返回 null
 */
function findConnectorRenderablePath(svg: SVGSVGElement): SVGPathElement | null {
  const candidates = Array.from(svg.querySelectorAll('path'))
  return candidates.find((path) => {
    if (!(path instanceof SVGElement) || path.closest('defs')) {
      return false
    }

    const d = (path.getAttribute('d') || '').trim()
    if (!d) {
      return false
    }

    const stroke = path.getAttribute('stroke') || window.getComputedStyle(path).stroke || ''
    return stroke !== '' && stroke !== 'none'
  }) ?? null
}

/**
 * 解析 Connector 的紧边界视口。
 * 说明：优先使用路径几何坐标和线宽/箭头留白，避免竖线或横线在 DOMRect 中退化为 0 宽/0 高；
 * 若宿主环境不支持 getBBox，再退回到页面实际渲染矩形。
 * @param svg Connector 根 SVG
 * @param path 实际连线路径
 * @returns 供 SVG 序列化使用的紧边界 viewBox
 */
function resolveConnectorViewBox(svg: SVGSVGElement, path: SVGPathElement): SvgViewBoxRect | null {
  const geometryViewBox = resolveConnectorGeometryViewBox(path)
  if (geometryViewBox) {
    return geometryViewBox
  }

  return resolveRenderedConnectorViewBox(svg, path)
}

/**
 * 根据 SVG 几何坐标计算 Connector 的导出视口，并为线宽与箭头预留留白。
 * @param path 实际连线路径
 * @returns 几何视口；不可用时返回 null
 */
function resolveConnectorGeometryViewBox(path: SVGPathElement): SvgViewBoxRect | null {
  const getBBox = (path as SVGPathElement & { getBBox?: () => DOMRect | SVGRect }).getBBox
  if (typeof getBBox !== 'function') {
    return null
  }

  let geometryBox: DOMRect | SVGRect
  try {
    geometryBox = getBBox.call(path)
  } catch {
    return null
  }

  const padding = resolveConnectorSvgPadding(path)
  const width = geometryBox.width + padding * 2
  const height = geometryBox.height + padding * 2
  if (width <= 0 || height <= 0) {
    return null
  }

  return {
    x: geometryBox.x - padding,
    y: geometryBox.y - padding,
    width,
    height,
  }
}

/**
 * 根据页面渲染矩形回退计算 Connector 的导出视口。
 * @param svg Connector 根 SVG
 * @param path 实际连线路径
 * @returns 渲染视口；不可用时返回 null
 */
function resolveRenderedConnectorViewBox(svg: SVGSVGElement, path: SVGPathElement): SvgViewBoxRect | null {
  const svgRect = svg.getBoundingClientRect()
  const pathRect = path.getBoundingClientRect()

  if (svgRect.width <= 0 || svgRect.height <= 0 || pathRect.width <= 0 || pathRect.height <= 0) {
    return null
  }

  return {
    x: pathRect.left - svgRect.left,
    y: pathRect.top - svgRect.top,
    width: pathRect.width,
    height: pathRect.height,
  }
}

/**
 * 估算 Connector 导出所需的额外留白，覆盖线宽、圆头和箭头 marker。
 * @param path Connector 路径元素
 * @returns 视口额外留白，单位与 SVG 用户坐标一致
 */
function resolveConnectorSvgPadding(path: SVGPathElement): number {
  const strokeWidth = Number.parseFloat(
    path.getAttribute('stroke-width')
    || window.getComputedStyle(path).strokeWidth
    || '0',
  )
  const normalizedStrokeWidth = Number.isFinite(strokeWidth) && strokeWidth > 0 ? strokeWidth : 1
  const hasMarker = Boolean(path.getAttribute('marker-start') || path.getAttribute('marker-end'))
  return normalizedStrokeWidth * (hasMarker ? 6 : 2)
}

/**
 * 将 SVG 内部视口矩形换算为 PPTX 绝对位置尺寸。
 * @param svg 原始 SVG 根节点
 * @param viewBox 需要导出的内部视口
 * @param viewportElement 视口宿主元素
 * @param layout 布局测量器
 * @returns PPTX 盒模型；不可用时返回 null
 */
function resolveSvgViewBoxPptxBox(
  svg: SVGSVGElement,
  viewBox: SvgViewBoxRect,
  viewportElement: Element,
  layout: PPTXDomConverterLayout,
): ElementBox | null {
  const viewportBox = layout.getPptxBox(viewportElement)
  const viewportPixels = layout.measureElementPixels(viewportElement)
  if (!viewportBox || viewportPixels.width <= 0 || viewportPixels.height <= 0) {
    return null
  }

  const viewportSize = resolveSvgViewportSize(svg, viewportElement, viewportPixels, layout)
  if (!viewportSize || viewportSize.width <= 0 || viewportSize.height <= 0) {
    return null
  }

  const scaleX = viewportBox.w / viewportSize.width
  const scaleY = viewportBox.h / viewportSize.height
  const x = viewportBox.x + viewBox.x * scaleX
  const y = viewportBox.y + viewBox.y * scaleY
  const w = viewBox.width * scaleX
  const h = viewBox.height * scaleY

  return {
    x: layout.roundInch(Math.max(0, x)),
    y: layout.roundInch(Math.max(0, y)),
    w: layout.roundInch(Math.max(0.01, w)),
    h: layout.roundInch(Math.max(0.01, h)),
  }
}

/**
 * 解析 SVG 当前使用的坐标视口尺寸。
 * @param svg SVG 根节点
 * @param viewportElement 视口宿主元素
 * @param measured 当前页面中的渲染尺寸
 * @param layout 布局测量器
 * @returns SVG 用户坐标系下的宽高
 */
function resolveSvgViewportSize(
  svg: SVGSVGElement,
  viewportElement: Element,
  measured: { width: number; height: number },
  layout: PPTXDomConverterLayout,
): { width: number; height: number } | null {
  const liveViewBox = svg.viewBox?.baseVal
  if (liveViewBox && liveViewBox.width > 0 && liveViewBox.height > 0) {
    return {
      width: liveViewBox.width,
      height: liveViewBox.height,
    }
  }

  const rawViewBox = svg.getAttribute('viewBox')
  if (rawViewBox) {
    const values = rawViewBox
      .trim()
      .split(/[\s,]+/)
      .map(value => Number.parseFloat(value))
    if (values.length === 4 && values.every(value => Number.isFinite(value)) && values[2] > 0 && values[3] > 0) {
      return {
        width: values[2],
        height: values[3],
      }
    }
  }

  const layoutSize = resolveElementLayoutSize(viewportElement, layout)
  if (layoutSize) {
    return layoutSize
  }

  if (measured.width > 0 && measured.height > 0) {
    return {
      width: measured.width,
      height: measured.height,
    }
  }

  return null
}

/**
 * 读取元素未受 transform 缩放影响的布局尺寸。
 * 说明：Connector 的 path 坐标由 offsetLeft/offsetWidth 生成，属于布局坐标；
 * 页面预览缩放后 getBoundingClientRect 会变小，不能作为 SVG 内部坐标分母。
 * @param element SVG 视口对应的页面元素
 * @param layout 布局测量器
 * @returns 布局尺寸；不可用时返回 null
 */
function resolveElementLayoutSize(
  element: Element,
  layout: PPTXDomConverterLayout,
): { width: number; height: number } | null {
  if (element instanceof HTMLElement) {
    const style = window.getComputedStyle(element)
    const width = firstPositiveNumber(
      layout.parseCssPixel(style.width),
      element.offsetWidth,
      element.clientWidth,
    )
    const height = firstPositiveNumber(
      layout.parseCssPixel(style.height),
      element.offsetHeight,
      element.clientHeight,
    )
    if (width > 0 && height > 0) {
      return { width, height }
    }
  }

  const style = window.getComputedStyle(element)
  const width = firstPositiveNumber(
    layout.parseCssPixel(style.width),
    Number.parseFloat(element.getAttribute('width') || ''),
  )
  const height = firstPositiveNumber(
    layout.parseCssPixel(style.height),
    Number.parseFloat(element.getAttribute('height') || ''),
  )
  return width > 0 && height > 0 ? { width, height } : null
}

/**
 * 从候选值中选择第一个正数。
 * @param values 候选数字列表
 * @returns 第一个正数，不存在时返回 0
 */
function firstPositiveNumber(...values: number[]): number {
  return values.find(value => Number.isFinite(value) && value > 0) ?? 0
}
