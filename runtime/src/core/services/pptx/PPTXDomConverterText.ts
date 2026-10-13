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
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXDomConverterTransform } from './PPTXDomConverterTransform'
import { PPTXDomRichTextParser, type PptxDomRichTextResult } from './PPTXDomRichTextParser'
import { ShapeGeometryResolver } from './extractors/ShapeGeometryResolver'
import { TextWidthGuard } from './extractors/TextWidthGuard'

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
    extra?: Partial<PptxExportReportItem>,
  ) => PptxExportReportItem
}

/**
 * PPTX 文本与形状导出 helper。
 */
export class PPTXDomConverterText {
  private readonly richTextParser = new PPTXDomRichTextParser()
  private richTextCache = new WeakMap<HTMLElement, PptxDomRichTextResult | null>()
  private readonly transform: PPTXDomConverterTransform
  private readonly shapeGeometry: ShapeGeometryResolver
  private readonly widthGuard: TextWidthGuard

  constructor(private readonly layout: PPTXDomConverterLayout) {
    this.transform = new PPTXDomConverterTransform(layout)
    this.shapeGeometry = new ShapeGeometryResolver(layout)
    this.widthGuard = new TextWidthGuard(layout, this.shapeGeometry)
  }

  /**
   * 初始化页面级富文本缓存。
   */
  beginPage(): void {
    this.richTextCache = new WeakMap<HTMLElement, PptxDomRichTextResult | null>()
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
   */
  addShapeElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): void {
    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      return
    }

