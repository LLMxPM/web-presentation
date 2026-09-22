/**
 * 文件用途：将运行时页面 DOM 启发式转换为 PPTX 文本、形状、图片与截图块。
 */

import type {
  PptxExportReportItem,
  PptxExportReportPage,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import { PPTXCssParser } from '@/core/services/pptx/PPTXCssParser'
import { PPTXSvgSerializer } from '@/core/services/pptx/PPTXSvgSerializer'
import { PPTXDomConverterGradient } from '@/core/services/pptx/PPTXDomConverterGradient'
import type { PptxDomGradientExportHost } from '@/core/services/pptx/PPTXDomConverterGradient'
import { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXDomConverterMedia } from '@/core/services/pptx/PPTXDomConverterMedia'
import type { PptxDomMediaExportHost } from '@/core/services/pptx/PPTXDomConverterMedia'
import { PPTX_3D_SCREENSHOT_REASON, PPTXDomConverterRaster } from '@/core/services/pptx/PPTXDomConverterRaster'
import { PPTXDomConverterTable } from '@/core/services/pptx/PPTXDomConverterTable'
import type { PptxDomTableExportHost } from '@/core/services/pptx/PPTXDomConverterTable'
import { PPTXDomConverterText } from '@/core/services/pptx/PPTXDomConverterText'
import type { PptxDomTextExportHost } from '@/core/services/pptx/PPTXDomConverterText'
import { PPTXDomConverterTransform } from '@/core/services/pptx/PPTXDomConverterTransform'
import type { PptxPageConvertOptions, VisitContext } from '@/core/services/pptx/PPTXDomConverter.types'

export type {
  PptxGradientFillInstruction,
  PptxShapeTypes,
} from '@/core/services/pptx/PPTXDomConverter.types'
export type { PptxPageConvertOptions } from '@/core/services/pptx/PPTXDomConverter.types'

/**
 * DOM 到 PPTX 的启发式转换器。
 */
export class PPTXDomConverter {
  private readonly cssParser = new PPTXCssParser()
  private readonly layout = new PPTXDomConverterLayout(this.cssParser)
  private readonly transform = new PPTXDomConverterTransform(this.layout)
  private readonly svgSerializer = new PPTXSvgSerializer(this.cssParser, element => this.layout.measureElementPixels(element))
  private readonly media = new PPTXDomConverterMedia(this.layout, this.svgSerializer)
  private readonly raster = new PPTXDomConverterRaster(this.layout)
  private readonly table = new PPTXDomConverterTable(this.layout)
  private readonly text = new PPTXDomConverterText(this.layout)
  private readonly gradient = new PPTXDomConverterGradient(this.layout)
  private options!: PptxPageConvertOptions
  private reportPage!: PptxExportReportPage
  private groupSequence = 0
  private gradientSequence = 0

  /**
   * 转换单个页面。
   * @param options 页面转换上下文
   * @returns 当前页导出报告
   */
  async convertPage(options: PptxPageConvertOptions): Promise<PptxExportReportPage> {
    this.options = options
    this.reportPage = {
      pageIndex: options.pageIndex,
      pageTitle: options.pageTitle,
      pageRoute: options.pageRoute,
      items: [],
    }
    this.groupSequence = 0
    this.gradientSequence = 0

    this.layout.beginPage(options)
    this.layout.setRootBox(this.layout.measureRootBox(options.pageElement))

    this.applySlideBackground(options.pageElement)

    const rootContext: VisitContext = {
      groupDepth: 0,
    }
    for (const child of Array.from(options.pageElement.children)) {
      await this.visitElement(child, rootContext)
    }

    return this.reportPage
  }

  /**
   * 递归访问元素并按优先级转换。
   * @param element 当前元素
   * @param context 当前 HTML 容器组合上下文
   */
  private async visitElement(element: Element, context: VisitContext): Promise<void> {
    if (!this.layout.isVisibleElement(element)) {
      return
    }

    const threeDScreenshotTarget = this.raster.resolve3dScreenshotTarget(element, this.options.pageElement)
    if (threeDScreenshotTarget) {
      await this.addScreenshotBlock(threeDScreenshotTarget, 'complex-css', PPTX_3D_SCREENSHOT_REASON, context)
      return
    }

    if (element instanceof HTMLElement) {
      const preparedTransform = this.transform.prepare(element, context)
      try {
        if (preparedTransform.kind === 'unsupported') {
          await this.addScreenshotBlock(element, 'complex-css', '不支持的 CSS 2D transform 降级为局部截图', context)
          return
        }
        await this.visitPreparedElement(element, preparedTransform.context)
      }
      finally {
        preparedTransform.restore()
      }
      return
    }

    await this.visitPreparedElement(element, context)
  }

  /**
   * 转换已冻结动画并移除可映射旋转的元素。
   * @param element 当前元素
   * @param context 当前组合及旋转上下文
   */
  private async visitPreparedElement(element: Element, context: VisitContext): Promise<void> {

    if (this.table.isTableElement(element)) {
      const unsupportedReason = this.table.resolveUnsupportedReason(element)
      if (unsupportedReason) {
        await this.addScreenshotBlock(element, 'table', unsupportedReason, context)
        return
      }
      this.table.addTableElement(this.createTableExportHost(), element as HTMLElement, context)
      return
    }

    if (this.media.isMediaElement(element)) {
      await this.media.addMediaElement(this.createMediaExportHost(), element, context)
      return
    }

    let exportedBackgroundImage = false
    if (element instanceof HTMLElement) {
      exportedBackgroundImage = await this.media.addBackgroundImageElement(this.createMediaExportHost(), element, context)
      if (exportedBackgroundImage && !this.shouldContinueAfterVisualExport(element)) {
        return
      }
    }

    let exportedLinearGradient = false
    if (element instanceof HTMLElement) {
      exportedLinearGradient = this.gradient.addLinearGradientElement(this.createGradientExportHost(), element, context)
      if (exportedLinearGradient && !this.shouldContinueAfterVisualExport(element)) {
        return
      }
    }

    if (
      element instanceof HTMLElement &&
      !exportedBackgroundImage &&
      !exportedLinearGradient &&
      this.layout.shouldScreenshotComplexElement(element)
    ) {
      if (!this.hasVisibleTextContent(element)) {
        await this.addScreenshotBlock(element, 'complex-css', '复杂 CSS 容器降级为局部截图', context)
        return
      }
      this.addSkippedItem(
        'complex-css',
        this.layout.buildElementLabel(element),
        '复杂 CSS 容器包含可编辑内容，已展开子元素避免文本丢失',
        context,
      )
    }

    const textContext = element instanceof HTMLElement
      ? this.createTextInheritanceContext(element, context)
      : context
    const shouldAddShape = element instanceof HTMLElement && this.text.shouldAddShape(element)
    const shouldAddWholeText = element instanceof HTMLElement && this.text.shouldAddText(element)
    const shouldAddTextShape = element instanceof HTMLElement &&
      shouldAddWholeText &&
      (shouldAddShape || this.layout.shouldPreservePaddedInlineTextBox(element, window.getComputedStyle(element)))
    const elementContext = element instanceof HTMLElement && this.shouldCreateCompositionGroup(element, shouldAddShape, shouldAddWholeText)
      ? this.createGroupContext(element, textContext)
      : textContext

    if (
      element instanceof HTMLElement &&
      shouldAddTextShape &&
      this.text.addTextShapeElement(this.createTextExportHost(), element, elementContext)
    ) {
      return
    }

    if (element instanceof HTMLElement && shouldAddShape) {
      this.text.addShapeElement(this.createTextExportHost(), element, elementContext)
    }

    if (element instanceof HTMLElement && shouldAddWholeText) {
      this.text.addTextElement(this.createTextExportHost(), element, elementContext)
      return
    }

    for (const childNode of Array.from(element.childNodes)) {
      if (childNode instanceof Element) {
        await this.visitElement(childNode, elementContext)
        continue
      }
      if (element instanceof HTMLElement && childNode instanceof Text) {
        this.text.addDirectTextNode(this.createTextExportHost(), element, childNode, elementContext)
      }
    }
  }

  /**
   * 判断视觉容器在导出背景或截图兜底后，是否仍需继续导出叠加内容。
   * @param element 已完成视觉层导出的容器
   * @returns 是否继续遍历子节点
   */
  private shouldContinueAfterVisualExport(element: HTMLElement): boolean {
    if (this.layout.hasVisibleChildElement(element)) {
      return true
    }

    return Array.from(element.childNodes).some(childNode => {
      return childNode instanceof Text && Boolean(this.layout.normalizeText(childNode.textContent || ''))
    })
  }

  /**
   * 判断子树中是否存在可见文本，复杂 CSS 截图会据此避免吞掉可编辑文本。
   * @param element 候选容器
   */
  private hasVisibleTextContent(element: HTMLElement): boolean {
    return Array.from(element.childNodes).some(childNode => {
      if (childNode instanceof Text) {
        return Boolean(this.layout.normalizeText(childNode.textContent || ''))
      }
      if (childNode instanceof HTMLElement && this.layout.isVisibleElement(childNode)) {
        return this.hasVisibleTextContent(childNode)
      }
      return false
    })
  }

  /**
   * 使用页面根背景设置 slide 背景。
   * @param pageElement 页面根元素
   */
  private applySlideBackground(pageElement: HTMLElement): void {
    const style = window.getComputedStyle(pageElement)
    const backgroundColor = this.layout.parseCssColor(
      this.layout.resolveBackgroundColorValue(pageElement, style),
      pageElement,
    )
    if (backgroundColor) {
      this.options.slide.background = {
        color: backgroundColor.hex,
        transparency: this.layout.alphaToTransparency(backgroundColor.alpha),
      }
    }
  }

  /**
   * 构造媒体导出宿主能力对象。
   */
  private createMediaExportHost(): PptxDomMediaExportHost {
    return {
      options: this.options,
      buildPptObjectMeta: (...args) => this.buildPptObjectMeta(...args),
      addReportItem: (...args) => this.addReportItem(...args),
      addSkippedItem: (...args) => this.addSkippedItem(...args),
    }
  }

  /**
   * 构造表格导出宿主能力对象。
   */
  private createTableExportHost(): PptxDomTableExportHost {
    return {
      options: this.options,
      buildPptObjectMeta: (...args) => this.buildPptObjectMeta(...args),
      addReportItem: (...args) => this.addReportItem(...args),
      addSkippedItem: (...args) => this.addSkippedItem(...args),
    }
  }

  /**
   * 构造文本导出宿主能力对象。
   */
  private createTextExportHost(): PptxDomTextExportHost {
    return {
      options: this.options,
      buildPptObjectMeta: (...args) => this.buildPptObjectMeta(...args),
      addReportItem: (...args) => this.addReportItem(...args),
    }
  }

  /**
   * 构造渐变导出宿主能力对象。
   */
  private createGradientExportHost(): PptxDomGradientExportHost {
    return {
      options: this.options,
      buildPptObjectMeta: (...args) => this.buildPptObjectMeta(...args),
      addReportItem: (...args) => this.addReportItem(...args),
      addSkippedItem: (...args) => this.addSkippedItem(...args),
      createGradientObjectName: element => this.createGradientObjectName(element),
    }
  }

  /**
   * 通过媒体 helper 添加局部截图块。
   * @param element 目标元素
   * @param sourceType 源类型
   * @param reason 降级原因
   * @param context 当前组合上下文
   */
  private async addScreenshotBlock(
    element: Element,
    sourceType: PptxReportSourceType,
    reason: string,
    context: VisitContext,
  ): Promise<void> {
    await this.media.addScreenshotBlock(this.createMediaExportHost(), element, sourceType, reason, context)
  }

  /**
   * 构造 PPT 对象元信息，方便在选择窗格和报告中追踪 HTML 组合。
   * @param context 当前组合上下文
   * @param role PPT 对象角色
   * @param label 对象摘要
   * @param includeAltText 是否写入图片 altText
   */
  private buildPptObjectMeta(
    context: VisitContext,
    role: string,
    label: string,
    includeAltText = false,
  ): Record<string, unknown> {
    if (!context.groupId) {
      return includeAltText ? { altText: label.slice(0, 240) } : {}
    }

    const objectName = this.normalizeObjectName(`${context.groupId}:${role}:${label}`)
    return {
      objectName,
      ...(includeAltText ? { altText: `${context.groupLabel || context.groupId} · ${label}`.slice(0, 240) } : {}),
    }
  }

  /**
   * 判断元素是否应作为一组 HTML 容器对象展开。
   * @param element 当前元素
   * @param hasShape 当前元素是否会生成 shape
   * @param hasWholeText 当前元素是否会生成整体 text
   */
  private shouldCreateCompositionGroup(element: HTMLElement, hasShape: boolean, hasWholeText: boolean): boolean {
    const tagName = element.tagName.toLowerCase()
    const hasChildren = element.children.length > 0
    if (hasShape && (hasWholeText || hasChildren)) {
      return true
    }
    if (this.isLayoutContainerTag(tagName) && hasChildren && this.layout.hasVisibleChildElement(element)) {
      return true
    }
    return false
  }

  /**
   * 创建子级组合上下文。
   * @param element 触发组合的 HTML 容器
   * @param parent 父级组合上下文
   */
  private createGroupContext(element: HTMLElement, parent: VisitContext): VisitContext {
    const groupId = this.createGroupId(element)
    return {
      ...parent,
      groupId,
      parentGroupId: parent.groupId,
      groupDepth: parent.groupDepth + 1,
      groupLabel: this.layout.buildElementLabel(element),
    }
  }

  /**
   * 创建用于后处理定位的渐变形状对象名。
   * @param element 渐变元素
   */
  private createGradientObjectName(element: HTMLElement): string {
    this.gradientSequence += 1
    const label = this.layout.buildElementLabel(element)
    return this.normalizeObjectName(`pptx-gradient-p${this.options.pageIndex}-${this.gradientSequence}-${label}`)
  }

  /**
   * 计算传给子节点的文本对齐继承上下文。
   * @param element 当前元素
   * @param parent 父级上下文
   */
  private createTextInheritanceContext(element: HTMLElement, parent: VisitContext): VisitContext {
    const style = window.getComputedStyle(element)
    const ownHorizontalAlign = this.layout.resolveOwnInheritableTextHorizontalAlign(element, style)
    const ownVerticalAlign = this.layout.resolveOwnTextVerticalAlign(element, style)

    return {
      ...parent,
      inheritedTextAlign: ownHorizontalAlign !== 'left' || this.layout.hasExplicitTextHorizontalAlign(element)
        ? ownHorizontalAlign
        : parent.inheritedTextAlign,
      inheritedVerticalAlign: ownVerticalAlign !== 'top' || this.layout.hasExplicitVerticalAlign(element)
        ? ownVerticalAlign
        : parent.inheritedVerticalAlign,
    }
  }

  /**
   * 创建稳定可读的组合 ID。
   * @param element HTML 容器
   */
  private createGroupId(element: HTMLElement): string {
    this.groupSequence += 1
    const tagName = element.tagName.toLowerCase()
    const id = element.id ? `-${element.id}` : ''
    const className = String(element.getAttribute('class') || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .join('-')
    return this.normalizeObjectName(`p${this.options.pageIndex}-g${this.groupSequence}-${tagName}${id}${className ? `-${className}` : ''}`)
  }

  /**
   * 判断标签是否常用于 HTML 布局组合。
   * @param tagName 小写标签名
   */
  private isLayoutContainerTag(tagName: string): boolean {
    return [
      'a',
      'article',
      'aside',
      'button',
      'div',
      'footer',
      'header',
      'li',
      'main',
      'nav',
      'section',
      'span',
    ].includes(tagName)
  }

  /**
   * 清理 PowerPoint 对象名，避免选择窗格名称过长或含控制字符。
   * @param value 原始对象名
   */
  private normalizeObjectName(value: string): string {
    const withoutControlCharacters = Array.from(value)
      .filter(char => char.charCodeAt(0) >= 32)
      .join('')
    return withoutControlCharacters
      .replace(/[^\w\u4e00-\u9fa5#.-]+/g, '-')
      .replace(/-+/g, '-')
      .slice(0, 120)
  }

  /**
   * 写入报告项。
   * @param sourceType 源类型
   * @param result 导出结果
   * @param editable 是否可编辑
   * @param label 对象摘要
   * @param reason 原因
   */
  private addReportItem(
    sourceType: PptxReportSourceType,
    result: PptxReportItemResult,
    editable: boolean,
    label: string,
    reason?: string,
    context?: VisitContext,
  ): PptxExportReportItem {
    const item: PptxExportReportItem = {
      pageIndex: this.options.pageIndex,
      pageTitle: this.options.pageTitle,
      pageRoute: this.options.pageRoute,
      sourceType,
      result,
      editable,
      label,
      reason,
      groupId: context?.groupId,
      parentGroupId: context?.parentGroupId,
      groupDepth: context?.groupId ? context.groupDepth : undefined,
      groupLabel: context?.groupLabel,
    }
    this.reportPage.items.push(item)
    return item
  }

  /**
   * 添加跳过报告项。
   * @param sourceType 源类型
   * @param label 对象摘要
   * @param reason 跳过原因
   */
  private addSkippedItem(sourceType: PptxReportSourceType, label: string, reason: string, context?: VisitContext): void {
    this.addReportItem(sourceType, 'skipped', false, label, reason, context)
  }
}
