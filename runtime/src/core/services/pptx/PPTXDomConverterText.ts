/**
 * 文件用途：封装 PPTX DOM 转换里的文本、文本形状和简单图形导出逻辑。
 */

import type {
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type {
  BorderInfo,
  ElementBox,
  PptxPageConvertOptions,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import { INLINE_TEXT_TAGS } from '@/core/services/pptx/PPTXDomConverter.types'
import type { ParsedColor } from '@/core/services/pptx/PPTXCssParser'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXDomConverterTransform } from './PPTXDomConverterTransform'
import { PPTXDomRichTextParser, type PptxDomRichTextResult } from './PPTXDomRichTextParser'

type TextShapeGeometryKind =
  | 'circle'
  | 'rounded-square'
  | 'horizontal-capsule'
  | 'vertical-capsule'
  | 'rounded-rect'
  | 'rect'

type TextWidthGuardProfile = 'default' | 'capsule' | 'padded-shape' | 'fragment'

interface ResolvedTextShapeGeometry {
  shape: string
  options: Record<string, unknown>
  kind: TextShapeGeometryKind
}

interface ResolvedTextShapeVisual {
  options: Record<string, unknown>
  geometry: ResolvedTextShapeGeometry
}

export interface PptxDomTextExportHost {
  options: PptxPageConvertOptions
  buildPptObjectMeta: (
    context: VisitContext,
    role: string,
    label: string,
    includeAltText?: boolean,
  ) => Record<string, unknown>
  addReportItem: (
    sourceType: PptxReportSourceType,
    result: PptxReportItemResult,
    editable: boolean,
    label: string,
    reason?: string,
    context?: VisitContext,
  ) => PptxExportReportItem
}

/**
 * PPTX 文本与形状导出 helper。
 */
export class PPTXDomConverterText {
  private readonly richTextParser = new PPTXDomRichTextParser()
  private readonly richTextCache = new WeakMap<HTMLElement, PptxDomRichTextResult | null>()
  private readonly transform: PPTXDomConverterTransform

  constructor(private readonly layout: PPTXDomConverterLayout) {
    this.transform = new PPTXDomConverterTransform(layout)
  }

  /**
   * 判断元素是否应添加为 PPT 形状。
   * @param element 候选元素
   */
  shouldAddShape(element: HTMLElement): boolean {
    const style = window.getComputedStyle(element)
    const box = this.layout.measureElementPixels(element)
    if (box.width <= 0 || box.height <= 0) {
      return false
    }

    return Boolean(this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element)) ||
      this.layout.getBorderInfos(element, style).length > 0
  }

  /**
   * 添加简单形状、卡片、边框或分隔线。
   * @param host 导出宿主能力
   * @param element 源元素
   * @param context 当前组合上下文
   */
  addShapeElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): void {
    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      return
    }

    const style = window.getComputedStyle(element)
    const elementOpacity = this.layout.parseOpacity(style.opacity)
    const fillColor = this.applyOpacity(
      this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element),
      elementOpacity,
    )
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.applyOpacity(border.color, elementOpacity) || border.color,
    }))
    const uniformBorder = this.getUniformBorderInfo(borders)
    const label = this.layout.buildElementLabel(element)
    const isHorizontalLine = box.h <= 0.04 && box.w > box.h
    const isVerticalLine = box.w <= 0.04 && box.h > box.w

    if (isHorizontalLine || isVerticalLine) {
      const minLineWidth = this.layout.roundInch(this.layout.inchPerPxX())
      const minLineHeight = this.layout.roundInch(this.layout.inchPerPxY())
      const lineWidth = isHorizontalLine ? box.w : Math.max(box.w, minLineWidth)
      const lineHeight = isVerticalLine ? box.h : Math.max(box.h, minLineHeight)
      const lineX = isVerticalLine ? Math.max(0, box.x + box.w / 2 - lineWidth / 2) : box.x
      const lineY = isHorizontalLine ? Math.max(0, box.y + box.h / 2 - lineHeight / 2) : box.y

      if (fillColor && borders.length === 0) {
        host.options.slide.addShape(host.options.shapeTypes.rect, {
          ...this.transform.applyToBox({ x: lineX, y: lineY, w: lineWidth, h: lineHeight }, context),
          fill: this.buildFillOptions(fillColor),
          line: this.buildTransparentLineOptions(),
          ...host.buildPptObjectMeta(context, 'shape', label),
        })
        host.addReportItem('shape', 'editable-shape', true, label, '背景色分隔线转为 PPT rect', context)
        return
      }

      host.options.slide.addShape(host.options.shapeTypes.line, {
        ...this.transform.applyToBox({ x: lineX, y: lineY, w: lineWidth, h: lineHeight }, context),
        line: this.buildLineOptions(
          uniformBorder,
          fillColor,
          Math.max(0.75, this.layout.measuredPxToPt(isHorizontalLine ? box.h / this.layout.inchPerPxY() : box.w / this.layout.inchPerPxX())),
        ),
        ...host.buildPptObjectMeta(context, 'line', label),
      })
      host.addReportItem('shape', 'editable-shape', true, label, '分隔线转为 PPT line', context)
      return
    }

    const shapeGeometry = this.resolveShapeGeometry(host, element, style, box)
    host.options.slide.addShape(
      shapeGeometry.shape,
      {
        ...this.transform.applyToBox(box, context),
        fill: this.buildFillOptions(fillColor),
        line: uniformBorder ? this.buildLineOptions(uniformBorder) : this.buildTransparentLineOptions(),
        ...shapeGeometry.options,
        ...host.buildPptObjectMeta(context, 'shape', label),
      },
    )
    if (!uniformBorder && borders.length > 0) {
      borders.forEach(border => this.addBorderSideLine(host, box, border, context, label))
    }
    host.addReportItem('shape', 'editable-shape', true, label, '纯色块、卡片或简单边框转为 PPT shape', context)
  }

  /**
   * 判断元素是否应添加为文本。
   * @param element 候选元素
   */
  shouldAddText(element: HTMLElement): boolean {
    const text = this.layout.normalizeText(element.textContent || '')
    if (!text) {
      return false
    }

    if (element.children.length === 0) {
      return true
    }

    const style = window.getComputedStyle(element)
    if (this.layout.resolveLayoutDisplay(element, style)) {
      return false
    }
    if (element.children.length === 1 && !this.hasDirectTextContent(element)) {
      return false
    }

    return Boolean(this.resolveRichText(element))
  }

  /**
   * 添加 PPT 可编辑文本框。
   * @param host 导出宿主能力
   * @param element 文本元素
   * @param context 当前组合上下文
   */
  addTextElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): void {
    const richText = this.resolveRichText(element)
    const text = richText?.text || this.layout.normalizeText(element.textContent || '')
    const rawBox = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!text || !rawBox) {
      return
    }

    const style = window.getComputedStyle(element)
    const box = this.expandTextBoxToAncestorRemainingWidth(rawBox, element, element, style, text, false, context)
    const sourceType = this.resolveTextSourceType(element, style, text)
    const shouldPreservePaddedBox = this.layout.shouldPreservePaddedInlineTextBox(element, style)
    const textMargin = this.resolveTextShapeMargin(element, style)
    const textOptions = this.buildTextRunOptions(element, style, text, context, shouldPreservePaddedBox)
    const guardedBox = shouldPreservePaddedBox
      ? box
      : this.applyTextBoxWidthGuard(host, element, box, style, text, String(textOptions.align || 'left'), false)

    host.options.slide.addText(richText?.runs || text, {
      ...this.transform.applyToBox(guardedBox, context),
      margin: textMargin,
      ...textOptions,
      isTextBox: true,
      ...host.buildPptObjectMeta(context, 'text', text),
    })
    host.addReportItem(sourceType, 'editable-text', true, text.slice(0, 60), '文本转为 PPT text', context)
  }

  /**
   * 添加带文本的 PPT 形状，让背景、边框、圆角和内边距由 PPT 自动绘制。
   * @param host 导出宿主能力
   * @param element 文本形状源元素
   * @param context 当前组合上下文
   */
  addTextShapeElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): boolean {
    const richText = this.resolveRichText(element)
    const text = richText?.text || this.layout.normalizeText(element.textContent || '')
    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!text || !box) {
      return false
    }

    const style = window.getComputedStyle(element)
    const shapeVisual = this.buildTextShapeVisualOptions(host, element, style, box)
    if (!shapeVisual) {
      return false
    }

    const sourceType = this.resolveTextSourceType(element, style, text)
    const label = this.layout.buildElementLabel(element)
    const textOptions = this.buildTextRunOptions(element, style, text, context, true)
    const shouldPreservePaddedBox = this.layout.shouldPreservePaddedInlineTextBox(element, style)
    const guardedBox = this.resolveTextShapeExportBox(
      host,
      element,
      box,
      style,
      text,
      String(textOptions.align || 'left'),
      shapeVisual.geometry.kind,
      shouldPreservePaddedBox,
    )

    host.options.slide.addText(richText?.runs || text, {
      ...this.transform.applyToBox(guardedBox, context),
      ...shapeVisual.options,
      margin: this.resolveTextShapeMargin(element, style),
      ...textOptions,
      ...host.buildPptObjectMeta(context, 'text-shape', text),
    })
    host.addReportItem(sourceType, 'editable-text', true, text.slice(0, 60), '带背景文本转为 PPT text shape', context)
    host.addReportItem('shape', 'editable-shape', true, label, '背景、边框和圆角由 PPT 文本形状绘制', context)
    return true
  }

  /**
   * 添加直属文本节点为 PPT 可编辑文本框，保留 flex/grid 容器中的混合内容。
   * @param host 导出宿主能力
   * @param parentElement 文本节点父元素
   * @param textNode 文本节点
   * @param context 当前组合上下文
   */
  addDirectTextNode(
    host: PptxDomTextExportHost,
    parentElement: HTMLElement,
    textNode: Text,
    context: VisitContext,
  ): boolean {
    const text = this.layout.normalizeText(textNode.textContent || '')
    const box = this.resolveDirectTextNodeBox(parentElement, textNode, context)
    if (!text || !box) {
      return false
    }

    const style = window.getComputedStyle(parentElement)
    const sourceType = this.resolveTextSourceType(parentElement, style, text)
    const textOptions = {
      ...this.buildTextRunOptions(parentElement, style, text, context, false),
      align: 'left',
      valign: 'top',
    }
    const guardedBox = this.applyTextBoxWidthGuard(
      host,
      parentElement,
      box,
      style,
      text,
      'left',
      false,
      'fragment',
    )

    host.options.slide.addText(text, {
      ...this.transform.applyToBox(guardedBox, context),
      margin: 0,
      ...textOptions,
      isTextBox: true,
      ...host.buildPptObjectMeta(context, 'text', text),
    })
    host.addReportItem(sourceType, 'editable-text', true, text.slice(0, 60), '直属文本节点转为 PPT text', context)
    return true
  }

  /**
   * 解析直属文本节点的导出盒模型。
   * 当文本位于布局容器末尾时，优先使用父容器剩余宽度，避免文本框过度贴字导致 PPT 中换行。
   * @param parentElement 文本节点父元素
   * @param textNode 文本节点
   */
  private resolveDirectTextNodeBox(parentElement: HTMLElement, textNode: Text, context: VisitContext): ElementBox | null {
    const textBox = this.layout.getPptxTextNodeBox(textNode, Boolean(context.rotationSteps?.length))
    if (!textBox) {
      return null
    }

    const style = window.getComputedStyle(parentElement)
    const text = this.layout.normalizeText(textNode.textContent || '')
      return this.expandTextBoxToAncestorRemainingWidth(textBox, textNode, parentElement, style, text, true, context)
  }

  /**
   * 尝试将文本框扩展到祖先容器的剩余宽度，降低 flex/list 场景中因为内容贴边导致的 PPT 换行概率。
   * 仅对没有显式宽度约束的单行复杂文本启用，并在首个可用祖先处停止，避免误伤本来就应换行的段落。
   * @param box 当前文本框
   * @param anchorNode 文本锚点，可为文本元素或直属文本节点
   * @param styleSource 用于判断宽度约束和文本复杂度的元素
   * @param style 计算样式
   * @param text 文本内容
   * @param isFragment 是否为直属文本节点
   */
  private expandTextBoxToAncestorRemainingWidth(
    box: ElementBox,
    anchorNode: Node,
    styleSource: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    isFragment: boolean,
    context: VisitContext,
  ): ElementBox {
    if (!this.shouldExpandToAncestorRemainingWidth(box, styleSource, style, text, isFragment)) {
      return box
    }

    let currentNode: Node | null = anchorNode

    while (currentNode?.parentElement) {
      if (currentNode instanceof HTMLElement && this.hasExplicitWidthConstraint(currentNode)) {
        break
      }

      const parent = currentNode.parentElement
      if (!this.isLastMeaningfulNodeBranch(parent, currentNode)) {
        break
      }

      const style = window.getComputedStyle(parent)
      if (!this.isEligibleRemainingWidthContainer(parent, style)) {
        currentNode = parent
        continue
      }

      const parentBox = this.layout.getPptxBox(parent, Boolean(context.rotationSteps?.length))
      if (!parentBox) {
        break
      }

      const remainingWidth = this.layout.roundInch(Math.max(0.01, (parentBox.x + parentBox.w) - box.x))
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
   * 判断当前文本是否值得尝试扩到祖先剩余宽度。
   * @param box 当前文本框
   * @param element 文本样式参考元素
   * @param style 计算样式
   * @param text 文本内容
   * @param isFragment 是否为直属文本节点
   */
  private shouldExpandToAncestorRemainingWidth(
    box: ElementBox,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    isFragment: boolean,
  ): boolean {
    if (this.hasExplicitWidthConstraint(element)) {
      return false
    }
    if (!this.isLikelySingleLineTextBox(box, style, text)) {
      return false
    }

    const fontSizePt = Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16))
    const fontSizeIn = fontSizePt / 72
    return this.resolveContentComplexityWidthGuardIn(element, style, text, fontSizeIn, isFragment) > 0
  }

  /**
   * 判断元素是否存在显式宽度约束。
   * @param element 候选元素
   */
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

  /**
   * 判断父容器是否适合作为剩余宽度来源。
   * @param element 父容器
   * @param style 父容器计算样式
   */
  private isEligibleRemainingWidthContainer(element: HTMLElement, style: CSSStyleDeclaration): boolean {
    const display = this.layout.resolveLayoutDisplay(element, style)
    if (display === 'flex' && !this.layout.resolveFlexDirection(element, style).startsWith('column')) {
      return true
    }
    return element.tagName.toLowerCase() === 'li'
  }

  /**
   * 判断当前节点分支是否为父容器中的最后有效分支。
   * @param parent 父容器
   * @param childNode 当前节点
   */
  private isLastMeaningfulNodeBranch(parent: HTMLElement, childNode: Node): boolean {
    const childNodes = Array.from(parent.childNodes)
    const currentIndex = childNodes.indexOf(childNode as ChildNode)
    if (currentIndex < 0) {
      return false
    }

    return childNodes.slice(currentIndex + 1).every(node => !this.isMeaningfulNode(node))
  }

  /**
   * 判断节点是否会占据后续可用宽度。
   * @param node 候选节点
   */
  private isMeaningfulNode(node: Node): boolean {
    if (node.nodeType === Node.TEXT_NODE) {
      return Boolean(this.layout.normalizeText(node.textContent || ''))
    }
    if (node instanceof HTMLElement) {
      return this.layout.isVisibleElement(node) &&
        (Boolean(this.layout.normalizeText(node.textContent || '')) || this.shouldAddShape(node))
    }
    return false
  }

  /**
   * 解析并缓存安全 inline 子树的 rich text runs，避免判定与导出阶段重复遍历 DOM。
   */
  private resolveRichText(element: HTMLElement): PptxDomRichTextResult | null {
    if (element.children.length === 0) {
      return null
    }
    if (this.richTextCache.has(element)) {
      return this.richTextCache.get(element) || null
    }

    const result = this.richTextParser.parse(
      element,
      (owner, style, text) => this.buildTextCharacterOptions(owner, style, text),
    )
    this.richTextCache.set(element, result)
    return result
  }

  /**
   * 判断元素是否包含可见直属文本；单一子元素场景继续沿用既有独立盒模型导出路径。
   */
  private hasDirectTextContent(element: HTMLElement): boolean {
    return Array.from(element.childNodes).some(node => {
      return node instanceof Text && Boolean(this.layout.normalizeText(node.textContent || ''))
    })
  }

  /**
   * 构造 PPT fill 参数。
   * @param color 填充颜色
   */
  private buildFillOptions(color: ParsedColor | null): Record<string, unknown> {
    if (!color) {
      return {
        type: 'none',
        transparency: 100,
      }
    }

    return {
      type: 'solid',
      color: color.hex,
      transparency: this.layout.alphaToTransparency(color.alpha),
    }
  }

  /**
   * 构造 PPT line 参数。
   * @param border 边框信息
   * @param fallbackColor 兜底颜色
   * @param fallbackWidthPt 兜底线宽
   */
  private buildLineOptions(
    border?: BorderInfo | null,
    fallbackColor?: ParsedColor | null,
    fallbackWidthPt = 1,
  ): Record<string, unknown> {
    const color = border?.color || fallbackColor || { hex: '000000', alpha: 1 }
    return {
      color: color.hex,
      transparency: this.layout.alphaToTransparency(color.alpha),
      width: border?.widthPt || fallbackWidthPt,
      dashType: border?.dashType || 'solid',
    }
  }

  /**
   * 构造透明线条参数。
   */
  private buildTransparentLineOptions(): Record<string, unknown> {
    return {
      color: 'FFFFFF',
      transparency: 100,
      width: 0,
    }
  }

  /**
   * 对非统一边框逐边画线，提高卡片和分隔线还原度。
   * @param host 导出宿主能力
   * @param box 元素 PPTX 位置尺寸
   * @param border 边框信息
   * @param context 当前组合上下文
   * @param label 对象摘要
   */
  private addBorderSideLine(
    host: PptxDomTextExportHost,
    box: ElementBox,
    border: BorderInfo,
    context: VisitContext,
    label: string,
  ): void {
    const line = this.buildLineOptions(border)
    if (border.side === 'top') {
      host.options.slide.addShape(host.options.shapeTypes.line, {
        ...this.transform.applyToBox({ x: box.x, y: box.y, w: box.w, h: 0 }, context),
        line,
        ...host.buildPptObjectMeta(context, 'border-top', label),
      })
      return
    }

    if (border.side === 'bottom') {
      host.options.slide.addShape(host.options.shapeTypes.line, {
        ...this.transform.applyToBox({ x: box.x, y: box.y + box.h, w: box.w, h: 0 }, context),
        line,
        ...host.buildPptObjectMeta(context, 'border-bottom', label),
      })
      return
    }

    if (border.side === 'left') {
      host.options.slide.addShape(host.options.shapeTypes.line, {
        ...this.transform.applyToBox({ x: box.x, y: box.y, w: 0, h: box.h }, context),
        line,
        ...host.buildPptObjectMeta(context, 'border-left', label),
      })
      return
    }

    host.options.slide.addShape(host.options.shapeTypes.line, {
      ...this.transform.applyToBox({ x: box.x + box.w, y: box.y, w: 0, h: box.h }, context),
      line,
      ...host.buildPptObjectMeta(context, 'border-right', label),
    })
  }

  /**
   * 判断边框是否四边一致，可直接用 rect line 表示。
   * @param borders 四边边框
   */
  private getUniformBorderInfo(borders: BorderInfo[]): BorderInfo | null {
    if (borders.length !== 4) {
      return null
    }

    const [first] = borders
    const isUniform = borders.every(border => {
      return border.color.hex === first.color.hex &&
        Math.abs(border.color.alpha - first.color.alpha) < 0.001 &&
        Math.abs(border.widthPx - first.widthPx) < 0.001 &&
        border.dashType === first.dashType
    })

    return isUniform ? first : null
  }

  /**
   * 将元素 opacity 叠加到颜色透明度。
   * @param color 原始颜色
   * @param opacity 元素透明度
   */
  private applyOpacity(color: ParsedColor | null, opacity: number): ParsedColor | null {
    if (!color) {
      return null
    }

    return {
      hex: color.hex,
      alpha: Math.max(0, Math.min(1, color.alpha * opacity)),
    }
  }

  /**
   * 构造 PPT 文本通用样式参数。
   * @param host 导出宿主能力
   * @param element 文本元素
   * @param style 计算样式
   * @param text 文本内容
   * @param context 当前组合上下文
   * @param isTextShape 是否为带形状文本
   */
  private buildTextRunOptions(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    context: VisitContext,
    isTextShape = false,
  ): Record<string, unknown> {
    return {
      ...this.buildTextCharacterOptions(element, style, text),
      fit: 'none',
      breakLine: false,
      align: isTextShape
        ? this.layout.resolveTextShapeHorizontalAlign(element, style, context)
        : this.layout.resolveTextHorizontalAlign(element, style, context),
      valign: this.layout.resolveTextVerticalAlign(element, style, text, context),
    }
  }

  /**
   * 构造单个富文本 run 可表达的字符级样式，不混入段落和文本框属性。
   */
  private buildTextCharacterOptions(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
  ): Record<string, unknown> {
    const fontSize = Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16))
    const color = this.applyOpacity(this.layout.parseCssColor(style.color, element), this.layout.parseOpacity(style.opacity))
    const letterSpacing = this.layout.parseCssPixel(style.letterSpacing)
    const hyperlink = this.resolveTextHyperlink(element)
    const isSubscript = Boolean(element.closest('sub'))
    const isSuperscript = !isSubscript && Boolean(element.closest('sup'))
    const hasUnderline = style.textDecorationLine.includes('underline') || Boolean(element.closest('u'))
    const hasStrike = style.textDecorationLine.includes('line-through') || Boolean(element.closest('s, del'))
    return {
      fontFace: this.layout.normalizeFontFace(style.fontFamily, text),
      fontSize,
      color: color?.hex || '000000',
      transparency: this.layout.alphaToTransparency(color?.alpha ?? 1),
      bold: this.layout.isBoldFont(style.fontWeight),
      italic: style.fontStyle === 'italic',
      underline: hasUnderline,
      strike: hasStrike,
      subscript: isSubscript,
      superscript: isSuperscript,
      ...(letterSpacing !== 0 ? { charSpacing: this.layout.cssPxToPt(letterSpacing) } : {}),
      ...(hyperlink ? { hyperlink } : {}),
    }
  }

  /**
   * 将安全的外部链接映射为 PPT run hyperlink，其它协议保持普通文本。
   */
  private resolveTextHyperlink(element: HTMLElement): { url: string } | null {
    const anchor = element.closest('a')
    if (!(anchor instanceof HTMLAnchorElement)) {
      return null
    }
    const rawHref = anchor.getAttribute('href')?.trim() || ''
    if (!/^(https?:|mailto:|tel:)/i.test(rawHref)) {
      return null
    }
    return { url: rawHref }
  }

  /**
   * 构造文本形状的外观参数。
   * @param host 导出宿主能力
   * @param element 源元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   */
  private buildTextShapeVisualOptions(
    host: PptxDomTextExportHost,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): ResolvedTextShapeVisual | null {
    const isHorizontalLine = box.h <= 0.04 && box.w > box.h
    const isVerticalLine = box.w <= 0.04 && box.h > box.w
    if (isHorizontalLine || isVerticalLine) {
      return null
    }

    const elementOpacity = this.layout.parseOpacity(style.opacity)
    const fillColor = this.applyOpacity(
      this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element),
      elementOpacity,
    )
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.applyOpacity(border.color, elementOpacity) || border.color,
    }))
    const uniformBorder = this.getUniformBorderInfo(borders)
    if (borders.length > 0 && !uniformBorder) {
      return null
    }

    const shapeGeometry = this.resolveShapeGeometry(host, element, style, box)
    return {
      options: {
        shape: shapeGeometry.shape,
        fill: this.buildFillOptions(fillColor),
        line: uniformBorder ? this.buildLineOptions(uniformBorder) : this.buildTransparentLineOptions(),
        ...shapeGeometry.options,
      },
      geometry: shapeGeometry,
    }
  }

  /**
   * 解析 PPT 形状类型和圆角参数，正圆优先使用原生 ellipse。
   * @param host 导出宿主能力
   * @param element 源元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   */
  private resolveShapeGeometry(
    host: PptxDomTextExportHost,
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): ResolvedTextShapeGeometry {
    if (this.shouldUseEllipseShape(element, style, box)) {
      return {
        shape: host.options.shapeTypes.ellipse,
        options: {},
        kind: 'circle',
      }
    }

    const radiusIn = this.resolveShapeCornerRadiusIn(element, style, box)
    const isFullRadius = radiusIn > 0 && this.isFullRadiusShape(element, radiusIn, box)
    const kind: TextShapeGeometryKind = radiusIn <= 0
      ? 'rect'
      : (this.isExplicitFixedSquareShape(element, box)
          ? 'rounded-square'
          : isFullRadius
          ? (box.w > box.h ? 'horizontal-capsule' : 'vertical-capsule')
          : 'rounded-rect')
    return {
      shape: radiusIn > 0 ? host.options.shapeTypes.roundRect : host.options.shapeTypes.rect,
      options: radiusIn > 0 ? { rectRadius: radiusIn } : {},
      kind,
    }
  }

  /** 判断圆角是否表达了 full-radius 形状。 */
  private isFullRadiusShape(element: HTMLElement, radiusIn: number, box: ElementBox): boolean {
    return element.classList.contains('rounded-full') ||
      radiusIn >= (Math.min(box.w, box.h) / 2) - 0.0001
  }

  /**
   * 判断 full-radius 的近似正方形是否应导出为 PPT 原生椭圆。
   * @param element 源元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   */
  private shouldUseEllipseShape(element: HTMLElement, style: CSSStyleDeclaration, box: ElementBox): boolean {
    if (!this.isNearSquareBox(box)) {
      return false
    }

    const minSide = Math.min(box.w, box.h)
    const radiusIn = this.resolveShapeCornerRadiusIn(element, style, box)
    if (radiusIn <= 0) {
      return false
    }

    return element.classList.contains('rounded-full') || radiusIn >= (minSide / 2) - 0.0001
  }

  /** 判断 PPT 外接框是否可视为近似正方形。 */
  private isNearSquareBox(box: ElementBox): boolean {
    const minSide = Math.min(box.w, box.h)
    const maxSide = Math.max(box.w, box.h)
    return minSide > 0 && Math.abs(maxSide - minSide) <= Math.max(0.01, minSide * 0.04)
  }

  /**
   * 判断作者是否通过 width/height、尺寸类或 aspect-square 明确声明了固定正方形。
   * 内容自然撑开的近方形不会锁定，避免误伤普通文本标签。
   */
  private isExplicitFixedSquareShape(element: HTMLElement, box: ElementBox): boolean {
    if (!this.isNearSquareBox(box)) {
      return false
    }

    const utilities = Array.from(element.classList).map(className => className.split(':').pop() || className)
    const hasSizeUtility = utilities.some(className => /^size-/.test(className))
    const hasWidthUtility = utilities.some(className => /^w-/.test(className))
    const hasHeightUtility = utilities.some(className => /^h-/.test(className))
    const hasAspectSquare = utilities.includes('aspect-square')
    const hasInlineWidth = Boolean(element.style.getPropertyValue('width'))
    const hasInlineHeight = Boolean(element.style.getPropertyValue('height'))
    const hasExplicitWidth = hasInlineWidth || hasWidthUtility
    const hasExplicitHeight = hasInlineHeight || hasHeightUtility
    return hasSizeUtility ||
      (hasExplicitWidth && hasExplicitHeight) ||
      (hasAspectSquare && (hasExplicitWidth || hasExplicitHeight))
  }

  /**
   * 按几何和布局语义选择文本宽度保护：圆和纵向胶囊锁定外形，横向胶囊及内容宽度形状允许横向扩宽。
   */
  private resolveTextShapeExportBox(
    host: PptxDomTextExportHost,
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    align: string,
    geometryKind: TextShapeGeometryKind,
    shouldPreservePaddedBox: boolean,
  ): ElementBox {
    if (geometryKind === 'circle' || geometryKind === 'rounded-square') {
      return this.normalizeCircleBox(box)
    }
    if (geometryKind === 'vertical-capsule') {
      return box
    }
    if (geometryKind === 'horizontal-capsule') {
      return this.applyTextBoxWidthGuard(host, element, box, style, text, align, true, 'capsule')
    }
    if (this.shouldApplyContentSizedShapeWidthGuard(element, style, box, text)) {
      return this.applyTextBoxWidthGuard(host, element, box, style, text, align, true, 'padded-shape')
    }
    if (shouldPreservePaddedBox) {
      return box
    }
    return this.applyTextBoxWidthGuard(host, element, box, style, text, align, true, 'default')
  }

  /**
   * 判断内容宽度驱动的 flex 行子项是否应使用更强的文本形状宽度保护。
   * 这类块级 div 在 flex 中通常按内容取宽，但不会被 pill-like 判定识别。
   * @param element 文本形状元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   * @param text 文本内容
   */
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

    const parentStyle = window.getComputedStyle(parent)
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

  /**
   * 判断带 padding 的文本形状是否大概率为单行，测量时扣除上下内边距。
   * @param element 文本形状元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   * @param text 文本内容
   */
  private isLikelySingleLinePaddedShape(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
    text: string,
  ): boolean {
    if (!this.layout.isSingleLineText(text)) {
      return false
    }
    if (['nowrap', 'pre', 'pre-line', 'pre-wrap'].includes(style.whiteSpace)) {
      return true
    }

    const fontSizePx = this.layout.parseCssPixel(style.fontSize) || 16
    const lineHeightPx = this.layout.parseCssPixel(style.lineHeight) || fontSizePx * 1.2
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const boxHeightPx = Math.max(0, box.h / this.layout.inchPerPxY() - padding.top - padding.bottom)
    return boxHeightPx <= lineHeightPx * 1.9
  }

  /** 判断文本形状是否声明了显式宽度约束。 */
  private hasExplicitTextShapeWidth(element: HTMLElement): boolean {
    if (element.style.getPropertyValue('width')) {
      return true
    }

    return Array.from(element.classList)
      .map(className => className.split(':').pop() || className)
      .some(className => /^(?:min-|max-)?w-(?!auto$)/.test(className))
  }

  /** 判断 flex 子项是否通过 grow 或非 auto flex-basis 参与填充布局。 */
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

  /** 将近似正圆的 PPT 外接框收敛为保持中心不变的正方形。 */
  private normalizeCircleBox(box: ElementBox): ElementBox {
    const side = Math.min(box.w, box.h)
    return {
      x: this.layout.roundInch(box.x + (box.w - side) / 2),
      y: this.layout.roundInch(box.y + (box.h - side) / 2),
      w: this.layout.roundInch(side),
      h: this.layout.roundInch(side),
    }
  }

  /**
   * 给 PPT 文本框增加宽度冗余，降低 PowerPoint 字宽差异导致末字换行的概率。
   * @param host 导出宿主能力
   * @param box 原始 PPT 坐标盒
   * @param style 计算样式
   * @param text 文本内容
   * @param align 水平对齐
   * @param isTextShape 是否为带背景形状文本
   */
  private applyTextBoxWidthGuard(
    host: PptxDomTextExportHost,
    element: HTMLElement,
    box: ElementBox,
    style: CSSStyleDeclaration,
    text: string,
    align: string,
    isTextShape: boolean,
    guardProfile: TextWidthGuardProfile = 'default',
  ): ElementBox {
    const guardWidth = this.calculateTextWidthGuard(element, box, style, text, isTextShape, guardProfile)
    if (guardWidth <= 0) {
      return box
    }

    let nextX = box.x
    if (align === 'center') {
      nextX -= guardWidth / 2
    } else if (align === 'right') {
      nextX -= guardWidth
    }

    nextX = Math.max(0, nextX)
    const maxWidth = Math.max(0.01, host.options.slideWidthIn - nextX)
    return {
      ...box,
      x: this.layout.roundInch(nextX),
      w: this.layout.roundInch(Math.min(maxWidth, box.w + guardWidth)),
    }
  }

  /**
   * 按文本形状和布局 profile 计算宽度冗余，降低 PowerPoint 字宽差异导致末字换行的概率。
   * @param box 原始 PPT 坐标盒
   * @param style 计算样式
   * @param text 文本内容
   * @param isTextShape 是否为带背景形状文本
   */
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
    const isSingleLine = this.isLikelySingleLineTextBox(box, style, text)
    const isCapsule = guardProfile === 'capsule'
    const isPaddedShape = guardProfile === 'padded-shape'
    const isFragment = guardProfile === 'fragment'
    const isStrongShapeGuard = isCapsule || isPaddedShape
    const ratioGuard = box.w * (
      isSingleLine
        ? (isStrongShapeGuard ? 0.024 : (isTextShape ? 0.018 : 0.03))
        : (isStrongShapeGuard ? 0.012 : (isTextShape ? 0.008 : 0.015))
    )
    const emGuard = fontSizeIn * (
      isSingleLine
        ? (this.layout.containsCjkText(text) ? (isStrongShapeGuard ? 1 : 0.8) : (isStrongShapeGuard ? 0.6 : 0.45))
        : (this.layout.containsCjkText(text) ? (isStrongShapeGuard ? 0.45 : 0.35) : (isStrongShapeGuard ? 0.28 : 0.2))
    )
    const contentComplexityGuard = isCapsule
      ? 0
      : this.resolveContentComplexityWidthGuardIn(
          element,
          style,
          text,
          fontSizeIn,
          isFragment,
          isPaddedShape,
        )
    const paddingGuard = isStrongShapeGuard ? this.resolveHorizontalPaddingGuardIn(element, style) : 0
    const minGuard = isCapsule ? 0.03 : (isPaddedShape ? 0.04 : (isTextShape ? 0.02 : 0.04))
    const contentAwareMaxGuard = contentComplexityGuard > 0
      ? contentComplexityGuard + (isFragment ? 0.03 : 0.02)
      : 0
    const maxGuard = Math.max(
      isCapsule ? 0.09 : (isPaddedShape ? 0.12 : (isTextShape ? 0.04 : 0.08)),
      box.w * (isStrongShapeGuard ? 0.12 : (isTextShape ? 0.06 : 0.11)),
      contentAwareMaxGuard,
    )
    return Math.min(maxGuard, Math.max(minGuard, ratioGuard, emGuard, contentComplexityGuard, paddingGuard))
  }

  /**
   * 判断文本盒是否大概率是单行，单行更容易出现末字换行。
   * @param box PPT 坐标盒
   * @param style 计算样式
   * @param text 文本内容
   */
  private isLikelySingleLineTextBox(box: ElementBox, style: CSSStyleDeclaration, text: string): boolean {
    if (!this.layout.isSingleLineText(text)) {
      return false
    }
    if (['nowrap', 'pre', 'pre-line', 'pre-wrap'].includes(style.whiteSpace)) {
      return true
    }

    const fontSizePx = this.layout.parseCssPixel(style.fontSize) || 16
    const lineHeightPx = this.layout.parseCssPixel(style.lineHeight) || fontSizePx * 1.2
    const boxHeightPx = box.h / this.layout.inchPerPxY()
    return boxHeightPx <= lineHeightPx * 1.9
  }

  /**
   * 将 HTML padding 映射为 PPT 文本形状内边距。
   * PptxGenJS 4.0.1 的文本框 margin 数组实际按 left、right、bottom、top 消费，
   * 与表格单元格和类型注释的顺序不同，因此这里以最终 OOXML inset 字段为准。
   * @param element 源元素
   * @param style 计算样式
   */
  private resolveTextShapeMargin(element: HTMLElement, style: CSSStyleDeclaration): number | [number, number, number, number] {
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

  /**
   * 解析文本形状内边距缩放，pill/badge 适当收紧 padding 以贴近 HTML 视觉密度。
   * @param element 源元素
   * @param style 计算样式
   */
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

  /**
   * 读取带水平 padding 的文本形状对扩宽的附加需求。
   * @param element 源元素
   * @param style 计算样式
   */
  private resolveHorizontalPaddingGuardIn(element: HTMLElement, style: CSSStyleDeclaration): number {
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const paddingScale = this.resolveTextShapePaddingScale(element, style)
    const horizontalPaddingPx = Math.max(0, (padding.left + padding.right) * paddingScale.horizontal)
    const measuredPaddingPx = this.layout.cssPxToMeasuredPx(horizontalPaddingPx * 0.45)
    return this.layout.roundInch(this.layout.measuredPxToInch(measuredPaddingPx))
  }

  /**
   * 读取通用文本复杂度额外 guard，补偿 PPT 对长 token 和中英混排的字宽偏差。
   * @param element 源元素
   * @param style 计算样式
   * @param text 文本内容
   * @param fontSizeIn 字号对应 inch
   * @param isFragment 是否为直属文本节点这类紧贴内容的片段文本
   * @param isContentDrivenOverride 是否由内容宽度驱动，可提升复杂文本的保护强度
   */
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

  /**
   * 提取文本里影响 PPT 宽度估算的复杂度指标。
   * @param text 规范化后的文本
   */
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

  /**
   * 判断当前文本框是否主要由内容自然宽度驱动，适合增加额外 guard。
   * @param element 源元素
   * @param style 计算样式
   */
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

  /**
   * 将元素圆角从 CSS px 换算为 PPTX roundRect 需要的 inch 半径。
   * @param element 源元素
   * @param style 计算样式
   * @param box PPT 坐标盒
   */
  private resolveShapeCornerRadiusIn(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    box: ElementBox,
  ): number {
    const radiusPx = this.layout.resolveElementCornerRadiusPx(element, style)
    if (radiusPx <= 0) {
      return 0
    }

    const measuredRadiusPx = this.layout.cssPxToMeasuredPx(radiusPx)
    const radiusIn = this.layout.measuredPxToInch(measuredRadiusPx)
    const maxRadiusIn = Math.max(0, Math.min(box.w, box.h) / 2)
    return this.layout.roundInch(Math.min(maxRadiusIn, Math.max(0, radiusIn)))
  }

  /**
   * 根据元素和样式推断文本类型。
   * @param element 文本元素
   * @param style 计算样式
   * @param text 文本内容
   */
  private resolveTextSourceType(element: HTMLElement, style: CSSStyleDeclaration, text: string): PptxReportSourceType {
    const tagName = element.tagName.toLowerCase()
    const fontSize = this.layout.parseCssPixel(style.fontSize)
    const numericChars = text.replace(/[^\d.%+-]/g, '').length
    if (numericChars >= Math.max(2, text.length * 0.55) && fontSize >= 22) {
      return 'number'
    }
    if (/^h[1-6]$/.test(tagName) || fontSize >= 30 || (this.layout.isBoldFont(style.fontWeight) && fontSize >= 22)) {
      return 'title'
    }
    return 'body'
  }
}
