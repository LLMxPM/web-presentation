/**
 * 文件用途：负责 PPTX 文本框宽度防折行保护（WidthGuard）、向祖先容器剩余宽度扩展以及文本框内边距（margin）换算。
 */

import { getComputedStyle as getOwnerComputedStyle, isHTMLElement } from '@/core/services/pptx/dom/PPTXDomEnvironment'

import type { ElementBox, VisitContext } from '@/core/services/pptx/PPTXDomConverter.types'
import { INLINE_TEXT_TAGS } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import type { ShapeGeometryResolver, TextShapeGeometryKind } from './ShapeGeometryResolver'
import { calculatePunctuationWidthGuard } from './TextPunctuationGuard'
import { isOutsideTextExpansionBounds, TextExpansionBoundsResolver } from './TextExpansionBounds'
import { measureSingleLineText } from './TextLineLayout'
import { resolveCapsuleNativeInsetGuard, resolveCapsuleWidthGuardLimit } from './CapsuleWidthBudget'

export type TextWidthGuardProfile = 'default' | 'capsule' | 'padded-shape' | 'fragment'

/**
 * 文本框宽度防折行保护与内边距计算器。
 */
export class TextWidthGuard {
  private readonly expansionBounds: TextExpansionBoundsResolver

  constructor(
    private readonly layout: PPTXDomConverterLayout,
    private readonly shapeGeometry: ShapeGeometryResolver,
  ) {
    this.expansionBounds = new TextExpansionBoundsResolver(layout)
  }

  /**
   * 尝试将文本框扩展到祖先容器的剩余宽度，降低 flex/list 场景中因为内容贴边导致的 PPT 换行概率。
   */
  expandTextBoxToAncestorRemainingWidth(
    box: ElementBox,
    anchorNode: Node,
    styleSource: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    isFragment: boolean,
    context: VisitContext,
    isMeaningfulElement: (node: HTMLElement) => boolean,
  ): ElementBox {
    if (!this.shouldExpandToAncestorRemainingWidth(box, styleSource, style, text, isFragment, anchorNode)) {
      return box
    }

    let currentNode: Node | null = anchorNode

    while (currentNode?.parentElement) {
      if (isHTMLElement(currentNode) && this.hasExplicitWidthConstraint(currentNode)) {
        break
      }

      const parent = currentNode.parentElement
      if (!this.isLastMeaningfulNodeBranch(parent, currentNode, isMeaningfulElement)) {
        break
      }

      const parentStyle = getOwnerComputedStyle(parent)
      if (!this.isEligibleRemainingWidthContainer(parent, parentStyle)) {
        currentNode = parent
        continue
      }

      const parentBox = this.layout.getPptxBox(parent, Boolean(context.rotationSteps?.length))
      if (!parentBox) {
        break
      }

      const bounds = this.expansionBounds.resolve(anchorNode, box)
      if (isOutsideTextExpansionBounds(box, bounds)) return box
      const remainingWidth = this.layout.roundInch(Math.max(box.w, Math.min(parentBox.x + parentBox.w, bounds.right) - box.x))
      return remainingWidth > box.w
        ? {
            ...box,
            w: remainingWidth,
          }
        : box
    }

    return box
  }

  /**
   * 按几何和布局语义选择文本形状导出盒：正圆与圆角方框锁定正方形，横向胶囊与内容驱动形状增加防折行冗余。
   */
  resolveTextShapeExportBox(
    slideWidthIn: number,
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    align: string,
    geometryKind: TextShapeGeometryKind,
    shouldPreservePaddedBox: boolean,
  ): ElementBox {
    if (geometryKind === 'circle' || geometryKind === 'rounded-square') {
      return this.shapeGeometry.normalizeCircleBox(box)
    }
    if (geometryKind === 'vertical-capsule') {
      return box
    }
    if (geometryKind === 'horizontal-capsule') {
      return this.applyTextBoxWidthGuard(slideWidthIn, element, box, style, text, align, true, 'capsule')
    }
    if (this.shouldApplyContentSizedShapeWidthGuard(element, style, box, text)) {
      return this.applyTextBoxWidthGuard(slideWidthIn, element, box, style, text, align, true, 'padded-shape')
    }
    if (shouldPreservePaddedBox) {
      return box
    }
    return this.applyTextBoxWidthGuard(slideWidthIn, element, box, style, text, align, true, 'default')
  }

