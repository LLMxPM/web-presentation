/**
 * 文件用途：在无真实排版引擎的环境（如 JSDOM 单元测试）下，按父级 Flexbox 规则推断子项坐标回退值。
 */

import { getComputedStyle as getOwnerComputedStyle, isHTMLElement } from '@/core/services/pptx/dom/PPTXDomEnvironment'

import type { ElementPadding, MeasuredElementBox } from '@/core/services/pptx/PPTXDomConverter.types'

export interface FlexFallbackMeasureHost {
  measureElementRawPixels: (element: Element) => MeasuredElementBox
  measureElementPixels: (element: Element) => MeasuredElementBox
  isRawVisibleElement: (element: Element) => boolean
  resolveLayoutDisplay: (element: HTMLElement, style: CSSStyleDeclaration) => 'flex' | 'grid' | ''
  resolveFlexDirection: (element: HTMLElement, style: CSSStyleDeclaration) => string
  resolveElementPaddingPixels: (element: HTMLElement, style: CSSStyleDeclaration) => ElementPadding
  cssPxToMeasuredPx: (value: number) => number
  resolveClassJustifyContent: (element: HTMLElement) => string
  resolveClassAlignItems: (element: HTMLElement) => string
}

/**
 * Flexbox 布局回退估算器。
 */
export class JsdomFlexFallback {
  /**
   * 在测量环境没有执行 flex 布局时，按父级 flex 规则推断直接子项位置。
   * @param host 测量与样式宿主
   * @param element 源元素
   * @param rawBox 原始测量盒
   * @returns 修正后的测量盒
   */
  applyFlexItemLayoutFallback(
    host: FlexFallbackMeasureHost,
    element: Element,
    rawBox: MeasuredElementBox,
  ): MeasuredElementBox {
    if (!(isHTMLElement(element)) || !element.parentElement) {
      return rawBox
    }
    if (this.isOutOfFlowPositionedElement(element)) {
      return rawBox
    }

    const parent = element.parentElement
    const parentStyle = getOwnerComputedStyle(parent)
    if (host.resolveLayoutDisplay(parent, parentStyle) !== 'flex') {
      return rawBox
    }

    const items = Array.from(parent.children).filter((child): child is HTMLElement => {
      return isHTMLElement(child) &&
        !this.isOutOfFlowPositionedElement(child) &&
        host.isRawVisibleElement(child)
    })
    const itemIndex = items.indexOf(element)
    if (itemIndex < 0) {
      return rawBox
    }

    const parentRawBox = host.measureElementRawPixels(parent)
    const parentBox = host.measureElementPixels(parent)
    const padding = host.resolveElementPaddingPixels(parent, parentStyle)
    const paddingLeft = host.cssPxToMeasuredPx(padding.left)
    const paddingRight = host.cssPxToMeasuredPx(padding.right)
    const paddingTop = host.cssPxToMeasuredPx(padding.top)
    const paddingBottom = host.cssPxToMeasuredPx(padding.bottom)
    const contentLeft = parentBox.left + paddingLeft
    const contentTop = parentBox.top + paddingTop
    const contentWidth = Math.max(0, parentBox.width - paddingLeft - paddingRight)
    const contentHeight = Math.max(0, parentBox.height - paddingTop - paddingBottom)
    const isColumn = host.resolveFlexDirection(parent, parentStyle).startsWith('column')
    const itemBoxes = items.map(item => host.measureElementRawPixels(item))
    const nextBox = { ...rawBox }

    if (isColumn) {
      const expectedTop = this.resolveFlexMainCoordinate(
        contentTop,
        contentHeight,
        itemBoxes.map(box => box.height),
        itemIndex,
        host.resolveClassJustifyContent(parent) || parentStyle.justifyContent,
      )
      const expectedLeft = this.resolveFlexCrossCoordinate(
        contentLeft,
        contentWidth,
        rawBox.width,
        host.resolveClassAlignItems(parent) || parentStyle.alignItems,
      )
      if (this.shouldUseFlexCoordinateFallback(rawBox.top, parentRawBox.top, expectedTop, parentBox.top)) {
        nextBox.top = expectedTop
      }
      if (this.shouldUseFlexCoordinateFallback(rawBox.left, parentRawBox.left, expectedLeft, parentBox.left)) {
        nextBox.left = expectedLeft
      }
      return nextBox
    }

    const expectedLeft = this.resolveFlexMainCoordinate(
      contentLeft,
      contentWidth,
      itemBoxes.map(box => box.width),
      itemIndex,
      host.resolveClassJustifyContent(parent) || parentStyle.justifyContent,
    )
    const expectedTop = this.resolveFlexCrossCoordinate(
      contentTop,
      contentHeight,
      rawBox.height,
      host.resolveClassAlignItems(parent) || parentStyle.alignItems,
    )
    if (this.shouldUseFlexCoordinateFallback(rawBox.left, parentRawBox.left, expectedLeft, parentBox.left)) {
      nextBox.left = expectedLeft
    }
    if (this.shouldUseFlexCoordinateFallback(rawBox.top, parentRawBox.top, expectedTop, parentBox.top)) {
      nextBox.top = expectedTop
    }
    return nextBox
  }

