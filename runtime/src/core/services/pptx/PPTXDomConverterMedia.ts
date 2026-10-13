/**
 * 文件用途：封装 PPTX DOM 转换里的媒体、背景图、截图与 SVG/canvas 导出逻辑。
 */

import type {
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type { PPTXSvgSerializer } from '@/core/services/pptx/PPTXSvgSerializer'
import type {
  ElementBox,
  ImageSizingOptions,
  PptxPageConvertOptions,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import {
  isMediaViewerElement,
  parseRuntimeKitChartPayload,
  resolveRuntimeKitMediaSourceType,
  type PptxChartDataPayload,
} from '@/core/services/pptx/PPTXRuntimeKitExportDom'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXImageDataResolver } from '@/core/services/pptx/PPTXImageDataResolver'
import { PPTXDomConverterTransform } from '@/core/services/pptx/PPTXDomConverterTransform'
import { buildIntrinsicProxyBox, resolveIntrinsicImageSize } from './assets/image-intrinsic-size'
import { buildConnectorSvgExportPayload, type ResolvedSvgExportPayload } from './svg/ConnectorTightBounds'

const PPT_UNSAFE_SVG_REASON = 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图'
const PPT_UNSAFE_SVG_SOURCE_REASON = 'SVG 源文件含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图'

export interface PptxDomMediaExportHost {
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
  addSkippedItem: (
    sourceType: PptxReportSourceType,
    label: string,
    reason: string,
    context?: VisitContext,
  ) => void
}

interface ResolvedImageSizingOptions {
  w?: number
  h?: number
  sizing?: ImageSizingOptions
}

/**
 * PPTX 媒体导出 helper。
 */
export class PPTXDomConverterMedia {
  private readonly imageDataResolver = new PPTXImageDataResolver()
  private readonly transform: PPTXDomConverterTransform

  constructor(
    private readonly layout: PPTXDomConverterLayout,
    private readonly svgSerializer: PPTXSvgSerializer,
  ) {
    this.transform = new PPTXDomConverterTransform(layout)
  }

  /**
   * 判断元素是否属于媒体或复杂渲染组件。
   * 说明：Runtime Kit viewer 以显式导出契约识别，历史样式类名保留为兜底。
   * @param element 候选元素
   */
  isMediaElement(element: Element): boolean {
    const tagName = element.tagName.toLowerCase()
    return isMediaViewerElement(element) ||
      tagName === 'img' ||
      tagName === 'svg' ||
      tagName === 'canvas' ||
      tagName === 'video'
  }

  /**
   * 添加媒体、SVG、canvas、视频封面或局部截图。
   * @param host 导出宿主能力
   * @param element 媒体元素
   * @param context 当前组合上下文
   */
  async addMediaElement(host: PptxDomMediaExportHost, element: Element, context: VisitContext): Promise<void> {
    const sourceType = this.resolveMediaSourceType(element)
    const label = this.layout.buildElementLabel(element)

    if (sourceType === 'formula') {
      await this.addFormulaSvgBlocks(host, element, label, context)
      return
    }

    if (this.isSvgBasedSource(sourceType, element)) {
      const svg = this.findRenderableSvg(element)
      if (svg) {
        if (await this.addUnsupportedSvgScreenshot(host, element, svg, sourceType, context, PPT_UNSAFE_SVG_REASON)) {
          return
        }
        await this.addSvgBlock(host, svg, this.resolveSvgPlacementElement(sourceType, element, svg), sourceType, label, context)
        return
      }
      await this.addScreenshotBlock(host, element, sourceType, '未找到可序列化 SVG，降级为局部截图', context)
      return
    }

    if (sourceType === 'chart') {
      const chartPayload = parseRuntimeKitChartPayload(element)
      if (chartPayload && typeof host.options.slide.addChart === 'function') {
        if (this.addNativeChartBlock(host, element, chartPayload, label, context)) {
          return
        }
      }

      const svg = this.findRenderableSvg(element)
      if (svg) {
        if (await this.addUnsupportedSvgScreenshot(host, element, svg, sourceType, context, PPT_UNSAFE_SVG_REASON)) {
          return
        }
        await this.addSvgBlock(host, svg, this.resolveSvgPlacementElement(sourceType, element, svg), sourceType, label, context)
        return
      }

      const canvas = element.querySelector?.('canvas') ?? (element instanceof HTMLCanvasElement ? element : null)
      if (canvas instanceof HTMLCanvasElement && await this.addCanvasBlock(host, canvas, element, sourceType, label, context)) {
        return
      }

      await this.addScreenshotBlock(host, element, sourceType, 'ECharts 未提供 SVG 或 canvas，降级为局部截图', context)
      return
    }

    if (sourceType === 'canvas' && element instanceof HTMLCanvasElement) {
      if (!await this.addCanvasBlock(host, element, element, sourceType, label, context)) {
        host.addSkippedItem(sourceType, label, 'canvas 像素为空或无法读取', context)
      }
      return
    }

    if (sourceType === 'video') {
      await this.addVideoBlock(host, element, label, context)
      return
    }

    const image = element instanceof HTMLImageElement ? element : element.querySelector?.('img')
    if (image instanceof HTMLImageElement && await this.addImagePathBlock(host, image.currentSrc || image.src, element, sourceType, label, context)) {
      return
    }

    await this.addScreenshotBlock(host, element, sourceType, '未找到可直接导出的图片资源，降级为局部截图', context)
  }

  /**
   * 将简单 CSS background-image: url(...) 导出为 PPT 图片块。
   * @param host 导出宿主能力
   * @param element 背景图元素
   * @param context 当前组合上下文
   */
  async addBackgroundImageElement(
    host: PptxDomMediaExportHost,
    element: HTMLElement,
    context: VisitContext,
  ): Promise<boolean> {
    const style = window.getComputedStyle(element)
    const backgroundUrl = this.extractSingleBackgroundImageUrl(style.backgroundImage)
    if (!backgroundUrl) {
      return false
    }

    const label = this.layout.buildElementLabel(element)
    if (backgroundUrl.startsWith('data:image/')) {
      await this.addImageDataBlock(host, backgroundUrl, element, 'image', label, 'CSS 背景图导出为图片块', context, backgroundUrl)
      return true
    }

    return this.addImagePathBlock(host, backgroundUrl, element, 'image', label, context, 'CSS 背景图导出为图片块')
  }

  /**
   * 添加视频封面图；没有封面时尝试当前帧，最后降级为截图。
   */
  private async addVideoBlock(
    host: PptxDomMediaExportHost,
    element: Element,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const video = element instanceof HTMLVideoElement ? element : element.querySelector?.('video')
    if (!(video instanceof HTMLVideoElement)) {
      await this.addScreenshotBlock(host, element, 'video', '未找到 video 元素，降级为局部截图', context)
      return
    }

    const poster = video.getAttribute('poster') || video.poster
    if (poster && await this.addImagePathBlock(host, poster, element, 'video', label, context, '视频封面图导出为图片块')) {
      return
    }

    try {
      const canvas = document.createElement('canvas')
      const rect = this.layout.measureElementPixels(video)
      canvas.width = Math.max(1, Math.round(rect.width))
      canvas.height = Math.max(1, Math.round(rect.height))
      const canvasContext = canvas.getContext('2d')
      if (!canvasContext) {
        throw new Error('无法创建视频帧 canvas')
      }
      canvasContext.drawImage(video, 0, 0, canvas.width, canvas.height)
      await this.addImageDataBlock(host, canvas.toDataURL('image/png'), element, 'video', label, '视频当前帧导出为图片块', context)
    } catch {
      await this.addScreenshotBlock(host, element, 'video', '视频无封面且当前帧不可读取，降级为局部截图', context)
    }
  }

  /**
   * 判断当前媒体类型是否应优先导出为 SVG。
   */
  private isSvgBasedSource(sourceType: PptxReportSourceType, element: Element): boolean {
    return sourceType === 'svg' ||
      sourceType === 'mermaid' ||
      sourceType === 'drawio' ||
      sourceType === 'formula' ||
      element.tagName.toLowerCase() === 'svg'
  }

  /**
   * 将 SVG 添加为 PPT 图片块。
   */
  private addSvgBlock(
    host: PptxDomMediaExportHost,
    svg: SVGSVGElement,
    boxElement: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const exportPayload = this.resolveSvgExportPayload(svg, boxElement)
    return this.addImageDataBlock(
      host,
      exportPayload.data,
      exportPayload.boxElement,
      sourceType,
      label,
      'SVG 作为可移动缩放图片块',
      context,
      undefined,
      exportPayload.boxOverride,
    )
  }

  /**
   * 逐个导出 MathJax 生成的公式 SVG，避免多段公式只保留首段。
   */
  private async addFormulaSvgBlocks(
    host: PptxDomMediaExportHost,
    element: Element,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const svgs = this.findRenderableSvgs(element)
    if (svgs.length === 0) {
      await this.addScreenshotBlock(host, element, 'formula', '未找到可序列化 SVG，降级为局部截图', context)
      return
    }

    for (const svg of svgs) {
      if (await this.addUnsupportedSvgScreenshot(host, element, svg, 'formula', context, PPT_UNSAFE_SVG_REASON)) {
        continue
      }
      await this.addSvgBlock(host, svg, svg, 'formula', label, context)
    }
  }

  /**
   * 将 canvas 添加为 PNG 图片块。
   */
  private addCanvasBlock(
    host: PptxDomMediaExportHost,
    canvas: HTMLCanvasElement,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
  ): Promise<boolean> {
    if (canvas.width <= 0 || canvas.height <= 0) {
      return Promise.resolve(false)
    }

    try {
      return this.addImageDataBlock(host, canvas.toDataURL('image/png'), element, sourceType, label, 'canvas 导出为 PNG 图片块', context)
        .then(() => true)
    } catch {
      return Promise.resolve(false)
    }
  }

  /**
   * 按 URL 添加图片块。
   */
  private async addImagePathBlock(
    host: PptxDomMediaExportHost,
    path: string,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
    reason = '图片作为可移动缩放图片块',
  ): Promise<boolean> {
    if (!path) {
      return false
    }

    const svgSource = await this.svgSerializer.resolveSvgSource(path)
    if (svgSource) {
      if (this.svgSerializer.shouldRasterizeSourceForPpt(svgSource)) {
        const screenshotTarget = this.resolveScreenshotTarget(element)
        if (screenshotTarget) {
          await this.addScreenshotBlock(host, screenshotTarget, sourceType, PPT_UNSAFE_SVG_SOURCE_REASON, context)
          return true
        }
      }
      await this.addImageDataBlock(
        host,
        this.svgSerializer.svgSourceToDataUrl(svgSource),
        element,
        sourceType === 'image' ? 'svg' : sourceType,
        label,
        'SVG 源文件原样嵌入为可移动缩放图片块',
        context,
      )
      return true
    }

    const imageData = host.options.resourceSession
      ? await host.options.resourceSession.resolveImage(path)
      : await this.imageDataResolver.resolve(path)
    if (imageData) {
      await this.addImageDataBlock(host, imageData, element, sourceType, label, reason, context, imageData)
      return true
    }

    if (this.imageDataResolver.shouldAvoidDeferredPath(path)) {
      await this.addScreenshotBlock(host, element, sourceType, `图片 URL 无法读取，降级为局部截图：${path}`, context)
      return true
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      host.addSkippedItem(sourceType, label, '图片元素尺寸无效', context)
      return true
    }

    const imageSizing = await this.buildImageSizing(element, box, path)
    host.options.slide.addImage({
      path,
      ...this.buildTransformedImageOptions(box, imageSizing, context),
      ...host.buildPptObjectMeta(context, 'image', label, true),
    })
    host.addReportItem(sourceType, 'image', false, label, reason, context)
    return true
  }

  /**
   * 按 data URL 添加图片块。
   */
  private addImageDataBlock(
    host: PptxDomMediaExportHost,
    data: string,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    reason: string,
    context: VisitContext,
    source?: string,
    boxOverride?: ElementBox,
  ): Promise<void> {
    const box = boxOverride ?? this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      host.addSkippedItem(sourceType, label, '图片块尺寸无效', context)
      return Promise.resolve()
    }

    return this.buildImageSizing(element, box, source || data).then(imageSizing => {
      host.options.slide.addImage({
        data,
        ...this.buildTransformedImageOptions(box, imageSizing, context),
        ...host.buildPptObjectMeta(context, data.startsWith('data:image/svg') ? 'svg' : 'image', label, true),
      })
      host.addReportItem(sourceType, data.startsWith('data:image/svg') ? 'svg' : 'image', false, label, reason, context)
    })
  }

  /**
   * 添加局部截图块。
   */
  async addScreenshotBlock(
    host: PptxDomMediaExportHost,
    element: Element,
    sourceType: PptxReportSourceType,
    reason: string,
    context: VisitContext,
  ): Promise<void> {
    if (!(element instanceof HTMLElement)) {
      host.addSkippedItem(sourceType, this.layout.buildElementLabel(element), '非 HTML 元素无法局部截图', context)
      return
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    const label = this.layout.buildElementLabel(element)
    if (!box) {
      host.addSkippedItem(sourceType, label, '截图元素尺寸无效', context)
      return
    }

    try {
      const data = await host.options.captureElementAsPng(element)
      host.options.resourceSession?.recordScreenshot()
      host.options.slide.addImage({
        data,
        ...this.transform.applyToBox(box, context),
        ...host.buildPptObjectMeta(context, 'screenshot', label, true),
      })
      host.addReportItem(sourceType, 'screenshot', false, label, reason, context)
    } catch (error) {
      host.addSkippedItem(
        sourceType,
        label,
        `局部截图失败：${error instanceof Error ? error.message : '未知错误'}`,
        context,
      )
    }
  }

  /**
   * 先应用 object-fit 尺寸，再把图片盒模型映射到旋转后的中心位置。
   */
  private buildTransformedImageOptions(
    box: ElementBox,
    sizing: ResolvedImageSizingOptions,
    context: VisitContext,
  ): Record<string, unknown> {
    const sizedBox = {
      ...box,
      w: sizing.w ?? box.w,
      h: sizing.h ?? box.h,
    }
    return {
      ...this.transform.applyToBox(sizedBox, context),
      ...(sizing.sizing ? { sizing: sizing.sizing } : {}),
    }
  }

  /**
   * 根据图片元素样式构造 PPTX 图片缩放策略。
   */
  private async buildImageSizing(element: Element, box: ElementBox, source?: string): Promise<ResolvedImageSizingOptions> {
    const sizingMode = this.resolveImageSizingMode(element)
    if (!sizingMode) {
      return {}
    }

    const result: ResolvedImageSizingOptions = {
      sizing: {
        type: sizingMode,
        w: box.w,
        h: box.h,
      },
    }

    const intrinsicSize = await resolveIntrinsicImageSize(element, source)
    if (!intrinsicSize) {
      return result
    }

    const proxyBox = buildIntrinsicProxyBox(box, intrinsicSize)
    return {
      w: proxyBox.w,
      h: proxyBox.h,
      sizing: result.sizing,
    }
  }

  /**
   * 读取当前元素对应的 cover/contain 模式。
   */
  private resolveImageSizingMode(element: Element): ImageSizingOptions['type'] | null {
    const image = element instanceof HTMLImageElement ? element : element.querySelector?.('img')
    if (image instanceof HTMLElement) {
      const style = window.getComputedStyle(image)
      if (style.objectFit === 'contain' || style.objectFit === 'cover') {
        return style.objectFit
      }
    }

    if (element instanceof HTMLElement) {
      const style = window.getComputedStyle(element)
      if (style.backgroundSize === 'contain' || style.backgroundSize === 'cover') {
        return style.backgroundSize
      }
    }

    return null
  }

  /**
   * 从 CSS background-image 中提取单个 url。
   */
  private extractSingleBackgroundImageUrl(value: string): string {
    const normalized = String(value || '').trim()
    if (!normalized || normalized === 'none' || normalized.includes('gradient(')) {
      return ''
    }

    const match = /^url\(\s*(?:"([^"]+)"|'([^']+)'|([^'")]+))\s*\)$/i.exec(normalized)
    if (!match) {
      return ''
    }

    return (match[1] || match[2] || match[3] || '').trim()
  }

  /**
   * 查找元素内可序列化的 SVG。
   */
  private findRenderableSvg(element: Element): SVGSVGElement | null {
    if (element instanceof SVGSVGElement) {
      return element
    }
    return element.querySelector?.('svg') as SVGSVGElement | null
  }

  /**
   * 查找元素内全部可序列化 SVG。
   */
  private findRenderableSvgs(element: Element): SVGSVGElement[] {
    if (element instanceof SVGSVGElement) {
      return [element]
    }
    return Array.from(element.querySelectorAll?.('svg') ?? [])
      .filter((svg): svg is SVGSVGElement => svg instanceof SVGSVGElement)
  }

  /**
   * 当 SVG 含 PowerPoint 不兼容结构时，优先降级为局部截图，避免图形保留但文字丢失。
   */
  private async addUnsupportedSvgScreenshot(
    host: PptxDomMediaExportHost,
    element: Element,
    svg: SVGSVGElement,
    sourceType: PptxReportSourceType,
    context: VisitContext,
    reason: string,
  ): Promise<boolean> {
    if (!this.svgSerializer.shouldRasterizeForPpt(svg)) {
      return false
    }

    const screenshotTarget = this.resolveScreenshotTarget(element)
    if (!screenshotTarget) {
      return false
    }

    await this.addScreenshotBlock(host, screenshotTarget, sourceType, reason, context)
    return true
  }

  /**
   * 为局部截图选择稳定的 HTML 宿主。
   */
  private resolveScreenshotTarget(element: Element): HTMLElement | null {
    if (element instanceof HTMLElement) {
      return element
    }
    return element.parentElement instanceof HTMLElement ? element.parentElement : null
  }

  /**
   * 为 SVG 类资源选择最终的 PPT 定位参考元素。
   */
  private resolveSvgPlacementElement(
    sourceType: PptxReportSourceType,
    element: Element,
    svg: SVGSVGElement,
  ): Element {
    if (sourceType === 'formula') {
      return svg
    }
    return element
  }

  /**
   * 解析 SVG 的导出载荷；Connector 等特殊组件优先使用紧边界视口。
   */
  private resolveSvgExportPayload(svg: SVGSVGElement, boxElement: Element): ResolvedSvgExportPayload {
    const connectorPayload = buildConnectorSvgExportPayload(svg, this.layout, this.svgSerializer)
    if (connectorPayload) {
      return connectorPayload
    }

    return {
      data: this.svgSerializer.svgToDataUrl(svg),
      boxElement,
    }
  }

  /**
   * 解析媒体源类型。
   * 说明：判定顺序收口在 PPTXRuntimeKitExportDom，显式契约优先、类名与标签名兜底。
   * @param element 候选元素
   * @returns 报告源类型；无法归类时为 unknown
   */
  private resolveMediaSourceType(element: Element): PptxReportSourceType {
    return resolveRuntimeKitMediaSourceType(element) ?? 'unknown'
  }

  /**
   * 将具备图表数据契约的元素导出为 PPT 原生可编辑图表。
   */
  private addNativeChartBlock(
    host: PptxDomMediaExportHost,
    element: Element,
    payload: PptxChartDataPayload,
    label: string,
    context: VisitContext,
  ): boolean {
    const box = this.layout.getPptxBox(element as HTMLElement, Boolean(context.rotationSteps?.length))
    if (!box) {
      return false
    }

    const chartData = payload.series.map(s => ({
      name: s.name,
      labels: payload.categories,
      values: s.values,
    }))

    const objectMeta = host.buildPptObjectMeta(context, 'chart', label)
    const objectName = typeof objectMeta.objectName === 'string' ? objectMeta.objectName : undefined
    const extra = objectName ? { primitiveIds: [objectName] } : undefined

    const chartOptions: Record<string, unknown> = {
      ...this.transform.applyToBox(box, context),
      showLegend: payload.options?.showLegend ?? true,
      showTitle: payload.options?.showTitle ?? Boolean(payload.title),
      title: payload.title,
      ...(payload.options?.holeSize ? { holeSize: payload.options.holeSize } : {}),
      ...objectMeta,
    }

    host.options.slide.addChart!(payload.chartType, chartData, chartOptions)
    host.addReportItem(
      'chart',
      'editable-shape',
      true,
      label,
      `图表转为 PPT 原生可编辑图表（${payload.chartType}）`,
      context,
      extra,
    )
    return true
  }
}