  /**
   * 仅给单行 PPT 文本框增加宽度冗余；多行保留原宽度和对齐位置，避免扩宽改变段落布局。
   */
  applyTextBoxWidthGuard(
    slideWidthIn: number,
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    align: string,
    isTextShape: boolean,
    guardProfile: TextWidthGuardProfile = 'default',
    anchorNode: Node = element,
  ): ElementBox {
    if (!this.isLikelySingleLineTextBox(element, box, style, text, anchorNode)) {
      return box
    }
    const guardWidth = this.calculateTextWidthGuard(element, box, style, text, isTextShape, guardProfile)
    if (guardWidth <= 0) {
      return box
    }

    const bounds = this.expansionBounds.resolve(anchorNode, box, slideWidthIn)
    if (isOutsideTextExpansionBounds(box, bounds)) return box
    const leftRoom = Math.max(0, box.x - bounds.left)
    const rightRoom = Math.max(0, bounds.right - box.x - box.w)
    const allowLeftShift = !this.hasExplicitWidthConstraint(element)
    const { extra, shiftLeft } = this.resolveExpansionShift(guardWidth, leftRoom, rightRoom, align, allowLeftShift)
    if (extra <= 0) return box
    const nextX = box.x - shiftLeft
    return {
      ...box,
      x: this.layout.roundInch(nextX),
      w: this.layout.roundInch(box.w + extra),
    }
  }

  /**
   * 计算有界且最贴近对齐意图的扩宽量与 X 坐标偏移，在贴边时允许非对称借用对侧可用空间防折行。
   */
  private resolveExpansionShift(
    guardWidth: number,
    leftRoom: number,
    rightRoom: number,
    align: string,
    allowLeftShift = true,
  ): { extra: number; shiftLeft: number } {
    if (align === 'center') {
      const symmetricRoom = 2 * Math.min(leftRoom, rightRoom)
      if (symmetricRoom >= guardWidth) {
        const extra = guardWidth
        return { extra, shiftLeft: extra / 2 }
      }
      const totalRoom = leftRoom + rightRoom
      const extra = Math.min(guardWidth, totalRoom)
      if (extra <= 0) return { extra: 0, shiftLeft: 0 }
      const minShiftLeft = Math.max(0, extra - rightRoom)
      const maxShiftLeft = Math.min(leftRoom, extra)
      const preferredShiftLeft = extra / 2
      const shiftLeft = Math.max(minShiftLeft, Math.min(maxShiftLeft, preferredShiftLeft))
      return { extra, shiftLeft }
    }

    if (align === 'right') {
      const extra = Math.min(guardWidth, leftRoom)
      return { extra, shiftLeft: extra }
    }

    // 默认 left 对齐：优先向右扩；若元素无固定宽度约束且右侧贴边，允许向左借位微移
    const shiftRight = Math.min(rightRoom, guardWidth)
    const remainingNeed = guardWidth - shiftRight
    const shiftLeft = allowLeftShift ? Math.min(leftRoom, remainingNeed) : 0
    const extra = shiftRight + shiftLeft
    return { extra, shiftLeft }
  }

  /**
   * 将 HTML padding 映射为 PPT 文本形状内边距。
   * PptxGenJS 4.0.1 的文本框 margin 数组实际按 [left, right, bottom, top] 消费。
   */
  resolveTextShapeMargin(element: HTMLElement, style: CSSStyleDeclaration): number | [number, number, number, number] {
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const paddingScale = this.resolveTextShapePaddingScale(element, style)
    const margin: [number, number, number, number] = [
      this.layout.cssPxToPt(Math.max(0, padding.left * paddingScale.horizontal)),
      this.layout.cssPxToPt(Math.max(0, padding.right * paddingScale.horizontal)),
      this.layout.cssPxToPt(Math.max(0, padding.bottom * paddingScale.vertical)),
      this.layout.cssPxToPt(Math.max(0, padding.top * paddingScale.vertical)),
    ]
    return margin.some(value => value > 0) ? margin : 0
  }