    const style = window.getComputedStyle(element)
    const elementOpacity = this.layout.parseOpacity(style.opacity)
    const fillColor = this.shapeGeometry.applyOpacity(
      this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(element, style), element),
      elementOpacity,
    )
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.shapeGeometry.applyOpacity(border.color, elementOpacity) || border.color,
    }))
    const uniformBorder = this.shapeGeometry.getUniformBorderInfo(borders)
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
          fill: this.shapeGeometry.buildFillOptions(fillColor),
          line: this.shapeGeometry.buildTransparentLineOptions(),
          ...host.buildPptObjectMeta(context, 'shape', label),
        })
        host.addReportItem('shape', 'editable-shape', true, label, '背景色分隔线转为 PPT rect', context)
        return
      }

      host.options.slide.addShape(host.options.shapeTypes.line, {
        ...this.transform.applyToBox({ x: lineX, y: lineY, w: lineWidth, h: lineHeight }, context),
        line: this.shapeGeometry.buildLineOptions(
          uniformBorder,
          fillColor,
          Math.max(0.75, this.layout.measuredPxToPt(isHorizontalLine ? box.h / this.layout.inchPerPxY() : box.w / this.layout.inchPerPxX())),
        ),
        ...host.buildPptObjectMeta(context, 'line', label),
      })
      host.addReportItem('shape', 'editable-shape', true, label, '分隔线转为 PPT line', context)
      return
    }

    const shapeGeometry = this.shapeGeometry.resolveShapeGeometry(host.options.shapeTypes, element, style, box)
    host.options.slide.addShape(
      shapeGeometry.shape,
      {
        ...this.transform.applyToBox(box, context),
        fill: this.shapeGeometry.buildFillOptions(fillColor),
        line: uniformBorder ? this.shapeGeometry.buildLineOptions(uniformBorder) : this.shapeGeometry.buildTransparentLineOptions(),
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
   */
  addTextElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): void {
    const richText = this.resolveRichText(element)
    const text = richText?.text || this.layout.normalizeText(element.textContent || '')
    const rawBox = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!text || !rawBox) {
      return
    }

    const style = window.getComputedStyle(element)
    const box = this.widthGuard.expandTextBoxToAncestorRemainingWidth(
      rawBox,
      element,
      element,
      style,
      text,
      false,
      context,
      node => Boolean(this.layout.normalizeText(node.textContent || '')) || this.shouldAddShape(node),
    )
    const sourceType = this.resolveTextSourceType(element, style, text)
    const shouldPreservePaddedBox = this.layout.shouldPreservePaddedInlineTextBox(element, style)
    const textMargin = this.widthGuard.resolveTextShapeMargin(element, style)
    const textOptions = this.buildTextRunOptions(element, style, text, context, shouldPreservePaddedBox)
    const guardedBox = shouldPreservePaddedBox
      ? box
      : this.widthGuard.applyTextBoxWidthGuard(
          host.options.slideWidthIn,
          element,
          box,
          style,
          text,
          String(textOptions.align || 'left'),
          false,
        )

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
   */
  addTextShapeElement(host: PptxDomTextExportHost, element: HTMLElement, context: VisitContext): boolean {
    const richText = this.resolveRichText(element)
    const text = richText?.text || this.layout.normalizeText(element.textContent || '')
    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!text || !box) {
      return false
    }

    const style = window.getComputedStyle(element)
    const shapeVisual = this.shapeGeometry.buildTextShapeVisualOptions(host.options.shapeTypes, element, style, box)
    if (!shapeVisual) {
      return false
    }

    const sourceType = this.resolveTextSourceType(element, style, text)
    const label = this.layout.buildElementLabel(element)
    const textOptions = this.buildTextRunOptions(element, style, text, context, true)
    const shouldPreservePaddedBox = this.layout.shouldPreservePaddedInlineTextBox(element, style)
    const guardedBox = this.widthGuard.resolveTextShapeExportBox(
      host.options.slideWidthIn,
      element,
      box,
      style,
      text,
      String(textOptions.align || 'left'),
      shapeVisual.geometry.kind,
      shouldPreservePaddedBox,
    )

    const objectMeta = host.buildPptObjectMeta(context, 'text-shape', text)
    const objectName = typeof objectMeta.objectName === 'string' ? objectMeta.objectName : undefined
    const extra = objectName ? { primitiveIds: [objectName] } : undefined

    host.options.slide.addText(richText?.runs || text, {
      ...this.transform.applyToBox(guardedBox, context),
      ...shapeVisual.options,
      margin: this.widthGuard.resolveTextShapeMargin(element, style),
      ...textOptions,
      ...objectMeta,
    })
    host.addReportItem(sourceType, 'editable-text', true, text.slice(0, 60), '带背景文本转为 PPT text shape', context, extra)
    host.addReportItem('shape', 'editable-shape', true, label, '背景、边框和圆角由 PPT 文本形状绘制', context, extra)
    return true
  }

  /**
   * 添加直属文本节点为 PPT 可编辑文本框，保留 flex/grid 容器中的混合内容。
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
    const guardedBox = this.widthGuard.applyTextBoxWidthGuard(
      host.options.slideWidthIn,
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

  private resolveDirectTextNodeBox(parentElement: HTMLElement, textNode: Text, context: VisitContext): ElementBox | null {
    const textBox = this.layout.getPptxTextNodeBox(textNode, Boolean(context.rotationSteps?.length))
    if (!textBox) {
      return null
    }

    const style = window.getComputedStyle(parentElement)
    const text = this.layout.normalizeText(textNode.textContent || '')
    return this.widthGuard.expandTextBoxToAncestorRemainingWidth(
      textBox,
      textNode,
      parentElement,
      style,
      text,
      true,
      context,
      node => Boolean(this.layout.normalizeText(node.textContent || '')) || this.shouldAddShape(node),
    )
  }

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

  private hasDirectTextContent(element: HTMLElement): boolean {
    return Array.from(element.childNodes).some(node => {
      return node instanceof Text && Boolean(this.layout.normalizeText(node.textContent || ''))
    })
  }

  private addBorderSideLine(
    host: PptxDomTextExportHost,
    box: ElementBox,
    border: BorderInfo,
    context: VisitContext,
    label: string,
  ): void {
    const line = this.shapeGeometry.buildLineOptions(border)
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

  private buildTextCharacterOptions(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
  ): Record<string, unknown> {
    const fontSize = Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16))
    const color = this.shapeGeometry.applyOpacity(
      this.layout.parseCssColor(style.color, element),
      this.layout.parseOpacity(style.opacity),
    )
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