  /**
   * 按 flex 主轴分布计算子项坐标。
   */
  resolveFlexMainCoordinate(
    contentStart: number,
    contentSize: number,
    itemSizes: number[],
    itemIndex: number,
    justifyContent: string,
  ): number {
    const normalizedJustify = String(justifyContent || '').trim()
    const totalItemSize = itemSizes.reduce((total, size) => total + size, 0)
    const previousSize = itemSizes.slice(0, itemIndex).reduce((total, size) => total + size, 0)
    const freeSize = Math.max(0, contentSize - totalItemSize)
    const itemCount = itemSizes.length

    if (normalizedJustify === 'center') {
      return contentStart + freeSize / 2 + previousSize
    }
    if (normalizedJustify === 'flex-end' || normalizedJustify === 'end') {
      return contentStart + freeSize + previousSize
    }
    if (normalizedJustify === 'space-between' && itemCount > 1) {
      return contentStart + previousSize + (freeSize / (itemCount - 1)) * itemIndex
    }
    if (normalizedJustify === 'space-around' && itemCount > 0) {
      const distributedSize = freeSize / itemCount
      return contentStart + distributedSize / 2 + previousSize + distributedSize * itemIndex
    }
    if (normalizedJustify === 'space-evenly' && itemCount > 0) {
      const distributedSize = freeSize / (itemCount + 1)
      return contentStart + distributedSize + previousSize + distributedSize * itemIndex
    }
    return contentStart + previousSize
  }

  /**
   * 按 flex 交叉轴对齐计算子项坐标。
   */
  resolveFlexCrossCoordinate(
    contentStart: number,
    contentSize: number,
    itemSize: number,
    alignItems: string,
  ): number {
    const normalizedAlign = String(alignItems || '').trim()
    const freeSize = Math.max(0, contentSize - itemSize)
    if (normalizedAlign === 'center') {
      return contentStart + freeSize / 2
    }
    if (normalizedAlign === 'flex-end' || normalizedAlign === 'end') {
      return contentStart + freeSize
    }
    return contentStart
  }

  /**
   * 判断是否应使用 flex 推断坐标，避免覆盖真实浏览器布局。
   */
  shouldUseFlexCoordinateFallback(
    rawCoordinate: number,
    rawParentCoordinate: number,
    expectedCoordinate: number,
    parentCoordinate: number,
  ): boolean {
    if (Math.abs(rawCoordinate - expectedCoordinate) <= 1) {
      return false
    }

    const rawRelativeCoordinate = rawCoordinate - rawParentCoordinate
    const expectedRelativeCoordinate = expectedCoordinate - parentCoordinate
    return expectedRelativeCoordinate > 1 && Math.abs(rawRelativeCoordinate) <= 1
  }

  /**
   * 判断元素是否脱离普通文档流，避免 flex 兜底错误重算绝对定位坐标。
   */
  private isOutOfFlowPositionedElement(element: HTMLElement): boolean {
    const position = getOwnerComputedStyle(element).position
    return position === 'absolute' || position === 'fixed'
  }
}