  /** 仅允许无显式宽度约束的单行复杂文字借用祖先空白，避免多行段落被拉宽。 */
  private shouldExpandToAncestorRemainingWidth(
    box: ElementBox,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    isFragment: boolean,
    anchorNode: Node,
  ): boolean {
    if (this.hasExplicitWidthConstraint(element)) {
      return false
    }
    if (!this.isLikelySingleLineTextBox(element, box, style, text, anchorNode)) {
      return false
    }

    const fontSizePt = Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16))
    const fontSizeIn = fontSizePt / 72
    return this.resolveContentComplexityWidthGuardIn(element, style, text, fontSizeIn, isFragment) > 0
  }

  private hasExplicitWidthConstraint(element: HTMLElement): boolean {
    if (
      element.style.getPropertyValue('width') ||
      element.style.getPropertyValue('min-width') ||
      element.style.getPropertyValue('max-width') ||
      element.style.getPropertyValue('flex-basis')
    ) {
      return true
    }

    return Array.from(element.classList).some(className => {
      return /^(?:min-|max-)?w-/.test(className) || /^basis-/.test(className)
    })
  }

  private isEligibleRemainingWidthContainer(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const display = this.layout.resolveLayoutDisplay(element, style)
    if (display === 'flex' && !this.layout.resolveFlexDirection(element, style).startsWith('column')) {
      return true
    }
    return element.tagName.toLowerCase() === 'li'
  }

  private isLastMeaningfulNodeBranch(
    parent: HTMLElement,
    childNode: Node,
    isMeaningfulElement: (node: HTMLElement) => boolean,
  ): boolean {
    const childNodes = Array.from(parent.childNodes)
    const currentIndex = childNodes.indexOf(childNode as ChildNode)
    if (currentIndex < 0) {
      return false
    }

    return childNodes.slice(currentIndex + 1).every(node => !this.isMeaningfulNode(node, isMeaningfulElement))
  }

  private isMeaningfulNode(node: Node, isMeaningfulElement: (node: HTMLElement) => boolean): boolean {
    if (node.nodeType === Node.TEXT_NODE) {
      return Boolean(this.layout.normalizeText(node.textContent || ''))
    }
    if (isHTMLElement(node)) {
      return this.layout.isVisibleElement(node) && isMeaningfulElement(node)
    }
    return false
  }

  private shouldApplyContentSizedShapeWidthGuard(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
    text: string,
  ): boolean {
    const parent = element.parentElement
    if (!parent || !this.isLikelySingleLinePaddedShape(element, style, box, text)) {
      return false
    }

    const parentStyle = getOwnerComputedStyle(parent)
    if (this.layout.resolveLayoutDisplay(parent, parentStyle) !== 'flex' ||
      this.layout.resolveFlexDirection(parent, parentStyle).startsWith('column')) {
      return false
    }

    const padding = this.layout.resolveElementPaddingPixels(element, style)
    if (padding.left + padding.right <= 0) {
      return false
    }

    return !this.hasExplicitTextShapeWidth(element) && !this.hasFlexGrowth(element, style)
  }

  /** 优先按实际文字行判断；没有浏览器布局时扣除 padding，再估计单行内容高度。 */
  private isLikelySingleLinePaddedShape(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
    text: string,
  ): boolean {
    if (!this.layout.isSingleLineText(text)) {
      return false
    }
    const measuredSingleLine = measureSingleLineText(element)
    if (measuredSingleLine !== null) return measuredSingleLine
    if (['nowrap', 'pre'].includes(style.whiteSpace)) {
      return true
    }

    const fontSizePx = this.layout.parseCssPixel(style.fontSize) || 16
    const lineHeightPx = this.layout.parseCssPixel(style.lineHeight) || fontSizePx * 1.2
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const boxHeightPx = Math.max(0, box.h / this.layout.inchPerPxY() - padding.top - padding.bottom)
    return boxHeightPx <= lineHeightPx * 1.9
  }

  private hasExplicitTextShapeWidth(element: HTMLElement): boolean {
    if (element.style.getPropertyValue('width')) {
      return true
    }

    return Array.from(element.classList)
      .map(className => className.split(':').pop() || className)
      .some(className => /^(?:min-|max-)?w-(?!auto$)/.test(className))
  }

  private hasFlexGrowth(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const flexGrow = Number.parseFloat(style.flexGrow)
    if (Number.isFinite(flexGrow) && flexGrow > 0) {
      return true
    }

    const flexBasis = String(style.flexBasis || '').trim()
    if (flexBasis && flexBasis !== 'auto') {
      return true
    }

    return Array.from(element.classList)
      .map(className => className.split(':').pop() || className)
      .some(className => ['flex-1', 'flex-auto', 'grow'].includes(className) || /^grow-/.test(className))
  }

  /** 为已确认的单行文字计算有界宽度余量；调用方负责行布局判断和可用空间限制。 */
  private calculateTextWidthGuard(
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    isTextShape: boolean,
    guardProfile: TextWidthGuardProfile = 'default',
  ): number {
    const fontSizePt = Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16))
    const fontSizeIn = fontSizePt / 72
    const isCapsule = guardProfile === 'capsule'
    const isPaddedShape = guardProfile === 'padded-shape'
    const isFragment = guardProfile === 'fragment'
    const isStrongShapeGuard = isCapsule || isPaddedShape
    const ratioGuard = box.w * (isStrongShapeGuard ? 0.024 : (isTextShape ? 0.018 : 0.03))
    const emGuard = fontSizeIn * (this.layout.containsCjkText(text)
      ? (isStrongShapeGuard ? (isCapsule ? 0.55 : 1) : 0.8)
      : (isStrongShapeGuard ? (isCapsule ? 0.35 : 0.6) : 0.45))
    const contentComplexityGuard = this.resolveContentComplexityWidthGuardIn(
      element,
      style,
      text,
      fontSizeIn,
      isFragment,
      isPaddedShape,
    )
    const capsuleNativeInset = isCapsule
      ? resolveCapsuleNativeInsetGuard(this.layout, element, style, box)
      : 0
    // 几何内缩需求参与总预算，并接受胶囊自身尺寸上限。
    const capsuleInsetGuard = isCapsule
      ? Math.min(capsuleNativeInset, box.w * 0.11)
      : 0
    const paddingGuard = isStrongShapeGuard ? this.resolveHorizontalPaddingGuardIn(element, style) : 0
    const punctuationGuard = calculatePunctuationWidthGuard(text, fontSizeIn, box.w, isTextShape)
    const letterSpacingPx = this.layout.parseCssPixel(style.letterSpacing)
    const letterSpacingIn = letterSpacingPx > 0
      ? this.layout.roundInch(this.layout.cssPxToMeasuredPx(letterSpacingPx) * this.layout.inchPerPxX())
      : 0
    // PPT DrawingML spc 针对每个字符（含空格）机械追加字距，累积排版膨胀需要有界字距保护
    const letterSpacingGuard = letterSpacingIn > 0 && text.length > 1
      ? Math.min(
          letterSpacingIn * Math.min((text.length - 1) * 0.15, 2.5),
          box.w * (isTextShape ? 0.12 : 0.16),
        )
      : 0
    // 字距膨胀与标点/数学符号字形展开为正交独立的排版误差，组合参与保护
    const typographicGuard = punctuationGuard + letterSpacingGuard
    const minGuard = isCapsule
      ? Math.min(0.04, box.w * 0.05)
      : (isPaddedShape ? 0.04 : (isTextShape ? 0.02 : 0.04))
    const contentAwareMaxGuard = contentComplexityGuard > 0
      ? contentComplexityGuard + (isFragment ? 0.03 : 0.02)
      : 0
    const capsuleMaxGuard = isCapsule
      ? resolveCapsuleWidthGuardLimit(box, capsuleNativeInset)
      : 0
    const maxGuard = Math.max(
      isCapsule ? capsuleMaxGuard : (isPaddedShape ? 0.12 : (isTextShape ? 0.04 : 0.08)),
      box.w * (isStrongShapeGuard ? (isCapsule ? 0.11 : 0.14) : (isTextShape ? 0.06 : 0.16)),
      contentAwareMaxGuard,
      typographicGuard,
      capsuleInsetGuard,
    )
    return Math.min(
      isCapsule ? capsuleMaxGuard : maxGuard,
      Math.max(
        minGuard,
        ratioGuard,
        emGuard,
        contentComplexityGuard,
        capsuleInsetGuard,
        paddingGuard,
        typographicGuard,
      ),
    )
  }

  /** 优先观察真实文字行；显式多行直接保留，无布局环境才用盒高与行高回退。 */
  private isLikelySingleLineTextBox(
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    anchorNode: Node = element,
  ): boolean {
    if (!this.layout.isSingleLineText(text)) {
      return false
    }
    const measuredSingleLine = measureSingleLineText(anchorNode)
    if (measuredSingleLine !== null) return measuredSingleLine
    if (['nowrap', 'pre'].includes(style.whiteSpace)) {
      return true
    }

    const fontSizePx = this.layout.parseCssPixel(style.fontSize) || 16
    const lineHeightPx = this.layout.parseCssPixel(style.lineHeight) || fontSizePx * 1.2
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const boxHeightPx = Math.max(0, box.h / this.layout.inchPerPxY() - padding.top - padding.bottom)
    return boxHeightPx <= lineHeightPx * 1.9
  }

  private resolveTextShapePaddingScale(
    element: HTMLElement,
    style: CSSStyleDeclaration,
  ): { horizontal: number; vertical: number } {
    if (this.layout.isPillLikeTextShape(element, style)) {
      return {
        horizontal: 0.75,
        vertical: 0.75,
      }
    }

    return {
      horizontal: 1,
      vertical: 1,
    }
  }

  private resolveHorizontalPaddingGuardIn(element: HTMLElement, style: CSSStyleDeclaration): number {
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const paddingScale = this.resolveTextShapePaddingScale(element, style)
    const horizontalPaddingPx = Math.max(0, (padding.left + padding.right) * paddingScale.horizontal)
    const measuredPaddingPx = this.layout.cssPxToMeasuredPx(horizontalPaddingPx * 0.45)
    return this.layout.roundInch(this.layout.measuredPxToInch(measuredPaddingPx))
  }

  private resolveContentComplexityWidthGuardIn(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    fontSizeIn: number,
    isFragment = false,
    isContentDrivenOverride = false,
  ): number {
    const normalizedText = this.layout.normalizeText(text)
    const metrics = this.collectTextComplexityMetrics(normalizedText)
    const isContentDriven = isContentDrivenOverride || isFragment || this.isContentWidthDrivenInlineText(element, style)
    const baseGuard = fontSizeIn * (
      metrics.hasMixedScripts
        ? (metrics.hasDenseAsciiPhrase
            ? (isContentDriven ? 1.05 : 0.68)
            : (isContentDriven ? 0.9 : 0.55))
        : (metrics.hasLongAsciiToken ? (isContentDriven ? 0.45 : 0.24) : 0)
    )
    const tokenGuard = metrics.longestAsciiTokenLength >= 10
      ? fontSizeIn * Math.min(
          isContentDriven ? 0.8 : 0.55,
          (isContentDriven ? 0.18 : 0.12) + (metrics.longestAsciiTokenLength - 10) * (isContentDriven ? 0.04 : 0.03),
        )
      : 0
    const structureGuard = fontSizeIn * (
      (metrics.hasBracketedLongToken ? (isContentDriven ? 0.45 : 0.28) : 0) +
      (metrics.hasLongAsciiToken ? (isContentDriven ? 0.35 : 0.22) : 0) +
      (metrics.hasSlashSeparatedAscii ? (isContentDriven ? 0.34 : 0.2) : 0) +
      (metrics.hasMixedScripts && metrics.asciiTokenCount >= 2 ? (isContentDriven ? 0.2 : 0.12) : 0) +
      (metrics.hasDenseAsciiPhrase ? (isContentDriven ? 0.14 : 0.08) : 0)
    )
    const minComplexGuard = metrics.hasBracketedLongToken || metrics.hasLongAsciiToken || metrics.hasSlashSeparatedAscii
      ? (isContentDriven ? 0.18 : 0.12)
      : 0
    const cap = isContentDriven ? 0.3 : 0.24
    return Math.min(cap, this.layout.roundInch(Math.max(minComplexGuard, baseGuard + tokenGuard + structureGuard)))
  }

  private collectTextComplexityMetrics(text: string): {
    asciiTokenCount: number
    asciiCharCount: number
    longestAsciiTokenLength: number
    hasMixedScripts: boolean
    hasDenseAsciiPhrase: boolean
    hasSlashSeparatedAscii: boolean
    hasBracketedLongToken: boolean
    hasLongAsciiToken: boolean
  } {
    const asciiLikeTokens: string[] = text.match(/[A-Za-z0-9._-]+/g) ?? []
    const asciiCharCount = asciiLikeTokens.reduce((total, token) => total + token.length, 0)
    const longestAsciiTokenLength = asciiLikeTokens.reduce((maxLength, token) => Math.max(maxLength, token.length), 0)
    const hasMixedScripts = this.layout.containsCjkText(text) && /[A-Za-z]/.test(text)
    return {
      asciiTokenCount: asciiLikeTokens.length,
      asciiCharCount,
      longestAsciiTokenLength,
      hasMixedScripts,
      hasDenseAsciiPhrase: asciiLikeTokens.length >= 3 && asciiCharCount >= 18,
      hasSlashSeparatedAscii: /[A-Za-z0-9._-]+\s*\/\s*[A-Za-z0-9._-]+/.test(text),
      hasBracketedLongToken: /\([^)]{10,}\)/.test(text),
      hasLongAsciiToken: longestAsciiTokenLength >= 14,
    }
  }

  private isContentWidthDrivenInlineText(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const tagName = element.tagName.toLowerCase()
    const isInlineLike = style.display.includes('inline') || INLINE_TEXT_TAGS.has(tagName)
    if (!isInlineLike) {
      return false
    }

    const hasExplicitInlineWidth = Boolean(element.style.getPropertyValue('width'))
    const hasWidthUtility = Array.from(element.classList).some(className => {
      return /^(?:min-|max-)?w-/.test(className)
    })
    return !hasExplicitInlineWidth && !hasWidthUtility
  }
}
